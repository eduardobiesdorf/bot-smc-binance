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
                 stop_ini=g['stop'], movs=0,
                 degraus=[[g['vela_ms'], g['stop']]],
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


def _vigente(r, ms):
    """O stop que valia naquele instante. Sem isso o stop movido hoje
    seria aplicado a velas de ontem, e a operacao 'fecharia' no passado."""
    deg = r.get('degraus') or [[r['vela_ms'], r.get('stop_ini', r['stop'])]]
    val = deg[0][1]
    for q, s in deg:
        if q <= ms:
            val = s
    return val


def _revisar_gatilho(r, h):
    compra = r['lado'] == 'compra'
    ent, alvo = r['entrada'], r['alvo']
    # 1R e sempre medido pelo stop ORIGINAL, senao o trailing distorceria
    # o resultado: stop mais perto faria qualquer perda parecer menor.
    risco = abs(ent - r.get('stop_ini', r['stop']))
    idx = next((i for i, c in enumerate(h) if c[0] == r['vela_ms']), None)
    if idx is None:
        return None                      # a vela ja saiu da janela baixada
    for k in range(idx + 1, len(h)):
        hi, lo = h[k][2], h[k][3]
        stop = _vigente(r, h[k][0])
        bateu_stop = (lo <= stop) if compra else (hi >= stop)
        bateu_alvo = (hi >= alvo) if compra else (lo <= alvo)
        if bateu_stop and bateu_alvo:
            bateu_alvo = False           # na duvida dentro da vela, conta stop
        if bateu_stop or bateu_alvo:
            r['status'] = 'alvo' if bateu_alvo else 'stop'
            r['fim_ms'] = h[k][0]
            r['horas'] = k - idx
            if bateu_alvo:
                r['resultado_r'] = r['rr']
            else:
                saida = stop
                r['resultado_r'] = ((saida - ent) if compra else (ent - saida)) / risco
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


# ------------------------------------------------- stop movel por estrutura
# A estrutura que o Eduardo marcou: A-B-C-D formam uma perna a favor, E varre
# o extremo de C e "falha", F rompe o extremo de D e confirma. Quando isso
# acontece a favor da operacao, o stop sobe para o extremo de E.
#
# Medido em 22 meses no nucleo 20, com pivo de 1 vela (k=1) nos 15 minutos:
#   stop fixo                      R/op +0,625  rebaixamento 9,5R
#   movendo sempre                 R/op +0,561  rebaixamento 6,0R
#   movendo so se travar >= +0,3R  R/op +0,690  rebaixamento 6,5R  <-- este
# A ultima e melhor nas duas pontas. Mover o stop enquanto ele ainda trava
# prejuizo economiza pouco na perda e tira de muita vencedora -- foi o que
# aconteceria no AAVE de 06/11, cortado a -0,28R antes de ir a +2,2R.
#
# Checar de hora em hora da exatamente o mesmo numero que checar a cada 15
# minutos, entao nao precisa rodar mais vezes.
K_PIVO = 1          # quantas velas de cada lado definem um pivo
FOLGA_ATR = 0.25    # o stop fica essa distancia alem do extremo de E
MIN_TRAVA = 0.30    # so move se o stop novo travar pelo menos isso em R
#                   # Medido no nucleo 20, 22 meses, k=1 nos 15m:
#                   #   stop fixo      R/op +0,625  rebaixamento 9,5R
#                   #   move sempre    R/op +0,561  rebaixamento 6,0R
#                   #   trava >=0,1R   R/op +0,610  rebaixamento 6,5R
#                   #   trava >=0,3R   R/op +0,690  rebaixamento 6,5R
#                   # 0,3R e o unico que ganha nas DUAS pontas. Abaixo
#                   # disso o stop aperta cedo demais e corta vencedora.
ESP_VARR = 20       # velas para E acontecer depois de D
ESP_ROMPE = 12      # velas para F acontecer depois de E


def _atr(h, p=14):
    if len(h) < p + 1:
        return [None] * len(h)
    tr = [h[0][2] - h[0][3]]
    for i in range(1, len(h)):
        tr.append(max(h[i][2] - h[i][3], abs(h[i][2] - h[i-1][4]),
                      abs(h[i][3] - h[i-1][4])))
    out = [None] * len(h)
    s = sum(tr[:p]) / p
    out[p-1] = s
    for i in range(p, len(h)):
        s = (s * (p - 1) + tr[i]) / p
        out[i] = s
    return out


