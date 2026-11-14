"""SETUP 5 na BANCADA REAL do Eduardo: 3 maos ao mesmo tempo, no maximo.

Duas perguntas dele:

  1) As moedas 151-300 dao gatilho em DIAS NOVOS ou nos mesmos dias em que
     as 150 maiores ja deram? Se for nos mesmos dias, elas nao servem para
     nada -- ele nao tem mao sobrando. Se for em dias novos, elas preenchem
     os buracos.

  2) Com no maximo 3 posicoes abertas ao mesmo tempo, o que sobra do
     resultado? E quando mais de 3 disparam juntos, qual regra de escolha
     e a melhor?

Universo ROLANTE (re-escolhido a cada trimestre pelo volume mediano do
trimestre anterior). Risco fixo de $100 por operacao.

Uso:  python3 setup5_bancada.py <pasta> [--n 300]
"""
import argparse, glob, os, statistics, sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explosao8 as e8
import setup5_falha as s5
import falha5
from explosao import ler
from lista_operacoes import vol, TRI, BRT
from alvo_lote import z_de
from venda_topo import lotes_de

H = 3600_000


def rebaixamento(ops):
    pior = pico = atual = 0.0
    for o in sorted(ops, key=lambda o: o['saida_ms']):
        atual += o['liq']
        pico = max(pico, atual)
        pior = min(pior, atual - pico)
    return pior


def resumo(rot, ops, meses, larg=30):
    if not ops:
        print(f"  {rot:<{larg}}{'—':>6}")
        return
    v = [o['liq'] for o in ops]
    g = [o for o in ops if o['fim'] == 'alvo']
    L = lotes_de(ops)
    lv = [sum(y['liq'] for y in x) for x in L]
    tot = sum(v)
    print(f"  {rot:<{larg}}{len(ops):>6}{len(ops)/meses:>6.1f}"
          f"{len(g)/len(ops)*100:>8.1f}%{statistics.mean(o['rr'] for o in ops):>6.2f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}"
          f"{z_de(lv):>+8.2f}{rebaixamento(ops):>+9.0f}")


def cab(larg=30):
    print(f"  {'':<{larg}}{'ops':>6}{'/mês':>6}{'acerto':>9}{'R:R':>6}"
          f"{'líq/op':>9}{'total':>9}{'z/LOTE':>8}{'rebaix':>9}")


