"""Explosao de vela unica COM os filtros achados no H8:

  - RSI depois da explosao >= 70 (na direcao da operacao)
  - a explosao estendeu >= 0.5 volatilidade antes de voltar

Mostra mes a mes, por ano, por tamanho de moeda e o teste do acaso.
Rodar no H1 e um teste fora da amostra: o filtro nasceu no H8.

Uso:  python3 explosao_filtro.py <pasta> [--tf 1,4,8] [--corte 0.32]
"""
import sys, os, glob, csv, statistics, random, argparse, itertools
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explosao import ler, curva
from explosao_mtf import varrer, BASE

RSI_MIN = 70.0
EST_MIN = 0.5


def passa(o):
    return o['rsi_depois'] >= RSI_MIN and o['estende'] >= EST_MIN


def pior_seq(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, larg=32):
    if not sel:
        print(f"{rot:<{larg}}{'—':>6}"); return
    v = [o['liq'] for o in sel]
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    p25 = [o['liq'] for o in sel if o['ano'] == 2025]
    p26 = [o['liq'] for o in sel if o['ano'] == 2026]
    print(f"{rot:<{larg}}{len(v):>6}{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(v):>+10.1f}{tot:>+10.0f}{dd:>9.0f}"
          f"{pior_seq(v):>7}"
          f"{(statistics.mean(p25) if p25 else 0):>+11.1f}"
          f"{(statistics.mean(p26) if p26 else 0):>+11.1f}")


def cab(larg=32):
    print(f"{'':<{larg}}{'n':>6}{'acerto':>9}{'méd/op':>10}{'total':>10}"
          f"{'pior rb':>9}{'seq':>7}{'2025':>11}{'2026':>11}")


def nulo(sel):
    if len(sel) < 25:
        return None
    v = [o['liq'] for o in sel]
    random.seed(5)
    n = [statistics.mean([x if random.random() < .5 else -x for x in v])
         for _ in range(300)]
    dp = statistics.pstdev(n) or 1e-9
    return (statistics.mean(v) - statistics.mean(n)) / dp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--tf', default='1,4,8')
    ap.add_argument('--corte', type=float, default=0.32,
                    help='volume mediano mínimo, em milhões de USD por hora')
    ap.add_argument('--csv', default='')
    a = ap.parse_args()

    cru, fora = [], 0
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) < 400:
            continue
        vm = statistics.median(v[4] * v[5] for v in h)
        if vm < a.corte * 1e6:
            fora += 1; continue
        cru.append((os.path.basename(p).replace('_1h.csv', ''), h, vm))
    cru.sort(key=lambda x: -x[2])
    n3 = max(1, len(cru) // 3)
    faixa = {s: ('1 maiores' if k < n3 else
                 '2 do meio' if k < 2*n3 else '3 menores')
             for k, (s, _, _) in enumerate(cru)}
    print(f"{len(cru)} moedas com volume mediano ≥ {a.corte:.2f} M USD/h "
          f"({fora} ficaram de fora)")
    if cru:
        print(f"  da maior ({cru[0][0]}, {cru[0][2]/1e6:,.0f} M/h) "
              f"à menor ({cru[-1][0]}, {cru[-1][2]/1e6:,.2f} M/h)")

    for tf in [int(x) for x in a.tf.split(',')]:
        ops = []
        for sim, h1, vm in cru:
            for r in varrer(sim, h1, tf, BASE):
                if r['grande']:
                    ops.append(dict(r['grande'], sim=sim, faixa=faixa[sim],
                                    rsi_depois=r['rsi_depois'],
                                    estende=r['estende'],
                                    mes=r['grande']['q'].strftime('%Y-%m')))
        ops.sort(key=lambda o: o['q'])
        sel = [o for o in ops if passa(o)]
        print(f"\n{'='*104}")
        print(f"  H{tf} — {len(ops)} setups, {len(sel)} passam no filtro "
              f"(RSI depois ≥ {RSI_MIN:.0f} e estendeu ≥ {EST_MIN} vol.)")
        print('='*104)
        cab()
        painel('sem filtro', ops)
        painel('COM o filtro', sel)
        painel('  os que o filtro descartou',
               [o for o in ops if not passa(o)])
        z = nulo(sel)
        if z is not None:
            print(f"  teste do acaso no filtrado: z = {z:+.2f}")
        if len(sel) < 25:
            continue

        print(f"\n  mês a mês, já filtrado:")
        print(f"  {'mês':<9}{'n':>4}{'gain':>6}{'loss':>6}{'acerto':>8}"
              f"{'resultado':>12}{'acumulado':>12}")
        ac = 0.0
        for m in sorted({o['mes'] for o in sel}):
            v = [o for o in sel if o['mes'] == m]
            g = sum(1 for o in v if o['liq'] > 0)
            s = sum(o['liq'] for o in v); ac += s
            print(f"  {m:<9}{len(v):>4}{g:>6}{len(v)-g:>6}"
                  f"{g/len(v)*100:>7.1f}%{s:>+12.0f}{ac:>+12.0f}")

        print(f"\n  por tamanho de moeda, já filtrado:")
        cab()
        for rot in ('1 maiores', '2 do meio', '3 menores'):
            painel(f'  {rot}', [o for o in sel if o['faixa'] == rot])

        if a.csv:
            nome = f"{a.csv}_h{tf}.csv"
            with open(nome, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['data_brasilia', 'par', 'entrada', 'stop',
                            'stop_pct', 'risco_retorno', 'rsi_depois',
                            'estendeu_vol', 'fim', 'horas',
                            'resultado_usd', 'acumulado_usd'])
                ac = 0.0
                for o in sel:
                    ac += o['liq']
                    w.writerow([f"{o['q']:%Y-%m-%d %H:%M}", o['sim'],
                                f"{o['ent']:.8g}", f"{o['stop']:.8g}",
                                f"{o['risco_pct']:.2f}", f"{o['rr']:.2f}",
                                f"{o['rsi_depois']:.1f}",
                                f"{o['estende']:.2f}", o['fim'], o['horas'],
                                f"{o['liq']:.2f}", f"{ac:.2f}"])
            print(f"  csv: {nome}")


if __name__ == '__main__':
    main()
