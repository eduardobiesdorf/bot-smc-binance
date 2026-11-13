"""SETUP 4 -- a primeira forca depois da queda, alvo na piscina.

A configuracao que o Eduardo descreveu olhando o AKEUSDT no diario:

  1. o preco VEM CAINDO e o VOLUME VEM AUMENTANDO durante a queda
  2. do nada vem UMA vela verde forte -- a primeira forca
  3. ela NAO precisa romper topo nenhum (e a diferenca para o setup 3)
  4. o preco retorna no order block que ela deixou
  5. entra ali, e o alvo e a ULTIMA PISCINA DE LIQUIDEZ que ele deixou
     -- o topo fractal ainda nao superado acima da entrada

A diferenca para o setup 3 nao e detalhe: la a vela tem de FECHAR ALEM
DO ULTIMO PIVO, o que exige rompimento. Aqui basta ser a primeira vela
de forca saindo do fundo. No AKE a vela saiu de 0,0025 e foi a 0,0117,
bem abaixo da prateleira de 0,021 -- nao rompeu nada. Por isso ele se
qualifica aqui e nao la.

E o alvo muda: em vez do extremo da propria vela, e a liquidez parada
acima, que costuma estar bem mais longe.

Uso:  python3 setup4_piscina.py <pasta> [--tf 24] [--desenhar 3]
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
import bot_varredura as bot
from explosao import ler, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))

CFG4 = dict(
    jan=20,          # velas da janela de queda
    queda_atr=2.0,   # a queda, em volatilidades
    fundo=0.35,      # a vela sai do terco de baixo da faixa
    vol_cresce=1.3,  # volume do ultimo terco / primeiro terco da queda
    sigma=2.5,       # tamanho da vela de forca
    corpo=0.5,
    vol_vela=1.5,    # volume da vela de forca
    ob_busca=6,
    espera=30,       # velas esperando o retorno ao bloco
    gatilho_max=6,   # velas para o gatilho depois do encosto
    raso=0.5,        # o encosto nao passa de 0,5x o bloco (None desliga)
    stop_folga=0.10,
    piscina_jan=60,  # ate onde procurar a piscina
    rr_min=1.2,
)


def achar(h, cfg=None):
    cfg = cfg or CFG4
    if len(h) < 80:
        return []
    a, mv = e8.atr(h, 14), e8.medvol(h, 20)
    jan = cfg['jan']
    out, i = [], max(jan, 25) + 1
    while i < len(h) - 2:
        o, hi, lo, cl, v = h[i][1], h[i][2], h[i][3], h[i][4], h[i][5]
        rng = hi - lo
        if rng <= 0 or a[i-1] <= 0 or mv[i-1] <= 0:
            i += 1; continue
        # 2) a vela de forca, verde
        if cl <= o or rng < cfg['sigma']*a[i-1] or (cl-o)/rng < cfg['corpo'] \
                or v < cfg['vol_vela']*mv[i-1]:
            i += 1; continue
        # 1a) vinha caindo
        if (h[i-jan][4] - h[i-1][4]) / a[i-1] < cfg['queda_atr']:
            i += 1; continue
        faixa = h[i-jan:i]
        tmax = max(x[2] for x in faixa); tmin = min(x[3] for x in faixa)
        if tmax > tmin and (lo - tmin)/(tmax - tmin) > cfg['fundo']:
            i += 1; continue
        # 1b) o volume VEM AUMENTANDO durante a queda
        t = jan // 3
        v0 = statistics.mean(x[5] for x in h[i-jan:i-jan+t])
        v1 = statistics.mean(x[5] for x in h[i-t:i])
        if v0 <= 0 or v1/v0 < cfg['vol_cresce']:
            i += 1; continue
        # 4) o order block
        ob_base = ob_topo = ob_i = None
        j = i - 1
        while j >= max(0, i - cfg['ob_busca']):
            if h[j][4] <= h[j][1]:
                ob_base, ob_topo, ob_i = h[j][3], h[j][2], j
                break
            j -= 1
        if ob_base is None:
            i += 1; continue
        meio = (ob_base + ob_topo)/2
        tocou = extremo = ent_k = None
        pico = hi
        for k in range(i+1, min(i+1+cfg['espera'], len(h))):
            hk, lk, ok, ck = h[k][2], h[k][3], h[k][1], h[k][4]
            if tocou is None:
                pico = max(pico, hk)
                if lk <= ob_topo:
                    tocou, extremo = k, lk
                else:
                    continue
            else:
                extremo = min(extremo, lk)
            if extremo < ob_base - a[i]*1.0:
                break
            if k - tocou > cfg['gatilho_max']:
                break
            if cfg['raso'] is not None:
                alt = ob_topo - ob_base
                if alt > 0 and (ob_base - extremo)/alt > cfg['raso'] \
                        and extremo < meio:
                    break
            rk = hk - lk
            if rk <= 0 or ck <= ob_topo or ck <= ok:
                continue
            corpo = (ck-ok)/rk
            pav = (min(ok, ck)-lk)/rk
            if corpo < 0.5 and pav < 0.5:
                continue
            ent_k = k
            break
        if ent_k is None:
            i += 1; continue
        ent = h[ent_k][4]
        stop = ob_base - a[i]*cfg['stop_folga']
        risco = ent - stop
        if risco <= 0:
            i += 1; continue
        # 5) o alvo: a piscina de liquidez acima
        d = bot.piscina(h, ent_k, False, ent, cfg['piscina_jan'])
        if d is None:
            i += 1; continue
        alvo = ent + d
        if d/risco < cfg['rr_min']:
            i += 1; continue
        out.append(dict(i=i, ob=ob_i, ob_base=ob_base, ob_topo=ob_topo,
                        meio=meio, tocou=tocou, idx=ent_k, entrada=ent,
                        stop=stop, alvo=alvo, rr=d/risco,
                        risco_pct=risco/ent*100, vol_cresce=v1/v0,
                        vela_ms=h[ent_k][0], exp_ms=h[i][0],
                        tam_vela=rng/a[i-1], vol_x=v/mv[i-1]))
        i = ent_k + 1
    return out


def desenhar(sim, h, g, tf, caminho):
    cfg = CFG4
    a = e8.atr(h, 14)
    i, k = g['i'], g['idx']
    fim = None
    for m in range(k+1, min(k+1+120, len(h))):
        if h[m][3] <= g['stop']: fim = ('stop', m); break
        if h[m][2] >= g['alvo']: fim = ('alvo', m); break
    m_fim = fim[1] if fim else min(k+25, len(h)-1)
    a0 = max(0, i - cfg['jan'] - 4)
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

    ax.axvspan(d(i-cfg['jan'])-0.5, d(i)-0.5, color='#ef5350', alpha=.06)
    ax.annotate('a queda, com volume aumentando',
                ((d(i-cfg['jan'])+d(i))/2, max(x[2] for x in vel)),
                color='#ef9a9a', fontsize=10, ha='center',
                xytext=(0, -14), textcoords='offset points')
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

    ax.add_patch(Rectangle((d(g['ob'])-0.5, g['ob_base']),
                           a1-a0-d(g['ob']), g['ob_topo']-g['ob_base'],
                           facecolor='#42a5f5', alpha=.12, zorder=1))
    ax.annotate('order block', (d(g['ob']), g['ob_base']), color='#42a5f5',
                fontsize=10, ha='center', xytext=(0, -20),
                textcoords='offset points')
    ax.axvspan(d(i)-0.5, d(i)+0.5, color='#ffd54f', alpha=.20, zorder=2)
    ax.annotate(f"a primeira força\n{g['tam_vela']:.1f}x a volatilidade, "
                f"{g['vol_x']:.1f}x o volume", (d(i), h[i][2]),
                color='#ffd54f', fontsize=10, ha='center',
                xytext=(0, 16), textcoords='offset points')
    ax.axvline(d(k), color='#ffffff', linewidth=1.0, alpha=.35,
               linestyle='--', zorder=2)
    ax.annotate('entrada', (d(k), g['entrada']), color='#ffffff',
                fontsize=9.5, ha='center', xytext=(0, 14),
                textcoords='offset points')
    for y, cor, rot in (
            (g['entrada'], '#ffffff', f"entrada  {g['entrada']:,.{c}f}"),
            (g['stop'], '#ef5350', f"stop  {g['stop']:,.{c}f}   "
                                   f"({g['risco_pct']:.2f}% de risco)"),
            (g['alvo'], '#26a69a', f"alvo  {g['alvo']:,.{c}f}   "
                                   f"(a piscina de liquidez)")):
        ax.axhline(y, color=cor, linewidth=1.2, alpha=.92, zorder=6)
        ax.annotate(rot, (len(vel)-1, y), color=cor, fontsize=9,
                    xytext=(8, 0), textcoords='offset points', va='center')

    cara = {'alvo': '✓ bateu o alvo', 'stop': '✗ bateu o stop'}.get(
        fim[0] if fim else '', '• não resolveu')
    q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
    ax.set_title(f"{sim.replace('USDT','')}  ·  a primeira força depois da "
                 f"queda  ·  velas de {tf}h  ·  {q:%d/%m/%Y} (Brasília)  ·  "
                 f"R:R 1:{g['rr']:.2f}  ·  {cara}",
                 color='#e8eaed', fontsize=12.5, pad=14)
    ax.set_xlim(-1, len(vel) + 20)
    fig.tight_layout()
    fig.savefig(caminho, dpi=115, facecolor='#13161b')
    plt.close(fig)
    return fim[0] if fim else 'aberta'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--tf', type=int, default=24)
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
    print(f"{len(achados)} ocorrências nas {len(cru)} maiores, "
          f"velas de {a.tf}h\n")
    for k, (sim, g, h) in enumerate(achados[-a.desenhar:][::-1], 1):
        nome = f"setup4_{k}_{sim}.png"
        r = desenhar(sim, h, g, a.tf, nome)
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        print(f"  {k}. {sim:<14} {q:%d/%m/%Y}  R:R 1:{g['rr']:.2f}  "
              f"risco {g['risco_pct']:.2f}%  vela {g['tam_vela']:.1f}x  "
              f"volume cresceu {g['vol_cresce']:.1f}x  → {r}   ({nome})")


if __name__ == '__main__':
    main()
