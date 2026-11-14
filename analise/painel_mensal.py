"""Os TRES setups que rodam no bot, mes a mes, em 2026.

  Setup 1  varredura de liquidez, em H4   (50 maiores)
  Setup 3  reversao de 8h, entrada no H1  (150 maiores)
  Setup 5  rompimento falso, em H1        (150 maiores)

Universo ROLANTE: a cada trimestre, as N maiores pelo volume mediano do
trimestre ANTERIOR, e so contam as operacoes daquele trimestre. Nada de
olhar o futuro.

Risco fixo de 100 por operacao, taxa de 0.05% por perna e funding. O
total no fim soma os tres como se rodassem juntos, que e o que o bot faz.

Uso:  python3 painel_mensal.py <pasta> [--ano 2026]
"""
import argparse, glob, os, statistics, sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot_varredura as bot
import explosao8 as e8
import falha5
import reversao8 as rev
from cruzar_setups import reversao
from explosao import ler, RISCO, TAXA, FUND8
from setup1_real import rodar as rodar1

BRT = dt.timezone(dt.timedelta(hours=-3))
TRI = 90*24*3600_000
MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun',
         'jul', 'ago', 'set', 'out', 'nov', 'dez']


def vol(h, ini=None, fim=None):
    v = [x[4]*x[5] for x in h
         if (ini is None or x[0] >= ini) and (fim is None or x[0] < fim)]
    return statistics.median(v) if len(v) >= 100 else 0.0


def falso(h1, sim):
    """Setup 5: as entradas do modulo AO VIVO, resolvidas."""
    cfg = falha5.CFG
    ops = []
    for g, _ in falha5.exemplos(h1, cfg):
        k, alta = g['idx'], g['alta']
        fim = saida = None
        n = 0
        for m in range(k+1, len(h1)):
            n += 1
            if n > falha5.MAX_BARRAS:
                fim, saida = 'tempo', h1[m][4]; break
            hi, lo = h1[m][2], h1[m][3]
            bs = (hi >= g['stop']) if alta else (lo <= g['stop'])
            ba = (lo <= g['alvo']) if alta else (hi >= g['alvo'])
            if bs:
                fim, saida = 'stop', g['stop']; break
            if ba:
                fim, saida = 'alvo', g['alvo']; break
        if fim is None:
            continue
        pos = RISCO/(g['risco_pct']/100)
        mov = (g['entrada']-saida)/g['entrada'] if alta else \
              (saida-g['entrada'])/g['entrada']
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        ops.append(dict(sim=sim, q=q, ano=q.year, rr=g['rr'], fim=fim,
                        stop_pct=g['risco_pct'],
                        liq=pos*mov - pos*TAXA*2 - pos*(n/8)*FUND8))
    return ops


def rolante(serie, t0, t1, n, gerar):
    """Re-escolhe o universo a cada trimestre e junta as operacoes."""
    ops, t = [], t0 + TRI
    while t < t1:
        jan = sorted(serie, key=lambda s: -vol(serie[s], t-TRI, t))[:n]
        for s in jan:
            for o in gerar(serie[s], s):
                ms = o['q'].timestamp()*1000
                if t <= ms < t + TRI:
                    ops.append(o)
        t += TRI
    return sorted(ops, key=lambda o: o['q'])


def linha(rot, ops, larg=16):
    if not ops:
        print(f"  {rot:<{larg}}{'—':>6}")
        return
    g = [o for o in ops if o['liq'] > 0]
    pior = pico = atual = 0
    for o in ops:
        atual += o['liq']; pico = max(pico, atual)
        pior = min(pior, atual - pico)
    print(f"  {rot:<{larg}}{len(ops):>6}{len(ops)/12:>7.1f}"
          f"{len(g)/len(ops)*100:>8.0f}%"
          f"{statistics.mean(o['rr'] for o in ops):>7.2f}"
          f"{statistics.mean(o['stop_pct'] for o in ops):>8.1f}%"
          f"{statistics.mean(o['liq'] for o in ops):>+9.1f}"
          f"{sum(o['liq'] for o in ops):>+9.0f}{pior:>+9.0f}")


def cab(larg=16):
    print(f"  {'':<{larg}}{'ops':>6}{'/mês':>7}{'acerto':>9}{'R:R':>7}"
          f"{'stop':>9}{'líq/op':>9}{'total':>9}{'rebaix':>9}")


def mensal(nome, grupos, ano):
    print(f"\n  {nome}\n  {'mês':<6}" +
          "".join(f"{k:>14}" for k in grupos) + f"{'TOTAL':>14}")
    acum = {k: 0.0 for k in grupos}
    tot = 0.0
    for m in range(1, 13):
        cel, soma = [], 0.0
        for k, ops in grupos.items():
            v = [o for o in ops if o['q'].year == ano and o['q'].month == m]
            s = sum(o['liq'] for o in v)
            acum[k] += s; soma += s
            cel.append(f"{len(v):>3}  {s:>+8.0f}" if v else f"{'—':>13}")
        tot += soma
        if any(c.strip() != '—' for c in cel):
            print(f"  {MESES[m-1]:<6}" + "".join(f"{c:>14}" for c in cel)
                  + f"{soma:>+14.0f}")
    print(f"  {'ano':<6}" +
          "".join(f"{acum[k]:>+14.0f}" for k in grupos) + f"{tot:>+14.0f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--ano', type=int, default=2026)
    a = ap.parse_args()
    serie = {}
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            serie[os.path.basename(p).replace('_1h.csv', '')] = h
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    print(f"{len(serie)} pares · base até "
          f"{dt.datetime.fromtimestamp(t1/1000, BRT):%d/%m/%Y %H:%M} "
          f"(Brasília) · universo rolante · $100 de risco por operação\n")

    cfg1 = dict(bot.CFG)
    g = {}
    g['setup 1 (H4)'] = rolante(
        serie, t0, t1, 50,
        lambda h, s: rodar1(rev.juntar(h, 4), s, cfg1, trailing=True))
    g['setup 3 (H8)'] = rolante(serie, t0, t1, 150,
                                lambda h, s: reversao(h, s))
    g['setup 5 (H1)'] = rolante(serie, t0, t1, 150, falso)

    meses_tot = (t1-t0)/(1000*3600*24*30.4)
    print(f"  OS 7 ANOS INTEIROS ({meses_tot:.0f} meses)")
    cab()
    for k, v in g.items():
        linha(k, v)
    linha('OS TRÊS', sorted([o for v in g.values() for o in v],
                            key=lambda o: o['q']))

    print(f"\n  SÓ {a.ano}")
    cab()
    gy = {k: [o for o in v if o['q'].year == a.ano] for k, v in g.items()}
    for k, v in gy.items():
        linha(k, v)
    linha('OS TRÊS', sorted([o for v in gy.values() for o in v],
                            key=lambda o: o['q']))

    mensal(f"MÊS A MÊS EM {a.ano}  ·  ops e líquido por $100 de risco",
           g, a.ano)
    print()


if __name__ == '__main__':
    main()
