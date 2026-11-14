"""Os TRES setups que rodam no bot, mes a mes, em 2026.

  Setup 1  varredura de liquidez, em H4   (150 maiores)
  Setup 3  reversao de 8h, entrada no H1  (150 maiores)
  Setup 5  rompimento falso, em H1        (150 maiores)

14/11/2026 -- o setup 1 passou de 50 para 150 pares no bot, e as acoes
tokenizadas e stablecoins saem da base aqui tambem, para o backteste medir
exatamente o que o bot vai olhar.

Universo ROLANTE: a cada trimestre, as N maiores pelo volume mediano do
trimestre ANTERIOR, e so contam as operacoes daquele trimestre. Nada de
olhar o futuro.

Risco fixo de 100 por operacao, taxa de 0.05% por perna e funding. O
total no fim soma os tres como se rodassem juntos, que e o que o bot faz.

Uso:  python3 painel_mensal.py <pasta> [--ano 2026]
"""
import argparse, glob, os, statistics, sys, time
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


def universos(serie, t0, t1, n):
    """Os N maiores de CADA trimestre, pelo volume do trimestre ANTERIOR.

    Calculado uma vez so e reaproveitado pelos tres setups -- a escolha do
    universo nao depende de qual setup vai rodar nele.
    """
    out, t = [], t0 + TRI
    while t < t1:
        out.append((t, sorted(serie, key=lambda s: -vol(serie[s], t-TRI, t))[:n]))
        t += TRI
    return out


def rolante(serie, janelas, gerar):
    """Junta as operacoes do universo rolante, trimestre a trimestre.

    14/11/2026 -- antes isso rodava o backteste do par INTEIRO uma vez por
    trimestre e descartava tudo que caia fora da janela: 150 pares x 28
    trimestres = 4200 backtestes para aproveitar 150. Com o setup 1 subindo
    de 50 para 150 pares a rodada passou de 3 horas. Agora cada par roda UMA
    vez e o trimestre so filtra o que ja esta pronto. O resultado e o mesmo;
    muda o tempo.
    """
    pronto, ops = {}, []
    for t, jan in janelas:
        for s in jan:
            if s not in pronto:
                pronto[s] = gerar(serie[s], s)
            for o in pronto[s]:
                ms = o['q'].timestamp()*1000
                if t <= ms < t + TRI:
                    ops.append(o)
    return sorted(ops, key=lambda o: o['q'])


def linha(rot, ops, meses=12, larg=16):
    if not ops:
        print(f"  {rot:<{larg}}{'—':>6}")
        return
    g = [o for o in ops if o['liq'] > 0]
    pior = pico = atual = 0
    for o in ops:
        atual += o['liq']; pico = max(pico, atual)
        pior = min(pior, atual - pico)
    print(f"  {rot:<{larg}}{len(ops):>6}{len(ops)/meses:>7.1f}"
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
    fora = bot.STABLE | bot.COMMODITY | bot.ACOES
    serie, cortados = {}, []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        sim = os.path.basename(p).replace('_1h.csv', '')
        if sim.endswith('USDT') and sim[:-4] in fora:
            cortados.append(sim)
            continue
        h = ler(p)
        if len(h) >= 400:
            serie[sim] = h
    if cortados:
        print(f"fora da base ({len(cortados)}): {', '.join(cortados)}\n")
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    print(f"{len(serie)} pares · base até "
          f"{dt.datetime.fromtimestamp(t1/1000, BRT):%d/%m/%Y %H:%M} "
          f"(Brasília) · universo rolante · $100 de risco por operação\n")

    cfg1 = dict(bot.CFG)
    jan = universos(serie, t0, t1, 150)
    print(f"  universo rolante: {len(jan)} trimestres de 150 pares\n")

    g = {}
    for nome, gerar in (
            ('setup 1 (H4)',
             lambda h, s: rodar1(rev.juntar(h, 4), s, cfg1, trailing=True)),
            ('setup 3 (H8)', lambda h, s: reversao(h, s)),
            ('setup 5 (H1)', falso)):
        rel = time.time()
        g[nome] = rolante(serie, jan, gerar)
        print(f"  {nome}: {len(g[nome])} operações "
              f"em {time.time()-rel:.0f}s", flush=True)

    meses_tot = (t1-t0)/(1000*3600*24*30.4)
    print(f"  OS 7 ANOS INTEIROS ({meses_tot:.0f} meses)")
    cab()
    for k, v in g.items():
        linha(k, v, meses_tot)
    linha('OS TRÊS', sorted([o for v in g.values() for o in v],
                            key=lambda o: o['q']), meses_tot)

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
