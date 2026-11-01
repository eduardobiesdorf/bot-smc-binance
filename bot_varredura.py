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

import grafico_varredura as graf

BRT = timezone(timedelta(hours=-3))
BASE_URL = "https://data-api.binance.vision/api/v3"
ESTADO = "varredura_enviados.json"
DIAG = "diagnostico_varredura.txt"
RESUMO = "resumo_varredura.txt"
MAX_CENARIOS = 4   # no maximo 4 imagens de radar por rodada

CFG = dict(imp_min=3, imp_max=8, sigma=2.5, frac_direcao=0.7, corpo_imp=0.5,
           vol_mult=1.5, vol_periodo=20, atr_periodo=14, estrut_janela=30,
           ob_busca=6, furo_atr=0.0, furo_max=2.5, corpo_min=0.5,
           pavio_min=0.5, espera_max=60, stop_folga=0.10, rr_min=1.2,
           risco_min_pct=0.0, max_espera_gatilho=4, vol_varr_min=1.2)


# ------------------------------------------------------------------ dados
def buscar(simbolo, interval='1h', limite=400):
    r = requests.get(f"{BASE_URL}/klines",
                     params={'symbol': simbolo, 'interval': interval,
                             'limit': limite}, timeout=20)
    r.raise_for_status()
    agora = int(time.time() * 1000)
    return [[int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]),
             float(c[5])] for c in r.json() if int(c[6]) < agora]


# Nao sao cripto: stablecoins, commodities e acoes tokenizadas. As acoes
# na Binance levam um B no fim do ticker (SNDKB = SanDisk, INTCB = Intel,
# CRCLB = Circle). Elas seguem o pregao de Nova York, ficam paradas no fim
# de semana e nao tem a liquidez que esse setup procura.
# Os 50 pares de maior volume em USD-M Futures, em ordem de volume.
# Os 20 primeiros sao o NUCLEO, onde a estrategia foi validada:
#   nucleo (1-20):  n=292 em 2 anos, +0,092R/op. +0,020 em 2025, +0,202 em 2026
#   extra  (21-50): n=396,          -0,099R/op. -0,297 em 2025, +0,164 em 2026
# O extra entra porque o Eduardo quer ver, mas vai sempre marcado no alerta.
# Com --dinamico o bot volta a rankear por volume de 24h do spot.
UNIVERSO = [
    'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT',
    'HYPEUSDT', 'SUIUSDT', 'BNBUSDT', 'ADAUSDT', 'ZECUSDT',
    'ENAUSDT', 'LINKUSDT', 'AVAXUSDT', 'LTCUSDT', 'TRUMPUSDT',
    'AAVEUSDT', 'WLDUSDT', 'TAOUSDT', 'NEARUSDT', 'BCHUSDT',
    # ---------- daqui para baixo e a faixa EXTRA ----------
    'FILUSDT', 'PUMPUSDT', 'UNIUSDT', 'DOTUSDT', 'ASTERUSDT',
    'ONDOUSDT', 'PENGUUSDT', 'TRXUSDT', 'CRVUSDT', 'ARBUSDT',
    'XLMUSDT', 'APTUSDT', 'TIAUSDT', 'HBARUSDT', 'OPUSDT',
    'XPLUSDT', 'VIRTUALUSDT', 'FETUSDT', 'INJUSDT', 'WLFIUSDT',
    'TONUSDT', 'SEIUSDT', 'EIGENUSDT', 'ICPUSDT', 'PENDLEUSDT',
    'ZROUSDT', 'REUSDT', 'POLUSDT', 'DASHUSDT', 'STRKUSDT',
]
NUCLEO = set(UNIVERSO[:20])

# Os pares que o bot nao escaneava ate 01/11/2026, quando a lista passou
# de 20 (ordem do spot) para 50 (ordem de futuros).
ANTIGOS = {'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'DOGEUSDT', 'BNBUSDT',
           'ADAUSDT', 'LINKUSDT', 'SUIUSDT', 'AVAXUSDT', 'TRXUSDT',
           'NEARUSDT', 'LTCUSDT', 'UNIUSDT', 'DOTUSDT', 'AAVEUSDT',
           'XLMUSDT', 'HBARUSDT', 'BCHUSDT', 'ONDOUSDT'}
