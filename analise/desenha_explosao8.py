"""Desenha os ultimos gatilhos da explosao de 8h, com dado fresco.

Roda no Actions (o container de analise nao alcanca a Binance), grava os
PNG em imagens_explosao8/ e o workflow commita a pasta.

Uso:  python3 desenha_explosao8.py [--quantos 3] [--top 50]
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import explosao8 as exp8

BRT = timezone(timedelta(hours=-3))
BASE_URL = "https://data-api.binance.vision/api/v3"
PASTA = "imagens_explosao8"


def buscar(simbolo, interval='8h', limite=250):
    r = requests.get(f"{BASE_URL}/klines",
                     params={'symbol': simbolo, 'interval': interval,
                             'limit': limite}, timeout=25)
    r.raise_for_status()
    agora = int(time.time() * 1000)
    return [[int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]),
             float(c[5])] for c in r.json() if int(c[6]) < agora]


def universo(top):
    t = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), 'bot_varredura.py')).read()
    ns = {}
    exec(t[t.index('UNIVERSO = ['):t.index('NUCLEO = set(UNIVERSO[:20])')], ns)
    return list(ns['UNIVERSO'])[:top]


def desfecho(h, g):
    """O que aconteceu depois da entrada, ate hoje."""
    compra = g['lado'] == 'compra'
    for m in range(g['idx']+1, min(g['idx']+1+exp8.MAX_BARRAS, len(h))):
        hi, lo = h[m][2], h[m][3]
        if compra:
            if lo <= g['stop']: return 'stop', g['stop'], m
            if hi >= g['alvo']: return 'alvo', g['alvo'], m
        else:
            if hi >= g['stop']: return 'stop', g['stop'], m
            if lo <= g['alvo']: return 'alvo', g['alvo'], m
    return 'aberta', h[-1][4], len(h)-1


def casas(*v):
    n = 0
    for r in v:
        t = f"{r:.10f}".rstrip('0')
        n = max(n, len(t.split('.')[1]) if '.' in t else 0)
    return max(2, min(n, 8))


def desenhar(sim, h, g, caminho):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fim, preco, m_fim = desfecho(h, g)
    a0 = max(0, g['exp_idx'] - 10)
    a1 = min(len(h), max(m_fim, g['idx']) + 10)
    vel = h[a0:a1]
    d = lambda i: i - a0
    c = casas(g['entrada'], g['stop'], g['alvo'])

    fig, ax = plt.subplots(figsize=(13, 7.2), facecolor='#13161b')
    ax.set_facecolor('#13161b')
    for n, v in enumerate(vel):
        o, hi, lo, cl = v[1], v[2], v[3], v[4]
        cor = '#26a69a' if cl >= o else '#ef5350'
        ax.plot([n, n], [lo, hi], color=cor, linewidth=1.0, zorder=2)
        ax.add_patch(Rectangle((n-0.34, min(o, cl)), 0.68,
                               max(abs(cl-o), (hi-lo)*0.003),
                               facecolor=cor, edgecolor=cor, zorder=3))

    # a vela da explosao e o order block
    ax.axvspan(d(g['exp_idx'])-0.5, d(g['exp_idx'])+0.5,
               color='#ffd54f', alpha=.16, zorder=1)
    ax.annotate('a explosão', (d(g['exp_idx']), h[g['exp_idx']][2]),
                color='#ffd54f', fontsize=11, ha='center',
                xytext=(0, 12), textcoords='offset points')
    ob = g.get('ob_idx')
    if ob is not None:
        ax.axvspan(d(ob)-0.5, d(ob)+0.5, color='#42a5f5', alpha=.16, zorder=1)
        ax.annotate('order block', (d(ob), h[ob][3]), color='#42a5f5',
                    fontsize=10, ha='center', xytext=(0, -22),
                    textcoords='offset points')
    ax.axvspan(d(g['idx'])-0.5, d(g['idx'])+0.5, color='#ffffff', alpha=.10,
               zorder=1)
    ax.annotate('gatilho', (d(g['idx']), h[g['idx']][3]), color='#ffffff',
                fontsize=10, ha='center', xytext=(0, -22),
                textcoords='offset points')

    for y, cor, rot in (
            (g['entrada'], '#ffffff', f"entrada  {g['entrada']:,.{c}f}"),
            (g['stop'], '#ef5350', f"stop  {g['stop']:,.{c}f}   "
                                   f"({g['risco_pct']:.2f}%)"),
            (g['alvo'], '#26a69a', f"alvo  {g['alvo']:,.{c}f}"),
            (g['topo'], '#78909c', f"topo da explosão  {g['topo']:,.{c}f}")):
        ax.axhline(y, color=cor, linewidth=1.1, alpha=.9,
                   linestyle='-' if cor != '#78909c' else '--', zorder=4)
        ax.annotate(rot, (len(vel)-1, y), color=cor, fontsize=9,
                    xytext=(8, 0), textcoords='offset points', va='center')

    cara = {'alvo': '✓ bateu o alvo', 'stop': '✗ bateu o stop',
            'aberta': '• ainda aberta'}[fim]
    q = datetime.fromtimestamp(g['vela_ms']/1000, BRT)
    ax.set_title(
        f"{sim.replace('USDT','')}  ·  8h  ·  gatilho em "
        f"{q:%d/%m/%Y %H:%M} (Brasília)  ·  {g['lado']}  ·  "
        f"R:R 1:{g['rr']:.2f}  ·  RSI {g['rsi']:.0f}  ·  {cara}",
        color='#e8eaed', fontsize=12, pad=14)
    ax.tick_params(colors='#6b7280', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#2a2f38')
    ax.grid(color='#1e232b', linewidth=.6)
    ax.set_xlim(-1, len(vel) + 16)
    fig.tight_layout()
    fig.savefig(caminho, dpi=115, facecolor='#13161b')
    plt.close(fig)
    return fim, q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--quantos', type=int, default=3)
    ap.add_argument('--top', type=int, default=50)
    a = ap.parse_args()
    os.makedirs(PASTA, exist_ok=True)
    for f in os.listdir(PASTA):
        if f.endswith('.png'):
            os.remove(os.path.join(PASTA, f))

    achados = []
    for sim in universo(a.top):
        try:
            h = buscar(sim)
        except Exception as e:
            print(f"{sim}: {e}", flush=True)
            continue
        if len(h) < 70:
            continue
        for g in exp8.historico(h):
            # guarda o indice do order block para desenhar
            j = g['exp_idx'] - 1
            alta = g['lado'] == 'compra'
            while j >= max(0, g['exp_idx'] - exp8.CFG8['ob_busca']):
                if (h[j][4] > h[j][1]) != alta:
                    g['ob_idx'] = j
                    break
                j -= 1
            achados.append((g['vela_ms'], sim, g, h))
    achados.sort(reverse=True, key=lambda x: x[0])
    print(f"{len(achados)} gatilhos no histórico de 8h dos "
          f"{a.top} pares (~{len(achados)/ (250*8/24/30):.1f} por mês)",
          flush=True)
    for n, (_, sim, g, h) in enumerate(achados[:a.quantos], 1):
        cam = os.path.join(PASTA, f"{n:02d}_{sim}.png")
        fim, q = desenhar(sim, h, g, cam)
        print(f"  {cam}  {sim} {q:%d/%m/%Y %H:%M} {g['lado']} "
              f"entrada {g['entrada']:.8g} stop {g['stop']:.8g} "
              f"alvo {g['alvo']:.8g} R:R 1:{g['rr']:.2f} "
              f"RSI {g['rsi']:.0f} estendeu {g['estendeu']:.2f} → {fim}",
              flush=True)


if __name__ == '__main__':
    main()
