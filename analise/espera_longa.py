"""Esperar mais pelo encosto, e levar o padrao para o diario.

Duas perguntas do Eduardo:

  1. a espera pelo encosto hoje e de 30 dias (90 velas de 8h). E se
     for 60, 90, 120, 150?
  2. a mesma estrategia com velas DIARIAS, tambem com espera longa.
     A reversao ja foi testada em H4, H2, H1 e 5 minutos -- todas
     bruto negativo ou zero. O diario nunca foi testado, e o gradiente
     favorece: se tem algo acima de 8 horas, e la.

Duas leituras do diario, como no teste de 5 minutos:

  fractal   as mesmas CONTAGENS de vela do H8: queda em 20 velas (agora
            20 dias), pivo de +-2 dias, busca de 30 dias. O desenho
            identico, so que maior.
  ancorado  os mesmos TEMPOS do H8: queda em 160 horas (~7 dias), pivo
            de +-1 dia, busca de 10 dias. O mesmo contexto.

TUDO medido no universo ROLANTE e so compra, porque desde 13/11 nenhum
resultado conta antes disso.

Uso:  python3 espera_longa.py <pasta> [--n 150]
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
from explosao import ler, curva, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))
TRI = 90*24*3600_000


def cfg_de(tf_h, dias, modo='fractal'):
    """O cfg para um tempo grafico e uma espera em dias."""
    c = dict(rev.CFG)
    c['tf_h'] = tf_h
    c['espera'] = round(dias*24/tf_h)
    if tf_h != 8:
        if modo == 'fractal':
            pass                      # mantem as contagens do H8
        else:
            c['tend_jan'] = max(5, round(160/tf_h))
            c['busca_topo'] = max(5, round(240/tf_h))
            c['pivo'] = max(1, round(16/tf_h))
    return c


def rodar(h1, sim, cfg):
    """As operacoes como o bot as acha: padrao no tf, gatilho no H1."""
    hp = rev.juntar(h1, cfg['tf_h'])
    if len(hp) < 60:
        return []
    mv1 = e8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    tp = [v[0] for v in hp]
    ops = []
    for e in rev.explosoes(hp, cfg):
        g = rev.entrada(h1, mv1, e, cfg, pos1)
        if not g:
            continue
        compra = g['lado'] == 'compra'
        risco = abs(g['entrada'] - g['stop'])
        # resolve nas velas do proprio tf, como o bot faz
        i = max(k for k, t in enumerate(tp) if t <= g['vela_ms'])
        fim = saida = None
        for m in range(i+1, min(i+1+rev.MAX_BARRAS, len(hp))):
            hi, lo = hp[m][2], hp[m][3]
            if compra:
                if lo <= g['stop']: fim, saida = 'stop', g['stop']; break
                if hi >= g['alvo']: fim, saida = 'alvo', g['alvo']; break
            else:
                if hi >= g['stop']: fim, saida = 'stop', g['stop']; break
                if lo <= g['alvo']: fim, saida = 'alvo', g['alvo']; break
        if fim is None:
            continue
        pos = RISCO/(risco/g['entrada'])
        mov = (saida-g['entrada'])/g['entrada']*(1 if compra else -1)
        horas = (m-i)*cfg['tf_h']
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        ops.append(dict(sim=sim, q=q, ano=q.year, rr=g['rr'],
                        stop_pct=g['risco_pct'], ms=g['vela_ms'],
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return ops


def vol(h, ini=None, fim=None):
    v = [x[4]*x[5] for x in h
         if (ini is None or x[0] >= ini) and (fim is None or x[0] < fim)]
    return statistics.median(v) if len(v) >= 100 else 0.0


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, meses, larg=30):
    if not sel:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in sel]
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    anos = sorted({o['ano'] for o in sel})
    por, bons = [], 0
    for y in anos:
        vy = [o['liq'] for o in sel if o['ano'] == y]
        m = statistics.mean(vy); bons += m > 0
        por.append(f"{str(y)[2:]}:{m:+.0f}({len(vy)})")
    z = ''
    if len(v) >= 25:
        random.seed(3)
        nu = [statistics.mean([x if random.random() < .5 else -x for x in v])
              for _ in range(300)]
        z = f"{(statistics.mean(v)-statistics.mean(nu))/(statistics.pstdev(nu) or 1e-9):+.2f}"
    print(f"{rot:<{larg}}{len(v):>5}{len(v)/meses:>6.1f}"
          f"{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(o['rr'] for o in sel):>7.2f}"
          f"{statistics.mean(o['stop_pct'] for o in sel):>7.2f}%"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{z:>8}{bons}/{len(anos)}  {' '.join(por)}")


def cab(larg=30):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>9}{'R:R':>7}{'stop':>8}"
          f"{'líq/op':>9}{'total':>9}{'rb':>8}{'seq':>5}{'z':>8}{'anos+':>4}"
          f"  por ano")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    a = ap.parse_args()
    serie = {}
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            serie[os.path.basename(p).replace('_1h.csv', '')] = h
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    meses = (t1-t0)/(1000*3600*24*30.4)
    print(f"{len(serie)} pares · {meses:.0f} meses · universo ROLANTE de "
          f"{a.n} · só compra\n")

    # as janelas trimestrais, calculadas uma vez
    janelas = []
    t = t0 + TRI
    while t < t1:
        janelas.append((t, sorted(serie, key=lambda s: -vol(serie[s], t-TRI, t))[:a.n]))
        t += TRI

    def rolante(cfg):
        cache, ops = {}, []
        for t, jan in janelas:
            for s in jan:
                if s not in cache:
                    cache[s] = rodar(serie[s], s, cfg)
                for o in cache[s]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"{'='*140}\n  1) ESPERAR MAIS PELO ENCOSTO — padrão em H8\n{'='*140}")
    cab()
    for d in (30, 60, 90, 120, 150):
        cfg = cfg_de(8, d)
        painel(f'H8 · espera {d} dias' + ('  ← hoje' if d == 30 else ''),
               rolante(cfg), meses)

    print(f"\n{'='*140}\n  2) O DIÁRIO — mesmas contagens de vela (fractal)\n"
          f"{'='*140}")
    cab()
    for d in (30, 60, 90, 120, 150):
        painel(f'D1 fractal · espera {d} dias', rolante(cfg_de(24, d)), meses)

    print(f"\n{'='*140}\n  3) O DIÁRIO — mesmos tempos do H8 (ancorado)\n"
          f"{'='*140}")
    cab()
    for d in (30, 60, 90, 120, 150):
        painel(f'D1 ancorado · espera {d} dias',
               rolante(cfg_de(24, d, 'ancorado')), meses)

    print(f"\n{'='*140}\n  4) E O 12h, que fica no meio?\n{'='*140}")
    cab()
    for d in (30, 90, 150):
        painel(f'12h · espera {d} dias', rolante(cfg_de(12, d)), meses)


if __name__ == '__main__':
    main()
