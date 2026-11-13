"""Desenha os ultimos gatilhos do SETUP 1 (varredura), config AO VIVO.

Usa bot_varredura.CFG direto -- tf='4h' e furo_ob=0,15 -- entao a
imagem mostra o que o bot manda agora.

Uso:  python3 desenha_setup1.py <pasta> [--n 150] [--quantos 2]
"""
import argparse, glob, os, statistics, sys
import datetime as dt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot_varredura as bot
import reversao8 as rev
from explosao import ler

BRT = dt.timezone(dt.timedelta(hours=-3))
MAXBAR = 120


def achar_todos(h1, sim):
    cfg = dict(bot.CFG)
    tf = int(cfg['tf'].replace('h', ''))
    h = rev.juntar(h1, tf) if tf > 1 else h1
    if len(h) < 200:
        return [], [], tf
    a = bot.atr(h, cfg['atr_periodo'])
    mv = bot.media_volume(h, cfg['vol_periodo'])
    out = []
    for imp in bot.achar_impulsos(h, a, mv, cfg):
        g = bot.seguir(h, a, imp, cfg, mv)
        if g and g.get('fase') == 'gatilho':
            g['imp'] = imp
            out.append(g)
    return out, h, tf


def desenhar(sim, h, g, tf, caminho):
    cfg = bot.CFG
    a = bot.atr(h, cfg['atr_periodo'])
    imp = g['imp']
    compra = g['lado'] == 'compra'
    ent, stop, alvo = g['entrada'], g['stop'], g['alvo']
    base, topo_ob = imp['ob_base'], imp['ob_topo']
    k = g['idx']
    kv = g['varredura']
    ext = stop + a[k]*cfg['stop_folga'] if compra else \
          stop - a[k]*cfg['stop_folga']
    alt = topo_ob - base
    fund = (((base - ext) if compra else (ext - topo_ob)) / alt) if alt else 0
    lim = (base - alt*cfg['furo_ob']) if compra else (topo_ob + alt*cfg['furo_ob'])

    fim = None
    for m in range(k+1, min(k+1+MAXBAR, len(h))):
        hi, lo = h[m][2], h[m][3]
        if compra:
            if lo <= stop: fim = ('stop', m); break
            if hi >= alvo: fim = ('alvo', m); break
        else:
            if hi >= stop: fim = ('stop', m); break
            if lo <= alvo: fim = ('alvo', m); break
    m_fim = fim[1] if fim else min(k + 30, len(h) - 1)

    a0 = max(0, imp['ini'] - 10)
    a1 = min(len(h), m_fim + 6)
    vel = h[a0:a1]
    d = lambda i: i - a0
    t = f"{ent:.10f}".rstrip('0')
    c = max(2, min(len(t.split('.')[1]) if '.' in t else 0, 8))

    fig, ax = plt.subplots(figsize=(15, 7.8), facecolor='#13161b')
    ax.set_facecolor('#13161b')

    ax.axvspan(d(imp['ini'])-0.5, d(imp['fim'])+0.5, color='#26a69a',
               alpha=.10, zorder=0)
    ax.annotate('o impulso', ((d(imp['ini'])+d(imp['fim']))/2,
                              max(x[2] for x in vel)),
                color='#26a69a', fontsize=11, ha='center',
                xytext=(0, -14), textcoords='offset points')

    for n, v in enumerate(vel):
        o, hi, lo, cl = v[1], v[2], v[3], v[4]
        cor = '#26a69a' if cl >= o else '#ef5350'
        ax.plot([n, n], [lo, hi], color=cor, linewidth=1.1, zorder=3)
        ax.add_patch(Rectangle((n-0.34, min(o, cl)), 0.68,
                               max(abs(cl-o), (hi-lo)*0.004),
                               facecolor=cor, edgecolor=cor, zorder=4))

    ax.add_patch(Rectangle((d(imp['ob'])-0.5, base), a1-a0-d(imp['ob']),
                           alt, facecolor='#42a5f5', alpha=.12, zorder=1))
    ax.annotate('order block', (d(imp['ob']), base), color='#42a5f5',
                fontsize=10, ha='center', xytext=(0, -20),
                textcoords='offset points')
    ax.axhline(lim, color='#ffa726', linewidth=1.1, linestyle=':',
               alpha=.95, zorder=5)
    ax.annotate(f"limite do furo: {cfg['furo_ob']:.2f}x a altura do bloco",
                (len(vel)-1, lim), color='#ffa726', fontsize=8.5,
                xytext=(8, 0), textcoords='offset points', va='center')

    if kv is not None and a0 <= kv < a1:
        ax.axvspan(d(kv)-0.5, d(kv)+0.5, color='#ef5350', alpha=.22, zorder=2)
        ax.annotate(f'a varredura\nfurou {fund:.2f}x o bloco',
                    (d(kv), h[kv][3] if compra else h[kv][2]),
                    color='#ef9a9a', fontsize=10, ha='center',
                    xytext=(0, -34 if compra else 18),
                    textcoords='offset points')
    ax.axvline(d(k), color='#ffffff', linewidth=1.0, alpha=.35,
               linestyle='--', zorder=2)
    ax.annotate('entrada (a reversão)', (d(k), ent), color='#ffffff',
                fontsize=9.5, ha='center', xytext=(0, 16),
                textcoords='offset points')

    for y, cor, rot in (
            (ent, '#ffffff', f"entrada  {ent:,.{c}f}"),
            (stop, '#ef5350', f"stop  {stop:,.{c}f}   "
                              f"({g['risco_pct']:.2f}% de risco)"),
            (alvo, '#26a69a', f"alvo  {alvo:,.{c}f}   "
                              f"(o topo do impulso)")):
        ax.axhline(y, color=cor, linewidth=1.2, alpha=.92, zorder=6)
        ax.annotate(rot, (len(vel)-1, y), color=cor, fontsize=9,
                    xytext=(8, 0), textcoords='offset points', va='center')

    cara = {'alvo': '✓ bateu o alvo', 'stop': '✗ bateu o stop'}.get(
        fim[0] if fim else '', '• não resolveu')
    q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
    dias = (h[m_fim][0]-h[k][0])/86400_000
    ax.set_title(
        f"{sim.replace('USDT','')}  ·  varredura do order block em H{tf}  ·  "
        f"{q:%d/%m/%Y %H:%M} (Brasília)  ·  {g['lado']}  ·  "
        f"R:R 1:{g['rr']:.2f}  ·  {cara} em {dias:.0f} dias",
        color='#e8eaed', fontsize=12.5, pad=14)
    ax.tick_params(colors='#6b7280', labelsize=8)
    for s_ in ax.spines.values():
        s_.set_color('#2a2f38')
    ax.grid(color='#1e232b', linewidth=.6)
    ax.set_xlim(-1, len(vel) + 22)
    fig.tight_layout()
    fig.savefig(caminho, dpi=115, facecolor='#13161b')
    plt.close(fig)
    return fim[0] if fim else 'aberta'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    ap.add_argument('--quantos', type=int, default=2)
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h,
                        statistics.median(v[4]*v[5] for v in h)))
    cru.sort(key=lambda x: -x[2])
    cru = cru[:a.n]
    todos, series, tfs = [], {}, {}
    for sim, h1, _ in cru:
        gs, h, tf = achar_todos(h1, sim)
        if gs:
            series[sim] = h
            tfs[sim] = tf
            todos += [(sim, g) for g in gs]
    todos.sort(key=lambda x: x[1]['vela_ms'])
    print(f"{len(todos)} gatilhos do setup 1 nas {len(cru)} maiores "
          f"(tf={bot.CFG['tf']}, furo <= {bot.CFG['furo_ob']}x)")
    for k, (sim, g) in enumerate(todos[-a.quantos:][::-1], 1):
        nome = f"setup1_{k}_{sim}.png"
        r = desenhar(sim, series[sim], g, tfs[sim], nome)
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        print(f"  {k}. {sim} {q:%d/%m/%Y %H:%M} {g['lado']} "
              f"R:R 1:{g['rr']:.2f} risco {g['risco_pct']:.2f}% → {r} "
              f"({nome})")


if __name__ == '__main__':
    main()
