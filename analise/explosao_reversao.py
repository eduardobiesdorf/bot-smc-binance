"""Explosao de REVERSAO: o preco vem caindo e uma vela unica rompe o
ultimo topo.

Diferente do que esta no ar. La a vela tem de fechar acima da maxima
das ultimas 20 velas -- num mercado caindo isso quase nunca acontece,
entao o padrao so arma em continuacao de alta.

Aqui:
  tendencia  o preco vinha CAINDO: o fundo da vela da explosao esta
             pelo menos X volatilidades abaixo da maxima das ultimas N
  ultimo topo  o pivo de alta mais recente antes da explosao (2 velas
             mais baixas de cada lado), nao a maxima de 20 velas
  explosao   UMA vela que fecha acima desse pivo, >= 2,5x a
             volatilidade, corpo >= 50%, volume >= 1,5x a media
  resto      igual: order block, encosto, gatilho, alvo no topo da
             vela mais 90% do tamanho dela

A versao de venda e espelhada: o preco vinha subindo e uma vela unica
rompe o ultimo fundo.

Uso:  python3 explosao_reversao.py <pasta> [--desenhar <dir>]
"""
import argparse
import glob
import itertools
import os
import random
import statistics
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explosao8 as exp8
from explosao import ler, juntar, curva, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))

BASE = dict(sigma=2.5, vol=1.5, ob_busca=6, espera=30, gatilho_max=4,
            furo_max=1.0, rr_min=1.2, stop_folga=0.10, rsi_min=0.0,
            est_min=0.5, alvo_proj=0.9,
            pivo=2,           # velas de cada lado que definem o ultimo topo
            busca_topo=30,    # ate onde procurar esse topo
            tend_jan=20,      # janela para medir a tendencia anterior
            tend_atr=2.0,     # queda LIQUIDA, em volatilidades
            perto_do_fundo=0.35)  # a explosao sai do terco de baixo


def ultimo_topo(h, i, alta, cfg):
    """O pivo mais recente antes de i. Numa queda e um topo mais baixo."""
    k = cfg['pivo']
    for c in range(i - k - 1, max(0, i - cfg['busca_topo']) - 1, -1):
        if c - k < 0 or c + k >= i:
            continue
        if alta:
            ref = h[c][2]
            if all(h[x][2] <= ref for x in range(c-k, c+k+1) if x != c):
                return ref, c
        else:
            ref = h[c][3]
            if all(h[x][3] >= ref for x in range(c-k, c+k+1) if x != c):
                return ref, c
    return None, None


def historico(h, cfg):
    if len(h) < 80:
        return []
    a, mv, rs = exp8.atr(h, 14), exp8.medvol(h, 20), exp8.rsi(h, 14)
    fora, i = [], max(cfg['tend_jan'], cfg['busca_topo'], 21) + 1
    while i < len(h) - 2:
        o, hi, lo, cl, vol = h[i][1], h[i][2], h[i][3], h[i][4], h[i][5]
        rng = hi - lo
        if rng <= 0 or a[i-1] <= 0 or mv[i-1] <= 0 \
                or rng < cfg['sigma']*a[i-1] or abs(cl-o)/rng < 0.5 \
                or vol < cfg['vol']*mv[i-1]:
            i += 1; continue
        alta = cl > o
        # 1) o preco vinha na direcao CONTRARIA, de verdade.
        # Comparar com a maxima de 30 velas atras era frouxo: num
        # mercado picotado o preco podia estar SUBINDO nas velas antes
        # da explosao e ainda assim passar. Agora exige queda LIQUIDA do
        # fechamento de N velas atras ate a vespera da explosao, e que a
        # explosao saia da parte de baixo da faixa.
        jan = h[i-cfg['tend_jan']:i]
        queda = (h[i-cfg['tend_jan']][4] - h[i-1][4]) / a[i-1] if alta else \
                (h[i-1][4] - h[i-cfg['tend_jan']][4]) / a[i-1]
        if queda < cfg['tend_atr']:
            i += 1; continue
        if cfg.get('perto_do_fundo'):
            tmax = max(x[2] for x in jan); tmin = min(x[3] for x in jan)
            if tmax > tmin:
                pos_ = (lo - tmin)/(tmax - tmin) if alta else \
                       (tmax - hi)/(tmax - tmin)
                if pos_ > cfg['perto_do_fundo']:
                    i += 1; continue
        # 2) rompeu o ULTIMO topo (ou fundo), nao a maxima de 20
        topo_ant, i_topo = ultimo_topo(h, i, alta, cfg)
        if topo_ant is None:
            i += 1; continue
        if (cl <= topo_ant) if alta else (cl >= topo_ant):
            i += 1; continue
        if cfg['rsi_min'] > 0:
            r = rs[i] if alta else 100 - rs[i]
            if r < cfg['rsi_min']:
                i += 1; continue
        g = exp8.seguir(h, a, i, alta, dict(exp8.CFG8, **{
            k: cfg[k] for k in ('ob_busca', 'espera', 'gatilho_max',
                                'furo_max', 'rr_min', 'stop_folga',
                                'alvo_proj')}))
        if not g:
            i += 1; continue
        est = abs(g['topo'] - h[i][4]) / a[i] if a[i] else 0.0
        if est < cfg['est_min']:
            i += 1; continue
        g['estendeu'] = est
        g['rsi'] = rs[i] if alta else 100 - rs[i]
        g['queda'] = queda
        g['topo_ant'] = topo_ant
        g['i_topo'] = i_topo
        fora.append(g)
        i = g['idx'] + 1
    return fora


