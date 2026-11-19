"""Risco fixo contra valor de entrada fixo, nas MESMAS operações.

A pergunta do Eduardo: olhando mês a mês com os três setups juntos, é
melhor arriscar sempre o mesmo (e deixar o tamanho da posição variar com o
stop) ou entrar sempre com o mesmo valor (e deixar a perda variar)?

Como a conta é exata. Todo componente do resultado -- a variação do preço,
a taxa das duas pernas e o funding -- escala LINEARMENTE com o tamanho da
posição. Entao, para a mesma operação:

    posição no risco fixo   =  RISCO / (stop% / 100)
    fator                   =  NOCIONAL / posição
    resultado no valor fixo =  resultado no risco fixo  x  fator

Nada é re-simulado: são as mesmas entradas, os mesmos stops e os mesmos
alvos, só com outro tamanho.

O NOCIONAL padrão é a MEDIANA das posições do risco fixo, para os dois
esquemas aplicarem mais ou menos o mesmo capital e a comparação ser justa.

Uso:  python3 dimensionamento.py <pasta> [--ano 2026] [--nocional 0]
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import painel_mensal as pm
from explosao import RISCO


def converter(ops, nocional):
    """Devolve a lista com `liq_fixo` ao lado do `liq` de risco fixo."""
    saida = []
    for o in ops:
        s = max(o.get('stop_pct', 0.0), 1e-9)
        pos = RISCO / (s / 100.0)
        d = dict(o)
        d['pos'] = pos
        d['liq_fixo'] = o['liq'] * (nocional / pos)
        saida.append(d)
    return saida


def resumo(rot, ops, campo, meses, larg=18):
    if not ops:
        print(f"  {rot:<{larg}}{'—':>7}")
        return
    v = [o[campo] for o in ops]
    g = [x for x in v if x > 0]
    pior = pico = atual = 0.0
    for x in v:
        atual += x
        pico = max(pico, atual)
        pior = min(pior, atual - pico)
    print(f"  {rot:<{larg}}{len(v):>6}{len(v)/meses:>7.1f}"
          f"{len(g)/len(v)*100:>8.0f}%"
          f"{statistics.mean(v):>+10.1f}{sum(v):>+10.0f}{pior:>+10.0f}"
          f"{statistics.pstdev(v):>10.1f}")


def cab(larg=18):
    print(f"  {'':<{larg}}{'ops':>6}{'/mês':>7}{'ganhos':>9}"
          f"{'médio':>10}{'total':>10}{'rebaixa':>10}{'oscila':>10}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--ano', type=int, default=2026)
    ap.add_argument('--nocional', type=float, default=0.0,
                    help='0 = usar a mediana das posições do risco fixo')
    a = ap.parse_args()

    fora = pm.bot.STABLE | pm.bot.COMMODITY | pm.bot.ACOES
    serie = {}
    import glob
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        sim = os.path.basename(p).replace('_1h.csv', '')
        if sim.endswith('USDT') and sim[:-4] in fora:
            continue
        h = pm.ler(p)
        if len(h) >= 400:
            serie[sim] = h
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    jan = pm.universos(serie, t0, t1, 150)
    cfg1 = dict(pm.bot.CFG)

    g = {}
    for nome, gerar in (
            ('setup 1 (H4)',
             lambda h, s: pm.rodar1(pm.rev.juntar(h, 4), s, cfg1,
                                    trailing=True)),
            ('setup 3 (H8)', lambda h, s: pm.reversao(h, s)),
            ('setup 5 (H1)', pm.falso)):
        g[nome] = pm.rolante(serie, jan, gerar)
        print(f"  {nome}: {len(g[nome])} operações", flush=True)

    todas = sorted([o for v in g.values() for o in v], key=lambda o: o['q'])
    pos = [RISCO / (max(o.get('stop_pct', 0.0), 1e-9) / 100.0) for o in todas]
    nocional = a.nocional or statistics.median(pos)
    meses = (t1 - t0) / (1000 * 3600 * 24 * 30.4)

    print(f"\n{len(serie)} pares · {meses:.0f} meses · "
          f"risco fixo de ${RISCO:.0f} por operação")
    print(f"valor de entrada fixo: ${nocional:,.0f} "
          f"(a mediana das posições do risco fixo)")
    print(f"posições no risco fixo: menor ${min(pos):,.0f} · "
          f"maior ${max(pos):,.0f} · mediana ${statistics.median(pos):,.0f}")
    print("\n  'oscila' é o desvio-padrão do resultado por operação: "
          "quanto maior, mais solavanco.\n")

    for titulo, filtro in (("OS MESES TODOS", lambda o: True),
                           (f"SÓ {a.ano}", lambda o: o['q'].year == a.ano)):
        m = meses if titulo.startswith("OS") else 12
        print(f"{'='*80}\n  {titulo}\n{'='*80}")
        for campo, nome in (('liq', 'RISCO FIXO'),
                            ('liq_fixo', 'VALOR FIXO')):
            print(f"\n  · {nome}")
            cab()
            for k, v in g.items():
                resumo(k, converter([o for o in v if filtro(o)], nocional),
                       campo, m)
            resumo('OS TRÊS', converter([o for o in todas if filtro(o)],
                                        nocional), campo, m)
        print()

    # mes a mes, os dois lado a lado
    print(f"{'='*80}\n  MÊS A MÊS EM {a.ano}  ·  os três juntos\n{'='*80}")
    print(f"  {'mês':<6}{'ops':>5}{'RISCO FIXO':>14}{'VALOR FIXO':>14}"
          f"{'diferença':>14}")
    conv = converter([o for o in todas if o['q'].year == a.ano], nocional)
    ac1 = ac2 = 0.0
    for mes in range(1, 13):
        v = [o for o in conv if o['q'].month == mes]
        if not v:
            continue
        s1 = sum(o['liq'] for o in v)
        s2 = sum(o['liq_fixo'] for o in v)
        ac1 += s1
        ac2 += s2
        print(f"  {pm.MESES[mes-1]:<6}{len(v):>5}{s1:>+14.0f}{s2:>+14.0f}"
              f"{s2-s1:>+14.0f}")
    print(f"  {'ano':<6}{len(conv):>5}{ac1:>+14.0f}{ac2:>+14.0f}"
          f"{ac2-ac1:>+14.0f}")

    # o stop largo paga mais por dolar aplicado?
    print(f"\n{'='*80}\n  O STOP LARGO PAGA MAIS?\n{'='*80}")
    print(f"  {'faixa de stop':<18}{'ops':>6}{'médio/op (risco fixo)':>24}"
          f"{'retorno por $1.000 aplicados':>30}")
    conv_t = converter(todas, nocional)
    faixas = [(0, 3), (3, 5), (5, 8), (8, 100)]
    for lo, hi in faixas:
        v = [o for o in conv_t if lo <= o.get('stop_pct', 0) < hi]
        if not v:
            continue
        por_mil = statistics.mean(o['liq'] / o['pos'] * 1000 for o in v)
        rot = f"{lo}% a {hi}%" if hi < 100 else f"acima de {lo}%"
        print(f"  {rot:<18}{len(v):>6}"
              f"{statistics.mean(o['liq'] for o in v):>+24.1f}"
              f"{por_mil:>+30.2f}")
    print()


if __name__ == '__main__':
    main()
