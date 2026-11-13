"""SETUP 5 -- rompimento falso com retorno a lateralidade. Em H1.

A configuracao que o Eduardo descreveu:

  1. LATERALIDADE  -- faixa estreita por ~30 velas de H1
  2. A IDA         -- fecha para fora da faixa e segue algumas velas,
                      com o VOLUME SUBINDO
  3. FORCA CONTRARIA -- uma vela grande CONTRA o movimento. O alerta
  4. FALHA DE CONTINUIDADE -- tenta retomar e NAO faz nova maxima
  5. A VOLTA       -- fecha de volta para DENTRO da faixa. A entrada
  6. O ALVO        -- o outro lado da faixa, o ultimo fundo/topo deixado
                      Stop acima da maxima da ida.

No caso de alta: rompe para cima, falha, volta -> VENDE buscando o
fundo da faixa. O espelho para baixo.

Uso:  python3 setup5_falha.py <pasta> [--tf 1] [--desenhar 3]
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
from explosao import ler, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))

CFG5 = dict(
    lat_jan=30,        # velas da lateralidade
    lat_max_atr=5.0,   # altura da faixa, em volatilidades: quanto menor, mais estreita
    ida_max=12,        # ate quantas velas a ida pode durar
    ida_min=2,         # e pelo menos quantas
    vol_sobe=1.3,      # volume medio da ida / volume medio da lateralidade
    forca_sigma=2.0,   # a vela contraria, em volatilidades
    forca_corpo=0.5,
    falha_max=8,       # velas para a falha e a volta acontecerem
    stop_folga=0.15,
    rr_min=1.2,
)


def achar(h, cfg=None):
    cfg = cfg or CFG5
    if len(h) < 120:
        return []
    a, mv = e8.atr(h, 14), e8.medvol(h, 20)
    L = cfg['lat_jan']
    out, i = [], L + 20
    while i < len(h) - 4:
        if a[i-1] <= 0 or mv[i-1] <= 0:
            i += 1; continue
        faixa = h[i-L:i]
        topo = max(x[2] for x in faixa)
        base = min(x[3] for x in faixa)
        alt = topo - base
        # 1) a lateralidade tem de ser ESTREITA
        if alt <= 0 or alt > cfg['lat_max_atr']*a[i-1]:
            i += 1; continue
        cl = h[i][4]
        # 2) a ida: fecha para fora da faixa
        if cl > topo:
            alta = True
        elif cl < base:
            alta = False
        else:
            i += 1; continue
        vol_lat = statistics.mean(x[5] for x in faixa)
        # segue a ida ate a vela de forca contraria
        ext = h[i][2] if alta else h[i][3]
        k_forca = None
        for k in range(i+1, min(i+1+cfg['ida_max'], len(h))):
            hk, lk, ok, ck = h[k][2], h[k][3], h[k][1], h[k][4]
            rk = hk - lk
            ext = max(ext, hk) if alta else min(ext, lk)
            if k - i < cfg['ida_min']:
                continue
            # 3) a vela de forca CONTRARIA
            if rk > 0 and rk >= cfg['forca_sigma']*a[k-1] \
                    and abs(ck-ok)/rk >= cfg['forca_corpo'] \
                    and ((ck < ok) if alta else (ck > ok)):
                k_forca = k
                break
        if k_forca is None:
            i += 1; continue
        vol_ida = statistics.mean(x[5] for x in h[i:k_forca+1])
        # 2b) o volume da ida tem de ser MAIOR que o da lateralidade
        if vol_lat <= 0 or vol_ida/vol_lat < cfg['vol_sobe']:
            i += 1; continue
        # 4) a falha: nao faz nova maxima  5) e volta para dentro da faixa
        ent_k = None
        for k in range(k_forca+1, min(k_forca+1+cfg['falha_max'], len(h))):
            hk, lk, ck = h[k][2], h[k][3], h[k][4]
            if (hk > ext) if alta else (lk < ext):
                break                      # retomou: nao houve falha
            if (ck < topo) if alta else (ck > base):
                ent_k = k                  # voltou para dentro da faixa
                break
        if ent_k is None:
            i += 1; continue
        ent = h[ent_k][4]
        stop = ext + a[ent_k]*cfg['stop_folga'] if alta else \
               ext - a[ent_k]*cfg['stop_folga']
        alvo = base if alta else topo      # 6) o outro lado da faixa
        risco = abs(ent-stop)
        dist = (ent-alvo) if alta else (alvo-ent)
        if risco <= 0 or dist <= 0 or dist/risco < cfg['rr_min']:
            i += 1; continue
        out.append(dict(lado='venda' if alta else 'compra', i=i,
                        topo=topo, base=base, ext=ext, k_forca=k_forca,
                        idx=ent_k, entrada=ent, stop=stop, alvo=alvo,
                        rr=dist/risco, risco_pct=risco/ent*100,
                        vol_x=vol_ida/vol_lat, vela_ms=h[ent_k][0],
                        lat_atr=alt/a[i-1]))
        i = ent_k + 1
    return out


def desenhar(sim, h, g, tf, caminho):
    cfg = CFG5
    venda = g['lado'] == 'venda'
    i, kf, k = g['i'], g['k_forca'], g['idx']
    fim = None
    for m in range(k+1, min(k+1+120, len(h))):
        hi, lo = h[m][2], h[m][3]
        if venda:
            if hi >= g['stop']: fim = ('stop', m); break
            if lo <= g['alvo']: fim = ('alvo', m); break
        else:
            if lo <= g['stop']: fim = ('stop', m); break
            if hi >= g['alvo']: fim = ('alvo', m); break
    m_fim = fim[1] if fim else min(k+30, len(h)-1)
    a0 = max(0, i - cfg['lat_jan'] - 4)
    a1 = min(len(h), m_fim + 5)
    vel = h[a0:a1]
    d = lambda x: x - a0
    t = f"{g['entrada']:.10f}".rstrip('0')
    c = max(2, min(len(t.split('.')[1]) if '.' in t else 0, 8))

    fig, (ax, axv) = plt.subplots(2, 1, figsize=(15, 9), sharex=True,
                                  gridspec_kw={'height_ratios': [4, 1]},
                                  facecolor='#13161b')
    for A in (ax, axv):
        A.set_facecolor('#13161b')
        A.tick_params(colors='#6b7280', labelsize=8)
        for s_ in A.spines.values():
            s_.set_color('#2a2f38')
        A.grid(color='#1e232b', linewidth=.6)

    ax.add_patch(Rectangle((d(i-cfg['lat_jan'])-0.5, g['base']),
                           a1-a0-d(i-cfg['lat_jan']), g['topo']-g['base'],
                           facecolor='#42a5f5', alpha=.10, zorder=0))
    ax.annotate(f"a lateralidade ({g['lat_atr']:.1f} volatilidades de altura)",
                ((d(i-cfg['lat_jan'])+d(i))/2, g['topo']),
                color='#64b5f6', fontsize=10, ha='center',
                xytext=(0, 8), textcoords='offset points')
    for n, v in enumerate(vel):
        o, hi, lo, cl = v[1], v[2], v[3], v[4]
        cor = '#26a69a' if cl >= o else '#ef5350'
        ax.plot([n, n], [lo, hi], color=cor, linewidth=1.1, zorder=3)
        ax.add_patch(Rectangle((n-0.34, min(o, cl)), 0.68,
                               max(abs(cl-o), (hi-lo)*0.004),
                               facecolor=cor, edgecolor=cor, zorder=4))
        axv.bar(n, v[5], color=cor, width=0.68, alpha=.85)
    mvv = e8.medvol(h, 20)
    axv.plot(range(len(vel)), [mvv[a0+n] for n in range(len(vel))],
             color='#ffd54f', linewidth=1.2)
    axv.set_ylabel('volume', color='#9aa3ae', fontsize=9)

    ax.axvspan(d(i)-0.5, d(kf)+0.5, color='#ffd54f', alpha=.10, zorder=1)
    ax.annotate(f"a ida ({g['vol_x']:.1f}x o volume da faixa)",
                ((d(i)+d(kf))/2, g['ext']), color='#ffd54f', fontsize=10,
                ha='center', xytext=(0, 14 if venda else -24),
                textcoords='offset points')
    ax.axvspan(d(kf)-0.5, d(kf)+0.5, color='#ab47bc', alpha=.28, zorder=2)
    ax.annotate('a força contrária', (d(kf), h[kf][3] if venda else h[kf][2]),
                color='#ce93d8', fontsize=10, ha='center',
                xytext=(0, -24 if venda else 16), textcoords='offset points')
    ax.axvline(d(k), color='#ffffff', linewidth=1.0, alpha=.35,
               linestyle='--', zorder=2)
    ax.annotate('a volta: entrada', (d(k), g['entrada']), color='#ffffff',
                fontsize=9.5, ha='center', xytext=(0, 14),
                textcoords='offset points')
    for y, cor, rot in (
            (g['entrada'], '#ffffff', f"entrada  {g['entrada']:,.{c}f}"),
            (g['stop'], '#ef5350', f"stop  {g['stop']:,.{c}f}   "
                                   f"({g['risco_pct']:.2f}% de risco)"),
            (g['alvo'], '#26a69a',
             f"alvo  {g['alvo']:,.{c}f}   "
             f"(o {'fundo' if venda else 'topo'} da faixa)")):
        ax.axhline(y, color=cor, linewidth=1.2, alpha=.92, zorder=6)
        ax.annotate(rot, (len(vel)-1, y), color=cor, fontsize=9,
                    xytext=(8, 0), textcoords='offset points', va='center')

    cara = {'alvo': '✓ bateu o alvo', 'stop': '✗ bateu o stop'}.get(
        fim[0] if fim else '', '• não resolveu')
    q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
    ax.set_title(f"{sim.replace('USDT','')}  ·  rompimento falso e volta à "
                 f"faixa  ·  velas de {tf}h  ·  {q:%d/%m/%Y %H:%M} "
                 f"(Brasília)  ·  {g['lado']}  ·  R:R 1:{g['rr']:.2f}  ·  "
                 f"{cara}", color='#e8eaed', fontsize=12.5, pad=14)
    ax.set_xlim(-1, len(vel) + 20)
    fig.tight_layout()
    fig.savefig(caminho, dpi=115, facecolor='#13161b')
    plt.close(fig)
    return fim[0] if fim else 'aberta'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--tf', type=int, default=1)
    ap.add_argument('--n', type=int, default=150)
    ap.add_argument('--desenhar', type=int, default=3)
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 2000:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h,
                        statistics.median(v[4]*v[5] for v in h)))
    cru.sort(key=lambda x: -x[2])
    cru = cru[:a.n]
    achados = []
    for sim, h1, _ in cru:
        h = rev.juntar(h1, a.tf) if a.tf > 1 else h1
        for g in achar(h):
            achados.append((sim, g, h))
    achados.sort(key=lambda x: x[1]['vela_ms'])
    meses = max(len(h) for _, h, _ in cru) / (24*30.4)
    print(f"{len(achados)} ocorrências nas {len(cru)} maiores, "
          f"velas de {a.tf}h, {meses:.0f} meses "
          f"= {len(achados)/meses:.1f} por mês\n")
    for k, (sim, g, h) in enumerate(achados[-a.desenhar:][::-1], 1):
        nome = f"setup5_{k}_{sim}.png"
        r = desenhar(sim, h, g, a.tf, nome)
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        print(f"  {k}. {sim:<13} {q:%d/%m/%Y %H:%M}  {g['lado']:<6} "
              f"R:R 1:{g['rr']:.2f}  risco {g['risco_pct']:.2f}%  "
              f"faixa {g['lat_atr']:.1f} vol  volume {g['vol_x']:.1f}x  "
              f"→ {r}   ({nome})")


if __name__ == '__main__':
    main()