NOVOS = [s for s in UNIVERSO if s not in ANTIGOS]

STABLE = {'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'USDP', 'AEUR', 'EURI',
          'EUR', 'XUSD', 'USD1', 'PYUSD'}
COMMODITY = {'XAUT', 'PAXG', 'XAGT'}
# acoes tokenizadas: seguem o pregao de Nova York, nao sao cripto
ACOES = {'SNDKB', 'INTCB', 'CRCLB', 'NVDAB', 'TSLAB', 'AAPLB', 'MSTRB',
         'COINB', 'METAB', 'AMZNB', 'GOOGLB', 'MSFTB', 'HOODB', 'PLTRB'}


def candidatos(n=60):
    """Pares USDT por volume de 24h, ja sem stablecoin e commodity."""
    r = requests.get(f"{BASE_URL}/ticker/24hr", timeout=40)
    r.raise_for_status()
    fora = STABLE | COMMODITY | ACOES
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


def negocia_sempre(h, limite=0.03):
    """Cripto negocia 24/7. Acao tokenizada tem horas mortas no fim de
    semana e fora do pregao -- velas com volume zero ou sem amplitude.
    Esse teste pega qualquer tokenizada nova sem eu precisar listar."""
    if len(h) < 200:
        return False
    mortas = sum(1 for c in h[-300:] if c[5] <= 0 or c[2] <= c[3])
    return mortas / len(h[-300:]) <= limite


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


def seguir(h, a, imp, cfg, mv):
    """Espera a varredura e a reversao. Devolve gatilho, cenario ou None."""
    fim, compra = imp['fim'], imp['alta']
    base, topo = imp['ob_base'], imp['ob_topo']
    limite = base - a[fim] * cfg['furo_atr'] if compra else \
             topo + a[fim] * cfg['furo_atr']
    alvo = imp['topo']
    varreu, extremo, k_varreu, vol_varr = False, None, None, 0.0

    for k in range(fim + 1, len(h)):
        if k - fim > cfg['espera_max']:
            return None
        hi, lo, o, cl = h[k][2], h[k][3], h[k][1], h[k][4]

        if not varreu:
            if (hi >= alvo) if compra else (lo <= alvo):
                return None            # ja foi ao alvo, acabou
            if (lo <= limite) if compra else (hi >= limite):
                vol_varr = (h[k][5] / mv[k]) if mv[k] > 0 else 0.0
                varreu, extremo, k_varreu = True, (lo if compra else hi), k
            else:
                continue

        # reacao tardia nao e caca a stop: ate 4 velas depois da varredura
        if k - k_varreu > cfg['max_espera_gatilho']:
            return None
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
        # Varredura sem volume nao e varredura: e o preco escorregando no
        # livro vazio. Medido em 21 meses de futuros, os gatilhos com volume
        # abaixo de 1,2x a media deram 21,3% de acerto e -0,152R por
        # operacao; acima disso, 32,6% e +0,051R. No nucleo, o piso leva de
        # +0,138 para +0,208R, com melhora em 2025 e em 2026.
        if vol_varr < cfg['vol_varr_min']:
            return None
        return dict(fase='gatilho', lado='compra' if compra else 'venda',
                    entrada=ent, stop=stop, alvo=alvo, rr=rr, idx=k,
                    vela_ms=h[k][0], risco_pct=risco / ent * 100,
                    tipo='martelo' if martelo and not impulsao else 'impulsão',
                    imp=imp, varredura=k_varreu, vol_varr=vol_varr)

    # chegou ao fim sem gatilho: ainda esta armado?
    if varreu:
        return dict(fase='cenario', lado='compra' if compra else 'venda',
                    imp=imp, alvo=alvo, preco=h[-1][4], vela_ms=h[-1][0],
                    varredura=k_varreu, vol_varr=vol_varr,
                    nota='limpou o order block, esperando a reversão')
    perto = abs(h[-1][4] - (base if compra else topo)) / max(a[-1], 1e-12)
    if perto <= 1.0:
        return dict(fase='cenario', lado='compra' if compra else 'venda',
                    imp=imp, alvo=alvo, preco=h[-1][4], vela_ms=h[-1][0],
                    varredura=None, vol_varr=0.0,
                    nota='chegou no order block, esperando a limpeza')
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


