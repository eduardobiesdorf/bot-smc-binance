"""O setup bate o acaso quando a conta e feita por LOTE?

As operacoes da reversao disparam em lote: 12 em 18 dias valem 69% de
todo o lucro, e 5 dos 9 lotes de 3+ operacoes tiveram acerto ZERO. Isso
quebra a hipotese de independencia que o z por operacao assume -- ele
cai de +2,47 para +1,3 quando se conta lote em vez de operacao.

O teste de entrada aleatoria (+4,51 desvios) tambem foi calculado por
operacao. Aqui ele e refeito no nivel certo:

  1. agrupa as operacoes reais em lotes (operacoes a menos de N dias)
  2. para cada lote, sorteia um INSTANTE e abre as mesmas operacoes
     naquele instante -- mesmas moedas, mesmo stop%, mesmo R:R, mesmo
     tamanho de lote. Um lote sorteado contra um lote real.
  3. compara as distribuicoes de lote

Se o setup so pega a mare, o lote sorteado rende igual. Se ele acha a
virada, o lote real ganha.

Uso:  python3 lote_controle.py <pasta> [--n 150] [--k 200]
"""
import argparse, glob, os, random, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
from explosao import ler, RISCO, TAXA, FUND8
from lista_operacoes import ops_de, vol, TRI, BRT


def resolve(hp, i, ent, stop, alvo, compra):
    for m in range(i+1, min(i+1+rev.MAX_BARRAS, len(hp))):
        hi, lo = hp[m][2], hp[m][3]
        if compra:
            if lo <= stop: return stop, m
            if hi >= alvo: return alvo, m
        else:
            if hi >= stop: return stop, m
            if lo <= alvo: return alvo, m
    return None, None


def uma(hp, i, stop_pct, rr, tf_h):
    ent = hp[i][4]
    stop = ent*(1 - stop_pct/100)
    alvo = ent + (ent-stop)*rr
    saida, m = resolve(hp, i, ent, stop, alvo, True)
    if saida is None:
        return None
    pos = RISCO/(stop_pct/100)
    mov = (saida-ent)/ent
    return pos*mov - pos*TAXA*2 - pos*((m-i)*tf_h/8)*FUND8


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    ap.add_argument('--k', type=int, default=200)
    a = ap.parse_args()
    serie = {}
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            serie[os.path.basename(p).replace('_1h.csv', '')] = h
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    cache, ops = {}, []
    t = t0 + TRI
    while t < t1:
        jan = sorted(serie, key=lambda s: -vol(serie[s], t-TRI, t))[:a.n]
        for s in jan:
            if s not in cache:
                cache[s] = ops_de(serie[s], s)
            for o in cache[s]:
                if t <= o['ms'] < t + TRI:
                    ops.append(o)
        t += TRI
    ops.sort(key=lambda o: o['q'])
    print(f"{len(ops)} operações reais\n")

    h8 = {s: rev.juntar(serie[s], rev.CFG['tf_h']) for s in {o['sim'] for o in ops}}
    tf = rev.CFG['tf_h']
    rng = random.Random(23)

    for dias in (7, 14, 30):
        lotes, at = [], [ops[0]]
        for o in ops[1:]:
            if (o['q'] - at[-1]['q']).days <= dias:
                at.append(o)
            else:
                lotes.append(at); at = [o]
        lotes.append(at)
        reais = [sum(o['liq_r'] for o in L) for L in lotes]

        # lotes sorteados: o mesmo conjunto de operacoes, instante sorteado
        sort = []
        for L in lotes:
            for _ in range(a.k):
                s_ = 0.0; ok = 0
                for o in L:
                    hp = h8[o['sim']]
                    lo_i, hi_i = 30, len(hp) - rev.MAX_BARRAS - 1
                    if hi_i <= lo_i:
                        continue
                    v = uma(hp, rng.randrange(lo_i, hi_i), o['stop_pct'],
                            o['rr'], tf)
                    if v is not None:
                        s_ += v; ok += 1
                if ok:
                    sort.append(s_ * len(L)/ok)

        mr, ms_ = statistics.mean(reais), statistics.mean(sort)
        er = statistics.pstdev(reais)/len(reais)**.5
        es = statistics.pstdev(sort)/len(sort)**.5
        d = mr - ms_
        e = (er**2 + es**2) ** .5
        print(f"  lotes de {dias} dias — {len(lotes)} lotes reais, "
              f"{len(sort)} lotes sorteados")
        print(f"    {'lote REAL':<22}méd {mr:>+8.0f}  ±{er:>5.0f}   "
              f"{sum(1 for x in reais if x>0)}/{len(reais)} positivos")
        print(f"    {'lote SORTEADO':<22}méd {ms_:>+8.0f}  ±{es:>5.0f}   "
              f"{sum(1 for x in sort if x>0)/len(sort)*100:.0f}% positivos")
        print(f"    diferença {d:>+8.0f}  ±{e:.0f}   →  "
              f"{d/e if e else 0:+.2f} DESVIOS\n")


if __name__ == '__main__':
    main()
