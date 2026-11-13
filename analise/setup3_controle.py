"""A reversao de 8h ganha de uma entrada ALEATORIA igual?

O setup 3 ficou so-comprado, e foi medido entre 2023 e 2026 -- um
periodo em que cripto subiu muito. Entao a duvida: ele le algo, ou
qualquer compra com stop de 7% e alvo de 1:3,76 teria dado dinheiro?

O controle: para CADA operacao de verdade, gera N operacoes na MESMA
moeda, com o MESMO tamanho de stop em %, o MESMO risco/retorno e a
MESMA janela maxima de resolucao, entrando numa vela de 8h sorteada.
Mesma direcao (compra). Tudo igual menos o momento da entrada.

Se o setup empata com o controle, ele nao escolhe momento nenhum: o
resultado e a mare do mercado. Se ganha, a leitura e real.

Uso:  python3 setup3_controle.py <pasta> [--n 150] [--k 20]
"""
import argparse
import glob
import os
import random
import statistics
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
from cruzar_setups import reversao, resolver, dinheiro
from explosao import ler, curva, RISCO


def vol(h, ini=None, fim=None):
    v = [x[4]*x[5] for x in h
         if (ini is None or x[0] >= ini) and (fim is None or x[0] < fim)]
    return statistics.median(v) if len(v) >= 100 else 0.0


def controles(h8, stop_pct, rr, k, rng):
    """k compras aleatorias com o mesmo stop% e o mesmo R:R."""
    out = []
    lo_i, hi_i = 30, len(h8) - rev.MAX_BARRAS - 1
    if hi_i <= lo_i:
        return out
    for _ in range(k):
        i = rng.randrange(lo_i, hi_i)
        ent = h8[i][4]
        stop = ent * (1 - stop_pct/100)
        alvo = ent + (ent-stop)*rr
        fim, saida, m = resolver(h8, i, ent, stop, alvo, True, rev.MAX_BARRAS)
        if fim is None:
            continue
        out.append(dinheiro(ent, saida, stop, True, (m-i)*8))
    return out


def resumo(rot, v, larg=30):
    if not v:
        print(f"{rot:<{larg}}{'—':>6}"); return
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    print(f"{rot:<{larg}}{len(v):>6}{len(g)/len(v)*100:>9.1f}%"
          f"{statistics.mean(v):>+10.1f}{statistics.pstdev(v)/len(v)**.5:>8.1f}"
          f"{tot:>+10.0f}{dd:>9.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    ap.add_argument('--k', type=int, default=20)
    a = ap.parse_args()
    rng = random.Random(7)
    serie = {}
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            serie[os.path.basename(p).replace('_1h.csv', '')] = h
    lista = sorted(serie, key=lambda s: -vol(serie[s]))[:a.n]
    print(f"{len(serie)} pares · universo de {len(lista)} · "
          f"{a.k} controles por operação\n")

    reais, ctrl = [], []
    for s in lista:
        ops = reversao(serie[s], s)
        if not ops:
            continue
        h8 = rev.juntar(serie[s], 8)
        for o in ops:
            reais.append(o['liq'])
            ctrl += controles(h8, o['stop_pct'], o['rr'], a.k, rng)

    print(f"{'':<30}{'n':>6}{'acerto':>10}{'méd/op':>10}{'±erro':>8}"
          f"{'total':>10}{'rebaix.':>9}")
    resumo('o SETUP (só compra)', reais)
    resumo('o CONTROLE (compra aleatória)', ctrl)
    if reais and ctrl:
        d = statistics.mean(reais) - statistics.mean(ctrl)
        e = (statistics.pvariance(reais)/len(reais) +
             statistics.pvariance(ctrl)/len(ctrl)) ** .5
        print(f"\n  diferença: {d:+.1f} por operação, erro padrão {e:.1f}"
              f"  →  {d/e if e else 0:+.2f} desvios")
        print(f"  (acima de +2 desvios o setup escolhe momento de verdade;"
              f" perto de 0 ele só pega a maré)")


if __name__ == '__main__':
    main()
