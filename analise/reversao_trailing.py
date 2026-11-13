"""O stop movel por estrutura aplicado a reversao de 8h.

A mesma regra que ja roda no setup 1: enquanto o preco anda a favor,
quando o mercado completa a estrutura A-B-C-D-E-F na direcao da
operacao, o stop sobe para alem do extremo de E. So move se travar pelo
menos MIN_TRAVA do risco original.

O risco e SEMPRE medido pelo stop ORIGINAL -- senao o trailing faria as
perdas parecerem menores do que foram.

Uso:  python3 reversao_trailing.py <pasta> [--n 150]
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
import reversao8 as rev
import explosao8 as e8
import acompanhamento as acomp
from explosao import ler, curva, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))
FOLGA_ATR = 0.25


def operacoes(h1, cru_sim):
    """Os gatilhos da reversao, como o bot os acha."""
    h8 = rev.juntar(h1, 8)
    if len(h8) < 60:
        return [], h8
    mv1 = e8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    out = []
    for e in rev.explosoes(h8, rev.CFG):
        g = rev.entrada(h1, mv1, e, rev.CFG, pos1)
        if g:
            out.append(g)
    return out, h8


def resolver(serie, i0, ent, stop0, alvo, alta, tfh, estr=None,
             trava=0.30, maxh=960):
    """Caminha ate o desfecho. Com estr, o stop pode subir no caminho."""
    risco = abs(ent - stop0)
    stop = stop0
    a = e8.atr(serie, 14)
    n = 0
    for m in range(i0+1, len(serie)):
        n += tfh
        if n > maxh:
            return 'tempo', serie[m][4], n, stop != stop0
        hi, lo = serie[m][2], serie[m][3]
        if alta:
            if lo <= stop: return 'stop', stop, n, stop != stop0
            if hi >= alvo: return 'alvo', alvo, n, stop != stop0
        else:
            if hi >= stop: return 'stop', stop, n, stop != stop0
            if lo <= alvo: return 'alvo', alvo, n, stop != stop0
        # move o stop DEPOIS de testar a vela: a estrutura so e
        # conhecida no fechamento dela
        if estr is not None:
            s = estr.get(m)
            if s and s['alta'] == alta:
                novo = s['extremo'] - a[m]*FOLGA_ATR if alta else \
                       s['extremo'] + a[m]*FOLGA_ATR
                ganho = (novo - stop) if alta else (stop - novo)
                if ganho > 0 and abs(novo - stop0)/risco >= trava:
                    stop = novo
    return None, None, None, False


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, larg=34):
    if not sel:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in sel]
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    anos = sorted({o['ano'] for o in sel})
    por, bons = [], 0
    for y in anos:
        vy = [o['liq'] for o in sel if o['ano'] == y]
        m = statistics.mean(vy)
        bons += m > 0
        por.append(f"{str(y)[2:]}:{m:+.0f}({len(vy)})")
    mov = sum(1 for o in sel if o.get('moveu'))
    z = ''
    if len(v) >= 25:
        random.seed(3)
        nu = [statistics.mean([x if random.random() < .5 else -x for x in v])
              for _ in range(300)]
        z = f"{(statistics.mean(v)-statistics.mean(nu))/(statistics.pstdev(nu) or 1e-9):+.2f}"
    print(f"{rot:<{larg}}{len(v):>5}{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(v):>+10.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{mov:>6}{z:>8}{bons}/{len(anos)}  {' '.join(por)}")


def cab(larg=34):
    print(f"{'':<{larg}}{'n':>5}{'acerto':>9}{'méd/op':>10}{'total':>9}"
          f"{'rb':>8}{'seq':>5}{'moveu':>6}{'z':>8}{'anos+':>4}  por ano")


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
    print(f"as {len(cru)} maiores\n")

    VAR = [('sem stop móvel (como está)', None, None, 0),
           ('trailing em H8 · trava 0,30', 8, 1, 0.30),
           ('trailing em H8 · trava 0,50', 8, 1, 0.50),
           ('trailing em H8 · move sempre', 8, 1, 0.0),
           ('trailing em H1 · trava 0,30', 1, 1, 0.30),
           ('trailing em H1 · trava 0,50', 1, 1, 0.50),
           ('trailing em H1 · pivô 2 velas', 1, 2, 0.30)]
    res = {r: [] for r, _, _, _ in VAR}
    for sim, h1, _ in cru:
        ops, h8 = operacoes(h1, sim)
        if not ops:
            continue
        e8h = acomp.estruturas(h8, 1, 20, 12)
        e8h2 = acomp.estruturas(h8, 2, 20, 12)
        e1h = acomp.estruturas(h1, 1, 20, 12)
        e1h2 = acomp.estruturas(h1, 2, 20, 12)
        t8 = [v[0] for v in h8]
        for g in ops:
            alta = g['lado'] == 'compra'
            risco = abs(g['entrada'] - g['stop'])
            i8 = max(k for k, v in enumerate(h8) if v[0] <= g['vela_ms'])
            for rot, tf, kp, trava in VAR:
                if tf is None:
                    serie, i0, tfh, estr = h8, i8, 8, None
                elif tf == 8:
                    serie, i0, tfh = h8, i8, 8
                    estr = e8h if kp == 1 else e8h2
                else:
                    serie, i0, tfh = h1, g['idx'], 1
                    estr = e1h if kp == 1 else e1h2
                fim, saida, horas, moveu = resolver(
                    serie, i0, g['entrada'], g['stop'], g['alvo'], alta,
                    tfh, estr, trava)
                if fim is None:
                    continue
                pos = RISCO/(risco/g['entrada'])
                mov = (saida-g['entrada'])/g['entrada']*(1 if alta else -1)
                q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
                res[rot].append(dict(
                    q=q, ano=q.year, moveu=moveu,
                    liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    cab()
    for rot, _, _, _ in VAR:
        v = sorted(res[rot], key=lambda o: o['q'])
        painel(rot, v)


if __name__ == '__main__':
    main()