def filtrar(ops, maos, regra):
    """Simula a bancada: no maximo `maos` posicoes abertas ao mesmo tempo.

    Os sinais sao ao vivo: se nao ha mao livre na hora, o sinal e PERDIDO
    (nao entra em fila). Quando varios disparam na mesma hora e nao cabem
    todos, `regra` decide quem entra.
    """
    chave = {
        'rr':    lambda o: -o['rr'],            # maior R:R primeiro
        'stop':  lambda o: o['risco_pct'],      # stop mais curto primeiro
        'ida':   lambda o: -o['excur'],         # ida mais forte primeiro
        'top':   lambda o: o['rank'],           # moeda mais liquida primeiro
        'ordem': lambda o: o['sim'],            # alfabetica (controle)
    }[regra]
    horas, livres, perdidas = {}, [], []
    for o in ops:
        horas.setdefault(o['ms'], []).append(o)
    abertas = []            # lista de ms de saida
    for ms in sorted(horas):
        abertas = [x for x in abertas if x > ms]
        cand = sorted(horas[ms], key=chave)
        for o in cand:
            if len(abertas) < maos:
                livres.append(o)
                abertas.append(o['saida_ms'])
            else:
                perdidas.append(o)
    return livres, perdidas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=300)
    a = ap.parse_args()

    serie = {}
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            serie[os.path.basename(p).replace('_1h.csv', '')] = h
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    meses = (t1-t0)/(1000*3600*24*30.4)

    cfg = dict(s5.CFG5, **{k: v for k, v in falha5.CFG.items()
                           if k in s5.CFG5})
    ind = {s: (e8.atr(h, 14), e8.medvol(h, 20)) for s, h in serie.items()}

    # Detecta uma vez por moeda e depois so filtra por trimestre/rank.
    bruto = {}
    for s, h in serie.items():
        at, mv = ind[s]
        for g in s5.achar(h, cfg, at, mv):
            r = s5.resolver(h, g, 1)
            if not r:
                continue
            bruto.setdefault(s, []).append(dict(
                sim=s, ms=g['vela_ms'], saida_ms=g['vela_ms']+r['horas']*H,
                lado=g['lado'], rr=g['rr'], risco_pct=g['risco_pct'],
                excur=g['excur'], fim=r['fim'], liq=r['liq'],
                horas=r['horas']))

    ops = []
    t = t0 + TRI
    while t < t1:
        jan = sorted(serie, key=lambda s: -vol(serie[s], t-TRI, t))
        pos = {s: k for k, s in enumerate(jan)}
        for s in jan[:a.n]:
            for o in bruto.get(s, []):
                if t <= o['ms'] < t + TRI:
                    ops.append(dict(o, rank=pos[s],
                                    lote=1 if pos[s] < 150 else 2))
        t += TRI
    ops.sort(key=lambda o: o['ms'])

    print(f"universo ROLANTE de {a.n} · {meses:.0f} meses · setup 5 · "
          f"risco fixo de $100 por operação\n")

    # ------------------------------------------------------------------
    # 1) O SEGUNDO LOTE (moedas 151-300) traz DIAS NOVOS?
    # ------------------------------------------------------------------
    print(f"{'='*96}\n  1) AS MOEDAS 151-300 DÃO GATILHO EM DIAS NOVOS?"
          f"\n{'='*96}\n")

    def dia(o):
        return dt.datetime.fromtimestamp(o['ms']/1000, BRT).date()

    l1 = [o for o in ops if o['lote'] == 1]
    l2 = [o for o in ops if o['lote'] == 2]
    d1, d2 = {dia(o) for o in l1}, {dia(o) for o in l2}
    novos = d2 - d1
    op_novos = [o for o in l2 if dia(o) in novos]
    op_repet = [o for o in l2 if dia(o) not in novos]

    print(f"  as 150 maiores            {len(l1):>5} gatilhos em "
          f"{len(d1):>4} dias distintos")
    print(f"  as 151-300                {len(l2):>5} gatilhos em "
          f"{len(d2):>4} dias distintos")
    print(f"  dias em que SÓ as 151-300 deram sinal: {len(novos)} "
          f"({len(novos)/len(d1|d2)*100:.0f}% dos dias com sinal)\n")
    cab()
    resumo('o 2º lote em DIA NOVO', op_novos, meses)
    resumo('o 2º lote em dia já ocupado', op_repet, meses)
    resumo('(as 150 maiores, p/ comparar)', l1, meses)

    # quantos sinais caem na MESMA HORA, que e o que trava a mao
    por_h = {}
    for o in ops:
        por_h.setdefault(o['ms'], []).append(o)
    simult = sorted((len(v) for v in por_h.values()), reverse=True)
    print(f"\n  na mesma HORA: {sum(1 for x in simult if x == 1)} horas com "
          f"1 sinal, {sum(1 for x in simult if x == 2)} com 2, "
          f"{sum(1 for x in simult if x >= 3)} com 3 ou mais "
          f"(o pior: {simult[0]} de uma vez)")
    por_d = {}
    for o in ops:
        por_d.setdefault(dia(o), []).append(o)
    dd = sorted((len(v) for v in por_d.values()), reverse=True)
    print(f"  no mesmo DIA:  {sum(1 for x in dd if x == 1)} dias com 1, "
          f"{sum(1 for x in dd if x == 2)} com 2, "
          f"{sum(1 for x in dd if x >= 3)} com 3 ou mais "
          f"(o pior: {dd[0]} de uma vez)")
    hm = statistics.median(o['horas'] for o in ops)
    print(f"  a operação fica aberta {hm:.0f} h na mediana "
          f"({hm/24:.1f} dia) — é isso que ocupa a mão\n")

    # ------------------------------------------------------------------
    # 2) A BANCADA: QUANTAS MAOS?
    # ------------------------------------------------------------------
    for univ, rot in ((150, 'as 150 maiores'), (a.n, f'as {a.n} maiores')):
        sub = [o for o in ops if o['rank'] < univ]
        print(f"{'='*96}\n  2) COM LIMITE DE MÃOS ABERTAS · {rot}"
              f"\n{'='*96}\n")
        cab()
        resumo('sem limite (o ideal)', sub, meses)
        for maos in (1, 2, 3, 4, 5):
            liv, perd = filtrar(sub, maos, 'rr')
            resumo(f'{maos} mão(s) · pega o maior R:R', liv, meses)
        print()

    # ------------------------------------------------------------------
    # 3) COM 3 MAOS, QUAL REGRA DE ESCOLHA?
    # ------------------------------------------------------------------
    print(f"{'='*96}\n  3) COM 3 MÃOS, QUEM ENTRA QUANDO VÁRIOS DISPARAM "
          f"JUNTOS?\n{'='*96}\n")
    for univ, rot in ((150, 'as 150 maiores'), (a.n, f'as {a.n} maiores')):
        sub = [o for o in ops if o['rank'] < univ]
        print(f"  · {rot}")
        cab()
        for regra, nome in (('rr', 'o maior R:R'),
                            ('stop', 'o stop mais curto'),
                            ('ida', 'a ida mais forte'),
                            ('top', 'a moeda mais líquida'),
                            ('ordem', 'ordem alfabética (controle)')):
            liv, perd = filtrar(sub, 3, regra)
            resumo(nome, liv, meses)
        liv, perd = filtrar(sub, 3, 'rr')
        print(f"    perdidos por falta de mão: {len(perd)} de {len(sub)} "
              f"({len(perd)/len(sub)*100:.0f}%) · "
              f"o que foi perdido valia {sum(o['liq'] for o in perd):+.0f}\n")

    # ------------------------------------------------------------------
    # 4) ANO A ANO com 3 maos, nas 300
    # ------------------------------------------------------------------
    liv, _ = filtrar(ops, 3, 'rr')
    print(f"{'='*96}\n  4) 3 MÃOS · {a.n} MOEDAS · ANO A ANO\n{'='*96}\n")
    cab()
    for y in sorted({dt.datetime.fromtimestamp(o['ms']/1000, BRT).year
                     for o in liv}):
        resumo(str(y), [o for o in liv
                        if dt.datetime.fromtimestamp(o['ms']/1000,
                                                     BRT).year == y], 12)
    print()


if __name__ == '__main__':
    main()