def faixa(sim):
    return ("✅ núcleo" if sim in NUCLEO
            else "⚠️ extra — fora do que foi validado")


def msg_gatilho(sim, g):
    seta = "🟢" if g['lado'] == 'compra' else "🔴"
    return (
        f"{seta} <b>{sim.replace('USDT', '/USDT')}</b> — "
        f"<b>{g['lado'].upper()}</b>   <i>{faixa(sim)}</i>\n"
        f"vela de H1 fechada às {quando(g['vela_ms'])}\n\n"
        f"entrada  <code>{fmt(g['entrada'])}</code>\n"
        f"stop     <code>{fmt(g['stop'])}</code>   "
        f"risco <b>{g['risco_pct']:.2f}%</b>\n"
        f"alvo     <code>{fmt(g['alvo'])}</code>   "
        f"<b>R:R 1:{g['rr']:.2f}</b>\n\n"
        f"<i>ordem limitada em {fmt(g['entrada'])}, válida ~4h. "
        f"A mercado o preço já correu e a vantagem some.</i>")


def msg_cenario(sim, c):
    return (f"👀 <b>{sim.replace('USDT', '/USDT')}</b> — de olho "
            f"({c['lado']})   <i>{faixa(sim)}</i>\n"
            f"{c['nota']}\n\n"
            f"preço  <code>{fmt(c['preco'])}</code>\n"
            f"alvo   <code>{fmt(c['alvo'])}</code>")


