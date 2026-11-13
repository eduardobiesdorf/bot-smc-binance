"""O setup 1 com o universo escolhido SEM olhar o futuro.

O problema: UNIVERSO[:50] no bot_varredura sao as 50 maiores de
NOVEMBRO DE 2026. Rodar 2023-2026 nessa lista e escolher o time depois
de ver o campeonato -- HYPE, ENA, TRUMP, PUMP, ASTER, PENGU, XPL,
VIRTUAL, WLFI e RE estao la porque cresceram, e as moedas que morreram
no caminho nao estao em lista nenhuma.

Tres universos, do mais viciado ao mais honesto:

  hoje      UNIVERSO[:50], a lista do bot. Sabe o futuro inteiro.
  periodo   as 50 maiores pelo volume mediano de TODO o periodo. Ainda
            sabe quem sobreviveu, mas inclui quem era grande em 2023.
  passado   as 50 maiores pelo volume dos 6 primeiros meses apenas.
            Escolhido em jan/2023 com o que se sabia em jan/2023.
  rolante   a cada trimestre, as 50 maiores pelo volume do trimestre
            ANTERIOR, e so conta as operacoes daquele trimestre. E o
            que o bot faz com --dinamico, e e a simulacao de verdade.

Uso:  python3 setup1_honesto.py <pasta>
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
from explosao import ler, curva
from setup1_real import rodar, cab, painel

BRT = dt.timezone(dt.timedelta(hours=-3))
TRI = 90*24*3600_000      # um trimestre em milissegundos


def vol(h, ini=None, fim=None):
    v = [x[4]*x[5] for x in h
         if (ini is None or x[0] >= ini) and (fim is None or x[0] < fim)]
    return statistics.median(v) if len(v) >= 100 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=50)
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
    print(f"{len(serie)} pares com dado · {meses:.0f} meses\n")

    hoje = [s for s in bot.UNIVERSO[:a.n] if s in serie]
    periodo = sorted(serie, key=lambda s: -vol(serie[s]))[:a.n]
    # quem ja existia em jan/2023 e era grande LA
    passado = sorted((s for s in serie if serie[s][0][0] <= t0 + 7*24*3600_000),
                     key=lambda s: -vol(serie[s], t0, seis))[:a.n]
    print(f"  lista de hoje  : {len(hoje)} moedas")
    print(f"  pelo período   : {len(periodo)} moedas · "
          f"{len(set(periodo) & set(hoje))} em comum com a de hoje")
    print(f"  pelo passado   : {len(passado)} moedas · "
          f"{len(set(passado) & set(hoje))} em comum com a de hoje")
    print(f"    entram:  {', '.join(sorted(set(passado)-set(hoje))[:12])} ...")
    print(f"    saem:    {', '.join(sorted(set(hoje)-set(passado))[:12])} ...")
    print()

    CFG = dict(bot.CFG)
    cab()
    for rot, lista, sm in (
            ('hoje (a lista do bot)',        hoje,    0.0),
            ('  hoje + stop >= 3%',          hoje,    3.0),
            ('período (sabe quem sobreviveu)', periodo, 0.0),
            ('  período + stop >= 3%',       periodo, 3.0),
            ('PASSADO (escolhido em 2023)',  passado, 0.0),
            ('  PASSADO + stop >= 3%',       passado, 3.0),
    ):
        ops = []
        for s in lista:
            ops += rodar(serie[s], s, CFG, trailing=True, stop_min=sm)
        ops.sort(key=lambda o: o['q'])
        painel(rot, ops, meses)

    # --- rolante: a cada trimestre, as 50 maiores do trimestre anterior
    print(f"\n  ROLANTE — a cada trimestre, as {a.n} maiores do trimestre")
    print(f"  anterior. Nenhuma informação do futuro em nenhum momento.")
    cab()
    for sm in (0.0, 1.5, 3.0, 4.0):
        ops = []
        t = t0 + TRI
        while t < t1:
            jan = sorted(serie, key=lambda s: -vol(serie[s], t-TRI, t))[:a.n]
            for s in jan:
                for o in rodar(serie[s], s, CFG, trailing=True, stop_min=sm):
                    ms = o['q'].timestamp()*1000
                    if t <= ms < t + TRI:
                        ops.append(o)
            t += TRI
        ops.sort(key=lambda o: o['q'])
        painel(f'  rolante + stop >= {sm:.1f}%' if sm else '  rolante, sem filtro',
               ops, meses)


if __name__ == '__main__':
    main()
