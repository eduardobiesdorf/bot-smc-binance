# -*- coding: utf-8 -*-
"""
Radar da VARREDURA DO ORDER BLOCK — tudo em H1.

A regra, no cenario de compra (o de venda e o espelho):

  1. IMPULSO de alta: 3 a 8 velas, deslocamento >= 2,5 ATR, corpo
     dominando o range, volume medio >= 1,5x a media das 20 anteriores.
  2. BOS: o impulso tem de romper o topo das 30 velas anteriores.
     Sem rompimento, a vela de baixa anterior nao e order block.
  3. ORDER BLOCK: a ultima vela de baixa antes do impulso.
     A zona vai da minima a maxima dela.
  4. VARREDURA: o preco volta e FURA a zona por baixo -- e aqui que
     morre o stop de quem comprou no order block.
  5. REVERSAO: uma vela fecha de volta acima da base da zona, com corpo
     a favor ou pavio longo.
  6. Entrada no fechamento dessa vela. Stop uns ticks abaixo da minima
     da varredura. Alvo no topo que o impulso deixou.

Medido em 2026, top 20 por volume, 199 operacoes:
  acerto 39,2% | R:R dos ganhos 1:1,96 (empate em 33,8%)
  risco mediano 1,30% | +0,171R por operacao | +34R no periodo
Nao validado fora de 2026. Serve como radar, nao como sistema automatico.

Uso:
    python bot_varredura.py --top 20
    python bot_varredura.py --teste        # imprime, nao envia
    python bot_varredura.py --ping         # so testa o Telegram
"""
import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

BRT = timezone(timedelta(hours=-3))
BASE_URL = "https://data-api.binance.vision/api/v3"
ESTADO = "varredura_enviados.json"
DIAG = "diagnostico_varredura.txt"
RESUMO = "resumo_varredura.txt"

CFG = dict(imp_min=3, imp_max=8, sigma=2.5, frac_direcao=0.7, corpo_imp=0.5,
           vol_mult=1.5, vol_periodo=20, atr_periodo=14, estrut_janela=30,
           ob_busca=6, furo_atr=0.0, furo_max=2.5, corpo_min=0.5,
           pavio_min=0.5, espera_max=60, stop_folga=0.10, rr_min=1.2,
           risco_min_pct=0.0)


# ------------------------------------------------------------------ dados
def buscar(simbolo, interval='1h', limite=400):
    r = requests.get(f"{BASE_URL}/klines",
                     params={'symbol': simbolo, 'interval': interval,
                             'limit': limite}, timeout=20)
    r.raise_for_status()
    agora = int(time.time() * 1000)
    return [[int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]),
             float(c[5])] for c in r.json() if int(c[6]) < agora]


def top_pares(n=20):
    r = requests.get(f"{BASE_URL}/ticker/24hr", timeout=40)
    r.raise_for_status()
    fora = {'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'USDP', 'AEUR', 'EURI',
            'EUR', 'XUSD', 'USD1', 'PYUSD'}
    cand = []
    for d in r.json():
        s = d.get('symbol', '')
        if not s.endswith('USDT') or s[:-4] in fora:
            continue
        try:
            cand.append((float(d['quoteVolume']), s))
        except (KeyError, ValueError):
            continue
    cand.sort(reverse=True)
    return [x[1] for x in cand[:n]]


# ------------------------------------------------------------------ calculo
def atr(v, p=14):
    tr = [v[0][2] - v[0][3]]
    for k in range(1, len(v)):
        c0 = v[k - 1][4]
        tr.append(max(v[k][2] - v[k][3], abs(v[k][2] - c0), abs(v[k][3] - c0)))
    out, s = [], 0.0
    for k, x in enumerate(tr):
        s += x
        if k >= p:
            s -= tr[k - p]
            out.append(s / p)
        else:
            out.append(s / (k + 1))
    return out


def media_volume(v, n):
    out = [0.0] * len(v)
    for i in range(len(v)):
        j = max(0, i - n)
        if i > j:
            out[i] = sum(x[5] for x in v[j:i]) / (i - j)
    return out