def manda_com_grafico(sim, e, h, texto):
    """Tenta mandar a imagem com a legenda. Se falhar, manda so o texto."""
    caminho = f"/tmp/{sim}_{e['fase']}.png"
    try:
        if graf.desenhar(sim, h, e, caminho) and graf.enviar_foto(caminho, texto):
            return True
    except Exception as ex:
        diag(f"{sim}: nao consegui desenhar ({ex})")
    return enviar(texto)


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
    ap.add_argument('--top', type=int, default=50)
    ap.add_argument('--dinamico', action='store_true',
                    help='rankear por volume de 24h em vez da lista fixa')
    ap.add_argument('--rr-min', type=float, default=CFG['rr_min'])
    ap.add_argument('--vol-min', type=float, default=CFG['vol_varr_min'],
                    help='volume minimo da vela que varre, x a media de 20')
    ap.add_argument('--so-gatilho', action='store_true')
    ap.add_argument('--teste', action='store_true')
    ap.add_argument('--ping', action='store_true')
    ap.add_argument('--novos', action='store_true',
                    help='com --ping: so os pares que entraram em 01/11/2026')
    ap.add_argument('--exemplos', type=int, default=2,
                    help='quantos gatilhos do historico mandar no ping')
    a = ap.parse_args()
    CFG['rr_min'] = a.rr_min
    CFG['vol_varr_min'] = a.vol_min

    open(DIAG, "w").close()
    diag(f"início {datetime.now(BRT):%d/%m %H:%M} BRT")

    if a.ping:
        enviar(f"✅ bot da varredura vivo — {datetime.now(BRT):%d/%m %H:%M}")
        # manda tambem o gatilho mais recente do historico, so para voce ver
        # o formato da mensagem e para eu confirmar que a imagem passa.
        achados = []
        fila_ping = NOVOS if a.novos else UNIVERSO[:a.top]
        diag(f"ping em {len(fila_ping)} pares"
             + (" (so os que entraram agora)" if a.novos else ""))
        for sim in fila_ping:
            try:
                h = buscar(sim, '1h', 400)
            except Exception:
                continue
            if len(h) < 150:
                continue
            a_ = atr(h, CFG['atr_periodo'])
            mv = media_volume(h, CFG['vol_periodo'])
            for imp in achar_impulsos(h, a_, mv, CFG):
                g = seguir(h, a_, imp, CFG, mv)
                if g and g['fase'] == 'gatilho':
                    achados.append((g['vela_ms'], sim, g, h))
        achados.sort(reverse=True, key=lambda x: x[0])
        if not achados:
            diag("nenhum gatilho no historico recente")
            enviar("nenhum gatilho no histórico recente dos 20 pares")
            return
        for _, sim, g, h in achados[:a.exemplos]:
            g['nucleo'] = sim in NUCLEO
            idade = (int(time.time() * 1000) - g['vela_ms']) / 3600000
            manda_com_grafico(
                sim, g, h[:g['idx'] + 1],
                f"🧪 <i>gatilho do histórico, {idade:.0f}h atrás — "
                f"não é alerta de agora</i>\n\n" + msg_gatilho(sim, g))
            diag(f"exemplo enviado: {sim} [{'nucleo' if sim in NUCLEO else 'extra'}] "
                 f"({idade:.0f}h)")
        return

    vistos = carregar()
    gatilhos, cenarios, linhas = [], [], []
    usados, descartados = [], []

    fila = candidatos(a.top * 3) if a.dinamico else UNIVERSO[:a.top]
    for sim in fila:
        if len(usados) >= a.top:
            break
        try:
            h = buscar(sim, '1h', 400)
        except Exception as e:
            diag(f"{sim}: erro ao buscar ({e})")
            continue
        if len(h) < 150:
            continue
        if not negocia_sempre(h):
            descartados.append(sim)
            continue
        usados.append(sim)
        a_ = atr(h, CFG['atr_periodo'])
        mv = media_volume(h, CFG['vol_periodo'])
        achou = None
        for imp in achar_impulsos(h, a_, mv, CFG):
            e = seguir(h, a_, imp, CFG, mv)
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
            achou['nucleo'] = sim in NUCLEO
            gatilhos.append((sim, achou, h))
            linhas.append(f"GATILHO [{'nucleo' if sim in NUCLEO else 'extra'}] "
                          f"{sim} {achou['lado']} "
                          f"R:R 1:{achou['rr']:.2f} risco {achou['risco_pct']:.2f}%")
        else:
            achou['nucleo'] = sim in NUCLEO
            cenarios.append((sim, achou, h))
            linhas.append(f"radar   {sim} {achou['lado']} — {achou['nota']}")

    diag(f"pares ({len(usados)}): {', '.join(usados)}")
    if descartados:
        diag(f"descartados (não negociam 24/7): {', '.join(descartados)}")
    diag(f"gatilhos {len(gatilhos)} | cenários {len(cenarios)}")
    try:
        with open(RESUMO, "w", encoding="utf-8") as f:
            f.write(f"{datetime.now(BRT):%d/%m %H:%M} BRT\n" +
                    "\n".join(linhas or ["nada"]) + "\n")
    except Exception:
        pass

    novos = []
    for sim, g, h in gatilhos:
        chave = f"{sim}-{g['vela_ms']}"
        if chave in vistos:
            continue
        vistos.add(chave)
        novos.append((sim, g, h))

    if a.teste:
        for sim, g, _ in novos:
            print(msg_gatilho(sim, g), "\n")
        for sim, c, _ in cenarios[:MAX_CENARIOS]:
            print(msg_cenario(sim, c), "\n")
        return

    for sim, g, h in novos:
        manda_com_grafico(sim, g, h, msg_gatilho(sim, g))

    if not a.so_gatilho:
        for sim, c, h in cenarios[:MAX_CENARIOS]:
            chave = f"cen-{sim}-{c['vela_ms']}"
            if chave in vistos:
                continue
            vistos.add(chave)
            manda_com_grafico(sim, c, h, msg_cenario(sim, c))
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
