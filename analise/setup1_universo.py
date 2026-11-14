"""SETUP 1: o bot olha 50 moedas. A medicao que justificou a config olhou 150.

O Eduardo reparou: o painel deu 20 operacoes em 7 anos, mas o comentario
dentro do bot_varredura documenta 55 operacoes no furo 0,15. A diferenca
nao e o setup -- e o universo. O setup1_fundo.py rodou com --n 150 e o bot
roda com --top 50.

No setup 5 a borda NAO diluiu quando o universo foi de 150 para 300 (o
liquido por operacao ficou parado em ~48 dolares). Aqui a pergunta e a
mesma: o setup 1 aguenta mais moedas, ou as moedas pequenas sujam?

Roda o caminho EXATO do bot (H4 + trailing, bot.CFG) no universo rolante,
variando so o tamanho: 50, 100, 150, 200, 300.

Uso:  python3 setup1_universo.py <pasta>
"""
import argparse, glob, os, statistics, sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot_varredura as bot
import reversao8 as rev
from explosao import ler
from lista_operacoes import vol, TRI, BRT
from alvo_lote import z_de
from setup1_real import rodar as rodar1
from venda_topo import lotes_de

TAMANHOS = (50, 100, 150, 200, 300)


def painel(rot, ops, meses, larg=26):
    if not ops:
        print(f"  {rot:<{larg}}{'—':>6}")
        return
    v = [o['liq'] for o in ops]
    g = [o for o in ops if o['liq'] > 0]
    L = lotes_de(ops)
    lv = [sum(y['liq'] for y in x) for x in L]
    tot = sum(v)
    anos = sorted({o['q'].year for o in ops})
    bons = sum(1 for y in anos
               if statistics.mean([o['liq'] for o in ops
                                   if o['q'].year == y]) > 0)
    pior = pico = atual = 0.0
    for o in ops:
        atual += o['liq']; pico = max(pico, atual)
        pior = min(pior, atual - pico)
    print(f"  {rot:<{larg}}{len(ops):>6}{len(ops)/meses:>6.1f}"
          f"{len(g)/len(ops)*100:>8.1f}%"
          f"{statistics.mean(o['rr'] for o in ops):>6.2f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}"
          f"{len(L):>6}{sum(1 for x in lv if x > 0):>5}{z_de(lv):>+8.2f}"
          f"{max(lv)/tot*100 if tot > 0 else 0:>7.0f}%{pior:>+9.0f}"
          f"  {bons}/{len(anos)}")


def cab(larg=26):
    print(f"  {'':<{larg}}{'ops':>6}{'/mês':>6}{'acerto':>9}{'R:R':>6}"
          f"{'líq/op':>9}{'total':>9}{'lotes':>6}{'pos':>5}{'z/LOTE':>8}"
          f"{'maior':>8}{'rebaix':>9}  anos+")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    a = ap.parse_args()

    serie = {}
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            serie[os.path.basename(p).replace('_1h.csv', '')] = h
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    meses = (t1-t0)/(1000*3600*24*30.4)

    cfg = dict(bot.CFG)
    janelas, t = [], t0 + TRI
    while t < t1:
        janelas.append((t, sorted(serie,
                                  key=lambda s: -vol(serie[s], t-TRI, t))))
        t += TRI

    # Detecta uma vez por moeda: o caminho do bot (H4 + trailing).
    bruto = {}
    for s, h in serie.items():
        try:
            bruto[s] = rodar1(rev.juntar(h, 4), s, cfg, trailing=True)
        except Exception:
            bruto[s] = []

    print(f"universo ROLANTE · {meses:.0f} meses · setup 1 (H4 + trailing, "
          f"a config exata do bot) · risco fixo de $100\n")
    print("  O bot roda em 50. A medição que escolheu o filtro do furo "
          "rodou em 150.\n  Pergunta: a borda aguenta mais moedas, como "
          "aguentou no setup 5?\n")
    cab()
    guard = {}
    for n in TAMANHOS:
        ops = []
        for t, jan in janelas:
            for s in jan[:n]:
                for o in bruto.get(s, []):
                    ms = o['q'].timestamp()*1000
                    if t <= ms < t + TRI:
                        ops.append(o)
        ops.sort(key=lambda o: o['q'])
        guard[n] = ops
        painel(f"as {n} maiores", ops, meses)

    # O que as moedas 51-300 trazem de avulso, por faixa.
    print(f"\n  SÓ A FAIXA QUE O BOT NÃO VÊ HOJE\n")
    cab()
    faixas = ((50, 100), (100, 150), (150, 200), (200, 300), (50, 300))
    for lo, hi in faixas:
        ops = []
        for t, jan in janelas:
            pos = {s: k for k, s in enumerate(jan)}
            for s in jan[lo:hi]:
                for o in bruto.get(s, []):
                    ms = o['q'].timestamp()*1000
                    if t <= ms < t + TRI:
                        ops.append(o)
        ops.sort(key=lambda o: o['q'])
        painel(f"as {lo+1}-{hi}", ops, meses)

    # Ano a ano nos dois extremos, para ver se o ganho e de um ano so.
    for n in (50, 300):
        print(f"\n  ANO A ANO · as {n} maiores\n")
        cab()
        for y in sorted({o['q'].year for o in guard[n]}):
            painel(str(y), [o for o in guard[n] if o['q'].year == y], 12)
    print()


if __name__ == '__main__':
    main()
