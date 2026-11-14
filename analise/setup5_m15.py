"""SETUP 5 em 15 MINUTOS: o padrao vive em 60 VELAS ou em 60 HORAS?

Pedido do Eduardo: os 5 ativos principais, 2025 e 2026, a configuracao
que ja esta no bot, em M15.

A pergunta que isso responde. A configuracao e toda contada em VELAS --
faixa de 60, ida de ate 24, falha em ate 16, piscina em 120, contexto em
300. Em H1 isso vira uma faixa de 60 horas e uma operacao que fica 42h
aberta na mediana. Em M15 as MESMAS 60 velas viram 15 horas, e a operacao
deve fechar em ~10h.

  se o numero aguentar  -> o padrao e estrutural (vale a forma, nao o
                           relogio) e em M15 cabem 4x mais gatilhos
  se desabar            -> o que funciona e um ciclo de mercado de uns
                           dois dias, e M15 e ruido

O H1 roda do lado, nos MESMOS 5 ativos e no MESMO periodo. Sem esse
controle o numero de M15 nao quer dizer nada: se M15 der pior, pode ser o
tempo grafico ou pode ser que 5 ativos grandes em 2 anos seja pouco.

Uso:  python3 setup5_m15.py <pasta> [--n 5] [--desde 2025]
"""
import argparse, glob, os, statistics, sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explosao8 as e8
import setup5_falha as s5
import falha5
from explosao import ler
from alvo_lote import z_de
from venda_topo import lotes_de

BRT = dt.timezone(dt.timedelta(hours=-3))
TFH = {'15m': 0.25, '1h': 1.0, '4h': 4.0}


def volume_mediano(h):
    v = sorted(c[4]*c[5] for c in h)
    return v[len(v)//2] if v else 0.0


def rodar(h, sim, cfg, tf, desde):
    at, mv = e8.atr(h, 14), e8.medvol(h, 20)
    out = []
    for g in s5.achar(h, cfg, at, mv):
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        if q.year < desde:
            continue
        r = s5.resolver(h, g, tf)
        if not r:
            continue
        out.append(dict(sim=sim, q=q, ano=q.year, lado=g['lado'],
                        rr=g['rr'], risco_pct=g['risco_pct'],
                        fim=r['fim'], liq=r['liq'], horas=r['horas']))
    return sorted(out, key=lambda o: o['q'])


def linha(rot, ops, meses, larg=22):
    if not ops:
        print(f"  {rot:<{larg}}{'—':>6}")
        return
    v = [o['liq'] for o in ops]
    g = [o for o in ops if o['fim'] == 'alvo']
    lv = [sum(y['liq'] for y in x) for x in lotes_de(ops)]
    tot = sum(v)
    pior = pico = atual = 0.0
    for o in ops:
        atual += o['liq']; pico = max(pico, atual)
        pior = min(pior, atual - pico)
    cp = sum(1 for o in ops if o['lado'] == 'compra')
    print(f"  {rot:<{larg}}{len(ops):>6}{len(ops)/meses:>7.1f}"
          f"{len(g)/len(ops)*100:>8.1f}%"
          f"{statistics.mean(o['rr'] for o in ops):>7.2f}"
          f"{statistics.mean(o['risco_pct'] for o in ops):>8.2f}%"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{z_de(lv):>+8.2f}"
          f"{pior:>+9.0f}{statistics.median(o['horas'] for o in ops):>8.0f}h"
          f"{cp:>6}/{len(ops)-cp}")


def cab(larg=22):
    print(f"  {'':<{larg}}{'ops':>6}{'/mês':>7}{'acerto':>9}{'R:R':>7}"
          f"{'stop':>9}{'líq/op':>9}{'total':>9}{'z/LOTE':>8}{'rebaix':>9}"
          f"{'aberta':>9}{'C/V':>12}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=5)
    ap.add_argument('--desde', type=int, default=2025)
    a = ap.parse_args()

    # a configuracao EXATA do bot, contada em velas
    cfg = dict(s5.CFG5, **{k: v for k, v in falha5.CFG.items()
                           if k in s5.CFG5})

    base = {}
    for iv in ('15m', '1h'):
        for p in sorted(glob.glob(os.path.join(a.pasta, f'*_{iv}.csv'))):
            sim = os.path.basename(p).split('_')[0]
            h = ler(p)
            if len(h) >= 500:
                base.setdefault(sim, {})[iv] = h
    completos = {s: d for s, d in base.items() if {'15m', '1h'} <= set(d)}
    if not completos:
        print("não achei par nenhum com 15m E 1h na pasta", a.pasta)
        return

    # os N principais pelo volume mediano em dolar, medido no H1
    top = sorted(completos, key=lambda s: -volume_mediano(completos[s]['1h']))
    escolhidos = top[:a.n]
    h1 = completos[escolhidos[0]]['1h']
    t0, t1 = h1[0][0], h1[-1][0]
    ini = max(t0, dt.datetime(a.desde, 1, 1, tzinfo=dt.timezone.utc)
              .timestamp()*1000)
    meses = (t1-ini)/(1000*3600*24*30.4)

    print(f"setup 5 em M15 contra H1 · {a.n} ativos · de {a.desde} para cá "
          f"({meses:.0f} meses) · risco fixo de $100\n")
    print(f"  os {a.n} escolhidos pelo volume mediano: "
          f"{', '.join(escolhidos)}")
    if len(top) > a.n:
        print(f"  (baixados e fora do corte: {', '.join(top[a.n:])})")
    print(f"\n  a mesma configuração, contada em VELAS: faixa {cfg['lat_jan']},"
          f" ida até {cfg['ida_max']}, falha até {cfg['falha_max']},"
          f" piscina {cfg['liq_janela']}, contexto {cfg['pre_jan']}")
    print(f"  em H1 isso é uma faixa de {cfg['lat_jan']}h; "
          f"em M15, de {cfg['lat_jan']/4:.0f}h\n")

    guard = {}
    for iv in ('1h', '15m'):
        ops = []
        for sim in escolhidos:
            ops += rodar(completos[sim][iv], sim, cfg, TFH[iv], a.desde)
        guard[iv] = sorted(ops, key=lambda o: o['q'])

    print(f"{'='*118}\n  OS DOIS TEMPOS GRÁFICOS, LADO A LADO\n{'='*118}")
    cab()
    linha('H1 (o do bot hoje)', guard['1h'], meses)
    linha('M15', guard['15m'], meses)

    print(f"\n{'='*118}\n  ANO A ANO\n{'='*118}")
    for iv in ('1h', '15m'):
        print(f"\n  · {iv}")
        cab()
        for y in sorted({o['ano'] for o in guard[iv]}):
            linha(str(y), [o for o in guard[iv] if o['ano'] == y], 12)

    print(f"\n{'='*118}\n  ATIVO POR ATIVO\n{'='*118}")
    for iv in ('1h', '15m'):
        print(f"\n  · {iv}")
        cab()
        for sim in escolhidos:
            linha(sim, [o for o in guard[iv] if o['sim'] == sim], meses)
    print()


if __name__ == '__main__':
    main()
