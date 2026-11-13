"""Os dois setups do bot conversam entre si?

  setup 1  a varredura do order block, em H1. O que vale dinheiro.
  setup 3  a reversao de 8h com entrada no H1. Em teste.

Mede tres coisas:
  1. quantas operacoes cada um da, no MESMO universo e periodo
  2. se eles disparam nas mesmas moedas nos mesmos dias
  3. se o setup 1 melhora quando pega emprestado o que faz o 3 funcionar

Uso:  python3 cruzar_setups.py <pasta> [--n 150]
"""
import argparse
import bisect
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
import reversao8 as rev
import explosao8 as e8
from explosao import ler, curva, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))
MAXBAR = 120


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, larg=34):
    if not sel:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in sel]
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    anos = sorted({o['ano'] for o in sel})
    por, bons = [], 0
    for y in anos:
        vy = [o['liq'] for o in sel if o['ano'] == y]
        m = statistics.mean(vy)
        bons += m > 0
        por.append(f"{str(y)[2:]}:{m:+.0f}({len(vy)})")
    z = ''
    if len(v) >= 25:
        random.seed(3)
        nu = [statistics.mean([x if random.random() < .5 else -x for x in v])
              for _ in range(300)]
        z = f"{(statistics.mean(v)-statistics.mean(nu))/(statistics.pstdev(nu) or 1e-9):+.2f}"
    print(f"{rot:<{larg}}{len(v):>5}{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(o['rr'] for o in sel):>7.2f}"
          f"{statistics.mean(o.get('stop_pct', 0) for o in sel):>7.2f}%"
          f"{statistics.mean(v):>+10.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{z:>8}{bons}/{len(anos):>2}  {' '.join(por)}")


def cab(larg=34):
    print(f"{'':<{larg}}{'n':>5}{'acerto':>9}{'R:R':>7}{'stop':>8}"
          f"{'méd/op':>10}"
          f"{'total':>9}{'rb':>8}{'seq':>5}{'z':>8}{'anos+':>5}"
          f"  por ano")


def resolver(h, idx, ent, stop, alvo, compra, maxbar=MAXBAR):
    for k in range(idx+1, min(idx+1+maxbar, len(h))):
        hi, lo = h[k][2], h[k][3]
        if compra:
            if lo <= stop: return 'stop', stop, k
            if hi >= alvo: return 'alvo', alvo, k
        else:
            if hi >= stop: return 'stop', stop, k
            if lo <= alvo: return 'alvo', alvo, k
    return None, None, None


def dinheiro(ent, saida, stop, compra, horas):
    pos = RISCO / (abs(ent-stop)/ent)
    mov = (saida-ent)/ent * (1 if compra else -1)
    return pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8


def varredura(h1, sim, cfg, extra):
    """O setup 1, com os emprestimos opcionais do setup 3."""
    a = bot.atr(h1, cfg['atr_periodo'])
    mv = bot.media_volume(h1, cfg['vol_periodo'])
    h8 = rev.juntar(h1, 8)
    a8 = e8.atr(h8, 14) if extra.get('queda') else None
    t8 = [v[0] for v in h8]
    ops = []
    for imp in bot.achar_impulsos(h1, a, mv, cfg):
        g = bot.seguir(h1, a, imp, cfg, mv)
        if not g or g.get('fase') != 'gatilho':
            continue
        compra = g['lado'] == 'compra'
        risco = abs(g['entrada'] - g['stop'])
        if extra.get('stop_min') and \
                risco/g['entrada']*100 < extra['stop_min']:
            continue
        if extra.get('stop_max') and \
                risco/g['entrada']*100 > extra['stop_max']:
            continue
        d = bot.piscina(h1, g['idx'], compra, g['entrada'], cfg['liq_janela'])
        if d is None or d/risco > cfg['liq_max_r']:
            continue
        # --- emprestimo 1: o contexto de queda de 7 dias do setup 3
        if extra.get('queda'):
            k8 = bisect.bisect_right(t8, h1[g['idx']][0]) - 1
            if k8 < 25 or a8[k8-1] <= 0:
                continue
            q = (h8[k8-20][4] - h8[k8-1][4]) / a8[k8-1] if compra else \
                (h8[k8-1][4] - h8[k8-20][4]) / a8[k8-1]
            if q < extra['queda']:
                continue
        # --- emprestimo 2: volume na vela do GATILHO (nao na varredura)
        if extra.get('vol_gat'):
            if mv[g['idx']] > 0 and \
                    h1[g['idx']][5] < extra['vol_gat']*mv[g['idx']]:
                continue
        # --- emprestimo 3: o alvo projetado do setup 3
        alvo = g['alvo']
        if extra.get('alvo_proj'):
            imp_ = g['imp']
            topo = imp_['topo']
            # tamanho do impulso: do inicio dele ate o extremo
            tam = abs(imp_['topo'] - h1[imp_['ini']][1])
            alvo = topo + extra['alvo_proj']*tam if compra else \
                   topo - extra['alvo_proj']*tam
        dist = (alvo - g['entrada']) if compra else (g['entrada'] - alvo)
        if dist <= 0:
            continue
        fim, saida, k = resolver(h1, g['idx'], g['entrada'], g['stop'],
                                 alvo, compra)
        if fim is None:
            continue
        q_ = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        ops.append(dict(sim=sim, ms=g['vela_ms'], q=q_, ano=q_.year,
                        rr=dist/risco, lado=g['lado'],
                        stop_pct=risco/g['entrada']*100,
                        liq=dinheiro(g['entrada'], saida, g['stop'],
                                     compra, k-g['idx'])))
    return ops


