"""Quantos avisos de encosto o bot mandaria, e quantos viram entrada.

O bot roda de hora em hora. Um aviso de encosto sai na primeira rodada
depois que o preco toca a borda do order block -- desde que o setup nao
morra na propria vela do toque. Conta isso, e quanto vira gatilho.

Uso:  python3 encostos_quantos.py <pasta> [--n 150]
"""
import argparse, glob, os, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler

BRT = dt.timezone(dt.timedelta(hours=-3))


def conta(h1, cfg):
    """(explosoes, avisos de encosto, gatilhos, horas do toque ao gatilho)"""
    h8 = rev.juntar(h1, 8)
    if len(h8) < 60:
        return 0, 0, 0, []
    mv1 = e8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    nexp = nenc = ngat = 0
    esperas = []
    for e in rev.explosoes(h8, cfg):
        nexp += 1
        alta = e['alta']
        k0 = pos1.get(e['fim_ms'])
        if k0 is None:
            continue
        borda = e['ob_topo'] if alta else e['ob_base']
        meio = (e['ob_base'] + e['ob_topo']) / 2
        morte = (e['ob_base'] - e['atr']*cfg['furo_max']) if alta else \
                (e['ob_topo'] + e['atr']*cfg['furo_max'])
        pico, tocou, extremo, avisou = e['topo'], None, None, False
        for k in range(k0, min(k0 + cfg['espera']*8, len(h1))):
            hi, lo, o, cl = h1[k][2], h1[k][3], h1[k][1], h1[k][4]
            if tocou is None:
                pico = max(pico, hi) if alta else min(pico, lo)
                if (lo <= borda) if alta else (hi >= borda):
                    tocou, extremo = k, (lo if alta else hi)
                else:
                    continue
            else:
                extremo = min(extremo, lo) if alta else max(extremo, hi)
            morreu = ((extremo < morte) if alta else (extremo > morte)) or \
                     (k - tocou > cfg['gat_h1']) or \
                     ((hi >= pico) if alta else (lo <= pico)) or \
                     ((extremo < meio) if alta else (extremo > meio))
            rng = hi - lo
            gat = False
            if rng > 0 and ((cl > borda) if alta else (cl < borda)) and \
                    ((cl > o) if alta else (cl < o)):
                corpo = abs(cl-o)/rng
                pav = ((min(o, cl)-lo) if alta else (hi-max(o, cl)))/rng
                gat = (corpo >= 0.5 or pav >= 0.5) and \
                      not (mv1[k] > 0 and h1[k][5] < cfg['vol_gat']*mv1[k])
            # o bot ve o estado no FECHAMENTO da vela: se nao morreu e
            # nao disparou, ele avisa "encostou"
            if not avisou and not morreu and not gat:
                nenc += 1
                avisou = True
            if gat and not morreu:
                ngat += 1
                esperas.append(k - tocou)
                break
            if morreu:
                break
    return nexp, nenc, ngat, esperas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h,
                        statistics.median(v[4]*v[5] for v in h)))
    cru.sort(key=lambda x: -x[2])
    cru = cru[:a.n]
    meses = max(len(h) for _, h, _ in cru) / (24*30.4)
    E = N = G = 0
    esp = []
    for sim, h1, _ in cru:
        x, y, z, w = conta(h1, rev.CFG)
        E += x; N += y; G += z; esp += w
    print(f"as {len(cru)} maiores · {meses:.0f} meses · só compra\n")
    print(f"  explosões que armam o padrão   {E:>5}  "
          f"{E/meses:>5.1f} por mês")
    print(f"  avisos de ENCOSTO              {N:>5}  "
          f"{N/meses:>5.1f} por mês   "
          f"({N/E*100 if E else 0:.0f}% das explosões chegam a encostar)")
    print(f"  gatilhos (a entrada de fato)   {G:>5}  "
          f"{G/meses:>5.1f} por mês   "
          f"({G/N*100 if N else 0:.0f}% dos encostos viram entrada)")
    if esp:
        esp.sort()
        print(f"\n  do encosto ao gatilho: mediana {esp[len(esp)//2]}h, "
              f"média {statistics.mean(esp):.0f}h, "
              f"máximo {max(esp)}h (o limite é {rev.CFG['gat_h1']}h)")
        print(f"  ou seja, o aviso de encosto te dá "
              f"{esp[len(esp)//2]}h de antecedência na mediana")


if __name__ == '__main__':
    main()
