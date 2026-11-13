"""O setup 1 medido EXATAMENTE como o bot o roda.

O cruzar_setups resolve a operacao no stop fixo. O bot nao faz isso: ele
move o stop quando a estrutura A-B-C-D-E-F se completa a favor, com
folga de 0,25 ATR alem do extremo de E, e so se o stop novo travar pelo
menos 0,30 do risco. Esse script usa a mesma funcao que o bot usa
(acompanhamento.estruturas) e os mesmos parametros (FOLGA_ATR,
MIN_TRAVA), para separar "o setup nao presta" de "o teste nao era o
setup".

O risco e SEMPRE medido pelo stop ORIGINAL, senao o trailing faria as
perdas parecerem menores do que foram.

Uso:  python3 setup1_real.py <pasta> [--n 50] [--topo 150]
"""
import argparse
import glob
import itertools
import os
import random
import statistics
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot_varredura as bot
import acompanhamento as acomp
from explosao import ler, curva, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))
MAXBAR = 120


def rodar(h1, sim, cfg, trailing, k_piv=acomp.K_PIVO, trava=acomp.MIN_TRAVA,
          folga=acomp.FOLGA_ATR, stop_min=0.0, maxbar=MAXBAR):
    a = bot.atr(h1, cfg['atr_periodo'])
    mv = bot.media_volume(h1, cfg['vol_periodo'])
    estr = acomp.estruturas(h1, k_piv) if trailing else {}
    ops = []
    for imp in bot.achar_impulsos(h1, a, mv, cfg):
        g = bot.seguir(h1, a, imp, cfg, mv)
        if not g or g.get('fase') != 'gatilho':
            continue
        compra = g['lado'] == 'compra'
        ent, stop0, alvo = g['entrada'], g['stop'], g['alvo']
        risco = abs(ent - stop0)
        if risco <= 0:
            continue
        if stop_min and risco/ent*100 < stop_min:
            continue
        d = bot.piscina(h1, g['idx'], compra, ent, cfg['liq_janela'])
        if d is None or d/risco > cfg['liq_max_r']:
            continue
        stop, moveu = stop0, False
        fim = saida = None
        for k in range(g['idx']+1, min(g['idx']+1+maxbar, len(h1))):
            hi, lo = h1[k][2], h1[k][3]
            if compra:
                if lo <= stop: fim, saida = 'stop', stop; break
                if hi >= alvo: fim, saida = 'alvo', alvo; break
            else:
                if hi >= stop: fim, saida = 'stop', stop; break
                if lo <= alvo: fim, saida = 'alvo', alvo; break
            # a estrutura so e conhecida no FECHAMENTO da vela: move
            # depois de testar stop e alvo nela
            e = estr.get(k)
            if e and e['alta'] == compra:
                novo = (e['extremo'] - a[k]*folga) if compra else \
                       (e['extremo'] + a[k]*folga)
                ganho = (novo - stop) if compra else (stop - novo)
                if ganho > 0 and abs(novo - stop0)/risco >= trava:
                    stop, moveu = novo, True
        if fim is None:
            continue
        pos = RISCO/(risco/ent)
        mov = (saida-ent)/ent*(1 if compra else -1)
        horas = k - g['idx']
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        ops.append(dict(sim=sim, q=q, ano=q.year, rr=abs(alvo-ent)/risco,
                        stop_pct=risco/ent*100, moveu=moveu, fim=fim,
                        bruto=pos*mov,
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return ops


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, meses, larg=34):
    if not sel:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in sel]
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    anos = sorted({o['ano'] for o in sel})
    por, bons = [], 0
    for y in anos:
        vy = [o['liq'] for o in sel if o['ano'] == y]
        m = statistics.mean(vy); bons += m > 0
        por.append(f"{str(y)[2:]}:{m:+.0f}({len(vy)})")
    z = ''
    if len(v) >= 25:
        random.seed(3)
        nu = [statistics.mean([x if random.random() < .5 else -x for x in v])
              for _ in range(300)]
        z = f"{(statistics.mean(v)-statistics.mean(nu))/(statistics.pstdev(nu) or 1e-9):+.2f}"
    mv = sum(1 for o in sel if o['moveu'])
    print(f"{rot:<{larg}}{len(v):>5}{len(v)/meses:>6.1f}{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(o['rr'] for o in sel):>7.2f}"
          f"{statistics.mean(o['stop_pct'] for o in sel):>7.2f}%"
          f"{statistics.mean(o['bruto'] for o in sel):>+8.1f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{mv/len(v)*100:>7.0f}%{z:>8}{bons}/{len(anos)}  {' '.join(por)}")


def cab(larg=34):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>9}{'R:R':>7}{'stop':>8}"
          f"{'bruto':>8}{'líq/op':>9}{'total':>9}{'rb':>8}{'seq':>5}"
          f"{'moveu':>8}{'z':>8}{'anos+':>4}  por ano")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=50)
    ap.add_argument('--topo', type=int, default=150)
    a = ap.parse_args()
    # as moedas que o bot realmente olha
    fila = bot.UNIVERSO[:a.n]
    cru, faltam = [], []
    for sim in fila:
        p = os.path.join(a.pasta, f'{sim}_1h.csv')
        if not os.path.exists(p):
            faltam.append(sim); continue
        h = ler(p)
        if len(h) < 400:
            faltam.append(sim); continue
        cru.append((sim, h))
    meses = max(len(h) for _, h in cru) / (24*30.4)
    print(f"as {len(cru)} moedas que o bot olha (UNIVERSO[:{a.n}]) · "
          f"{meses:.0f} meses")
    if faltam:
        print(f"  sem dado: {', '.join(faltam)}")
    print()
    CFG = dict(bot.CFG)
    cab()
    for rot, kw in (
            ('COMO O BOT RODA (trailing)',  dict(trailing=True)),
            ('  stop fixo, sem trailing',   dict(trailing=False)),
            ('  trailing · trava 0,0',      dict(trailing=True, trava=0.0)),
            ('  trailing · trava 0,5',      dict(trailing=True, trava=0.5)),
            ('  trailing · pivô 2 velas',   dict(trailing=True, k_piv=2)),
            ('  trailing · folga 0,5 ATR',  dict(trailing=True, folga=0.5)),
            ('  trailing + stop >= 1,5%',   dict(trailing=True, stop_min=1.5)),
            ('  trailing + stop >= 3,0%',   dict(trailing=True, stop_min=3.0)),
    ):
        ops = []
        for sim, h1 in cru:
            ops += rodar(h1, sim, CFG, **kw)
        ops.sort(key=lambda o: o['q'])
        painel(rot, ops, meses)

    # o mesmo, mas no universo largo, para separar "50 vs 150"
    print(f"\n  agora as {a.topo} maiores por volume, com o trailing:")
    larga = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            larga.append((os.path.basename(p).replace('_1h.csv', ''), h,
                          statistics.median(v[4]*v[5] for v in h)))
    larga.sort(key=lambda x: -x[2])
    cab()
    for n in (50, 100, a.topo):
        ops = []
        for sim, h1, _ in larga[:n]:
            ops += rodar(h1, sim, CFG, trailing=True)
        ops.sort(key=lambda o: o['q'])
        painel(f'  as {n} maiores · trailing', ops, meses)


if __name__ == '__main__':
    main()
