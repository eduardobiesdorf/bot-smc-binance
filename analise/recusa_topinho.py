"""Recusa no rompimento do topinho, depois de uma explosao.

Sequencia (caso de alta; a de baixa e espelhada):

  1. explosao de L ate H (vela unica ou pernada forte)
  2. recuo: o preco cai de H ate um fundo p, SEM furar o L
     e nesse recuo fica um topinho h, abaixo de H
  3. segunda subida: o preco rompe o h, mas nao passa do H
  4. recusa: uma vela fecha de volta abaixo do h
  5. venda no fechamento dessa vela
     stop acima da maxima da segunda subida
     alvo no L, o fundo de todo o movimento

Usar --desenhar para gravar imagens dos exemplos encontrados.
"""
import sys, os, glob, csv, statistics, argparse
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explosao import ler, juntar, atr, medvol

BRT = dt.timezone(dt.timedelta(hours=-3))


def explosoes(h, a, mv, cfg):
    """Pernadas fortes: 1 a 8 velas, >= sigma de volatilidade."""
    jan = cfg['janela']
    i = max(jan, 21) + 1
    while i < len(h) - 10:
        achou = None
        for n in range(1, cfg['perna_max'] + 1):
            f = i + n - 1
            if f >= len(h) - 10:
                break
            tramo = h[i:f+1]
            alta = h[f][4] > h[i][1]
            if a[i-1] <= 0 or mv[i-1] <= 0:
                continue
            if abs(h[f][4] - h[i][1]) < cfg['sigma'] * a[i-1]:
                continue
            corpo = sum(abs(v[4]-v[1]) for v in tramo)
            faixa = sum(v[2]-v[3] for v in tramo)
            if faixa <= 0 or corpo/faixa < 0.5:
                continue
            if statistics.mean(v[5] for v in tramo) < cfg['vol']*mv[i-1]:
                continue
            if alta and h[f][4] <= max(x[2] for x in h[i-jan:i]):
                continue
            if not alta and h[f][4] >= min(x[3] for x in h[i-jan:i]):
                continue
            achou = (i, f, alta)
            break
        if achou:
            yield achou
            i = achou[1] + 1
        else:
            i += 1


