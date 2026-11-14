"""SETUP 5 no UNIVERSO ROLANTE -- o teste que decide.

Tudo que foi medido ate aqui rodou nas 150 maiores de HOJE. Isso e
lookahead: HYPE, ENA, TRUMP, PUMP, ASTER, PENGU, XPL, VIRTUAL, WLFI e RE
estao na lista PORQUE cresceram. O mesmo vies ja me fez voltar atras tres
vezes neste projeto.

Aqui o universo e re-escolhido a cada trimestre pelo volume em dolar
MEDIANO do trimestre ANTERIOR, e so contam as operacoes daquele trimestre.

E a conta sai por OPERACAO e por LOTE: as entradas disparam em bloco (a
pior sequencia da entrada 'falha' foi 8 moedas stopando NO MESMO DIA),
entao o z por operacao assume independencia que nao existe. O z por lote
agrupa o que cai dentro de 14 dias e conta o sinal do lote.

Uso:  python3 setup5_rolante.py <pasta> [--n 150]
"""
import argparse, glob, os, statistics, sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explosao8 as e8
import setup5_falha as s5
from explosao import ler, RISCO, TAXA, FUND8
from lista_operacoes import vol, TRI, BRT
from alvo_lote import z_de
from venda_topo import lotes_de

# As duas candidatas que sairam do empilhamento, mais os controles.
BASE = dict(s5.CFG5, lat_jan=60, stop_em='extremo', alvo_em='piscina',
            pre_pivo=20, forca_apos=4)
ALINHADO = dict(BASE, aperto=1.00, pre_modo='alinhado')
CANDIDATAS = [
    # A COMBINADA e o que eu recomendei: folga 0.5 JUNTO com sem trava de
    # forca. Nunca tinha sido medida -- juntei o melhor de duas linhas
    # diferentes, o que e exatamente o tipo de coisa que nao se faz sem medir.
    ('>> COMBINADA  falha, folga 0.5, sem trava',
     dict(ALINHADO, entrada_em='falha', pre_folga=0.5, forca_apos=99)),
    ('FREQUÊNCIA  1.20x falha',
     dict(BASE, aperto=1.20, pre_modo='alinhado', entrada_em='falha')),
    ('TRANQUILIDADE  1.00x falha folga 0.5',
     dict(ALINHADO, entrada_em='falha', pre_folga=0.5)),
    ('— sem a trava da força',
     dict(ALINHADO, entrada_em='falha', forca_apos=99)),
    # Os dois pares abaixo comparam FALHA x VOLTA com TUDO o mais igual,
    # que e o que faltou na primeira tabela.
    ('— falha, sem trava, folga 0.0',
     dict(ALINHADO, entrada_em='falha', forca_apos=99, pre_folga=0.0)),
    ('— volta, sem trava, folga 0.0',
     dict(ALINHADO, entrada_em='volta', forca_apos=99, pre_folga=0.0)),
    ('— falha, sem trava, folga 0.5',
     dict(ALINHADO, entrada_em='falha', forca_apos=99, pre_folga=0.5)),
    ('— volta, sem trava, folga 0.5',
     dict(ALINHADO, entrada_em='volta', forca_apos=99, pre_folga=0.5)),
    ('— sem contexto (controle)',
     dict(BASE, aperto=1.00, pre_modo='off', entrada_em='falha',
          forca_apos=99)),
    ('— CONTRA o contexto (controle)',
     dict(BASE, aperto=1.00, pre_modo='contra', entrada_em='falha',
          forca_apos=99)),
]


def ops_de(h, sim, cfg, a, mv, tf=1):
    """Detecta e resolve, devolvendo o liquido de cada operacao."""
    out = []
    for g in s5.achar(h, cfg, a, mv):
        r = s5.resolver(h, g, tf)
        if not r:
            continue
        out.append(dict(sim=sim, ms=g['vela_ms'], fim=r['fim'], rr=g['rr'],
                        liq=r['liq'], horas=r['horas'],
                        q=dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)))
    return out