def reversao(h1, sim, stop_min=0.0, stop_max=0.0):
    h8 = rev.juntar(h1, 8)
    if len(h8) < 60:
        return []
    mv1 = e8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    ops = []
    for e in rev.explosoes(h8, rev.CFG):
        g = rev.entrada(h1, mv1, e, rev.CFG, pos1)
        if not g:
            continue
        compra = g['lado'] == 'compra'
        r_ = abs(g['entrada'] - g['stop'])/g['entrada']*100
        if stop_min and r_ < stop_min:
            continue
        if stop_max and r_ > stop_max:
            continue
        i8 = bisect.bisect_right([v[0] for v in h8], g['vela_ms']) - 1
        fim, saida, m = resolver(h8, i8, g['entrada'], g['stop'], g['alvo'],
                                 compra, rev.MAX_BARRAS)
        if fim is None:
            continue
        q_ = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        ops.append(dict(sim=sim, ms=g['vela_ms'], q=q_, ano=q_.year,
                        rr=g['rr'], lado=g['lado'], stop_pct=r_,
                        liq=dinheiro(g['entrada'], saida, g['stop'],
                                     compra, (m-i8)*8)))
    return ops


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
    CFG = dict(bot.CFG)
    print(f"as {len(cru)} maiores · mesmo universo e período para os dois\n")

    v1, v3 = [], []
    for sim, h1, _ in cru:
        v1 += varredura(h1, sim, CFG, {})
        v3 += reversao(h1, sim)
    v1.sort(key=lambda o: o['q']); v3.sort(key=lambda o: o['q'])
    meses = len({o['q'].strftime('%Y-%m') for o in v1 + v3}) or 1

    print(f"{'='*132}\n  1) QUANTO CADA UM DÁ, NO MESMO UNIVERSO\n{'='*132}")
    cab()
    painel(f'setup 1 — varredura H1', v1)
    painel(f'setup 3 — reversão H8', v3)
    print(f"\n  por mês: setup 1 = {len(v1)/meses:.1f}  ·  "
          f"setup 3 = {len(v3)/meses:.1f}  ·  juntos "
          f"{(len(v1)+len(v3))/meses:.1f}")

    print(f"\n{'='*132}\n  2) ELES DISPARAM JUNTOS?\n{'='*132}")
    por3 = {}
    for o in v3:
        por3.setdefault(o['sim'], []).append(o['ms'])
    for v in por3.values():
        v.sort()
    for jan_h, rot in ((24, '24 horas'), (72, '3 dias'), (168, '7 dias')):
        n = 0
        for o in v1:
            vv = por3.get(o['sim'])
            if not vv:
                continue
            i = bisect.bisect_left(vv, o['ms'] - jan_h*3600_000)
            if i < len(vv) and vv[i] <= o['ms'] + jan_h*3600_000:
                n += 1
        print(f"  operações do setup 1 com uma do setup 3 na mesma moeda "
              f"em ±{rot}: {n} de {len(v1)} ({n/len(v1)*100:.1f}%)")
    print("  (se fosse alto, seriam o mesmo evento contado duas vezes)")

    print(f"\n{'='*132}\n  3) O SETUP 1 MELHORA PEGANDO EMPRESTADO DO 3?\n"
          f"{'='*132}")
    cab()
    painel('setup 1 como está', v1)
    for rot, extra in (
            ('+ veio de queda de 1 volatilidade', dict(queda=1.0)),
            ('+ veio de queda de 2 volatilidades', dict(queda=2.0)),
            ('+ volume ≥1,2x na vela do gatilho', dict(vol_gat=1.2)),
            ('+ volume ≥1,5x na vela do gatilho', dict(vol_gat=1.5)),
            ('+ alvo projetado +90%', dict(alvo_proj=0.9)),
            ('+ queda 2 vol E volume ≥1,2x', dict(queda=2.0, vol_gat=1.2)),
            ('+ queda 2 vol E alvo +90%', dict(queda=2.0, alvo_proj=0.9)),
    ):
        ops = []
        for sim, h1, _ in cru:
            ops += varredura(h1, sim, CFG, extra)
        ops.sort(key=lambda o: o['q'])
        painel(rot, ops)

    print(f"\n{'='*140}\n  4) O STOP MÍNIMO — sobe o acerto e baixa o R:R?\n"
          f"     (nos 5 minutos esse filtro levou o acerto de 32,4% a 40,7%\n"
          f"      e o R:R de 3,20 a 2,18, de graça. Aqui tem lucro embaixo.)\n"
          f"{'='*140}")
    cab()
    for sm in (0.0, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0):
        ops = []
        for sim, h1, _ in cru:
            ops += varredura(h1, sim, CFG, dict(stop_min=sm))
        ops.sort(key=lambda o: o['q'])
        painel(f'setup 1 · stop >= {sm:.1f}%' if sm else 'setup 1 · sem mínimo',
               ops)
    print()
    for sm in (0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 7.0):
        ops = []
        for sim, h1, _ in cru:
            ops += reversao(h1, sim, stop_min=sm)
        ops.sort(key=lambda o: o['q'])
        painel(f'setup 3 · stop >= {sm:.1f}%' if sm else 'setup 3 · sem mínimo',
               ops)
    print()
    for sx in (3.0, 5.0, 8.0, 12.0):
        ops = []
        for sim, h1, _ in cru:
            ops += varredura(h1, sim, CFG, dict(stop_max=sx))
        ops.sort(key=lambda o: o['q'])
        painel(f'setup 1 · stop <= {sx:.1f}%', ops)


if __name__ == '__main__':
    main()
