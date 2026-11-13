"""A reversao lida no H1, com a ESTRUTURA do stop movel como gatilho.

O padrao (queda de 7 dias, uma vela rompe o ultimo topo, order block)
e o mesmo do H8. O que muda e a entrada: em vez de entrar na primeira
vela que fecha de volta para fora do order block, espera o preco
completar a estrutura A-B-C-D-E-F -- a mesma que o bot ja usa para
mover o stop:

  C e D  um fundo e um topo, com C acima de A e D acima de B
  E      varre o fundo de C e FALHA
  F      fecha acima do topo de D e confirma

No H1 o padrao acontece muito mais, e quase todo o excesso e ruido. A
aposta e que a estrutura separe o ruido do movimento de verdade.

Uso:  python3 reversao_estrutura.py <pasta> [--n 150] [--tf 1]
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
import reversao8 as rev
import explosao8 as e8
import acompanhamento as acomp
from explosao import ler, curva, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))

# O padrao no tempo grafico pedido, com as janelas valendo em HORAS
# (os mesmos 7 dias de queda e 10 dias procurando o topo do H8).
def cfg_tf(tfp, **extra):
    c = dict(rev.CFG)
    c['tend_jan'] = max(5, round(160/tfp))
    c['busca_topo'] = max(5, round(240/tfp))
    c['pivo'] = max(1, round(16/tfp))
    c['espera'] = max(5, round(720/tfp))
    c['gat_h1'] = round(48/tfp)
    c.update(extra)
    return c


def achar(h1, tfp, cfg, usar_estrutura, k_piv=1, stop_em_E=False,
          raso=True, vol_gat=0.0, esp_estr=24):
    """Devolve as operacoes da serie, com a entrada escolhida."""
    hp = rev.juntar(h1, tfp) if tfp > 1 else h1
    if len(hp) < 120:
        return []
    mv = e8.medvol(hp, 20)
    estr = acomp.estruturas(hp, k_piv, 20, 12) if usar_estrutura else {}
    ops = []
    for e in rev.explosoes(hp, cfg):
        alta = e['alta']
        i = e['i']
        borda = e['ob_topo'] if alta else e['ob_base']
        meio = (e['ob_base'] + e['ob_topo']) / 2
        morte = (e['ob_base'] - e['atr']*cfg['furo_max']) if alta else \
                (e['ob_topo'] + e['atr']*cfg['furo_max'])
        pico, tocou, extremo, ent_k = e['topo'], None, None, None
        for k in range(i+1, min(i+1+cfg['espera'], len(hp))):
            hi, lo, o, cl = hp[k][2], hp[k][3], hp[k][1], hp[k][4]
            if tocou is None:
                pico = max(pico, hi) if alta else min(pico, lo)
                if (lo <= borda) if alta else (hi >= borda):
                    tocou, extremo = k, (lo if alta else hi)
                else:
                    continue
            else:
                extremo = min(extremo, lo) if alta else max(extremo, hi)
            if (extremo < morte) if alta else (extremo > morte):
                break
            if (hi >= pico) if alta else (lo <= pico):
                break
            if raso and ((extremo < meio) if alta else (extremo > meio)):
                break
            if usar_estrutura:
                if k - tocou > esp_estr:
                    break
                s = estr.get(k)
                if not s or s['alta'] != alta:
                    continue
                ent_k, ext_E = k, s['extremo']
            else:
                if k - tocou > cfg['gat_h1']:
                    break
                rng = hi - lo
                dentro = (cl > borda) if alta else (cl < borda)
                favor = (cl > o) if alta else (cl < o)
                if rng <= 0 or not dentro or not favor:
                    continue
                corpo = abs(cl-o)/rng
                pav = ((min(o, cl)-lo) if alta else (hi-max(o, cl)))/rng
                if not (corpo >= 0.5 or pav >= 0.5):
                    continue
                ent_k, ext_E = k, extremo
            if vol_gat and mv[k] > 0 and hp[k][5] < vol_gat*mv[k]:
                ent_k = None
                continue
            break
        if ent_k is None:
            continue
        ent = hp[ent_k][4]
        if stop_em_E:
            stop = ext_E - e['atr']*cfg['stop_folga'] if alta else \
                   ext_E + e['atr']*cfg['stop_folga']
        else:
            stop = (e['ob_base'] - e['atr']*cfg['stop_folga']) if alta else \
                   (e['ob_topo'] + e['atr']*cfg['stop_folga'])
        risco = abs(ent - stop)
        if risco <= 0:
            continue
        ate_topo = (pico - ent) if alta else (ent - pico)
        if ate_topo <= 0 or ate_topo/risco < cfg['rr_min']:
            continue
        alvo = (e['topo'] + cfg['alvo_proj']*e['tam']) if alta else \
               (e['topo'] - cfg['alvo_proj']*e['tam'])
        dist = (alvo - ent) if alta else (ent - alvo)
        if dist <= 0:
            continue
        fim = saida = None
        for m in range(ent_k+1, min(ent_k+1+rev.MAX_BARRAS, len(hp))):
            hi, lo = hp[m][2], hp[m][3]
            if alta:
                if lo <= stop: fim, saida = 'stop', stop; break
                if hi >= alvo: fim, saida = 'alvo', alvo; break
            else:
                if hi >= stop: fim, saida = 'stop', stop; break
                if lo <= alvo: fim, saida = 'alvo', alvo; break
        if fim is None:
            continue
        pos = RISCO/(risco/ent)
        mov = (saida-ent)/ent*(1 if alta else -1)
        horas = (m-ent_k)*tfp
        q = dt.datetime.fromtimestamp(hp[ent_k][0]/1000, BRT)
        ops.append(dict(q=q, ano=q.year, rr=dist/risco,
                        risco_pct=risco/ent*100,
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return ops


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, meses, larg=38):
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
    print(f"{rot:<{larg}}{len(v):>5}{len(v)/meses:>7.1f}"
          f"{len(g)/len(v)*100:>8.1f}%{statistics.mean(o['rr'] for o in sel):>7.2f}"
          f"{statistics.mean(v):>+10.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{z:>8}{bons}/{len(anos)}  {' '.join(por)}")


def cab(larg=38):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>7}{'acerto':>9}{'R:R':>7}"
          f"{'méd/op':>10}{'total':>9}{'rb':>8}{'seq':>5}{'z':>8}{'anos+':>4}"
          f"  por ano")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    ap.add_argument('--tf', type=int, default=1)
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h,
                        statistics.median(v[4]*v[5] for v in h)))
    cru.sort(key=lambda x: -x[2])
    cru = cru[:a.n]
    meses = len(cru[0][1]) / (24*30.4) if cru else 1
    print(f"as {len(cru)} maiores · padrão em H{a.tf} · "
          f"{meses:.0f} meses\n")

    cfg = cfg_tf(a.tf)
    VAR = [
        ('gatilho simples (o de hoje, em H1)',
         dict(usar_estrutura=False)),
        ('gatilho simples + volume ≥1,2x',
         dict(usar_estrutura=False, vol_gat=1.2)),
        ('ESTRUTURA (pivô de 1 vela)',
         dict(usar_estrutura=True, k_piv=1)),
        ('ESTRUTURA (pivô de 2 velas)',
         dict(usar_estrutura=True, k_piv=2)),
        ('ESTRUTURA + stop no extremo de E',
         dict(usar_estrutura=True, k_piv=1, stop_em_E=True)),
        ('ESTRUTURA + volume ≥1,2x',
         dict(usar_estrutura=True, k_piv=1, vol_gat=1.2)),
        ('ESTRUTURA, sem exigir encosto raso',
         dict(usar_estrutura=True, k_piv=1, raso=False)),
        ('ESTRUTURA, espera 48 velas',
         dict(usar_estrutura=True, k_piv=1, esp_estr=48)),
    ]
    cab()
    for rot, kw in VAR:
        ops = []
        for sim, h1, _ in cru:
            ops += achar(h1, a.tf, cfg, **kw)
        ops.sort(key=lambda o: o['q'])
        painel(rot, ops, meses)


if __name__ == '__main__':
    main()