def achar_impulsos(h, a, mv, cfg):
    """Impulsos com BOS e order block identificado."""
    n, out = len(h), []
    s = cfg['vol_periodo'] + cfg['estrut_janela']
    while s < n - cfg['imp_min']:
        melhor = None
        for L in range(cfg['imp_min'], cfg['imp_max'] + 1):
            e = s + L - 1
            if e >= n:
                break
            jan = h[s:e + 1]
            desloc = jan[-1][4] - jan[0][1]
            if a[e] <= 0 or abs(desloc) / a[e] < cfg['sigma']:
                continue
            alta = desloc > 0
            favor = sum(1 for c in jan
                        if (c[4] > c[1]) == alta and c[4] != c[1])
            if favor / L < cfg['frac_direcao']:
                continue
            corpos = sum(abs(c[4] - c[1]) for c in jan)
            ranges = sum(c[2] - c[3] for c in jan)
            if ranges <= 0 or corpos / ranges < cfg['corpo_imp']:
                continue
            if mv[s] <= 0:
                continue
            volm = sum(c[5] for c in jan) / L
            if volm / mv[s] < cfg['vol_mult']:
                continue
            f = abs(desloc) / a[e]
            if melhor is None or f > melhor[0]:
                melhor = (f, e, alta, volm / mv[s])
        if melhor is None:
            s += 1
            continue
        _, e, alta, vr = melhor
        j0 = max(0, s - cfg['estrut_janela'])
        if alta:
            estrut = max(x[2] for x in h[j0:s])
            bos = h[e][4] > estrut
        else:
            estrut = min(x[3] for x in h[j0:s])
            bos = h[e][4] < estrut
        ob = None
        for k in range(s, max(j0, s - cfg['ob_busca']) - 1, -1):
            if (h[k][4] < h[k][1]) if alta else (h[k][4] > h[k][1]):
                ob = k
                break
        if ob is None or not bos:
            s = e + 1
            continue
        out.append(dict(ini=s, fim=e, alta=alta, vol_rel=vr, ob=ob,
                        ob_base=h[ob][3], ob_topo=h[ob][2],
                        topo=max(x[2] for x in h[s:e + 1]) if alta
                        else min(x[3] for x in h[s:e + 1]),
                        tam_atr=abs(h[e][4] - h[s][1]) / a[e]))
        s = e + 1
    return out


def seguir(h, a, imp, cfg):
    """Espera a varredura e a reversao. Devolve gatilho, cenario ou None."""
    fim, compra = imp['fim'], imp['alta']
    base, topo = imp['ob_base'], imp['ob_topo']
    limite = base - a[fim] * cfg['furo_atr'] if compra else \
             topo + a[fim] * cfg['furo_atr']
    alvo = imp['topo']
    varreu, extremo = False, None

    for k in range(fim + 1, len(h)):
        if k - fim > cfg['espera_max']:
            return None
        hi, lo, o, cl = h[k][2], h[k][3], h[k][1], h[k][4]

        if not varreu:
            if (hi >= alvo) if compra else (lo <= alvo):
                return None            # ja foi ao alvo, acabou
            if (lo <= limite) if compra else (hi >= limite):
                varreu, extremo = True, (lo if compra else hi)
            else:
                continue

        extremo = min(extremo, lo) if compra else max(extremo, hi)
        fmax = base - a[fim] * cfg['furo_max'] if compra else \
               topo + a[fim] * cfg['furo_max']
        if (extremo < fmax) if compra else (extremo > fmax):
            return None                # foi longe demais, virou continuacao

        dentro = (cl > base) if compra else (cl < topo)
        rng = hi - lo
        if rng <= 0 or not dentro:
            continue
        corpo = abs(cl - o)
        pavio = (min(o, cl) - lo) if compra else (hi - max(o, cl))
        favor = (cl > o) if compra else (cl < o)
        impulsao = favor and corpo / rng >= cfg['corpo_min']
        martelo = favor and pavio / rng >= cfg['pavio_min']
        if not (impulsao or martelo):
            continue

        ent = cl
        stop = extremo - a[k] * cfg['stop_folga'] if compra else \
               extremo + a[k] * cfg['stop_folga']
        risco = abs(ent - stop)
        dist = (alvo - ent) if compra else (ent - alvo)
        if risco <= 0 or dist <= 0:
            return None
        rr = dist / risco
        if rr < cfg['rr_min'] or risco / ent * 100 < cfg['risco_min_pct']:
            return None
        return dict(fase='gatilho', lado='compra' if compra else 'venda',
                    entrada=ent, stop=stop, alvo=alvo, rr=rr, idx=k,
                    vela_ms=h[k][0], risco_pct=risco / ent * 100,
                    tipo='martelo' if martelo and not impulsao else 'impulsão',
                    imp=imp, varrido=True)

    # chegou ao fim sem gatilho: ainda esta armado?
    if varreu:
        return dict(fase='cenario', lado='compra' if compra else 'venda',
                    imp=imp, alvo=alvo, preco=h[-1][4], vela_ms=h[-1][0],
                    nota='varreu o order block, esperando a vela de reversão')
    perto = abs(h[-1][4] - (base if compra else topo)) / max(a[-1], 1e-12)
    if perto <= 1.0:
        return dict(fase='cenario', lado='compra' if compra else 'venda',
                    imp=imp, alvo=alvo, preco=h[-1][4], vela_ms=h[-1][0],
                    nota='preço chegou no order block, esperando a varredura')
    return None


