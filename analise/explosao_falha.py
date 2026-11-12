"""A FALHA da explosao: o preco volta no order block e atravessa.

A explosao sobe, o preco volta, encosta no order block -- e em vez de
quicar, fecha do outro lado. Isso e o que acontece em 70% das vezes no
H1. Aqui a gente opera isso: vende a quebra, em vez de comprar o quique.

  confirmacao = 1 vela fechando alem do order block
                2 velas seguidas fechando alem
                reteste: fecha alem, volta no order block e falha de novo
  alvo        = o fundo de onde a explosao saiu, ou um multiplo do risco
  stop        = acima do topo do order block

Uso:  python3 explosao_falha.py <pasta> [--tf 1,4,8] [--corte 0.32]
"""
import sys, os, glob, statistics, random, argparse, itertools
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explosao import (ler, juntar, atr, medvol, curva, RISCO, TAXA, FUND8)

BRT = dt.timezone(dt.timedelta(hours=-3))
MAXBAR = 120


def achar(h, cfg, tf):
    a, mv = atr(h, 14), medvol(h, 20)
    jan, ops = cfg['janela'], []
    i = max(jan, 21) + 1
    while i < len(h) - 3:
        o, hi, lo, cl, vol = h[i][1], h[i][2], h[i][3], h[i][4], h[i][5]
        rng, av, mvv = hi - lo, a[i-1], mv[i-1]
        if rng <= 0 or av <= 0 or mvv <= 0:
            i += 1; continue
        if rng < cfg['sigma']*av or abs(cl-o)/rng < 0.5 or vol < cfg['vol']*mvv:
            i += 1; continue
        alta = cl > o
        if alta:
            if cl <= max(x[2] for x in h[i-jan:i]): i += 1; continue
        else:
            if cl >= min(x[3] for x in h[i-jan:i]): i += 1; continue
        j, ob = i-1, None
        while j >= max(0, i - cfg['ob_busca']):
            if (h[j][4] > h[j][1]) != alta:
                ob = j; break
            j -= 1
        if ob is None:
            i += 1; continue
        ob_base, ob_topo = h[ob][3], h[ob][2]
        borda = ob_topo if alta else ob_base          # onde encosta
        quebra = ob_base if alta else ob_topo         # onde falha
        # de onde a explosao saiu: o extremo das 20 velas antes dela
        origem = min(x[3] for x in h[i-jan:i+1]) if alta else \
                 max(x[2] for x in h[i-jan:i+1])

        g = seguir(h, a, i, alta, borda, quebra, origem, cfg)
        if g:
            ops.append(g); i = g['k'] + 1
        else:
            i += 1
    return ops


def seguir(h, a, i, alta, borda, quebra, origem, cfg):
    """alta = a explosao foi de alta; a FALHA dela e uma venda."""
    tocou = conf = None
    pico = h[i][2] if alta else h[i][3]
    for k in range(i+1, min(i + cfg['espera'] + 1, len(h))):
        o, hi, lo, cl = h[k][1], h[k][2], h[k][3], h[k][4]
        if tocou is None:
            pico = max(pico, hi) if alta else min(pico, lo)
            if (lo <= borda) if alta else (hi >= borda):
                tocou = k
            else:
                continue
        if k - tocou > cfg['espera_falha']:
            return None
        # a explosao deu certo e foi embora: nao e falha
        if (hi >= pico) if alta else (lo <= pico):
            return None
        fechou_alem = (cl < quebra) if alta else (cl > quebra)
        if cfg['conf'] == 1:
            if not fechou_alem:
                continue
            kk = k
        elif cfg['conf'] == 2:
            if not fechou_alem:
                conf = None; continue
            if conf is None:
                conf = k; continue
            kk = k                      # segunda seguida
        else:                            # reteste
            if conf is None:
                if fechou_alem:
                    conf = k
                continue
            # depois de quebrar, voltou a encostar e falhou de novo?
            volta = (hi >= quebra) if alta else (lo <= quebra)
            if not volta:
                continue
            if not fechou_alem:
                continue
            kk = k
        ent = h[kk][4]
        # stop do lado de fora do order block, usando o extremo desde a volta
        ext = max(x[2] for x in h[tocou:kk+1]) if alta else \
              min(x[3] for x in h[tocou:kk+1])
        s = ext + a[kk]*0.10 if alta else ext - a[kk]*0.10
        risco = abs(ent - s)
        if risco <= 0:
            return None
        if cfg['alvo'] == 'origem':
            alv = origem
        else:
            alv = ent - cfg['alvo']*risco if alta else ent + cfg['alvo']*risco
        dist = (ent - alv) if alta else (alv - ent)
        if dist <= 0 or dist/risco < cfg['rr_min']:
            return None
        # a FALHA de uma explosao de alta e uma VENDA
        venda = alta
        for m in range(kk+1, min(kk+1+MAXBAR, len(h))):
            vh, vl = h[m][2], h[m][3]
            if venda:
                if vh >= s: fim, saida = 'stop', s; break
                if vl <= alv: fim, saida = 'alvo', alv; break
            else:
                if vl <= s: fim, saida = 'stop', s; break
                if vh >= alv: fim, saida = 'alvo', alv; break
        else:
            return None
        pos = RISCO / (risco/ent)
        mov = (saida-ent)/ent * (-1 if venda else 1)
        horas = (m - kk)
        liq = pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8
        q = dt.datetime.fromtimestamp(h[kk][0]/1000, BRT)
        return dict(k=kk, lado='venda' if venda else 'compra', ent=ent,
                    stop=s, alvo=alv, rr=dist/risco, fim=fim, liq=liq,
                    risco_pct=risco/ent*100, q=q, ano=q.year,
                    mes=q.strftime('%Y-%m'), velas=m-kk)