def seguir(h, a, ini, fim, alta, cfg):
    H = max(x[2] for x in h[ini:fim+1]) if alta else \
        min(x[3] for x in h[ini:fim+1])
    L = min(x[3] for x in h[ini:fim+1]) if alta else \
        max(x[2] for x in h[ini:fim+1])
    faixa = abs(H - L)
    if faixa <= 0:
        return None

    # --- 1) o topinho: o primeiro pivo confirmado depois da explosao,
    #        abaixo do H. Pivo de k velas de cada lado, como se enxerga
    #        no grafico -- e so fica confirmado k velas depois, sem
    #        olhar o futuro na hora da entrada.
    kp = cfg['pivo']
    topinho = i_top = None
    lim = min(fim + 1 + cfg['espera'], len(h) - kp - 1)
    for k in range(fim + 1, lim):
        hi, lo = h[k][2], h[k][3]
        if (lo <= L) if alta else (hi >= L):
            return None
        if k - kp < fim + 1:
            continue
        c = k - kp                      # candidato a pivo, ja confirmado
        if c <= fim:
            continue
        if alta:
            ref = h[c][2]
            if ref >= H:
                continue
            if any(h[x][2] >= ref for x in range(c-kp, c+kp+1) if x != c):
                continue
        else:
            ref = h[c][3]
            if ref <= H:
                continue
            if any(h[x][3] <= ref for x in range(c-kp, c+kp+1) if x != c):
                continue
        topinho, i_top = ref, c
        break
    if topinho is None:
        return None

    # --- 1b) o recuo depois do topinho: tem de ser de verdade
    fundo_p = None
    for k in range(i_top + 1, min(i_top + 1 + cfg['espera'], len(h))):
        hi, lo = h[k][2], h[k][3]
        if (lo <= L) if alta else (hi >= L):
            return None
        prof = (topinho - lo) / faixa if alta else (hi - topinho) / faixa
        if prof >= cfg['recuo_min'] and k - i_top >= cfg['recuo_velas']:
            fundo_p = k
            break
    if fundo_p is None:
        return None

    # --- 2) a segunda subida rompe o topinho
    rompeu = None
    pico2 = None
    for k in range(fundo_p + 1, min(fundo_p + 1 + cfg['espera2'], len(h))):
        hi, lo = h[k][2], h[k][3]
        if (lo <= L) if alta else (hi >= L):
            return None
        if rompeu is None:
            if (hi > topinho) if alta else (lo < topinho):
                rompeu = k
                pico2 = hi if alta else lo
            else:
                continue
        else:
            pico2 = max(pico2, hi) if alta else min(pico2, lo)
        # passou do H: nao e topo mais baixo, e continuacao
        if cfg['abaixo_do_H'] and ((pico2 > H) if alta else (pico2 < H)):
            return None
        if k - rompeu > cfg['espera_recusa']:
            return None
        # --- 3) a recusa: fecha de volta para dentro
        cl, o = h[k][4], h[k][1]
        dentro = (cl < topinho) if alta else (cl > topinho)
        if not dentro:
            continue
        contra = (cl < o) if alta else (cl > o)
        if cfg['pede_contra'] and not contra:
            continue
        ent = cl
        s = pico2 + a[k]*cfg['folga'] if alta else pico2 - a[k]*cfg['folga']
        alv = L
        risco = abs(ent - s)
        dist = abs(ent - alv)
        if risco <= 0 or dist <= 0 or dist/risco < cfg['rr_min']:
            return None
        # stop microscopico nao e stop, e ruido -- e fica caro em taxa
        if risco/ent*100 < cfg['stop_min_pct']:
            return None
        return dict(ini=ini, fim=fim, alta=alta, H=H, L=L, topinho=topinho,
                    i_top=i_top, fundo_p=fundo_p, rompeu=rompeu, pico2=pico2, k=k,
                    ent=ent, stop=s, alvo=alv, rr=dist/risco,
                    risco_pct=risco/ent*100, ms=h[k][0],
                    q=dt.datetime.fromtimestamp(h[k][0]/1000, BRT),
                    lado='venda' if alta else 'compra')
    return None


BASE = dict(sigma=2.5, vol=1.5, janela=20, perna_max=8, espera=30,
            espera2=30, espera_recusa=6, recuo_min=0.35, recuo_velas=3,
            pivo=2, folga=0.10, rr_min=2.0, stop_min_pct=0.8,
            abaixo_do_H=True, pede_contra=True)


