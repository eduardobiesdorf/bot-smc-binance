"""A reversao de 8h com o universo escolhido SEM olhar o futuro.

O setup 1 nao sobreviveu a esse teste: +$9,40/op na lista de hoje,
-$1,00/op no universo rolante. A reversao de 8h foi medida nas "150
maiores por volume mediano do periodo", que tambem sabe quem sobreviveu
-- entao carrega o mesmo vicio, em grau desconhecido. Este script mede.

  periodo   as N maiores pelo volume mediano de todo o periodo (como foi
            medido ate agora)
  passado   as N maiores pelo volume dos 6 primeiros meses, escolhidas
            em jan/2023 com o que se sabia em jan/2023
  rolante   a cada trimestre, as N maiores pelo volume do trimestre
            ANTERIOR, contando so as operacoes do trimestre seguinte

Uso:  python3 setup3_honesto.py <pasta> [--n 150]
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
import bot_varredura as bot
from cruzar_setups import reversao
from explosao import ler, curva

BRT = dt.timezone(dt.timedelta(hours=-3))
TRI = 90*24*3600_000


def vol(h, ini=None, fim=None):
    v = [x[4]*x[5] for x in h
         if (ini is None or x[0] >= ini) and (fim is None or x[0] < fim)]
    return statistics.median(v) if len(v) >= 100 else 0.0


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, meses, larg=32):
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
    comp = sum(1 for o in sel if o['lado'] == 'compra')
    print(f"{rot:<{larg}}{len(v):>5}{len(v)/meses:>6.1f}"
          f"{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(o['rr'] for o in sel):>7.2f}"
          f"{statistics.mean(o['stop_pct'] for o in sel):>7.2f}%"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{comp/len(v)*100:>7.0f}%{z:>8}{bons}/{len(anos)}  {' '.join(por)}")


def cab(larg=32):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>9}{'R:R':>7}{'stop':>8}"
          f"{'líq/op':>9}{'total':>9}{'rb':>8}{'seq':>5}{'compra':>8}"
          f"{'z':>8}{'anos+':>4}  por ano")


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
    seis = t0 + 180*24*3600_000
    print(f"{len(serie)} pares com dado · {meses:.0f} meses · "
          f"universos de {a.n}\n")

    periodo = sorted(serie, key=lambda s: -vol(serie[s]))[:a.n]
    passado = sorted((s for s in serie if serie[s][0][0] <= t0 + 7*24*3600_000),
                     key=lambda s: -vol(serie[s], t0, seis))[:a.n]
    print(f"  pelo período: {len(periodo)} · pelo passado: {len(passado)} · "
          f"{len(set(periodo) & set(passado))} em comum\n")

    cache = {}

    def ops_de(s):
        if s not in cache:
            cache[s] = reversao(serie[s], s)
        return cache[s]

    cab()
    for rot, lista in (('PERÍODO (como foi medido)', periodo),
                       ('PASSADO (escolhido em 2023)', passado),
                       ('todas as moedas com dado', list(serie))):
        ops = []
        for s in lista:
            ops += ops_de(s)
        ops.sort(key=lambda o: o['q'])
        painel(rot, ops, meses)

    print(f"\n  ROLANTE — a cada trimestre, as {a.n} maiores do trimestre")
    print(f"  anterior. Nenhuma informação do futuro em nenhum momento.")
    cab()
    for n in (50, 150, 300):
        ops = []
        t = t0 + TRI
        while t < t1:
            jan = sorted(serie, key=lambda s: -vol(serie[s], t-TRI, t))[:n]
            for s in jan:
                for o in ops_de(s):
                    ms = o['q'].timestamp()*1000
                    if t <= ms < t + TRI:
                        ops.append(o)
            t += TRI
        ops.sort(key=lambda o: o['q'])
        painel(f'  rolante · {n} maiores', ops, meses)


if __name__ == '__main__':
    main()