def resolver(h, g):
    compra = g['lado'] == 'compra'
    for m in range(g['idx']+1, min(g['idx']+1+exp8.MAX_BARRAS, len(h))):
        hi, lo = h[m][2], h[m][3]
        if compra:
            if lo <= g['stop']: return 'stop', g['stop'], m
            if hi >= g['alvo']: return 'alvo', g['alvo'], m
        else:
            if hi >= g['stop']: return 'stop', g['stop'], m
            if lo <= g['alvo']: return 'alvo', g['alvo'], m
    return None, None, None


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, larg=30):
    if not sel:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in sel]
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    p25 = [o['liq'] for o in sel if o['ano'] == 2025]
    p26 = [o['liq'] for o in sel if o['ano'] == 2026]
    z = ''
    if len(v) >= 25:
        random.seed(3)
        nu = [statistics.mean([x if random.random() < .5 else -x for x in v])
              for _ in range(300)]
        z = (f"{(statistics.mean(v)-statistics.mean(nu))/(statistics.pstdev(nu) or 1e-9):+.2f}")
    print(f"{rot:<{larg}}{len(v):>5}{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(o['risco_pct'] for o in sel):>7.1f}%"
          f"{statistics.mean(v):>+10.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{(statistics.mean(p25) if p25 else 0):>+9.1f}{len(p25):>4}"
          f"{(statistics.mean(p26) if p26 else 0):>+9.1f}{len(p26):>4}{z:>8}")


def cab(larg=30):
    print(f"{'':<{larg}}{'n':>5}{'acerto':>9}{'stop':>7}{'méd/op':>10}"
          f"{'total':>9}{'rb':>8}{'seq':>5}{'2025':>9}{'n25':>4}"
          f"{'2026':>9}{'n26':>4}{'z':>8}")


