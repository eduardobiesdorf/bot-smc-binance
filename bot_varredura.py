# -*- coding: utf-8 -*-
"""
Radar da VARREDURA DO ORDER BLOCK — padrão em H4 desde 13/11/2026.

A regra, no cenario de compra (o de venda e o espelho):

  1. IMPULSO de alta: 3 a 8 velas, deslocamento >= 2,5 ATR, corpo
     dominando o range, volume medio >= 1,5x a media das 20 anteriores.
  2. BOS: o impulso tem de romper o topo das 30 velas anteriores.
     Sem rompimento, a vela de baixa anterior nao e order block.
  3. ORDER BLOCK: a ultima vela de baixa antes do impulso.
     A zona vai da minima a maxima dela.
  4. VARREDURA: o preco volta e FURA a zona por baixo -- e aqui que
     morre o stop de quem comprou no order block. O furo tem de ser
     RASO: no maximo 0,15x a altura do proprio bloco. Afundar mais que
     isso nao e caca a stop, e o bloco deixando de existir.
  5. REVERSAO: uma vela fecha de volta acima da base da zona, com corpo
     a favor ou pavio longo.
  6. Entrada no fechamento dessa vela. Stop uns ticks abaixo da minima
     da varredura. Alvo no topo que o impulso deixou.

MEDIDO EM 13/11/2026 (universo rolante de 150, 7 anos, so as operacoes
do trimestre seguinte, risco fixo de 100 USD):

      55 operacoes, 0,7 por mes, 41,8% de acerto, R:R 1:3,26
      +60,00 por operacao  ·  total +3.299
      teste do acaso por LOTE z = +1,86
      bate ENTRADA ALEATORIA por +2,38 desvios
        (lote real +97 ±50, 16/34 positivos · sorteado -21)
      2021 -719 (0 alvos/7 op) · 2022 +2.163 (9/13) · 2023 +249 (2/10)
      2024 +24 (1/3) · 2025 +636 (6/13) · 2026 +945 (5/9)
      5 de 6 anos positivos, mas 2022 carrega a maior parte

AS DUAS MUDANCAS DE 13/11/2026 e por que:

  H1 -> H4. Na configuracao antiga (H1, sem filtro de profundidade) o
  setup media -1,00 por operacao no universo rolante. O +9,40 que o
  validava vinha da lista UNIVERSO[:50], que sao as 50 maiores de
  NOVEMBRO DE 2026 -- escolher o time depois de ver o campeonato.
  Mesmas regras: 34,3% de acerto na lista de hoje contra 28,0% na
  lista de 2023.

  O FILTRO DE FURO RASO. O furo_max estava em 2,5 ATR, que quase nao
  filtra. Medido na altura do PROPRIO bloco o efeito e enorme e
  monotono -- e so no H4:

      H4 sem filtro  -12,00/op  ·  0,50x +7,60  ·  0,25x +28,20
      0,20x +42,90   ·  0,15x +60,00  ·  0,10x +92,70
      com o mesmo filtro: H1 -1,40, H2 +0,50, H8 -11,50

  E a MESMA regra do encosto raso do setup 3: o preco pode testar o
  bloco, nao pode destrui-lo. Os dois setups parecem opostos (um quer
  que o bloco segure, o outro que seja furado e devolvido) mas exigem
  a mesma coisa do tamanho do movimento contra: tem de ser pequeno.

REGRA PARA TESTES NOVOS: nenhum resultado conta antes de passar pelo
universo rolante, de ser contado por LOTE e de bater a entrada
aleatoria. Ver analise/setup1_fundo.py e analise/setup1_honesto.py.

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
import acompanhamento as acomp
import reversao8 as rev8
import falha5

BRT = timezone(timedelta(hours=-3))
BASE_URL = "https://data-api.binance.vision/api/v3"
ESTADO = "varredura_enviados.json"
DIAG = "diagnostico_varredura.txt"
RESUMO = "resumo_varredura.txt"
MAX_CENARIOS = 4   # no maximo 4 imagens de radar por rodada

# Dimensionamento. O que e fixo e a perda em dolar, nao o tamanho da
# posicao: com stop de 0,3% e de 9% no mesmo setup, posicao fixa
# arriscaria 30 vezes mais numa do que na outra.
CAIXA = 60.0       # banca, em USDT
RISCO_PCT = 2.0    # quanto da banca morre num stop
ALAV_MAX = 8.0     # liquidacao em 8x fica em -12%; nenhum stop chega la

CFG = dict(imp_min=3, imp_max=8, sigma=2.5, frac_direcao=0.7, corpo_imp=0.5,
           vol_mult=1.5, vol_periodo=20, atr_periodo=14, estrut_janela=30,
           ob_busca=6, furo_atr=0.0, furo_max=2.5, corpo_min=0.5,
           pavio_min=0.5, espera_max=60, stop_folga=0.10, rr_min=1.2,
           risco_min_pct=0.0, max_espera_gatilho=4, vol_varr_min=1.2,
           liq_janela=100, liq_max_r=1.5,
           # 13/11/2026 -- o setup passou de H1 para H4 e ganhou o filtro de
           # PROFUNDIDADE DO FURO medido na altura do PROPRIO BLOCO. Medido no
           # universo rolante, 7 anos, so as operacoes do trimestre seguinte:
           #
           #   H4 · furo <= 0,10x   37 op, 48,6% de acerto, 1:3,19, +92,70/op
           #   H4 · furo <= 0,15x   55 op, 41,8%,           1:3,26, +60,00/op
           #   H4 · furo <= 0,20x   73 op, 39,7%,           1:3,14, +42,90/op
           #   H4 · furo <= 0,25x   90 op, 36,7%,           1:3,29, +28,20/op
           #   H4 · furo <= 0,50x  147 op, 31,3%,           1:3,40,  +7,60/op
           #   H4 · sem filtro     412 op, 26,5%,           1:3,07, -12,00/op
           #   H1 · sem filtro (o de antes) -1,00/op no universo rolante
           #
           # Gradiente monotono, e o TOTAL quase nao muda entre 0,10 e 0,20
           # (3.431, 3.299, 3.129): apertar o filtro nao custa dinheiro, so
           # troca quantidade por qualidade. So funciona no H4 -- com o mesmo
           # filtro, H1 da -1,40, H2 +0,50 e H8 -11,50.
           #
           # Bate entrada aleatoria por +2,38 desvios (lote real +97 ±50,
           # 16/34 lotes positivos, sorteado -21). 5 de 6 anos positivos, mas
           # 2021 deu -719 com ZERO acerto em 7 operacoes e 2022 carrega a
           # maior parte. Ver analise/setup1_fundo.py.
           #
           # O furo raso aqui e a MESMA regra do encosto raso do setup 3: o
           # preco pode testar o bloco, nao pode destrui-lo.
           tf='4h', furo_ob=0.15)


# ------------------------------------------------------------------ dados
def buscar(simbolo, interval='1h', limite=400):
    r = requests.get(f"{BASE_URL}/klines",
                     params={'symbol': simbolo, 'interval': interval,
                             'limit': limite}, timeout=20)
    r.raise_for_status()
    agora = int(time.time() * 1000)
    return [[int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]),
             float(c[5])] for c in r.json() if int(c[6]) < agora]


# 14/11/2026 -- UMA serie de 1h por par, por rodada. Antes a reversao de 8h
# e o rompimento falso baixavam 1h/1300 cada um, e a varredura baixava
# 4h/400 por fora: 350 requisicoes para 150 pares. Agora sao 150. O H4 e o
# H8 saem da MESMA serie, do mesmo jeito que o backtest faz (rev8.juntar).
_CACHE_1H = {}
_CACHE_CAND = {}


def serie_1h(sim, limite=1300):
    """1300 velas de 1h (54 dias) por par, baixadas uma unica vez."""
    if sim not in _CACHE_1H:
        try:
            _CACHE_1H[sim] = buscar(sim, '1h', limite)
        except Exception:
            _CACHE_1H[sim] = []
    return _CACHE_1H[sim]


def fila_viva(n):
    """candidatos(n) com cache: os tres alertas pedem a mesma lista."""
    if n not in _CACHE_CAND:
        _CACHE_CAND[n] = candidatos(n)
    return _CACHE_CAND[n]


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
def rsi(h, p=14):
    """RSI de Wilder. Nao filtra nada: fica gravado para teste futuro.

    Medido em 22 meses, o RSI na vela da varredura separa bem (normalizado
    pelo lado, >=40 da +0,441R contra +0,113R abaixo disso), mas nao passou
    no teste do nulo (z=+1,35, p=0,10) e inverteu num semestre. Entao o bot
    so ANOTA, para daqui a alguns meses a gente testar em dado novo.
    """
    out = [None] * len(h)
    if len(h) < p + 1:
        return out
    g = l = 0.0
    for i in range(1, p + 1):
        d = h[i][4] - h[i - 1][4]
        g += max(d, 0.0); l += max(-d, 0.0)
    g /= p; l /= p
    out[p] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(p + 1, len(h)):
        d = h[i][4] - h[i - 1][4]
        g = (g * (p - 1) + max(d, 0.0)) / p
        l = (l * (p - 1) + max(-d, 0.0)) / p
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


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
                        fim_ms=h[e][0],   # identidade estavel do setup
                        ob_base=h[ob][3], ob_topo=h[ob][2],
                        topo=max(x[2] for x in h[s:e + 1]) if alta
                        else min(x[3] for x in h[s:e + 1]),
                        tam_atr=abs(h[e][4] - h[s][1]) / a[e]))
        s = e + 1
    return out


def piscina(h, i, compra, ent, janela):
    """Distancia ate a liquidez nao consumida mais proxima da entrada.

    Numa venda e o topo fractal ainda nao superado acima do preco; numa
    compra, o fundo ainda nao perdido abaixo. Devolve a distancia em
    preco, ou None se nao houver nenhuma na janela.

    Medido em 21 meses de futuros: quanto MAIS PERTO a piscina, melhor.
    Ate 1,5R de distancia o setup da +0,259R/op contra +0,051 sem filtro;
    acima de 2,5R cai para -0,369. A leitura e que uma piscina dentro do
    nosso risco e testada sem nos tirar, e depois o preco vai embora --
    enquanto uma piscina longe demais so e alcancada estourando o stop.
    """
    melhor = None
    for k in range(max(3, i - janela), i - 3):
        if compra:
            ext = all(h[k][3] < h[k - m][3] for m in (1, 2, 3)) and \
                  all(h[k][3] < h[k + m][3] for m in (1, 2, 3))
            if not ext or h[k][3] >= ent:
                continue
            if any(h[j][3] <= h[k][3] for j in range(k + 4, i + 1)):
                continue                      # ja foi consumida
            d = ent - h[k][3]
        else:
            ext = all(h[k][2] > h[k - m][2] for m in (1, 2, 3)) and \
                  all(h[k][2] > h[k + m][2] for m in (1, 2, 3))
            if not ext or h[k][2] <= ent:
                continue
            if any(h[j][2] >= h[k][2] for j in range(k + 4, i + 1)):
                continue
            d = h[k][2] - ent
        if melhor is None or d < melhor:
            melhor = d
    return melhor


def seguir(h, a, imp, cfg, mv, tr=None):
    """Espera a varredura e a reversao. Devolve gatilho, cenario ou None.

    tr: lista opcional. Se vier, recebe o motivo de cada recusa, para
    o modo --explicar. Nao muda nenhuma decisao.
    """
    def no(m):
        if tr is not None:
            tr.append(m)
        return None
    fim, compra = imp['fim'], imp['alta']
    base, topo = imp['ob_base'], imp['ob_topo']
    limite = base - a[fim] * cfg['furo_atr'] if compra else \
             topo + a[fim] * cfg['furo_atr']
    alvo = imp['topo']
    varreu, extremo, k_varreu, vol_varr = False, None, None, 0.0

    for k in range(fim + 1, len(h)):
        if k - fim > cfg['espera_max']:
            return no(f"passou de {cfg['espera_max']} velas sem varrer o order block")
        hi, lo, o, cl = h[k][2], h[k][3], h[k][1], h[k][4]

        if not varreu:
            if (hi >= alvo) if compra else (lo <= alvo):
                return no('o preço foi ao alvo antes de voltar no order block')
            if (lo <= limite) if compra else (hi >= limite):
                vol_varr = (h[k][5] / mv[k]) if mv[k] > 0 else 0.0
                varreu, extremo, k_varreu = True, (lo if compra else hi), k
            else:
                continue

        # reacao tardia nao e caca a stop: ate 4 velas depois da varredura
        if k - k_varreu > cfg['max_espera_gatilho']:
            return no(f"varreu mas não reverteu em {cfg['max_espera_gatilho']} velas")
        extremo = min(extremo, lo) if compra else max(extremo, hi)
        fmax = base - a[fim] * cfg['furo_max'] if compra else \
               topo + a[fim] * cfg['furo_max']
        if (extremo < fmax) if compra else (extremo > fmax):
            return no(f"furou o order block fundo demais (> {cfg['furo_max']:.1f} ATR): virou continuação, não varredura")
        # FURO RASO: a profundidade medida na altura do PROPRIO bloco.
        # O furo_max em ATR acima quase nao filtra; este e o que vale.
        alt_ob = topo - base
        if cfg.get('furo_ob') and alt_ob > 0:
            fund = ((base - extremo) if compra else (extremo - topo)) / alt_ob
            if fund > cfg['furo_ob']:
                return no(f"furou {fund:.2f}x a altura do bloco, máximo "
                          f"{cfg['furo_ob']:.2f}x: afundou demais para ser varredura")

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
            return no('alvo já ultrapassado ou stop inválido')
        rr = dist / risco
        if rr < cfg['rr_min'] or risco / ent * 100 < cfg['risco_min_pct']:
            return no(f"R:R 1:{rr:.2f} abaixo do mínimo {cfg['rr_min']:.2f}")
        # Varredura sem volume nao e varredura: e o preco escorregando no
        # livro vazio. Medido em 21 meses de futuros, os gatilhos com volume
        # abaixo de 1,2x a media deram 21,3% de acerto e -0,152R por
        # operacao; acima disso, 32,6% e +0,051R. No nucleo, o piso leva de
        # +0,138 para +0,208R, com melhora em 2025 e em 2026.
        if vol_varr < cfg['vol_varr_min']:
            return no(f"vela da varredura com {vol_varr:.2f}x o volume médio, mínimo {cfg['vol_varr_min']:.2f}x")
        d_liq = piscina(h, k, compra, ent, cfg['liq_janela'])
        if d_liq is None or d_liq / risco > cfg['liq_max_r']:
            return no('sem piscina de liquidez não consumida' if d_liq is None else f"piscina a {d_liq/risco:.1f}R da entrada, máximo {cfg['liq_max_r']:.1f}R")
        liq_r = d_liq / risco
        _r = rsi(h, 14)
        rsi_v, rsi_g = _r[k_varreu], _r[k]
        # normalizado pelo lado: "a favor" vira sempre numero baixo
        rsi_vn = rsi_v if (rsi_v is None or compra) else 100 - rsi_v
        return dict(fase='gatilho', lado='compra' if compra else 'venda',
                    rsi_varr=rsi_v, rsi_gat=rsi_g, rsi_varr_norm=rsi_vn,
                    entrada=ent, stop=stop, alvo=alvo, rr=rr, idx=k,
                    vela_ms=h[k][0], risco_pct=risco / ent * 100,
                    tipo='martelo' if martelo and not impulsao else 'impulsão',
                    imp=imp, varredura=k_varreu, vol_varr=vol_varr,
                    liq_r=liq_r)

    # chegou ao fim sem gatilho: ainda esta armado?
    if varreu:
        # O radar so pode avisar o que AINDA pode virar gatilho. Antes ele
        # avisava assim que o preco furava o order block, e ficava repetindo
        # "esperando a reversao" em setups ja mortos: tres dos primeiros
        # alertas (ETH, TRUMP e TIA) nunca poderiam virar entrada.
        #
        # 1) O volume da varredura e definitivo: ja aconteceu, nao melhora.
        if vol_varr < cfg['vol_varr_min']:
            return no(f"varredura com {vol_varr:.2f}x o volume médio, "
                      f"mínimo {cfg['vol_varr_min']:.2f}x — não vira gatilho")

        # 2) O stop ja esta definido pelo extremo da varredura, e o alvo pelo
        #    impulso. Entao da para saber ATE QUE PRECO a entrada ainda rende
        #    o R:R minimo:  teto = (alvo + rr*stop) / (1 + rr)
        #    A entrada mais favoravel possivel e a propria borda do order
        #    block, porque o gatilho exige fechar de volta dentro dele. Se
        #    nem ela alcanca o R:R minimo, o setup acabou.
        stop_h = extremo - a[-1] * cfg['stop_folga'] if compra else \
                 extremo + a[-1] * cfg['stop_folga']
        rrm = cfg['rr_min']
        teto = (alvo + rrm * stop_h) / (1 + rrm)
        melhor = base if compra else topo
        if (teto < melhor) if compra else (teto > melhor):
            rr_m = (abs(alvo - melhor) / abs(melhor - stop_h)
                    if abs(melhor - stop_h) > 0 else 0)
            return no(f"R:R no melhor caso seria 1:{rr_m:.2f}, abaixo de "
                      f"1:{rrm:.2f} — o pavio da varredura jogou o stop "
                      f"longe demais")

        return dict(fase='cenario', lado='compra' if compra else 'venda',
                    imp=imp, alvo=alvo, preco=h[-1][4], vela_ms=h[-1][0],
                    varredura=k_varreu, vol_varr=vol_varr,
                    stop_hip=stop_h, teto=teto,
                    nota='limpou o order block, esperando a reversão')
    perto = abs(h[-1][4] - (base if compra else topo)) / max(a[-1], 1e-12)
    if perto <= 1.0:
        return dict(fase='cenario', lado='compra' if compra else 'venda',
                    imp=imp, alvo=alvo, preco=h[-1][4], vela_ms=h[-1][0],
                    varredura=None, vol_varr=0.0,
                    nota='chegou no order block, esperando a limpeza')
    return no('nem varreu o order block nem chegou perto dele')


# ------------------------------------------------------------------ telegram
def fmt(x):
    return f"{x:,.8f}".rstrip('0').rstrip('.') if x < 1 else \
           f"{x:,.4f}".rstrip('0').rstrip('.')


def _casas(*refs):
    """Casas decimais que o par realmente usa, olhando varios precos."""
    n = 0
    for r in refs:
        t = f"{r:.10f}".rstrip('0')
        n = max(n, len(t.split('.')[1]) if '.' in t else 0)
    return max(2, min(n, 8))


def como(x, *refs, baixo=None):
    """Formata x com as casas do par.

    baixo=True arredonda PARA BAIXO, baixo=False para cima. E o que
    importa num teto de entrada: arredondar um teto de compra para cima
    faria o numero mentir, porque naquele preco o R:R ja nao fecha.
    """
    import math
    c = _casas(*refs)
    if baixo is not None:
        p = 10 ** c
        x = (math.floor(x * p) if baixo else math.ceil(x * p)) / p
    return f"{x:,.{c}f}"


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
    """Sempre horario de Brasilia. A Binance entrega em UTC, mas tudo o
    que chega para o Eduardo tem de estar no fuso em que ele opera."""
    return f"{datetime.fromtimestamp(ms / 1000, BRT):%d/%m %H:%M}"


def faixa(sim):
    return ("✅ núcleo" if sim in NUCLEO
            else "⚠️ extra — fora do que foi validado")


def mao(risco_pct):
    """Tamanho da posicao para arriscar sempre a mesma coisa em dolar.

    O stop varia de 0,3% a 9%, entao posicao fixa arrisca valores muito
    diferentes em cada operacao. Aqui o que e fixo e a PERDA: risco em
    dolar / stop em fracao = quanto de posicao comprar.

    Dois limites batem nisso:
      - alavancagem: posicao nunca passa de CAIXA * ALAV_MAX
      - minimo da corretora: a Binance recusa ordem abaixo de ~5 USDT
    """
    perda = CAIXA * RISCO_PCT / 100
    pos = perda / (risco_pct / 100)
    teto = CAIXA * ALAV_MAX
    cortou = pos > teto
    if cortou:
        pos = teto
        perda = pos * risco_pct / 100
    return dict(pos=pos, perda=perda, margem=pos / ALAV_MAX,
                alav=pos / CAIXA, cortou=cortou, minimo=pos < 5.0)


def msg_mao(risco_pct):
    m = mao(risco_pct)
    if m['minimo']:
        return ("\n<i>⚠️ posição ficaria abaixo do mínimo de 5 USDT "
                "da Binance — pula essa</i>")
    t = (f"\n<b>mão</b>  posição <code>{m['pos']:.2f}</code> USDT   "
         f"(margem <code>{m['margem']:.2f}</code> em {ALAV_MAX:.0f}x)\n"
         f"se o stop bater, perde <b>{m['perda']:.2f}</b> USDT")
    if m['cortou']:
        t += (f"\n<i>⚠️ stop apertado: a mão cheia passaria de "
              f"{ALAV_MAX:.0f}x, foi limitada. O risco caiu junto.</i>")
    return t


def msg_gatilho(sim, g):
    seta = "🟢" if g['lado'] == 'compra' else "🔴"
    return (
        f"{seta} <b>{sim.replace('USDT', '/USDT')}</b> — "
        f"<b>{g['lado'].upper()}</b>   <i>{faixa(sim)}</i>\n"
        f"vela de {CFG['tf'].upper()} fechada às "
        f"{quando(g['vela_ms'])} (Brasília)"
        + ("  <i>⚠️ a rodada da hora anterior falhou, este gatilho chegou "
           "atrasado</i>" if g.get('atraso') else "") + "\n\n"
        f"entrada  <code>{fmt(g['entrada'])}</code>\n"
        f"stop     <code>{fmt(g['stop'])}</code>   "
        f"risco <b>{g['risco_pct']:.2f}%</b>\n"
        f"alvo     <code>{fmt(g['alvo'])}</code>   "
        f"<b>R:R 1:{g['rr']:.2f}</b>\n"
        f"<i>liquidez a {g['liq_r']:.1f}R da entrada</i>\n"
        + msg_mao(g['risco_pct']) +
        f"\n\n<i>ordem limitada em {fmt(g['entrada'])}, válida ~4h. "
        f"A mercado o preço já correu e a vantagem some.</i>")


def msg_cenario(sim, c):
    t = (f"👀 <b>{sim.replace('USDT', '/USDT')}</b> — de olho "
         f"({c['lado']})   <i>{faixa(sim)}</i>\n"
         f"{c['nota']}\n\n"
         f"preço  <code>{fmt(c['preco'])}</code>\n"
         f"alvo   <code>{fmt(c['alvo'])}</code>")
    if c.get('teto') is None:
        return t
    # O stop ja esta travado no extremo da varredura. Entao existe um preco
    # limite de entrada acima (ou abaixo) do qual o R:R nao fecha mais.
    compra = c['lado'] == 'compra'
    ok = (c['preco'] <= c['teto']) if compra else (c['preco'] >= c['teto'])
    refs = (c['preco'], c['alvo'], c['imp']['ob_base'], c['imp']['ob_topo'])
    t += (f"\nstop ficaria em <code>{como(c['stop_hip'], *refs)}</code>   "
          f"<i>varredura {c['vol_varr']:.1f}x o volume</i>\n")
    if ok:
        t += (f"\n✅ no preço de agora o R:R fecha. Vira gatilho se uma vela "
              f"de reversão fechar {'acima' if compra else 'abaixo'} daqui, "
              f"em até 4 velas da varredura.")
    else:
        t += (f"\n⚠️ <b>só vira gatilho se voltar para "
              f"{como(c['teto'], *refs, baixo=compra)} ou "
              f"{'abaixo' if compra else 'acima'}</b> "
              f"(agora {como(c['preco'], *refs)}). "
              f"No preço de agora o R:R não fecha.")
    return t


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


def _cru(h, a, mv, imp, r, cfg):
    """Velas cruas do order block ate agora, para conferir no olho.

    Serve para separar 'o bot leu errado' de 'o preco fez isso mesmo'.
    """
    compra = imp['alta']
    base, topo = imp['ob_base'], imp['ob_topo']
    kv = r.get('varredura')
    ini = max(0, imp['ob'] - 2)
    diag(f"      ATR {fmt(a[imp['fim']])}  |  furo máximo permitido "
         f"{cfg['furo_max']:.1f} ATR = "
         f"{fmt(base - a[imp['fim']] * cfg['furo_max']) if compra else fmt(topo + a[imp['fim']] * cfg['furo_max'])}")
    diag(f"      {'vela':<12}{'abert':>11}{'máx':>11}{'mín':>11}"
         f"{'fech':>11}{'vol x méd':>11}   nota")
    for k in range(ini, len(h)):
        c = h[k]
        nota = []
        if k == imp['ob']:
            nota.append('ORDER BLOCK')
        if imp['ini'] <= k <= imp['fim']:
            nota.append('impulso')
        if kv is not None and k == kv:
            nota.append('>>> VARREDURA')
        furou = (c[3] <= base) if compra else (c[2] >= topo)
        if furou and k > imp['fim']:
            nota.append('furou o OB')
        vx = c[5] / mv[k] if mv[k] > 0 else 0
        diag(f"      {quando(c[0]):<12}{fmt(c[1]):>11}{fmt(c[2]):>11}"
             f"{fmt(c[3]):>11}{fmt(c[4]):>11}{vx:>10.1f}x   "
             + ' · '.join(nota))
    # qual seria o gatilho se a reversao viesse na vela de agora
    if kv is None:
        return
    ext = min(x[3] for x in h[kv:]) if compra else max(x[2] for x in h[kv:])
    ent = h[-1][4]
    stop = ext - a[-1] * cfg['stop_folga'] if compra else \
           ext + a[-1] * cfg['stop_folga']
    risco = abs(ent - stop)
    dist = (imp['topo'] - ent) if compra else (ent - imp['topo'])
    diag(f"      se a reversão viesse agora: entrada {fmt(ent)}  "
         f"stop {fmt(stop)}  alvo {fmt(imp['topo'])}")
    if risco > 0:
        diag(f"      → risco {risco / ent * 100:.2f}%   "
             f"R:R 1:{dist / risco:.2f}   "
             + ("PASSA" if dist / risco >= cfg['rr_min']
                else f"REPROVA (mínimo 1:{cfg['rr_min']:.2f})"))


def explicar(sim, velas=400):
    """Auditoria de um par: todo impulso achado e o destino de cada um.

    Serve para responder 'por que nao veio gatilho em X'. Usa exatamente a
    mesma funcao seguir() do bot, so que pedindo o motivo da recusa.
    """
    h = rev8.juntar(serie_1h(sim), 4)
    if not h:
        diag(f"{sim}: nao consegui o historico")
        return
    a, mv = atr(h, CFG['atr_periodo']), media_volume(h, CFG['vol_periodo'])
    diag(f"{sim}: {len(h)} velas de H4, de {quando(h[0][0])} "
         f"a {quando(h[-1][0])} (Brasília)")
    diag(f"filtros: R:R>={CFG['rr_min']}  volume da varredura>="
         f"{CFG['vol_varr_min']}x  piscina<={CFG['liq_max_r']}R  "
         f"gatilho ate {CFG['max_espera_gatilho']} velas depois\n")
    imps = achar_impulsos(h, a, mv, CFG)
    diag(f"{len(imps)} impulsos encontrados\n")
    for i, imp in enumerate(imps, 1):
        lado = 'compra' if imp['alta'] else 'venda'
        diag(f"{i:>2}. impulso de {'alta' if imp['alta'] else 'baixa'} "
             f"({lado}) — velas {quando(h[imp['ini']][0])} a "
             f"{quando(h[imp['fim']][0])}")
        diag(f"    order block {fmt(imp['ob_base'])}–{fmt(imp['ob_topo'])}"
             f"   alvo {fmt(imp['topo'])}")
        tr = []
        r = seguir(h, a, imp, CFG, mv, tr)
        if r is None:
            diag(f"    ✗ {tr[0] if tr else 'sem motivo registrado'}\n")
        elif r['fase'] == 'cenario':
            diag(f"    ⏳ radar: {r['nota']}"
                 + (f" (varredura com {r['vol_varr']:.2f}x o volume médio)"
                    if r['vol_varr'] else ""))
            _cru(h, a, mv, imp, r, CFG)
            diag("")
        else:
            diag(f"    ✓ GATILHO {r['lado']} em {quando(r['vela_ms'])}  "
                 f"entrada {fmt(r['entrada'])}  stop {fmt(r['stop'])}  "
                 f"alvo {fmt(r['alvo'])}  R:R 1:{r['rr']:.2f}  "
                 f"risco {r['risco_pct']:.2f}%  volume {r['vol_varr']:.2f}x  "
                 f"piscina {r['liq_r']:.1f}R")
            diag("    " + depois(h, r) + "\n")


def depois(h, r):
    """O que aconteceu desde o gatilho: bateu stop, alvo ou segue aberto."""
    compra = r['lado'] == 'compra'
    ent, stop, alvo = r['entrada'], r['stop'], r['alvo']
    risco = abs(ent - stop)
    pior = ent
    for k in range(r['idx'] + 1, len(h)):
        hi, lo = h[k][2], h[k][3]
        pior = min(pior, lo) if compra else max(pior, hi)
        if (lo <= stop) if compra else (hi >= stop):
            return f"→ bateu o STOP em {quando(h[k][0])} ({k - r['idx']}h depois)"
        if (hi >= alvo) if compra else (lo <= alvo):
            return (f"→ bateu o ALVO em {quando(h[k][0])} "
                    f"({k - r['idx']}h depois), +{r['rr']:.2f}R")
    agora = h[-1][4]
    pl = (agora - ent) / risco * (1 if compra else -1)
    folga = (pior - stop) / risco * (1 if compra else -1)
    return (f"→ AINDA ABERTO. Agora {fmt(agora)} = {pl:+.2f}R. "
            f"Chegou a {fmt(pior)}, a {folga:.2f}R do stop "
            f"({abs(pior - stop) / stop * 100:.2f}% de folga)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--top', type=int, default=150,
                    help='pares da varredura; era 50 até 14/11/2026')
    ap.add_argument('--fixo', action='store_true',
                    help='usar a lista fixa UNIVERSO em vez do volume vivo')
    ap.add_argument('--dinamico', action='store_true',
                    help='(sem efeito: o volume vivo agora é o padrão)')
    ap.add_argument('--rr-min', type=float, default=CFG['rr_min'])
    ap.add_argument('--vol-min', type=float, default=CFG['vol_varr_min'],
                    help='volume minimo da vela que varre, x a media de 20')
    ap.add_argument('--liq-max-r', type=float, default=CFG['liq_max_r'],
                    help='distancia maxima da piscina de liquidez, em R')
    ap.add_argument('--so-gatilho', action='store_true')
    ap.add_argument('--teste', action='store_true')
    ap.add_argument('--ping', action='store_true')
    ap.add_argument('--novos', action='store_true',
                    help='com --ping: so os pares que entraram em 01/11/2026')
    ap.add_argument('--exemplos', type=int, default=2,
                    help='quantos gatilhos do historico mandar no ping')
    ap.add_argument('--caixa', type=float, default=CAIXA,
                    help='banca em USDT, para calcular a mao')
    ap.add_argument('--risco-pct', type=float, default=RISCO_PCT,
                    help='quanto da banca morre num stop, em %%')
    ap.add_argument('--alav', type=float, default=ALAV_MAX,
                    help='alavancagem maxima')
    ap.add_argument('--explicar', default='',
                    help='par para auditar: lista todo impulso achado e '
                         'onde cada um foi recusado')
    ap.add_argument('--falha5-ping', action='store_true',
                    help='manda os ultimos gatilhos do rompimento falso, '
                         'so para ver o formato da mensagem')
    ap.add_argument('--falha5-exemplos', type=int, default=2,
                    help='quantos exemplos mandar com --falha5-ping')
    ap.add_argument('--sem-falha5', action='store_true',
                    help='desliga o quarto alerta (rompimento falso em H1)')
    ap.add_argument('--falha5-top', type=int, default=150,
                    help='quantas moedas o rompimento falso escaneia')
    ap.add_argument('--sem-reversao8', action='store_true',
                    help='não roda o terceiro alerta (reversão de 8h, '
                         'em teste)')
    ap.add_argument('--rev-top', type=int, default=150,
                    help='quantas moedas a reversão escaneia')
    ap.add_argument('--rev8-ping', action='store_true',
                    help='manda os gatilhos mais recentes da reversão de 8h '
                         'só para ver o formato da mensagem')
    ap.add_argument('--rev8-exemplos', type=int, default=2,
                    help='quantos gatilhos da reversão mandar no --rev8-ping')
    ap.add_argument('--velas', type=int, default=400,
                    help='quantas velas de H1 puxar no --explicar')
    a = ap.parse_args()
    CFG['rr_min'] = a.rr_min
    CFG['vol_varr_min'] = a.vol_min
    CFG['liq_max_r'] = a.liq_max_r
    globals()['CAIXA'] = a.caixa
    globals()['RISCO_PCT'] = a.risco_pct
    globals()['ALAV_MAX'] = a.alav

    open(DIAG, "w").close()
    diag(f"início {datetime.now(BRT):%d/%m %H:%M} BRT")

    if a.explicar:
        explicar(a.explicar.strip().upper(), a.velas)
        return

    if a.rev8_ping:
        # Reenvia os gatilhos mais recentes da reversao de 8h, so para ver
        # o formato. Nao e sinal de agora.
        enviar("🧪 <b>amostra do terceiro alerta</b> — reversão de 8h\n"
               "<i>gatilhos do histórico recente, reenviados só para você "
               "ver o formato. Não é sinal de agora.</i>")
        amostras = []
        fila = fila_viva(a.rev_top)
        diag(f"amostra da reversão de 8h em {len(fila)} pares")
        for sim in fila:
            v = serie_1h(sim)
            if len(v) < 500:
                continue
            for g in rev8.exemplos(v):
                amostras.append((g['vela_ms'], sim, g))
        amostras.sort(reverse=True, key=lambda x: x[0])
        diag(f"achou {len(amostras)} gatilho(s) no histórico de 54 dias")
        if not amostras:
            enviar("nenhum gatilho da reversão de 8h nos últimos 54 dias")
        for _, sim, g in amostras[:a.rev8_exemplos]:
            enviar(rev8.msg(sim, g, quando, fmt, msg_mao))
            diag(f"amostra enviada: {sim} {quando(g['vela_ms'])} "
                 f"R:R 1:{g['rr']:.2f}")
        return

    if a.falha5_ping:
        # Reenvia os gatilhos mais recentes do rompimento falso, com o
        # aviso de radar antes de cada um, so para ver o formato.
        enviar(f"🧪 <b>amostra do quarto alerta</b> — rompimento falso em "
               f"H1\n<i>gatilhos do histórico recente, reenviados só para "
               f"você ver o formato. Não é sinal de agora.</i>")
        amostras = []
        fila = fila_viva(a.falha5_top)
        diag(f"amostra do rompimento falso em {len(fila)} pares")
        for sim in fila:
            v = serie_1h(sim)
            if len(v) < 500:
                continue
            for g, c in falha5.exemplos(v):
                amostras.append((g['vela_ms'], sim, g, c))
        amostras.sort(reverse=True, key=lambda x: x[0])
        diag(f"achou {len(amostras)} gatilho(s) no histórico de 54 dias")
        if not amostras:
            enviar("nenhum gatilho do rompimento falso nos últimos 54 dias "
                   "— o último foi em 12/10, há mais de um mês")
        for _, sim, g, c in amostras[:a.falha5_exemplos]:
            if c:
                enviar(falha5.msg_contexto(sim, c, quando, fmt, msg_mao))
            enviar(falha5.msg(sim, g, quando, fmt, msg_mao))
            diag(f"amostra enviada: {sim} {quando(g['vela_ms'])} "
                 f"R:R 1:{g['rr']:.2f}")
        return

    if a.ping:
        enviar(f"✅ bot da varredura vivo — {datetime.now(BRT):%d/%m %H:%M}")
        # manda tambem o gatilho mais recente do historico, so para voce ver
        # o formato da mensagem e para eu confirmar que a imagem passa.
        achados = []
        fila_ping = NOVOS if a.novos else (UNIVERSO[:a.top] if a.fixo
                                           else fila_viva(a.top))
        diag(f"ping em {len(fila_ping)} pares"
             + (" (so os que entraram agora)" if a.novos else ""))
        for sim in fila_ping:
            v = serie_1h(sim)
            if len(v) < 500:
                continue
            h = rev8.juntar(v, 4)
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
    series = {}          # o acompanhamento reusa estas velas, sem rebaixar
    acomps = acomp.ler()

    # 14/11/2026 -- de 50 para 150 pares, e o H4 montado a partir do H1.
    # Medido no universo rolante de 7 anos, a config exata do bot:
    #    50 moedas  20 op  40,0% de acerto  1:2,97  +27,70/op  z/LOTE +0,62
    #   100 moedas  47 op  40,4%            1:3,26  +54,00/op  z/LOTE +1,75
    #   150 moedas  56 op  42,9%            1:3,25  +61,30/op  z/LOTE +1,93
    #   300 moedas  80 op  42,5%            1:3,38  +66,00/op  z/LOTE +2,37
    # Nas 50 o maior lote valia 108% do lucro: TUDO vinha de um punhado de
    # operacoes e o resto era negativo (2 anos positivos de 5). A partir de
    # 100 o setup passa a provar algo: 5 anos positivos de 6, concentracao
    # de 23-35%. A faixa 51-300, que o bot nao via, paga +78,70/op contra
    # +27,70 da faixa que ele via. Ver analise/setup1_universo.py.
    fila = UNIVERSO[:a.top] if a.fixo else fila_viva(a.top)
    for sim in fila:
        if len(usados) >= a.top:
            break
        v = serie_1h(sim)
        if len(v) < 500:
            continue
        h = rev8.juntar(v, 4)
        if len(h) < 150:
            continue
        if not negocia_sempre(h):
            descartados.append(sim)
            continue
        usados.append(sim)
        series[sim] = h
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
            # Aceita a vela de reversao recem-fechada e a anterior. Antes era
            # so a ultima: quando o Actions pulava uma hora agendada (3 de 23
            # no dia 04/11), aquele gatilho sumia para sempre. O estado em
            # varredura_enviados.json impede mandar duas vezes, e a ordem e
            # limitada valida ~4h, entao uma hora de atraso ainda serve.
            atraso = len(h) - 1 - achou['idx']
            if atraso > 1:
                diag(f"{sim}: gatilho antigo ({atraso} velas atrás)")
                continue
            achou['nucleo'] = sim in NUCLEO
            achou['atraso'] = atraso
            gatilhos.append((sim, achou, h))
            linhas.append(f"GATILHO [{'nucleo' if sim in NUCLEO else 'extra'}] "
                          f"{sim} {achou['lado']} "
                          f"R:R 1:{achou['rr']:.2f} risco {achou['risco_pct']:.2f}%"
                          + ("  (vela anterior)" if atraso else ""))
            diag(f"GATILHO {sim} {achou['lado']} "
                 f"vela {quando(achou['vela_ms'])} "
                 f"entrada {fmt(achou['entrada'])} "
                 f"R:R 1:{achou['rr']:.2f}"
                 + ("  [recuperado da vela anterior]" if atraso else ""))
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
    else:
        for sim, g, h in novos:
            manda_com_grafico(sim, g, h, msg_gatilho(sim, g))

        if not a.so_gatilho:
            for sim, c, h in cenarios[:MAX_CENARIOS]:
                chave = f"cen-{sim}-{c['vela_ms']}"
                if chave in vistos:
                    continue
                vistos.add(chave)
                manda_com_grafico(sim, c, h, msg_cenario(sim, c))
    # --- desfecho dos avisos antigos ---------------------------------
    # Os pares com aviso aberto que nao caíram na varredura desta rodada
    # ainda precisam ser revisados, entao busca so o que faltar.
    pendentes = {r['sim'] for r in acomps.values()
                 if r.get('status') == 'aberto'} - set(series)
    for sim in sorted(pendentes):
        v = serie_1h(sim)
        if len(v) < 500:
            diag(f"{sim}: nao revisei o aviso aberto (sem histórico)")
            continue
        series[sim] = rev8.juntar(v, 4)

    for sim, g, _ in novos:
        acomp.registrar_gatilho(acomps, sim, g)
    for sim, c, _ in cenarios:
        acomp.registrar_cenario(acomps, sim, c)

    # --- stop movel: 15m so dos pares com operacao aberta -------------
    # Uma busca por par aberto, uma vez por rodada. Nao muda a cadencia do
    # bot: medido em 22 meses, checar de hora em hora da exatamente o mesmo
    # resultado que checar a cada 15 minutos.
    abertos = {r['sim'] for r in acomps.values()
               if r.get('tipo') == 'gatilho' and r.get('status') == 'aberto'}
    s15 = {}
    for sim in sorted(abertos):
        try:
            v = buscar(sim, '15m', 300)
            if v:
                s15[sim] = v
        except Exception as e:
            diag(f"{sim}: não busquei o 15m para o stop móvel ({e})")
    if s15:
        diag("stop móvel — o que o bot está vendo:")
        for L in acomp.diagnostico_stops(acomps, s15):
            diag(L)
        for m in acomp.mover_stops(acomps, s15):
            if a.teste:
                print(m, "\n")
            else:
                enviar(m)
            diag("stop móvel: " + m.replace("\n", " | ")[:140])

    # --- segundo alerta: REVERSAO de 8h, entrada no H1 (EM TESTE) ----
    # O preco cai por uma semana, UMA vela de 8h rompe o ultimo topo, o
    # preco volta e ENCOSTA no order block sem afundar nele, e uma vela
    # de 1h confirma com volume. Estado proprio, em reversao8_estado.json
    # e historico_reversao8.csv.
    #
    # Busca 1h com limite 1300 (54 dias) e monta as velas de 8h a partir
    # dai: uma requisicao por par em vez de duas, e a mesma serie serve
    # para achar o gatilho de uma hora.
    if not a.sem_reversao8:
        try:
            rev_d = rev8.ler()
            fila_rev = fila_viva(a.rev_top)
            abertos_rev = {r['sim'] for r in rev_d.values()
                           if r.get('status') == 'aberto'}
            s8r, achados_r, vistos_r = {}, [], 0
            encostos_r = []
            for sim in sorted(set(fila_rev) | abertos_rev):
                v = serie_1h(sim)
                if len(v) < 500:
                    continue
                vistos_r += 1
                h8r = rev8.juntar(v, 8)
                if h8r:
                    s8r[sim] = h8r
                if sim not in fila_rev:
                    continue
                g = rev8.achar(v)
                if g:
                    achados_r.append((sim, g))
                    diag(f"REVERSÃO 8h {sim} {g['lado']} "
                         f"vela {quando(g['vela_ms'])} "
                         f"entrada {fmt(g['entrada'])} "
                         f"R:R 1:{g['rr']:.2f} "
                         f"queda {g['queda']:.1f} vol "
                         f"gatilho {g['vol_gat']:.1f}x")
                    continue
                # sem gatilho: o preço pode estar encostado, esperando.
                # Esse é o aviso que dá tempo de abrir o gráfico antes.
                enc = rev8.achar_encosto(v)
                if enc:
                    encostos_r.append((sim, enc))
                    diag(f"ENCOSTO 8h {sim} {enc['lado']} "
                         f"tocou {quando(enc['toque_ms'])} "
                         f"há {enc['horas']}h, faltam {enc['falta']}h "
                         f"· preço {fmt(enc['ref'])} "
                         f"stop {fmt(enc['stop'])} "
                         f"R:R 1:{enc['rr']:.2f} "
                         f"afundou {enc['fundura']*100:.0f}% até o meio")
            diag(f"reversão 8h: {vistos_r} pares olhados, "
                 f"{len(achados_r)} gatilho(s), "
                 f"{len(encostos_r)} encosto(s) esperando")
            for sim, g in achados_r:
                if not rev8.registrar(rev_d, sim, g):
                    continue
                texto = rev8.msg(sim, g, quando, fmt, msg_mao)
                if a.teste:
                    print(texto, "\n")
                else:
                    enviar(texto)
            for sim, enc in encostos_r:
                if not rev8.registrar_encosto(rev_d, sim, enc):
                    continue
                texto = rev8.msg_encosto(sim, enc, quando, fmt, msg_mao)
                if a.teste:
                    print(texto, "\n")
                else:
                    enviar(texto)
            for m in rev8.revisar(rev_d, s8r, fmt, quando):
                if a.teste:
                    print(m, "\n")
                else:
                    enviar(m)
                diag("reversão 8h, desfecho: " + m.replace("\n", " | ")[:140])
            if not a.teste:
                rev8.gravar(rev_d)
            diag(rev8.placar(rev_d).replace('<b>', '').replace('</b>', ''))
        except Exception as e:
            diag(f"reversão 8h falhou, o resto segue: {e}")

    # --- quarto alerta: ROMPIMENTO FALSO em H1 (EM TESTE) -----------
    # Faixa de 60 velas em cima de um topo JA ROMPIDO, o preco rompe a
    # faixa para o lado contrario ao contexto com volume, vem a vela de
    # forca contraria (o aviso), e a FALHA do topo dispara a entrada.
    # Alvo na piscina de liquidez alem de toda a faixa.
    #
    # Reaproveita a mesma serie de 1h que a reversao de 8h ja baixou:
    # nenhuma requisicao a mais. Estado proprio, em falha5_estado.json.
    if not a.sem_falha5:
        try:
            f5_d = falha5.ler()
            fila_f5 = fila_viva(a.falha5_top)
            abertos_f5 = {r['sim'] for r in f5_d.values()
                          if r.get('status') == 'aberto'}
            s_f5, achados_f5, ctx_f5, vistos_f5 = {}, [], [], 0
            for sim in sorted(set(fila_f5) | abertos_f5):
                v = serie_1h(sim)
                if len(v) < 500:
                    continue
                vistos_f5 += 1
                s_f5[sim] = v
                if sim not in fila_f5:
                    continue
                g = falha5.achar(v)
                if g:
                    achados_f5.append((sim, g))
                    diag(f"ROMPIMENTO FALSO {sim} {g['lado']} "
                         f"vela {quando(g['vela_ms'])} "
                         f"entrada {fmt(g['entrada'])} "
                         f"R:R 1:{g['rr']:.2f} "
                         f"ida {g['excur']:.2f}x volume {g['vol_x']:.1f}x")
                    continue
                c = falha5.achar_contexto(v)
                if c:
                    ctx_f5.append((sim, c))
                    diag(f"FORÇA CONTRÁRIA {sim} {c['lado']} "
                         f"força {quando(c['forca_ms'])} "
                         f"há {c['horas']}h, faltam {c['falta']} velas "
                         f"· gatilho abaixo de {fmt(c['forca_lim'])} "
                         f"· R:R 1:{c['rr']:.2f}")
            diag(f"rompimento falso: {vistos_f5} pares olhados, "
                 f"{len(achados_f5)} gatilho(s), "
                 f"{len(ctx_f5)} força(s) esperando a falha")
            for sim, g in achados_f5:
                if not falha5.registrar(f5_d, sim, g):
                    continue
                texto = falha5.msg(sim, g, quando, fmt, msg_mao)
                if a.teste:
                    print(texto, "\n")
                else:
                    enviar(texto)
            for sim, c in ctx_f5:
                if not falha5.registrar_contexto(f5_d, sim, c):
                    continue
                texto = falha5.msg_contexto(sim, c, quando, fmt, msg_mao)
                if a.teste:
                    print(texto, "\n")
                else:
                    enviar(texto)
            for m in falha5.revisar(f5_d, s_f5, fmt, quando):
                if a.teste:
                    print(m, "\n")
                else:
                    enviar(m)
                diag("rompimento falso, desfecho: "
                     + m.replace("\n", " | ")[:140])
            if not a.teste:
                falha5.gravar(f5_d)
            diag(falha5.placar(f5_d).replace('<b>', '').replace('</b>', ''))
        except Exception as e:
            diag(f"rompimento falso falhou, o resto segue: {e}")

    desfechos = acomp.revisar(acomps, series, CFG, seguir, achar_impulsos,
                              atr, media_volume)
    for m in desfechos:
        if a.teste:
            print(m, "\n")
        else:
            enviar(m)
        diag("desfecho: " + m.replace("\n", " | ")[:140])
    if desfechos and not a.teste:
        enviar(acomp.placar(acomps))
    if a.teste:
        print(acomp.placar(acomps))
        return
    acomp.gravar(acomps)

    salvar(vistos)
    diag(f"enviados {len(novos)} gatilhos, {len(desfechos)} desfechos")
    diag(acomp.placar(acomps).replace('<b>', '').replace('</b>', ''))
    mot = acomp.motivos(acomps)
    if mot:
        diag("por que os cenários morreram:\n" + mot)


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        print("=== ERRO ===")
        traceback.print_exc()
        raise