# ------------------------------------------------------------------ telegram
def fmt(x):
    return f"{x:,.8f}".rstrip('0').rstrip('.') if x < 1 else \
           f"{x:,.4f}".rstrip('0').rstrip('.')


def diag(linha):
    print(linha, flush=True)
    try:
        with open(DIAG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def enviar(texto, html=True):
    tok = os.getenv("TELEGRAM_TOKEN") or os.getenv("TOKEN_TELEGRAM")
    chat = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID_TELEGRAM")
    diag(f"TOKEN: {'ok ' + str(len(tok)) + ' chars' if tok else 'AUSENTE'}"
         f" | CHAT_ID: {'ok ' + str(len(chat)) + ' chars' if chat else 'AUSENTE'}")
    if not tok or not chat:
        return False
    dados = {'chat_id': chat, 'text': texto}
    if html:
        dados['parse_mode'] = 'HTML'
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data=dados, timeout=20)
        diag(f"HTTP {r.status_code}: {r.text[:200]}")
        if not r.ok and html:
            for t in ('<b>', '</b>', '<i>', '</i>', '<code>', '</code>'):
                texto = texto.replace(t, '')
            return enviar(texto, html=False)
        return r.ok
    except Exception as e:
        diag(f"ERRO de rede: {e}")
        return False


def quando(ms):
    return f"{datetime.fromtimestamp(ms / 1000, BRT):%d/%m %H:%M}"


def msg_gatilho(sim, g, posicao):
    imp = g['imp']
    seta = "🟢" if g['lado'] == 'compra' else "🔴"
    risco_usd = g['risco_pct'] / 100 * posicao
    ganho_usd = risco_usd * g['rr']
    par = sim.replace('USDT', '/USDT')
    return (
        f"{seta} <b>{par}</b> — VARREDURA DO ORDER BLOCK\n"
        f"<b>{g['lado'].upper()}</b> · gatilho de {g['tipo']}\n"
        f"vela de H1 fechada às <b>{quando(g['vela_ms'])}</b>\n\n"
        f"entrada  <code>{fmt(g['entrada'])}</code>\n"
        f"stop     <code>{fmt(g['stop'])}</code>   ({g['risco_pct']:.2f}%)\n"
        f"alvo     <code>{fmt(g['alvo'])}</code>   "
        f"<b>R:R 1:{g['rr']:.2f}</b>\n\n"
        f"<i>impulso: {imp['fim']-imp['ini']+1} velas, "
        f"{imp['tam_atr']:.1f} ATR, volume {imp['vol_rel']:.1f}× a média</i>\n"
        f"<i>order block: {fmt(imp['ob_base'])} – {fmt(imp['ob_topo'])}</i>\n\n"
        f"com posição de ${posicao:.0f}: risco <b>${risco_usd:.2f}</b>, "
        f"alvo <b>${ganho_usd:.2f}</b>\n"
        f"<i>confira o contexto no gráfico antes de entrar</i>")


