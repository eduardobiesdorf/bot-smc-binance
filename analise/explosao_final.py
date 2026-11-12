"""A configuracao escolhida da explosao de vela unica, aberta mes a mes.

  tempo grafico  velas de 8 horas
  explosao       UMA vela, >= 2,5x a volatilidade media de 14, corpo >=
                 50%, volume >= 1,5x a media de 20, fechando alem do
                 extremo das ultimas 20 velas
  filtros        RSI(14) depois da explosao >= 70 (na direcao da
                 operacao) e extensao >= 0,5 volatilidade antes de voltar
  order block    ultima vela de cor contraria antes da explosao
  entrada        o preco ENCOSTA no order block e uma vela fecha de volta
                 para fora, a favor -- entrada no fechamento dela
  stop           logo abaixo da base do order block
  alvo           topo da vela de explosao + 90% do tamanho dela
  risco          $100 fixos por operacao; a posicao sai dessa conta

Uso:  python3 explosao_final.py <pasta> [--faixas 4] [--alvo 0.9]
"""
import sys, os, glob, csv, statistics, random, itertools, argparse
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explosao import ler, curva, RISCO, TAXA, FUND8
from explosao_mtf import varrer, BASE

TF = 8
RSI_MIN, EST_MIN = 70.0, 0.5


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


def mes_a_mes(titulo, sel, meses):
    print(f"\n{'='*84}\n  {titulo}\n{'='*84}")
    if not sel:
        print("  nenhuma operação"); return
    print(f"  {len(sel)} operações em {len(meses)} meses = "
          f"{len(sel)/len(meses):.1f} por mês")
    print(f"  {'mês':<9}{'n':>4}{'gain':>6}{'loss':>6}{'acerto':>8}"
          f"{'resultado':>12}{'acumulado':>12}")
    ac, vazios = 0.0, 0
    for m in meses:
        v = [o for o in sel if o['mes'] == m]
        if not v:
            vazios += 1
            print(f"  {m:<9}{0:>4}{'':>6}{'':>6}{'—':>8}{'':>12}{ac:>+12.0f}")
            continue
        g = sum(1 for o in v if o['liq'] > 0)
        s = sum(o['liq'] for o in v); ac += s
        print(f"  {m:<9}{len(v):>4}{g:>6}{len(v)-g:>6}{g/len(v)*100:>7.0f}%"
              f"{s:>+12.0f}{ac:>+12.0f}")
    v = [o['liq'] for o in sel]
    g = sum(1 for x in v if x > 0)
    tot, dd = curva(v)
    z = z_nulo(v)
    print(f"  {'TOTAL':<9}{len(sel):>4}{g:>6}{len(sel)-g:>6}"
          f"{g/len(sel)*100:>7.0f}%{tot:>+12.0f}")
    p25 = [o['liq'] for o in sel if o['ano'] == 2025]
    p26 = [o['liq'] for o in sel if o['ano'] == 2026]
    print(f"  média ${statistics.mean(v):+,.1f}/op · mediana "
          f"${statistics.median(v):+,.1f} · pior rebaixamento ${dd:,.0f} · "
          f"pior sequência de stops {ps(v)}")
    print(f"  2025 ${(statistics.mean(p25) if p25 else 0):+,.1f}/op "
          f"({len(p25)} op) · 2026 "
          f"${(statistics.mean(p26) if p26 else 0):+,.1f}/op ({len(p26)} op)"
          + (f" · teste do acaso z = {z:+.2f}" if z is not None else ""))
    print(f"  meses sem nenhuma operação: {vazios} de {len(meses)}")
    ordenado = sorted(v, reverse=True)
    if len(v) > 5 and tot > 0:
        print(f"  as 3 maiores valem {sum(ordenado[:3])/tot*100:.0f}% do "
              f"total; sem elas sobram "
              f"${(tot-sum(ordenado[:3]))/(len(v)-3):+,.1f}/op")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--faixas', type=int, default=4)
    ap.add_argument('--alvo', type=float, default=0.9)
    ap.add_argument('--csv', default='')
    ap.add_argument('--tf', type=int, default=8)
    ap.add_argument('--corte', type=float, default=0.0)
    a = ap.parse_args()

    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) < 400:
            continue
        vm = statistics.median(v[4]*v[5] for v in h)
        if vm < a.corte*1e6:
            continue
        cru.append((os.path.basename(p).replace('_1h.csv', ''), h, vm))
    cru.sort(key=lambda x: -x[2])
    nf = max(1, len(cru) // a.faixas)
    faixa, rotulos = {}, []
    for k, (s, _, vm) in enumerate(cru):
        idx = min(k // nf, a.faixas - 1)
        faixa[s] = idx
    for i in range(a.faixas):
        vs = [vm for k, (s, _, vm) in enumerate(cru) if faixa[s] == i]
        rotulos.append(f"faixa {i+1}: {len(vs)} moedas, "
                       f"{min(vs)/1e6:,.2f} a {max(vs)/1e6:,.0f} M USD/h")
    print(f"{len(cru)} moedas · H{a.tf} · "
          f"alvo = topo da vela + {a.alvo*100:.0f}%")
    for r in rotulos:
        print("  " + r)

    cfg = dict(BASE, proj=a.alvo, proj_de='vela', rr_no_topo=True)
    ops = []
    for sim, h1, vm in cru:
        for r in varrer(sim, h1, a.tf, cfg):
            g = r['grande']
            if g and r['rsi_depois'] >= RSI_MIN and r['estende'] >= EST_MIN:
                ops.append(dict(g, sim=sim, faixa=faixa[sim], vol=vm,
                                mes=g['q'].strftime('%Y-%m')))
    ops.sort(key=lambda o: o['q'])
    if not ops:
        print("nenhuma operação"); return
    meses = sorted({o['mes'] for o in ops})

    mes_a_mes(f"TODAS AS {len(cru)} MOEDAS", ops, meses)
    for i in range(a.faixas):
        mes_a_mes(rotulos[i].upper(),
                  [o for o in ops if o['faixa'] == i], meses)

    if a.csv:
        with open(a.csv, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['data_brasilia', 'par', 'faixa', 'volume_mediano_usd_h',
                        'entrada', 'stop', 'alvo', 'stop_pct',
                        'risco_retorno', 'fim', 'horas', 'resultado_usd'])
            for o in ops:
                w.writerow([f"{o['q']:%Y-%m-%d %H:%M}", o['sim'],
                            o['faixa']+1, f"{o['vol']:.0f}",
                            f"{o['ent']:.8g}", f"{o['stop']:.8g}",
                            f"{o['alvo']:.8g}", f"{o['risco_pct']:.2f}",
                            f"{o['rr']:.2f}", o['fim'], o['horas'],
                            f"{o['liq']:.2f}"])
        print(f"\ncsv: {a.csv}")


if __name__ == '__main__':
    main()