def desenhar(h, g, sim, tf, caminho):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    a0 = max(0, g['ini'] - 12)
    a1 = min(len(h), g['k'] + 40)
    vel = h[a0:a1]
    fig, ax = plt.subplots(figsize=(13, 7), facecolor='#13161b')
    ax.set_facecolor('#13161b')
    for n, v in enumerate(vel):
        o, hi, lo, cl = v[1], v[2], v[3], v[4]
        c = '#26a69a' if cl >= o else '#ef5350'
        ax.plot([n, n], [lo, hi], color=c, linewidth=0.9, zorder=2)
        ax.add_patch(Rectangle((n-0.32, min(o, cl)), 0.64,
                               max(abs(cl-o), (hi-lo)*0.002),
                               facecolor=c, edgecolor=c, zorder=3))
    d = lambda i: i - a0
    ax.axvspan(d(g['ini'])-0.5, d(g['fim'])+0.5, color='#ffd54f', alpha=.10,
               zorder=1)
    ax.annotate('explosão', (d(g['fim']), g['H']), color='#ffd54f',
                fontsize=10, xytext=(0, 14), textcoords='offset points',
                ha='center')
    for y, cor, rot in ((g['H'], '#78909c', 'H  topo da explosão'),
                        (g['topinho'], '#42a5f5', 'h  topinho'),
                        (g['L'], '#ab47bc', 'L  fundo do movimento  = alvo'),
                        (g['stop'], '#ef5350', 'stop'),
                        (g['ent'], '#ffffff', 'entrada')):
        ax.axhline(y, color=cor, linewidth=1.1,
                   linestyle='-' if rot in ('entrada', 'stop') else '--',
                   alpha=.85, zorder=4)
        ax.annotate(rot, (len(vel)-1, y), color=cor, fontsize=9,
                    xytext=(6, 0), textcoords='offset points', va='center')
    ax.axvspan(d(g['rompeu'])-0.5, d(g['k'])+0.5, color='#ef5350', alpha=.12,
               zorder=1)
    ax.plot([d(g['i_top'])], [g['topinho']], marker='v', color='#42a5f5',
            markersize=9, zorder=6)
    ax.plot([d(g['fundo_p'])], [h[g['fundo_p']][3] if g['alta']
                                else h[g['fundo_p']][2]],
            marker='^', color='#66bb6a', markersize=9, zorder=6)
    ax.annotate('rompe o topinho\ne recusa', (d(g['k']), g['pico2']),
                color='#ef5350', fontsize=10, xytext=(0, 18),
                textcoords='offset points', ha='center')
    ax.set_title(f"{sim.replace('USDT','')}  ·  {tf}h  ·  "
                 f"{g['q']:%d/%m/%Y %H:%M} (Brasília)  ·  "
                 f"{g['lado']}  ·  risco/retorno 1:{g['rr']:.1f}  ·  "
                 f"stop {g['risco_pct']:.1f}%",
                 color='#e8eaed', fontsize=12, pad=14)
    ax.tick_params(colors='#6b7280', labelsize=8)
    for s in ax.spines.values():
        s.set_color('#2a2f38')
    ax.grid(color='#1e232b', linewidth=.6)
    ax.set_xlim(-1, len(vel) + 13)
    fig.tight_layout()
    fig.savefig(caminho, dpi=115, facecolor='#13161b')
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--tf', type=int, default=1)
    ap.add_argument('--corte', type=float, default=0.32)
    ap.add_argument('--desenhar', default='')
    ap.add_argument('--quantos', type=int, default=4)
    a = ap.parse_args()

    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400 and \
                statistics.median(v[4]*v[5] for v in h) >= a.corte*1e6:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h))

    achados = []
    for sim, h1 in cru:
        hg = juntar(h1, a.tf)
        if len(hg) < 120:
            continue
        ag, mvg = atr(hg, 14), medvol(hg, 20)
        for ini, fim, alta in explosoes(hg, ag, mvg, BASE):
            g = seguir(hg, ag, ini, fim, alta, BASE)
            if g:
                achados.append((sim, hg, g))
    print(f"{len(cru)} moedas · H{a.tf} · {len(achados)} ocorrências do padrão")
    if not achados:
        return
    rrs = [g['rr'] for _, _, g in achados]
    sp = [g['risco_pct'] for _, _, g in achados]
    print(f"risco/retorno: mediana 1:{statistics.median(rrs):.1f}  "
          f"(de 1:{min(rrs):.1f} a 1:{max(rrs):.1f})")
    print(f"stop: mediana {statistics.median(sp):.1f}%")
    print(f"vendas {sum(1 for _,_,g in achados if g['alta'])} · "
          f"compras {sum(1 for _,_,g in achados if not g['alta'])}")

    if a.desenhar:
        os.makedirs(a.desenhar, exist_ok=True)
        # pega exemplos espalhados no tempo e em moedas diferentes
        achados.sort(key=lambda x: x[2]['q'])
        vistos, escolhidos = set(), []
        passo = max(1, len(achados) // (a.quantos * 4))
        for sim, hg, g in achados[::passo]:
            if sim in vistos:
                continue
            vistos.add(sim); escolhidos.append((sim, hg, g))
            if len(escolhidos) >= a.quantos:
                break
        for n, (sim, hg, g) in enumerate(escolhidos, 1):
            cam = os.path.join(a.desenhar, f"exemplo{n}_{sim}.png")
            desenhar(hg, g, sim, a.tf, cam)
            print(f"  {cam}  —  {sim} {g['q']:%d/%m/%Y %H:%M} "
                  f"{g['lado']} 1:{g['rr']:.1f}")


if __name__ == '__main__':
    main()