BASE = dict(sigma=2.5, vol=1.5, janela=20, ob_busca=6, espera=30,
            espera_falha=6, conf=1, alvo='origem', rr_min=1.2)


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, larg=34):
    if not sel:
        print(f"{rot:<{larg}}{'—':>6}"); return
    v = [o['liq'] for o in sel]
    g = [x for x in v if x > 0]
    tot, dd = curva(v)
    p25 = [o['liq'] for o in sel if o['ano'] == 2025]
    p26 = [o['liq'] for o in sel if o['ano'] == 2026]
    z = ''
    if len(v) >= 25:
        random.seed(3)
        nu = [statistics.mean([x if random.random() < .5 else -x for x in v])
              for _ in range(300)]
        dp = statistics.pstdev(nu) or 1e-9
        z = f"{(statistics.mean(v)-statistics.mean(nu))/dp:>+7.2f}"
    print(f"{rot:<{larg}}{len(v):>6}{len(g)/len(v)*100:>8.1f}%"
          f"{statistics.mean(v):>+10.1f}{tot:>+10.0f}{dd:>8.0f}{ps(v):>5}"
          f"{(statistics.mean(p25) if p25 else 0):>+10.1f}{len(p25):>5}"
          f"{(statistics.mean(p26) if p26 else 0):>+10.1f}{len(p26):>5}{z:>7}")


def cab(larg=34):
    print(f"{'':<{larg}}{'n':>6}{'acerto':>9}{'méd/op':>10}{'total':>10}"
          f"{'rb':>8}{'seq':>5}{'2025':>10}{'n25':>5}{'2026':>10}{'n26':>5}"
          f"{'z':>7}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--tf', default='1,4,8')
    ap.add_argument('--corte', type=float, default=0.32)
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400 and \
                statistics.median(v[4]*v[5] for v in h) >= a.corte*1e6:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h))
    print(f"{len(cru)} moedas com volume mediano ≥ {a.corte:.2f} M USD/h")

    variantes = [
        ('1 vela · alvo na origem', dict(BASE)),
        ('2 velas seguidas · origem', dict(BASE, conf=2)),
        ('reteste da quebra · origem', dict(BASE, conf=3)),
        ('1 vela · alvo 2x o risco', dict(BASE, alvo=2.0)),
        ('1 vela · alvo 3x o risco', dict(BASE, alvo=3.0)),
        ('2 velas · alvo 2x o risco', dict(BASE, conf=2, alvo=2.0)),
        ('reteste · alvo 2x o risco', dict(BASE, conf=3, alvo=2.0)),
        ('1 vela · R:R mínimo 1:2', dict(BASE, rr_min=2.0)),
    ]
    for tf in [int(x) for x in a.tf.split(',')]:
        print(f"\n{'='*125}\n  H{tf} — falha da explosão\n{'='*125}")
        cab()
        for rot, cfg in variantes:
            ops = []
            for sim, h1 in cru:
                hg = juntar(h1, tf)
                if len(hg) >= 120:
                    ops += [dict(x, sim=sim) for x in achar(hg, cfg, tf)]
            ops.sort(key=lambda o: o['q'])
            painel(rot, ops)


if __name__ == '__main__':
    main()