def estruturas(h, k=K_PIVO, esp_varr=ESP_VARR, esp_rompe=ESP_ROMPE):
    """{indice de F: {alta, extremo de E}}. Nunca olha para a frente."""
    piv, pend, out = [], [], {}
    for i in range(k, len(h)):
        c = i - k
        if c >= k:
            eT = (all(h[c][2] > h[c-j][2] for j in range(1, k+1)) and
                  all(h[c][2] >= h[c+j][2] for j in range(1, k+1)))
            eF = (all(h[c][3] < h[c-j][3] for j in range(1, k+1)) and
                  all(h[c][3] <= h[c+j][3] for j in range(1, k+1)))
            for t, ok in (('T', eT), ('F', eF)):
                if not ok:
                    continue
                if piv and piv[-1][1] == t:
                    j, _ = piv[-1]
                    if (t == 'T' and h[c][2] > h[j][2]) or \
                       (t == 'F' and h[c][3] < h[j][3]):
                        piv[-1] = (c, t)
                else:
                    piv.append((c, t))
                if len(piv) >= 4:
                    (a, ta), (b, tb), (cc, tc), (d, td) = piv[-4:]
                    tip = ta + tb + tc + td
                    if tip == 'FTFT' and h[cc][3] > h[a][3] and h[d][2] > h[b][2]:
                        pend.append(dict(alta=True, C=cc, D=d, nasceu=i,
                                         E=None, ext=None))
                    elif tip == 'TFTF' and h[cc][2] < h[a][2] and h[d][3] < h[b][3]:
                        pend.append(dict(alta=False, C=cc, D=d, nasceu=i,
                                         E=None, ext=None))
        vivos = []
        for p in pend:
            if p['E'] is None:
                if i - p['nasceu'] > esp_varr:
                    continue
                if (h[i][3] < h[p['C']][3]) if p['alta'] else (h[i][2] > h[p['C']][2]):
                    p['E'] = i
                    p['ext'] = h[i][3] if p['alta'] else h[i][2]
                vivos.append(p)
                continue
            p['ext'] = min(p['ext'], h[i][3]) if p['alta'] else max(p['ext'], h[i][2])
            if i - p['E'] > esp_rompe:
                continue
            rompeu = (h[i][4] > h[p['D']][2]) if p['alta'] else (h[i][4] < h[p['D']][3])
            if rompeu and i > p['E']:
                out[i] = dict(alta=p['alta'], extremo=p['ext'], E=p['E'])
                continue
            vivos.append(p)
        pend = vivos
    return out


def mover_stops(d, series15):
    """Sobe o stop dos gatilhos abertos. Devolve as mensagens a mandar.

    series15: {par: velas de 15 minutos}. O bot busca so dos pares com
    operacao aberta, uma vez por rodada de hora em hora.
    """
    msgs = []
    for ch, r in d.items():
        if r.get('tipo') != 'gatilho' or r.get('status') != 'aberto':
            continue
        q = series15.get(r['sim'])
        if not q or len(q) < 60:
            continue
        compra = r['lado'] == 'compra'
        risco_ini = abs(r['entrada'] - r.get('stop_ini', r['stop']))
        a = _atr(q, 14)
        ev = estruturas(q)
        # so o que fechou DEPOIS do gatilho
        novos = [(i, e) for i, e in ev.items() if q[i][0] > r['vela_ms']]
        if not novos:
            continue
        antigo = r['stop']
        melhor = antigo
        quando_e = quando_f = None
        for i, e in sorted(novos):
            if e['alta'] != compra or a[i] is None:
                continue
            cand = (e['extremo'] - a[i] * FOLGA_ATR if compra
                    else e['extremo'] + a[i] * FOLGA_ATR)
            if not ((cand > melhor) if compra else (cand < melhor)):
                continue
            emR = ((cand - r['entrada']) if compra
                   else (r['entrada'] - cand)) / max(risco_ini, 1e-12)
            if emR < MIN_TRAVA:
                continue
            melhor = cand
            quando_e = q[e['E']][0]
            quando_f = q[i][0] + 900000          # vale do fim da vela F
        if melhor == antigo:
            continue
        r['stop'] = melhor
        r.setdefault('degraus', [[r['vela_ms'], r.get('stop_ini', antigo)]])
        r['degraus'].append([quando_f, melhor])
        r['movs'] = r.get('movs', 0) + 1
        emR = ((melhor - r['entrada']) if compra
               else (r['entrada'] - melhor)) / risco_ini
        seta = "🟢" if compra else "🔴"
        msgs.append(
            f"🔒 <b>{r['sim'].replace('USDT', '/USDT')}</b> — "
            f"stop movido   {seta} {r['lado']}\n"
            f"gatilho de {_quando(r['vela_ms'])}\n\n"
            f"de   <code>{antigo:.8g}</code>\n"
            f"para <code>{melhor:.8g}</code>   "
            f"<b>{emR:+.2f}R</b> travado\n"
            + (f"<i>estrutura falhou em {_quando(quando_e)} e o preço "
               f"retomou</i>\n" if quando_e else "")
            + f"\n<i>move a ordem de stop na corretora para "
              f"{melhor:.8g}</i>")
    return msgs


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
