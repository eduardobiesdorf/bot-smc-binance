"""Desenha os ultimos gatilhos da reversao, com a config AO VIVO.

Usa reversao8.CFG direto -- o mesmo codigo que o bot roda -- entao a
imagem mostra o alvo e os lados que estao valendo agora, nao os de
algum teste antigo.

Uso:  python3 desenha_ultimos.py <pasta> [--n 150] [--quantos 2]
"""
import argparse, glob, os, statistics, sys
import datetime as dt
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler

BRT = dt.timezone(dt.timedelta(hours=-3))


def achar_todos(h1, sim):
    cfg = rev.CFG
    h8 = rev.juntar(h1, cfg['tf_h'])
    if len(h8) < 60:
        return []
    mv1 = e8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    out = []
    for e in rev.explosoes(h8, cfg):
        g = rev.entrada(h1, mv1, e, cfg, pos1)
        if g:
            out.append((sim, e, g))
    return out


def desenhar(sim, h1, h8, e, g, caminho):
    cfg = rev.CFG
    alta = g['lado'] == 'compra'
    ent, stop, alvo = g['entrada'], g['stop'], g['alvo']
    meio = (e['ob_base'] + e['ob_topo']) / 2
    i8 = max(k for k, v in enumerate(h8) if v[0] <= g['vela_ms'])
    fim = None
    for m in range(i8, min(i8 + rev.MAX_BARRAS, len(h8))):
        hi, lo = h8[m][2], h8[m][3]
        if alta:
            if lo <= stop: fim = ('stop', m); break
            if hi >= alvo: fim = ('alvo', m); break
        else:
            if hi >= stop: fim = ('stop', m); break
            if lo <= alvo: fim = ('alvo', m); break
    m_fim = fim[1] if fim else min(i8 + 40, len(h8) - 1)

    tj = cfg['tend_jan']
    a0, a1 = max(0, e['i'] - tj - 4), min(len(h8), m_fim + 6)
    vel = h8[a0:a1]
    d = lambda i: i - a0
    t = f"{ent:.10f}".rstrip('0')
    c = max(2, min(len(t.split('.')[1]) if '.' in t else 0, 8))

    fig, ax = plt.subplots(figsize=(15, 7.8), facecolor='#13161b')
    ax.set_facecolor('#13161b')
    teto = max(x[2] for x in vel)

    ax.axvspan(d(e['i']-tj)-0.5, d(e['i'])-0.5, color='#ef5350', alpha=.06,
               zorder=0)
    ax.annotate(f"7 dias {'caindo' if alta else 'subindo'}  "
                f"({e['queda']:.1f} volatilidades)",
                ((d(e['i']-tj)+d(e['i']))/2, teto), color='#ef9a9a',
                fontsize=10, ha='center', xytext=(0, -14),
                textcoords='offset points')

    for n, v in enumerate(vel):
        o, hi, lo, cl = v[1], v[2], v[3], v[4]
        cor = '#26a69a' if cl >= o else '#ef5350'
        ax.plot([n, n], [lo, hi], color=cor, linewidth=1.1, zorder=3)
        ax.add_patch(Rectangle((n-0.34, min(o, cl)), 0.68,
                               max(abs(cl-o), (hi-lo)*0.004),
                               facecolor=cor, edgecolor=cor, zorder=4))

    ob_i, j = None, e['i'] - 1
    while j >= max(0, e['i'] - cfg['ob_busca']):
        if (h8[j][4] > h8[j][1]) != alta:
            ob_i = j; break
        j -= 1
    if ob_i is not None:
        ax.add_patch(Rectangle((d(ob_i)-0.5, e['ob_base']),
                               a1-a0-d(ob_i), e['ob_topo']-e['ob_base'],
                               facecolor='#42a5f5', alpha=.12, zorder=1))
        ax.annotate('order block', (d(ob_i), e['ob_base']), color='#42a5f5',
                    fontsize=10, ha='center', xytext=(0, -20),
                    textcoords='offset points')
    ax.axhline(meio, color='#42a5f5', linewidth=1.0, linestyle=':',
               alpha=.9, zorder=5)
    ax.annotate('meio do OB — o recuo não pode passar daqui',
                (len(vel)-1, meio), color='#42a5f5', fontsize=8.5,
                xytext=(8, 0), textcoords='offset points', va='center')
    ax.axhline(e['topo_ant'], color='#b39ddb', linewidth=1.0,
               linestyle=':', alpha=.85, zorder=5)
    ax.annotate('último topo (rompido pela explosão)',
                (len(vel)-1, e['topo_ant']), color='#b39ddb', fontsize=8.5,
                xytext=(8, 0), textcoords='offset points', va='center')

    ax.axvspan(d(e['i'])-0.5, d(e['i'])+0.5, color='#ffd54f', alpha=.20,
               zorder=2)
    ax.annotate('a explosão (1 vela de 8h)',
                (d(e['i']), h8[e['i']][2] if alta else h8[e['i']][3]),
                color='#ffd54f', fontsize=11, ha='center',
                xytext=(0, 14 if alta else -24), textcoords='offset points')
    ax.axvline(d(i8), color='#ffffff', linewidth=1.0, alpha=.35,
               linestyle='--', zorder=2)
    ax.annotate('entrada (gatilho no H1)', (d(i8), ent), color='#ffffff',
                fontsize=9.5, ha='center', xytext=(0, 16),
                textcoords='offset points')

    for y, cor, rot in (
            (ent, '#ffffff', f"entrada  {ent:,.{c}f}"),
            (stop, '#ef5350', f"stop  {stop:,.{c}f}   "
                              f"({g['risco_pct']:.2f}% de risco)"),
            (alvo, '#26a69a',
             f"alvo  {alvo:,.{c}f}   "
             f"(o {'topo' if alta else 'fundo'} da vela de explosão)"),):
        ax.axhline(y, color=cor, linewidth=1.2, alpha=.92,
                   linestyle='--' if cor == '#78909c' else '-', zorder=6)
        ax.annotate(rot, (len(vel)-1, y), color=cor, fontsize=9,
                    xytext=(8, 0), textcoords='offset points', va='center')

    cara = {'alvo': '✓ bateu o alvo', 'stop': '✗ bateu o stop'}.get(
        fim[0] if fim else '', '• não resolveu em 40 dias')
    q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
    dias = (h8[m_fim][0]-h8[i8][0])/86400_000
    ax.set_title(
        f"{sim.replace('USDT','')}  ·  padrão em 8h, entrada no H1  ·  "
        f"{q:%d/%m/%Y %H:%M} (Brasília)  ·  {g['lado']}  ·  "
        f"R:R 1:{g['rr']:.2f}  ·  {cara} em {dias:.0f} dias",
        color='#e8eaed', fontsize=12.5, pad=14)
    ax.tick_params(colors='#6b7280', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#2a2f38')
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
    todos = []
    for sim, h1, _ in cru:
        todos += achar_todos(h1, sim)
    todos.sort(key=lambda x: x[2]['vela_ms'])
    print(f"{len(todos)} gatilhos no histórico das {len(cru)} maiores")
    series = {s: h for s, h, _ in cru}
    for k, (sim, e, g) in enumerate(todos[-a.quantos:][::-1], 1):
        h1 = series[sim]
        h8 = rev.juntar(h1, rev.CFG['tf_h'])
        nome = f"gatilho_{k}_{sim}.png"
        r = desenhar(sim, h1, h8, e, g, nome)
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        print(f"  {k}. {sim} {q:%d/%m/%Y %H:%M} {g['lado']} "
              f"R:R 1:{g['rr']:.2f} risco {g['risco_pct']:.2f}% → {r} "
              f"({nome})")


if __name__ == '__main__':
    main()
