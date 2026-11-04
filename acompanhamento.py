# -*- coding: utf-8 -*-
"""Fecha o ciclo de cada aviso: o bot deixa de so avisar na entrada.

Hoje o radar fala uma vez e some. Aqui cada aviso vira um registro aberto,
e toda rodada os abertos sao reavaliados ate darem em alguma coisa:

  cenario  -> virou gatilho | morreu (com o motivo exato)
  gatilho  -> bateu o alvo  | bateu o stop | expirou sem resolver

O registro de cenario e por SETUP, nao por vela: a chave e a vela que
fecha o impulso. Assim o mesmo cenario nao abre cinco registros so porque
o bot reavisou cinco horas seguidas.

Este modulo nao importa nada do bot, para nao criar import circular: quem
chama passa as funcoes (seguir, achar_impulsos, atr, media_volume) e a
serie de velas ja baixada.
"""
import csv
import json
import os
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
ARQUIVO = "acompanhamento.json"
CSV_VIVO = "historico_ao_vivo.csv"
MAX_BARRAS = 120          # mesmo horizonte do backtest: ~5 dias


# ------------------------------------------------------------- estado
def ler():
    try:
        with open(ARQUIVO, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def gravar(d):
    try:
        # guarda os 400 mais recentes para o arquivo nao crescer sem fim
        itens = sorted(d.items(), key=lambda kv: kv[1].get('vela_ms', 0))
        with open(ARQUIVO, "w", encoding="utf-8") as f:
            json.dump(dict(itens[-400:]), f, ensure_ascii=False, indent=1)
    except Exception as e:
        print(f"nao gravei o acompanhamento: {e}", flush=True)


def _quando(ms):
    return f"{datetime.fromtimestamp(ms / 1000, BRT):%d/%m %H:%M}"


# ------------------------------------------------------------ registro
def registrar_gatilho(d, sim, g):
    ch = f"gat-{sim}-{g['vela_ms']}"
    if ch in d:
        return
    d[ch] = dict(tipo='gatilho', sim=sim, lado=g['lado'], status='aberto',
                 vela_ms=g['vela_ms'], entrada=g['entrada'], stop=g['stop'],
                 alvo=g['alvo'], rr=g['rr'], risco_pct=g['risco_pct'],
                 vol_varr=g.get('vol_varr', 0), liq_r=g.get('liq_r', 0),
                 rsi_varr=g.get('rsi_varr'), rsi_gat=g.get('rsi_gat'),
                 rsi_varr_norm=g.get('rsi_varr_norm'),
                 nucleo=bool(g.get('nucleo', True)))


def registrar_cenario(d, sim, c):
    """Chave pelo fim do impulso: um registro por setup, nao por vela."""
    ch = f"cen-{sim}-{c['imp']['fim_ms']}"
    if ch in d:
        return
    d[ch] = dict(tipo='cenario', sim=sim, lado=c['lado'], status='aberto',
                 vela_ms=c['vela_ms'], imp_fim_ms=c['imp']['fim_ms'],
                 alvo=c['alvo'], nota=c['nota'],
                 vol_varr=c.get('vol_varr', 0),
                 nucleo=bool(c.get('nucleo', True)))


# ------------------------------------------------------------- revisao
def revisar(d, series, cfg, seguir, achar_impulsos, atr, media_volume):
    """Reavalia os abertos. Devolve a lista de mensagens de desfecho."""
    msgs = []
    for ch, r in list(d.items()):
        if r.get('status') != 'aberto':
            continue
        h = series.get(r['sim'])
        if not h:
            continue
        if r['tipo'] == 'gatilho':
            m = _revisar_gatilho(r, h)
        else:
            m = _revisar_cenario(r, h, cfg, seguir, achar_impulsos,
                                 atr, media_volume)
        if m:
            msgs.append(m)
    return msgs


def _revisar_gatilho(r, h):
    compra = r['lado'] == 'compra'
    ent, stop, alvo = r['entrada'], r['stop'], r['alvo']
    risco = abs(ent - stop)
    idx = next((i for i, c in enumerate(h) if c[0] == r['vela_ms']), None)
    if idx is None:
        return None                      # a vela ja saiu da janela baixada
    for k in range(idx + 1, len(h)):
        hi, lo = h[k][2], h[k][3]
        bateu_stop = (lo <= stop) if compra else (hi >= stop)
        bateu_alvo = (hi >= alvo) if compra else (lo <= alvo)
        if bateu_stop and bateu_alvo:
            bateu_alvo = False           # na duvida dentro da vela, conta stop
        if bateu_stop or bateu_alvo:
            r['status'] = 'alvo' if bateu_alvo else 'stop'
            r['fim_ms'] = h[k][0]
            r['horas'] = k - idx
            r['resultado_r'] = r['rr'] if bateu_alvo else -1.0
            _csv(r)
            seta = "🎯" if bateu_alvo else "🛑"
            titulo = "ALVO" if bateu_alvo else "STOP"
            return (f"{seta} <b>{r['sim'].replace('USDT', '/USDT')}</b> — "
                    f"{titulo}\n"
                    f"gatilho de {_quando(r['vela_ms'])} → "
                    f"{_quando(h[k][0])} ({k - idx}h depois)\n"
                    f"entrada <code>{ent:.8g}</code> → "
                    f"<code>{(alvo if bateu_alvo else stop):.8g}</code>\n"
                    f"resultado <b>{r['resultado_r']:+.2f}R</b>")
        if k - idx >= MAX_BARRAS:
            r['status'] = 'expirou'
            r['fim_ms'] = h[k][0]
            r['horas'] = k - idx
            pl = (h[k][4] - ent) / risco * (1 if compra else -1)
            r['resultado_r'] = pl
            _csv(r)
            return (f"⌛ <b>{r['sim'].replace('USDT', '/USDT')}</b> — "
                    f"sem resolver em {MAX_BARRAS}h\n"
                    f"gatilho de {_quando(r['vela_ms'])}, não bateu stop "
                    f"nem alvo\n"
                    f"estava em <b>{pl:+.2f}R</b>. No backtest essas são "
                    f"descartadas — fecha a mão.")
    return None                          # segue aberto


def _revisar_cenario(r, h, cfg, seguir, achar_impulsos, atr, media_volume):
    a = atr(h, cfg['atr_periodo'])
    mv = media_volume(h, cfg['vol_periodo'])
    alvo_imp = None
    for imp in achar_impulsos(h, a, mv, cfg):
        if h[imp['fim']][0] == r['imp_fim_ms']:
            alvo_imp = imp
            break
    if alvo_imp is None:
        # o impulso saiu da janela de 400 velas; encerra sem veredito
        r['status'] = 'sumiu'
        return None
    tr = []
    e = seguir(h, a, alvo_imp, cfg, mv, tr)
    if e is None:
        r['status'] = 'morreu'
        r['motivo'] = tr[0] if tr else 'sem motivo registrado'
        return (f"⚪ <b>{r['sim'].replace('USDT', '/USDT')}</b> — cenário de "
                f"{r['lado']} encerrado <b>sem entrada</b>\n"
                f"<i>{r['motivo']}</i>")
    if e['fase'] == 'gatilho':
        r['status'] = 'virou_gatilho'
        return None                      # o alerta de gatilho vai sozinho
    return None                          # ainda armado


def _n(x):
    return '' if x is None else f'{x:.1f}'


def _csv(r):
    novo = not os.path.exists(CSV_VIVO)
    try:
        with open(CSV_VIVO, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if novo:
                w.writerow(['data_brt', 'par', 'faixa', 'lado', 'entrada',
                            'stop', 'alvo', 'rr', 'risco_pct', 'vol_varr',
                            'liq_r', 'rsi_varr', 'rsi_varr_norm', 'rsi_gat',
                            'desfecho', 'horas', 'resultado_r', 'fim_brt'])
            w.writerow([_quando(r['vela_ms']), r['sim'],
                        'nucleo' if r.get('nucleo') else 'extra', r['lado'],
                        f"{r['entrada']:.8g}", f"{r['stop']:.8g}",
                        f"{r['alvo']:.8g}", f"{r['rr']:.2f}",
                        f"{r['risco_pct']:.2f}", f"{r.get('vol_varr', 0):.2f}",
                        f"{r.get('liq_r', 0):.2f}",
                        _n(r.get('rsi_varr')), _n(r.get('rsi_varr_norm')),
                        _n(r.get('rsi_gat')), r['status'],
                        r.get('horas', ''), f"{r.get('resultado_r', 0):.3f}",
                        _quando(r.get('fim_ms', r['vela_ms']))])
    except Exception as e:
        print(f"nao gravei o csv ao vivo: {e}", flush=True)


# ------------------------------------------------------------- placar
def placar(d):
    """Uma linha com o que o bot acertou e errou desde que entrou no ar."""
    g = [r for r in d.values() if r['tipo'] == 'gatilho']
    fechados = [r for r in g if r['status'] in ('alvo', 'stop', 'expirou')]
    abertos = [r for r in g if r['status'] == 'aberto']
    cen = [r for r in d.values() if r['tipo'] == 'cenario']
    cen_mortos = [r for r in cen if r['status'] == 'morreu']
    if not fechados:
        return (f"<b>placar</b>  {len(g)} gatilhos "
                f"({len(abertos)} abertos)  ·  {len(cen)} cenários, "
                f"{len(cen_mortos)} encerrados sem entrada")
    ganhos = [r for r in fechados if r['resultado_r'] > 0]
    soma = sum(r['resultado_r'] for r in fechados)
    return (f"<b>placar</b>  {len(fechados)} fechados: "
            f"{len(ganhos)} gain / {len(fechados) - len(ganhos)} loss  "
            f"({len(ganhos) / len(fechados) * 100:.0f}%)  "
            f"total <b>{soma:+.2f}R</b>  ·  {len(abertos)} abertos  ·  "
            f"{len(cen_mortos)} cenários encerrados sem entrada")


def motivos(d):
    """Por que os cenarios morreram. Mostra onde o setup falha na pratica."""
    from collections import Counter
    c = Counter(r.get('motivo', '?') for r in d.values()
                if r['tipo'] == 'cenario' and r['status'] == 'morreu')
    if not c:
        return ""
    return "\n".join(f"  {n}x  {m}" for m, n in c.most_common())
