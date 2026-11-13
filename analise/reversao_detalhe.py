"""A configuracao validada da reversao, operacao por operacao.

  padrao     em velas de 8 horas
  universo   as N moedas de maior volume mediano
  entrada    no H1, depois que o preco encosta no order block
  filtro     ENCOSTO RASO: descarta se o recuo afundar abaixo do meio
             do order block
  variante   com e sem exigir volume >= 1,2x na vela do gatilho

Grava a lista completa das operacoes em CSV, com data em Brasilia.
"""
import argparse, csv, glob, itertools, os, random, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explosao import ler, curva
from reversao_confirma import rodar, BASE, painel, cab

BRT = dt.timezone(dt.timedelta(hours=-3))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h,
                        statistics.median(v[4]*v[5] for v in h)))
    cru.sort(key=lambda x: -x[2])
    cru = cru[:a.n]
    faixa = {s: 0 for s, _, _ in cru}
    print(f"as {len(cru)} maiores · de {cru[0][0]} "
          f"({cru[0][2]/1e6:,.0f} M USD/h) a {cru[-1][0]} "
          f"({cru[-1][2]/1e6:,.2f} M/h)")

    # A base validada: encosto raso + volume no gatilho.
    VAL = dict(BASE, modo='raso', vol_min=1.2)
    print(f"\n{'#'*132}\n#  OS TRES EIXOS, UM DE CADA VEZ, EM CIMA DA BASE "
          f"VALIDADA\n{'#'*132}")
    eixos = [
        ('o último topo: quantas velas de cada lado definem o pivô', [
            ('±1 vela  (pivô mais solto)', dict(VAL, pivo_h=8)),
            ('±2 velas  (a base)', dict(VAL)),
            ('±3 velas  (mais exigente)', dict(VAL, pivo_h=24)),
        ]),
        ('o último topo: até onde procurar para trás', [
            ('20 velas · 160h', dict(VAL, topo_h=160)),
            ('30 velas · 240h  (a base)', dict(VAL)),
            ('50 velas · 400h', dict(VAL, topo_h=400)),
            ('80 velas · 640h', dict(VAL, topo_h=640)),
        ]),
        ('a espera pelo preço voltar ao order block', [
            ('10 dias · 240h  (a base)', dict(VAL)),
            ('20 dias · 480h', dict(VAL, espera_h=480)),
            ('30 dias · 720h', dict(VAL, espera_h=720)),
            ('60 dias · 1440h', dict(VAL, espera_h=1440)),
        ]),
        ('o alvo: quanto do tamanho da vela além do topo dela', [
            ('+90%  (a base)', dict(VAL)),
            ('+100%', dict(VAL, alvo_proj=1.0)),
            ('+150%', dict(VAL, alvo_proj=1.5)),
            ('+200%', dict(VAL, alvo_proj=2.0)),
            ('+300%', dict(VAL, alvo_proj=3.0)),
        ]),
    ]
    for titulo, lista in eixos:
        print(f"\n{'-'*132}\n  {titulo}\n{'-'*132}")
        cab()
        for nome_, cfg_ in lista:
            painel(nome_, rodar(cru, cfg_, faixa, 1, 8))

    print(f"\n{'#'*132}\n#  COMBINANDO O QUE PASSOU\n{'#'*132}")
    cab()
    MELHOR = dict(VAL, espera_h=720, alvo_proj=1.0)
    for nome_, cfg_ in (
            ('base (10 dias, +90%, ±2)', VAL),
            ('espera 30 dias', dict(VAL, espera_h=720)),
            ('espera 30d + alvo +100%', MELHOR),
            ('espera 30d + alvo +100% + pivô ±1',
             dict(MELHOR, pivo_h=8)),
            ('espera 30d + pivô ±1', dict(VAL, espera_h=720, pivo_h=8)),
            ('espera 20 dias + alvo +100%',
             dict(VAL, espera_h=480, alvo_proj=1.0)),
            ('o mesmo, sem exigir volume',
             dict(MELHOR, vol_min=0.0)),
            ('sem volume + pivô ±1',
             dict(MELHOR, vol_min=0.0, pivo_h=8)),
    ):
        painel(nome_, rodar(cru, cfg_, faixa, 1, 8))

    for rot, cfg, nome in (
            ('ENCOSTO RASO + VOLUME, AJUSTADO', MELHOR, 'ajustado'),
            ('ENCOSTO RASO + VOLUME ≥1,2x (base)', VAL, 'raso_volume')):
        ops = rodar(cru, cfg, faixa, 1, 8)
        if not ops:
            print(f"\n{rot}: nenhuma"); continue
        print(f"\n{'='*132}\n  {rot}\n{'='*132}")
        cab()
        painel('resultado', ops)
        meses = sorted({o['mes'] for o in ops})
        t0, t1 = meses[0], meses[-1]
        todos = []
        y, m = int(t0[:4]), int(t0[5:])
        while f"{y}-{m:02d}" <= t1:
            todos.append(f"{y}-{m:02d}")
            m += 1
            if m > 12: m, y = 1, y+1
        print(f"\n  {len(ops)} operações em {len(todos)} meses = "
              f"{len(ops)/len(todos):.1f} por mês")
        print(f"  {'mês':<9}{'n':>4}{'gain':>6}{'loss':>6}{'acerto':>8}"
              f"{'resultado':>12}{'acumulado':>12}")
        ac, vazios = 0.0, 0
        for mm in todos:
            v = [o for o in ops if o['mes'] == mm]
            if not v:
                vazios += 1; continue
            g = sum(1 for o in v if o['liq'] > 0)
            s = sum(o['liq'] for o in v); ac += s
            print(f"  {mm:<9}{len(v):>4}{g:>6}{len(v)-g:>6}"
                  f"{g/len(v)*100:>7.0f}%{s:>+12.0f}{ac:>+12.0f}")
        print(f"  ({vazios} meses sem nenhuma operação)")
        vv = sorted((o['liq'] for o in ops), reverse=True)
        tot = sum(vv)
        print(f"  as 3 maiores valem {sum(vv[:3])/tot*100:.0f}% do total; "
              f"sem elas ${(tot-sum(vv[:3]))/(len(vv)-3):+,.1f}/op")
        print(f"  tempo médio até resolver: "
              f"{statistics.mean(o['horas'] for o in ops):.0f} h")
        arq = f"reversao_{nome}.csv"
        with open(arq, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['data_brasilia', 'par', 'lado', 'entrada', 'stop',
                        'alvo', 'stop_pct', 'risco_retorno', 'fim', 'horas',
                        'bruto_usd', 'taxa_usd', 'resultado_usd',
                        'acumulado_usd'])
            acc = 0.0
            for o in ops:
                acc += o['liq']
                w.writerow([f"{o['q']:%Y-%m-%d %H:%M}", o['sim'], o['lado'],
                            f"{o['ent']:.8g}", f"{o['stop']:.8g}",
                            f"{o['alvo']:.8g}", f"{o['risco_pct']:.2f}",
                            f"{o['rr']:.2f}", o['fim'], o['horas'],
                            f"{o['bruto']:.2f}", f"{-o['custo']:.2f}",
                            f"{o['liq']:.2f}", f"{acc:.2f}"])
        print(f"  csv: {arq}")


if __name__ == '__main__':
    main()
