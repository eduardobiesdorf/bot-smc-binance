"""Tres perguntas sobre a explosao de vela unica:

  1. quantos gatilhos disparam juntos, e o resultado piora quando isso
     acontece?
  2. o padrao funciona em H12 e no diario?
  3. os tempos graficos estao vendo eventos DIFERENTES ou o mesmo
     evento contado varias vezes?

Uso:  python3 explosao_simultaneo.py <pasta> [--corte 0.32]
"""
import sys, os, glob, csv, statistics, random, itertools, bisect, argparse
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explosao import ler, curva
from explosao_mtf import varrer, BASE

TFS = [(4, 'H4'), (8, 'H8'), (12, 'H12'), (24, 'Diário')]
CFG = dict(BASE, proj=0.9, proj_de='vela', rr_no_topo=True)
JUNTO_H = 24          # "ao mesmo tempo" = entradas dentro dessa janela


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def z_nulo(v):
    if len(v) < 25:
        return None
    random.seed(3)
    n = [statistics.mean([x if random.random() < .5 else -x for x in v])
         for _ in range(300)]
    dp = statistics.pstdev(n) or 1e-9
    return (statistics.mean(v) - statistics.mean(n)) / dp


def painel(rot, sel, larg=26):
    if not sel:
        print(f"{rot:<{larg}}{'—':>6}"); return
    v = [o['liq'] for o in sel]
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    p25 = [o['liq'] for o in sel if o['ano'] == 2025]
    p26 = [o['liq'] for o in sel if o['ano'] == 2026]
    z = z_nulo(v)
    print(f"{rot:<{larg}}{len(v):>5}{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(v):>+10.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{(statistics.mean(p25) if p25 else 0):>+9.1f}{len(p25):>5}"
          f"{(statistics.mean(p26) if p26 else 0):>+9.1f}{len(p26):>5}"
          f"{(f'{z:+.2f}' if z is not None else '—'):>8}")


def cab(larg=26):
    print(f"{'':<{larg}}{'n':>5}{'acerto':>9}{'méd/op':>10}{'total':>9}"
          f"{'rb':>8}{'seq':>5}{'2025':>9}{'n25':>5}{'2026':>9}{'n26':>5}"
          f"{'z':>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--corte', type=float, default=0.32)
    a = ap.parse_args()

    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) < 400:
            continue
        vm = statistics.median(v[4]*v[5] for v in h)
        if vm >= a.corte*1e6:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h))
    print(f"{len(cru)} moedas com volume mediano ≥ {a.corte:.2f} M USD/h")

    porv = {}
    for tf, nome in TFS:
        ops = []
        for sim, h1 in cru:
            for r in varrer(sim, h1, tf, CFG):
                g = r['grande']
                if g and r['rsi_depois'] >= 70 and r['estende'] >= 0.5:
                    ops.append(dict(g, sim=sim, ms_exp=r['ms_exp'],
                                    ms_ent=int(g['q'].timestamp()*1000)))
        ops.sort(key=lambda o: o['q'])
        porv[nome] = ops

    # ---------------------------------------------- 2) por tempo grafico
    print(f"\n{'='*112}\n  O PADRÃO EM CADA TEMPO GRÁFICO\n{'='*112}")
    cab()
    for tf, nome in TFS:
        painel(f'{nome}  ({len(porv[nome])/23:.1f} por mês)', porv[nome])

    # ------------------------------------- 1) quantos disparam ao mesmo tempo
    for tf, nome in TFS:
        ops = porv[nome]
        if len(ops) < 30:
            continue
        tempos = sorted(o['ms_ent'] for o in ops)
        for o in ops:
            t = o['ms_ent']
            o['junto'] = (bisect.bisect_right(tempos, t + JUNTO_H*3600_000)
                          - bisect.bisect_left(tempos, t - JUNTO_H*3600_000))
        print(f"\n{'-'*112}\n  {nome}: quantos gatilhos no universo inteiro "
              f"dentro de ±{JUNTO_H}h do gatilho\n{'-'*112}")
        cab()
        for lo, hi, rot in ((1, 1, 'sozinho'), (2, 2, 'com mais 1'),
                            (3, 4, 'com mais 2 a 3'),
                            (5, 8, 'com mais 4 a 7'),
                            (9, 999, 'com mais 8 ou mais')):
            painel(f'  {rot}',
                   [o for o in ops if lo <= o['junto'] <= hi])
        d = sorted(o['junto'] for o in ops)
        print(f"  mediana: {statistics.median(d):.0f} gatilhos na janela · "
              f"máximo: {max(d)} · "
              f"{sum(1 for x in d if x == 1)/len(d)*100:.0f}% vêm sozinhos")

    # --------------------------------- 3) os tempos graficos se repetem?
    print(f"\n{'='*112}\n  OS TEMPOS GRÁFICOS VEEM O MESMO EVENTO?\n"
          f"  (mesma moeda, explosões a menos de 24h uma da outra)\n{'='*112}")
    nomes = [n for _, n in TFS]
    print(f"{'':<10}" + ''.join(f"{n:>12}" for n in nomes))
    for na in nomes:
        A = porv[na]
        linha = f"{na:<10}"
        for nb in nomes:
            if na == nb:
                linha += f"{len(A):>12}"
                continue
            B = {}
            for o in porv[nb]:
                B.setdefault(o['sim'], []).append(o['ms_exp'])
            for v in B.values():
                v.sort()
            rep = 0
            for o in A:
                v = B.get(o['sim'])
                if not v:
                    continue
                i = bisect.bisect_left(v, o['ms_exp'] - 24*3600_000)
                if i < len(v) and v[i] <= o['ms_exp'] + 24*3600_000:
                    rep += 1
            linha += f"{rep/len(A)*100:>11.0f}%"
        print(linha)
    print("  lê-se: da linha, quantos % têm um equivalente na coluna")

    # quanto do dinheiro viria de eventos unicos se rodasse H4+H8+H12+D
    todos = []
    for _, n in TFS:
        for o in porv[n]:
            todos.append(dict(o, tfn=n))
    todos.sort(key=lambda o: o['ms_exp'])
    vistos, unicos = {}, []
    for o in todos:
        v = vistos.setdefault(o['sim'], [])
        if any(abs(x - o['ms_exp']) <= 24*3600_000 for x in v):
            continue
        v.append(o['ms_exp']); unicos.append(o)
    print(f"\n  rodando os quatro juntos: {len(todos)} alertas no total, "
          f"mas só {len(unicos)} eventos distintos "
          f"({(1-len(unicos)/len(todos))*100:.0f}% seriam repetição)")
    cab()
    painel('  os 4 juntos, sem filtrar', todos)
    painel('  só os eventos distintos', unicos)


if __name__ == '__main__':
    main()
