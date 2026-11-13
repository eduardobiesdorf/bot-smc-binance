"""Desenha uma operacao da reversao validada, com todos os elementos.

Uso:  python3 desenha_reversao.py <pasta> PAR "YYYY-MM-DD HH:MM" <saida.png>
"""
import os
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explosao8 as exp8
from explosao import ler, juntar
from reversao_confirma import explosoes, entrada_h4, BASE

BRT = dt.timezone(dt.timedelta(hours=-3))
CFG = dict(BASE, modo='raso', vol_min=1.2, espera_h=720, tfp=8)


def achar(h1, quando_ms):
    """Encontra a operacao cuja entrada caiu nesse instante."""
    h8 = juntar(h1, 8)
    mv1 = exp8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    for e in explosoes(h8, CFG):
        r = entrada_h4(h1, mv1, e, CFG, pos1, 1, 8)
        if r and abs(h1[r['idx']][0] - quando_ms) < 3600_000:
            return h8, e, r
    return None, None, None


def desenhar(sim, h1, h8, e, r, caminho):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    alta = e['alta']
    ent = r['ent']
    stop = (e['ob_base'] - e['atr']*CFG['stop_folga']) if alta else \
           (e['ob_topo'] + e['atr']*CFG['stop_folga'])
    alvo = (e['topo'] + CFG['alvo_proj']*e['tam']) if alta else \
           (e['topo'] - CFG['alvo_proj']*e['tam'])
    meio = (e['ob_base'] + e['ob_topo']) / 2
    ms_ent = h1[r['idx']][0]

    # resolve na serie de 8h, so para saber onde termina o desenho
    i8_ent = max(k for k, v in enumerate(h8) if v[0] <= ms_ent)
    fim = None
    for m in range(i8_ent, min(i8_ent + 120, len(h8))):
        hi, lo = h8[m][2], h8[m][3]
        if alta:
            if lo <= stop: fim = ('stop', m); break
            if hi >= alvo: fim = ('alvo', m); break
        else:
            if hi >= stop: fim = ('stop', m); break
            if lo <= alvo: fim = ('alvo', m); break
    m_fim = fim[1] if fim else min(i8_ent + 40, len(h8) - 1)

    tj = round(CFG['tend_h'] / 8)
    a0 = max(0, e['i'] - tj - 4)
    a1 = min(len(h8), m_fim + 6)
    vel = h8[a0:a1]
    d = lambda i: i - a0
    t = f"{ent:.10f}".rstrip('0')
    c = max(2, min(len(t.split('.')[1]) if '.' in t else 0, 8))

    fig, ax = plt.subplots(figsize=(14.5, 7.6), facecolor='#13161b')
    ax.set_facecolor('#13161b')

    # a janela da tendencia
    ax.axvspan(d(e['i']-tj)-0.5, d(e['i'])-0.5, color='#ef5350', alpha=.06,
               zorder=0)
    ax.annotate(f"7 dias de queda  ({e['queda']:.1f} volatilidades)",
                ((d(e['i']-tj)+d(e['i']))/2, max(x[2] for x in vel)),
                color='#ef9a9a', fontsize=10, ha='center',
                xytext=(0, -14), textcoords='offset points')

    for n, v in enumerate(vel):
        o, hi, lo, cl = v[1], v[2], v[3], v[4]
        cor = '#26a69a' if cl >= o else '#ef5350'
        ax.plot([n, n], [lo, hi], color=cor, linewidth=1.1, zorder=3)
        ax.add_patch(Rectangle((n-0.34, min(o, cl)), 0.68,
                               max(abs(cl-o), (hi-lo)*0.004),
                               facecolor=cor, edgecolor=cor, zorder=4))

    # o order block, como caixa
    ob_i = None
    j = e['i'] - 1
    while j >= max(0, e['i'] - CFG['ob_busca']):
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

    ax.axvspan(d(e['i'])-0.5, d(e['i'])+0.5, color='#ffd54f', alpha=.20,
               zorder=2)
    ax.annotate('a explosão', (d(e['i']), h8[e['i']][2] if alta
                               else h8[e['i']][3]),
                color='#ffd54f', fontsize=11, ha='center',
                xytext=(0, 14 if alta else -24), textcoords='offset points')
    if e.get('i_topo') is None:
        pass
    ax.axvline(d(i8_ent), color='#ffffff', linewidth=1.0, alpha=.35,
               linestyle='--', zorder=2)
    ax.annotate('entrada (gatilho no H1)', (d(i8_ent), ent), color='#ffffff',
                fontsize=9.5, ha='center', xytext=(0, 16),
                textcoords='offset points')

    for y, cor, rot in (
            (ent, '#ffffff', f"entrada  {ent:,.{c}f}"),
            (stop, '#ef5350', f"stop  {stop:,.{c}f}   "
                              f"({abs(ent-stop)/ent*100:.2f}%)"),
            (alvo, '#26a69a', f"alvo  {alvo:,.{c}f}   "
                              f"(topo da vela +90%)"),
            (e['topo'], '#78909c',
             f"{'topo' if alta else 'fundo'} da explosão  "
             f"{e['topo']:,.{c}f}")):
        ax.axhline(y, color=cor, linewidth=1.2, alpha=.92,
                   linestyle='--' if cor == '#78909c' else '-', zorder=6)
        ax.annotate(rot, (len(vel)-1, y), color=cor, fontsize=9,
                    xytext=(8, 0), textcoords='offset points', va='center')

    rr = abs(alvo-ent)/abs(ent-stop)
    cara = {'alvo': '✓ bateu o alvo', 'stop': '✗ bateu o stop'}.get(
        fim[0] if fim else '', '• não resolveu')
    q = dt.datetime.fromtimestamp(ms_ent/1000, BRT)
    ax.set_title(
        f"{sim.replace('USDT','')}  ·  padrão em 8h, entrada no H1  ·  "
        f"{q:%d/%m/%Y %H:%M} (Brasília)  ·  "
        f"{'compra' if alta else 'venda'}  ·  R:R 1:{rr:.2f}  ·  {cara}",
        color='#e8eaed', fontsize=12.5, pad=14)
    ax.tick_params(colors='#6b7280', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#2a2f38')
    ax.grid(color='#1e232b', linewidth=.6)
    ax.set_xlim(-1, len(vel) + 20)
    fig.tight_layout()
    fig.savefig(caminho, dpi=115, facecolor='#13161b')
    plt.close(fig)
    return fim[0] if fim else None


def main():
    pasta, sim, quando, saida = sys.argv[1:5]
    h1 = ler(os.path.join(pasta, f"{sim}_1h.csv"))
    ms = int(dt.datetime.strptime(quando, "%Y-%m-%d %H:%M")
             .replace(tzinfo=BRT).timestamp() * 1000)
    h8, e, r = achar(h1, ms)
    if not e:
        print(f"não achei a operação de {sim} em {quando}")
        return
    print(f"{sim} {quando}: {desenhar(sim, h1, h8, e, r, saida)} → {saida}")


if __name__ == '__main__':
    main()
