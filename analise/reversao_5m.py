"""A reversao em velas de 5 minutos, nos maiores ativos.

Tres leituras de "a mesma estrategia" num tempo grafico menor:

  fractal    as mesmas CONTAGENS de vela do H8: queda em 20 velas (100
             minutos), pivo de +-2, busca de 30. O desenho identico,
             so que menor.
  meio       janelas de algumas horas: queda em 240 velas (20h), pivo
             +-24 (2h), busca 360 (30h).
  ancorado   os mesmos TEMPOS do H8: queda em 160 horas, pivo de +-4h,
             busca de 240 horas. O mesmo contexto de uma semana.

Uso:  python3 reversao_5m.py <pasta> [--ativos BTCUSDT,...]
"""
import argparse, glob, itertools, os, random, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler, curva, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))
VPH = 12            # velas de 5 minutos por hora


def cfg5(nome):
    c = dict(rev.CFG)
    if nome == 'fractal':
        c.update(tend_jan=20, busca_topo=30, pivo=2, espera=90, gat_h1=6)
    elif nome == 'meio':
        c.update(tend_jan=240, busca_topo=360, pivo=24, espera=1080,
                 gat_h1=72)
    else:
        c.update(tend_jan=160*VPH, busca_topo=240*VPH, pivo=4*VPH,
                 espera=720*VPH, gat_h1=48*VPH)
    return c


def rodar(h, cfg, raso=True, vol_gat=1.2):
    mv = e8.medvol(h, 20)
    ops = []
    for e in rev.explosoes(h, cfg):
        alta, i = e['alta'], e['i']
        borda = e['ob_topo'] if alta else e['ob_base']
        meio = (e['ob_base'] + e['ob_topo']) / 2
        morte = (e['ob_base'] - e['atr']*cfg['furo_max']) if alta else \
                (e['ob_topo'] + e['atr']*cfg['furo_max'])
        pico, tocou, extremo, k_ent = e['topo'], None, None, None
        for k in range(i+1, min(i+1+cfg['espera'], len(h))):
            hi, lo, o, cl = h[k][2], h[k][3], h[k][1], h[k][4]
            if tocou is None:
                pico = max(pico, hi) if alta else min(pico, lo)
                if (lo <= borda) if alta else (hi >= borda):
                    tocou, extremo = k, (lo if alta else hi)
                else:
                    continue
            else:
                extremo = min(extremo, lo) if alta else max(extremo, hi)
            if (extremo < morte) if alta else (extremo > morte): break
            if k - tocou > cfg['gat_h1']: break
            if (hi >= pico) if alta else (lo <= pico): break
            if raso and ((extremo < meio) if alta else (extremo > meio)):
                break
            rng = hi - lo
            if rng <= 0: continue
            if not ((cl > borda) if alta else (cl < borda)): continue
            if not ((cl > o) if alta else (cl < o)): continue
            corpo = abs(cl-o)/rng
            pav = ((min(o, cl)-lo) if alta else (hi-max(o, cl)))/rng
            if not (corpo >= 0.5 or pav >= 0.5): continue
            if vol_gat and mv[k] > 0 and h[k][5] < vol_gat*mv[k]: continue
            k_ent = k; break
        if k_ent is None: continue
        ent = h[k_ent][4]
        stop = (e['ob_base'] - e['atr']*cfg['stop_folga']) if alta else \
               (e['ob_topo'] + e['atr']*cfg['stop_folga'])
        risco = abs(ent-stop)
        if risco <= 0: continue
        ate = (pico-ent) if alta else (ent-pico)
        if ate <= 0 or ate/risco < cfg['rr_min']: continue
        alvo = (e['topo'] + cfg['alvo_proj']*e['tam']) if alta else \
               (e['topo'] - cfg['alvo_proj']*e['tam'])
        dist = (alvo-ent) if alta else (ent-alvo)
        if dist <= 0: continue
        fim = saida = None
        for m in range(k_ent+1, min(k_ent+1+rev.MAX_BARRAS*8*VPH, len(h))):
            hi, lo = h[m][2], h[m][3]
            if alta:
                if lo <= stop: fim, saida = 'stop', stop; break
                if hi >= alvo: fim, saida = 'alvo', alvo; break
            else:
                if hi >= stop: fim, saida = 'stop', stop; break
                if lo <= alvo: fim, saida = 'alvo', alvo; break
        if fim is None: continue
        pos = RISCO/(risco/ent)
        mov = (saida-ent)/ent*(1 if alta else -1)
        horas = (m-k_ent)/VPH
        q = dt.datetime.fromtimestamp(h[k_ent][0]/1000, BRT)
        ops.append(dict(q=q, ano=q.year, rr=dist/risco,
                        risco_pct=risco/ent*100, bruto=pos*mov,
                        custo=pos*TAXA*2 + pos*(horas/8)*FUND8,
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return ops


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, meses, larg=30):
    if not sel:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in sel]; g = [x for x in v if x > 0]
    tot, dd = curva(v)
    anos = sorted({o['ano'] for o in sel}); por, bons = [], 0
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
    print(f"{rot:<{larg}}{len(v):>5}{len(v)/meses:>7.1f}"
          f"{len(g)/len(v)*100:>8.1f}%{statistics.mean(o['rr'] for o in sel):>7.2f}"
          f"{statistics.mean(o['risco_pct'] for o in sel):>7.2f}%"
          f"{statistics.mean(o['bruto'] for o in sel):>+9.1f}"
          f"{-statistics.mean(o['custo'] for o in sel):>7.1f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{dd:>8.0f}{ps(v):>5}"
          f"{z:>8}{bons}/{len(anos)}  {' '.join(por)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--ativos', default='')
    a = ap.parse_args()
    alvos = [x.strip().upper() for x in a.ativos.split(',') if x.strip()]
    arqs = sorted(glob.glob(os.path.join(a.pasta, '*_5m.csv')))
    cru = []
    for p in arqs:
        s = os.path.basename(p).replace('_5m.csv', '')
        if alvos and s not in alvos:
            continue
        h = ler(p)
        if len(h) >= 20000:
            cru.append((s, h))
    if not cru:
        print("sem dados de 5m"); return
    meses = max(len(h) for _, h in cru) / (12*24*30.4)
    print(f"{len(cru)} ativos · velas de 5 minutos · {meses:.0f} meses")
    print(f"  {', '.join(s for s, _ in cru)}\n")
    print(f"{'':<30}{'n':>5}{'/mês':>7}{'acerto':>9}{'R:R':>7}{'stop':>8}"
          f"{'bruto':>9}{'taxa':>7}{'líq/op':>9}{'total':>9}{'rb':>8}"
          f"{'seq':>5}{'z':>8}{'anos+':>4}  por ano")
    for nome, rot in (('fractal', 'fractal (mesmas contagens)'),
                      ('meio', 'meio-termo (janelas de horas)'),
                      ('ancorado', 'ancorado (mesmos 7 dias)')):
        cfg = cfg5(nome)
        ops = []
        for s, h in cru:
            ops += rodar(h, cfg)
        ops.sort(key=lambda o: o['q'])
        painel(rot, ops, meses)
        ops2 = []
        for s, h in cru:
            ops2 += rodar(h, cfg, vol_gat=0.0)
        ops2.sort(key=lambda o: o['q'])
        painel(f'  {nome}, sem volume', ops2, meses)


if __name__ == '__main__':
    main()