def desenhar(sim, h, g, caminho):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fim, preco, m = resolver(h, g)
    a0 = max(0, g['exp_idx'] - 34)
    a1 = min(len(h), (m or g['idx']) + 10)
    vel = h[a0:a1]
    d = lambda i: i - a0
    t = f"{g['entrada']:.10f}".rstrip('0')
    c = max(2, min(len(t.split('.')[1]) if '.' in t else 0, 8))
    fig, ax = plt.subplots(figsize=(13.5, 7.2), facecolor='#13161b')
    ax.set_facecolor('#13161b')
    for n, v in enumerate(vel):
        o, hi, lo, cl = v[1], v[2], v[3], v[4]
        cor = '#26a69a' if cl >= o else '#ef5350'
        ax.plot([n, n], [lo, hi], color=cor, linewidth=1.0, zorder=2)
        ax.add_patch(Rectangle((n-0.34, min(o, cl)), 0.68,
                               max(abs(cl-o), (hi-lo)*0.003),
                               facecolor=cor, edgecolor=cor, zorder=3))
    ax.axvspan(d(g['exp_idx'])-0.5, d(g['exp_idx'])+0.5, color='#ffd54f',
               alpha=.18, zorder=1)
    ax.annotate('a explosão', (d(g['exp_idx']), h[g['exp_idx']][2]),
                color='#ffd54f', fontsize=11, ha='center', xytext=(0, 12),
                textcoords='offset points')
    ax.axvspan(d(g['idx'])-0.5, d(g['idx'])+0.5, color='#ffffff', alpha=.12,
               zorder=1)
    ax.annotate('gatilho', (d(g['idx']), h[g['idx']][3]), color='#ffffff',
                fontsize=10, ha='center', xytext=(0, -22),
                textcoords='offset points')
    if g.get('i_topo') is not None and g['i_topo'] >= a0:
        ax.plot([d(g['i_topo'])], [g['topo_ant']], marker='v',
                color='#42a5f5', markersize=10, zorder=6)
        ax.annotate('último topo', (d(g['i_topo']), g['topo_ant']),
                    color='#42a5f5', fontsize=10, ha='center',
                    xytext=(0, 14), textcoords='offset points')
    alta = g['lado'] == 'compra'
    for y, cor, rot in (
            (g['entrada'], '#ffffff', f"entrada  {g['entrada']:,.{c}f}"),
            (g['stop'], '#ef5350',
             f"stop  {g['stop']:,.{c}f}  ({g['risco_pct']:.2f}%)"),
            (g['alvo'], '#26a69a', f"alvo  {g['alvo']:,.{c}f}"),
            (g['topo'], '#78909c',
             f"{'topo' if alta else 'fundo'} da explosão  "
             f"{g['topo']:,.{c}f}")):
        ax.axhline(y, color=cor, linewidth=1.1, alpha=.9,
                   linestyle='--' if cor == '#78909c' else '-', zorder=4)
        ax.annotate(rot, (len(vel)-1, y), color=cor, fontsize=9,
                    xytext=(8, 0), textcoords='offset points', va='center')
    cara = {'alvo': '✓ bateu o alvo', 'stop': '✗ bateu o stop',
            None: '• não resolveu'}[fim]
    q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
    ax.set_title(f"{sim.replace('USDT','')}  ·  8h  ·  {q:%d/%m/%Y %H:%M} "
                 f"(Brasília)  ·  {g['lado']}  ·  R:R 1:{g['rr']:.2f}  ·  "
                 f"vinha {'caindo' if alta else 'subindo'} "
                 f"{g['queda']:.1f} volatilidades  ·  {cara}",
                 color='#e8eaed', fontsize=11.5, pad=14)
    ax.tick_params(colors='#6b7280', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#2a2f38')
    ax.grid(color='#1e232b', linewidth=.6)
    ax.set_xlim(-1, len(vel) + 17)
    fig.tight_layout()
    fig.savefig(caminho, dpi=115, facecolor='#13161b')
    plt.close(fig)
    return fim


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--corte', type=float, default=0.32)
    ap.add_argument('--desenhar', default='')
    ap.add_argument('--quantos', type=int, default=3)
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) < 400:
            continue
        vm = statistics.median(v[4]*v[5] for v in h)
        if vm >= a.corte*1e6:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h, vm))
    cru.sort(key=lambda x: -x[2])
    n3 = max(1, len(cru)//3)
    grandes = {s for k, (s, _, _) in enumerate(cru) if k < n3}
    h8 = {s: juntar(h, 8) for s, h, _ in cru}
    print(f"{len(cru)} moedas com volume mediano ≥ {a.corte:.2f} M USD/h")

    def rodar(cfg):
        ops = []
        for sim, _, _ in cru:
            h = h8[sim]
            for g in historico(h, cfg):
                fim, saida, m = resolver(h, g)
                if fim is None:
                    continue
                pos = RISCO/(g['risco_pct']/100)
                mov = (saida-g['entrada'])/g['entrada'] * \
                    (1 if g['lado'] == 'compra' else -1)
                horas = (m-g['idx'])*8
                q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
                ops.append(dict(g, sim=sim, h=h, fim=fim, q=q, ano=q.year,
                                liq=pos*mov - pos*TAXA*2 -
                                pos*(horas/8)*FUND8))
        ops.sort(key=lambda o: o['q'])
        return ops

    VAR = [
        ('reversão: caiu 2 vol. em 20', dict(BASE)),
        ('caiu 3 volatilidades', dict(BASE, tend_atr=3.0)),
        ('caiu 4 volatilidades', dict(BASE, tend_atr=4.0)),
        ('queda medida em 30 velas', dict(BASE, tend_jan=30)),
        ('queda medida em 40 velas', dict(BASE, tend_jan=40)),
        ('sem exigir perto do fundo', dict(BASE, perto_do_fundo=None)),
        ('explosão no quarto de baixo', dict(BASE, perto_do_fundo=0.25)),
        ('pivô de 3 velas', dict(BASE, pivo=3)),
        ('sem exigir extensão', dict(BASE, est_min=0.0)),
    ]
    base_ops = None
    for titulo, filtro in (('AS GRANDES', lambda o: True),
                           ('O TERÇO MAIOR',
                            lambda o: o['sim'] in grandes)):
        print(f"\n{'='*124}\n  {titulo} — explosão de REVERSÃO em H8\n"
              f"{'='*124}")
        cab()
        for rot, cfg in VAR:
            ops = rodar(cfg)
            if base_ops is None:
                base_ops = ops
            painel(rot, [o for o in ops if filtro(o)])

    if a.desenhar and base_ops:
        os.makedirs(a.desenhar, exist_ok=True)
        base_ops.sort(key=lambda o: o['q'], reverse=True)
        vistos, esc = set(), []
        for o in base_ops:
            if o['sim'] in vistos:
                continue
            vistos.add(o['sim']); esc.append(o)
            if len(esc) >= a.quantos:
                break
        print()
        for n, o in enumerate(esc, 1):
            cam = os.path.join(a.desenhar, f"rev{n}_{o['sim']}.png")
            fim = desenhar(o['sim'], o['h'], o, cam)
            print(f"  {cam}  {o['sim']} {o['q']:%d/%m/%Y %H:%M} "
                  f"{o['lado']} R:R 1:{o['rr']:.2f} "
                  f"vinha {o['queda']:.1f} vol. contra → {fim}")


if __name__ == '__main__':
    main()