def painel(rot, ops, meses, larg=38):
    if not ops:
        print(f"{rot:<{larg}}{'—':>5}")
        return
    v = [o['liq'] for o in ops]
    g = [o for o in ops if o['fim'] == 'alvo']
    L = lotes_de(ops)
    lv = [sum(y['liq'] for y in x) for x in L]
    tot = sum(v)
    anos = sorted({o['q'].year for o in ops})
    bons = sum(1 for y in anos
               if statistics.mean([o['liq'] for o in ops
                                   if o['q'].year == y]) > 0)
    pior = pico = atual = 0
    for o in ops:
        atual += o['liq']; pico = max(pico, atual)
        pior = min(pior, atual - pico)
    print(f"{rot:<{larg}}{len(ops):>5}{len(ops)/meses:>6.1f}"
          f"{len(g)/len(ops)*100:>7.1f}%"
          f"{statistics.mean(o['rr'] for o in ops):>6.2f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{z_de(v):>+8.2f}"
          f"{len(L):>6}{sum(1 for x in lv if x > 0):>5}{z_de(lv):>+8.2f}"
          f"{max(lv)/tot*100 if tot > 0 else 0:>7.0f}%{pior:>+8.0f}"
          f"  {bons}/{len(anos)}")


def cab(larg=38):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>8}{'R:R':>6}"
          f"{'líq/op':>9}{'total':>9}{'z/op':>8}{'lotes':>6}{'pos':>5}"
          f"{'z/LOTE':>8}{'maior':>8}{'rebaix':>8}  anos+")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    a = ap.parse_args()
    serie = {}
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            serie[os.path.basename(p).replace('_1h.csv', '')] = h
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    meses = (t1-t0)/(1000*3600*24*30.4)
    janelas = []
    t = t0 + TRI
    while t < t1:
        janelas.append((t, sorted(serie,
                                  key=lambda s: -vol(serie[s], t-TRI, t))))
        t += TRI
    # o atr e o medvol sao a parte cara: uma vez por moeda, para sempre
    ind = {s: (e8.atr(h, 14), e8.medvol(h, 20)) for s, h in serie.items()}
    cache = {}

    def rolante(cfg):
        ch = tuple(sorted((k, str(v)) for k, v in cfg.items()))
        ops = []
        for t, jan in janelas:
            for s in jan[:a.n]:
                key = (s, ch)
                if key not in cache:
                    at, mv = ind[s]
                    cache[key] = ops_de(serie[s], s, cfg, at, mv)
                ops += [o for o in cache[key] if t <= o['ms'] < t + TRI]
        return sorted(ops, key=lambda o: o['ms'])

    print(f"universo ROLANTE de {a.n} · {meses:.0f} meses · setup 5 · "
          f"risco fixo de $100 por operação\n")
    print("  O universo é re-escolhido a cada trimestre pelo volume mediano "
          "do trimestre ANTERIOR.\n  z/op assume que as operações são "
          "independentes — elas não são. O z/LOTE é o que vale:\n  ele "
          "agrupa tudo que cai dentro de 14 dias e conta o sinal do lote.\n")
    guard = {}
    for rot, cfg in CANDIDATAS:
        guard[rot] = rolante(cfg)

    print(f"{'='*150}\n  OS 7 ANOS INTEIROS\n{'='*150}")
    cab()
    for rot, _ in CANDIDATAS:
        painel(rot, guard[rot], meses)

    # O Eduardo: 'de 2025 para tras ja e muito tempo, ja e um outro tipo de
    # mercado'. Entao o recorte recente, por conta propria.
    for ini in (2025, 2026):
        ops_f = {r: [o for o in v if o['q'].year >= ini]
                 for r, v in guard.items()}
        m = max((max(o['q'] for o in v) - min(o['q'] for o in v)).days/30.4
                for v in ops_f.values() if v)
        print(f"\n{'='*150}\n  SÓ DE {ini} PARA CÁ  ({m:.0f} meses)\n{'='*150}")
        cab()
        for rot, _ in CANDIDATAS:
            painel(rot, ops_f[rot], m)

    # E o ano a ano das tres que interessam
    print(f"\n{'='*150}\n  ANO A ANO\n{'='*150}")
    anos = sorted({o['q'].year for v in guard.values() for o in v})
    for rot, _ in CANDIDATAS[:4]:
        print(f"\n  {rot}")
        cab(larg=38)
        for y in anos:
            painel(f"    {y}", [o for o in guard[rot] if o['q'].year == y],
                   12)
    print()


if __name__ == '__main__':
    main()