def msg_cenario(itens):
    linhas = ["👀 <b>No radar</b> (ainda sem gatilho)\n"]
    for sim, c in itens:
        linhas.append(
            f"<b>{sim.replace('USDT','/USDT')}</b> {c['lado']} · "
            f"{c['nota']}\n"
            f"   preço <code>{fmt(c['preco'])}</code> · "
            f"alvo <code>{fmt(c['alvo'])}</code> · "
            f"OB {fmt(c['imp']['ob_base'])}–{fmt(c['imp']['ob_topo'])}")
    return "\n".join(linhas)


# ------------------------------------------------------------------ main
def carregar():
    try:
        with open(ESTADO) as f:
            return set(json.load(f))
    except Exception:
        return set()


def salvar(ch):
    try:
        with open(ESTADO, "w") as f:
            json.dump(sorted(ch)[-800:], f)
    except Exception as e:
        diag(f"nao salvou o estado: {e}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=20)
    ap.add_argument('--posicao', type=float, default=200.0,
                    help='tamanho da posicao em USD, so para mostrar o risco')
    ap.add_argument('--rr-min', type=float, default=CFG['rr_min'])
    ap.add_argument('--so-gatilho', action='store_true')
    ap.add_argument('--teste', action='store_true')
    ap.add_argument('--ping', action='store_true')
    a = ap.parse_args()
    CFG['rr_min'] = a.rr_min

    open(DIAG, "w").close()
    diag(f"início {datetime.now(BRT):%d/%m %H:%M} BRT")

    if a.ping:
        enviar(f"✅ bot da varredura vivo — {datetime.now(BRT):%d/%m %H:%M}")
        return

    pares = top_pares(a.top)
    diag(f"pares: {', '.join(pares)}")
    vistos = carregar()
    gatilhos, cenarios, linhas = [], [], []

    for sim in pares:
        try:
            h = buscar(sim, '1h', 400)
        except Exception as e:
            diag(f"{sim}: erro ao buscar ({e})")
            continue
        if len(h) < 150:
            continue
        a_ = atr(h, CFG['atr_periodo'])
        mv = media_volume(h, CFG['vol_periodo'])
        achou = None
        for imp in achar_impulsos(h, a_, mv, CFG):
            e = seguir(h, a_, imp, CFG)
            if e and (achou is None or e['fase'] == 'gatilho'):
                achou = e
                if e['fase'] == 'gatilho':
                    break
        if not achou:
            continue
        if achou['fase'] == 'gatilho':
            # so vale se a vela de reversao e a ULTIMA vela fechada
            if achou['idx'] != len(h) - 1:
                diag(f"{sim}: gatilho antigo ({len(h)-1-achou['idx']} velas atrás)")
                continue
            gatilhos.append((sim, achou))
            linhas.append(f"GATILHO {sim} {achou['lado']} "
                          f"R:R 1:{achou['rr']:.2f} risco {achou['risco_pct']:.2f}%")
        else:
            cenarios.append((sim, achou))
            linhas.append(f"radar   {sim} {achou['lado']} — {achou['nota']}")

    diag(f"gatilhos {len(gatilhos)} | cenários {len(cenarios)}")
    try:
        with open(RESUMO, "w", encoding="utf-8") as f:
            f.write(f"{datetime.now(BRT):%d/%m %H:%M} BRT\n" +
                    "\n".join(linhas or ["nada"]) + "\n")
    except Exception:
        pass

    novos = []
    for sim, g in gatilhos:
        chave = f"{sim}-{g['vela_ms']}"
        if chave in vistos:
            continue
        vistos.add(chave)
        novos.append((sim, g))

    if a.teste:
        for sim, g in novos:
            print(msg_gatilho(sim, g, a.posicao), "\n")
        if cenarios and not a.so_gatilho:
            print(msg_cenario(cenarios))
        return

    for sim, g in novos:
        enviar(msg_gatilho(sim, g, a.posicao))
    if cenarios and not a.so_gatilho:
        chave = "cenarios-" + str(max(c['vela_ms'] for _, c in cenarios))
        if chave not in vistos:
            vistos.add(chave)
            enviar(msg_cenario(cenarios))
    salvar(vistos)
    diag(f"enviados {len(novos)} gatilhos")


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        print("=== ERRO ===")
        traceback.print_exc()
        raise
