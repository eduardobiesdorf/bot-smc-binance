"""VWAP ancorada: o choque anda, a gente ancora a VWAP no inicio dele e
entra no toque dela, a favor do movimento. Alvo curto (1:1), stop curto.

  choque   = movimento forte e direcional (vela unica explosiva OU
             pernada de 3 a 8 velas, as duas testadas)
  ancora   = a primeira vela do choque, ou o extremo dele
  VWAP     = soma(preco tipico x volume) / soma(volume), desde a ancora
  entrada  = o preco volta e toca a VWAP, a favor do choque
  validade = a ordem so vale por N velas (a "hora limite")
  stop     = 1% fixo, ou uma fracao da volatilidade, ou o extremo da volta
  alvo     = multiplo do risco

Uso:  python3 vwap_ancorada.py <pasta> [--tf 1] [--corte 0.32]
"""
import sys, os, glob, statistics, random, argparse, itertools
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explosao import (ler, juntar, atr, medvol, curva, RISCO, TAXA, FUND8)

BRT = dt.timezone(dt.timedelta(hours=-3))
MAXBAR = 120


def choques_vela(h, a, mv, cfg):
    """Uma vela so, explosiva, rompendo o extremo de 20 velas."""
    jan = cfg['janela']
    for i in range(max(jan, 21) + 1, len(h) - 2):
        o, hi, lo, cl, vol = h[i][1], h[i][2], h[i][3], h[i][4], h[i][5]
        rng = hi - lo
        if rng <= 0 or a[i-1] <= 0 or mv[i-1] <= 0:
            continue
        if rng < cfg['sigma']*a[i-1] or abs(cl-o)/rng < 0.5:
            continue
        if vol < cfg['vol']*mv[i-1]:
            continue
        alta = cl > o
        if alta and cl <= max(x[2] for x in h[i-jan:i]):
            continue
        if not alta and cl >= min(x[3] for x in h[i-jan:i]):
            continue
        yield i, i, alta          # (inicio, fim, direcao)


def choques_perna(h, a, mv, cfg):
    """Pernada de 3 a 8 velas, >= sigma de volatilidade, direcional."""
    jan = cfg['janela']
    i = max(jan, 21) + 1
    while i < len(h) - 2:
        achou = None
        for n in range(3, 9):
            f = i + n - 1
            if f >= len(h) - 2:
                break
            tramo = h[i:f+1]
            alta = h[f][4] > h[i][1]
            desloc = abs(h[f][4] - h[i][1])
            if a[i-1] <= 0 or desloc < cfg['sigma']*a[i-1]:
                continue
            favor = sum(1 for v in tramo if (v[4] > v[1]) == alta)
            if favor / len(tramo) < 0.7:
                continue
            corpo = sum(abs(v[4]-v[1]) for v in tramo)
            faixa = sum(v[2]-v[3] for v in tramo)
            if faixa <= 0 or corpo/faixa < 0.5:
                continue
            vm = statistics.mean(v[5] for v in tramo)
            if mv[i-1] <= 0 or vm < cfg['vol']*mv[i-1]:
                continue
            if alta and h[f][4] <= max(x[2] for x in h[i-jan:i]):
                continue
            if not alta and h[f][4] >= min(x[3] for x in h[i-jan:i]):
                continue
            achou = (i, f, alta)
            break
        if achou:
            yield achou
            i = achou[1] + 1
        else:
            i += 1


def seguir(h, a, ini, fim, alta, cfg):
    anc = ini if cfg['ancora'] == 'inicio' else fim
    pv = vv = 0.0
    for k in range(anc, fim + 1):
        tp = (h[k][2] + h[k][3] + h[k][4]) / 3
        pv += tp * h[k][5]; vv += h[k][5]
    extremo = max(x[2] for x in h[ini:fim+1]) if alta else \
              min(x[3] for x in h[ini:fim+1])
    origem = h[ini][1]
    for k in range(fim + 1, min(fim + 1 + cfg['validade'], len(h))):
        hi, lo, cl = h[k][2], h[k][3], h[k][4]
        vwap = pv / vv if vv > 0 else None
        # o choque foi embora sem a gente? nao importa, a ordem segue valida
        # mas se o preco desfez o choque inteiro, cancela
        if (cl < origem) if alta else (cl > origem):
            return None
        if vwap is not None:
            tocou = (lo <= vwap) if alta else (hi >= vwap)
            if tocou:
                ent = vwap
                if cfg['stop'] == 'pct':
                    s = ent * (1 - cfg['stop_pct']/100) if alta else \
                        ent * (1 + cfg['stop_pct']/100)
                elif cfg['stop'] == 'atr':
                    s = ent - a[k]*cfg['stop_atr'] if alta else \
                        ent + a[k]*cfg['stop_atr']
                else:                               # origem do choque
                    s = origem - a[k]*0.10 if alta else origem + a[k]*0.10
                risco = abs(ent - s)
                if risco <= 0:
                    return None
                alv = ent + cfg['alvo']*risco if alta else \
                      ent - cfg['alvo']*risco
                # A entrada acontece DENTRO da vela k, e a gente nao sabe
                # a ordem dos precos dentro dela. Resolver a partir de k
                # seria olhar o futuro: com alvo de 1%, quase toda vela de
                # H1 e maior que isso, e o alvo "batia" na propria vela
                # mesmo que o topo tenha vindo ANTES do toque na VWAP.
                # Entao a operacao so comeca a valer na vela seguinte.
                for m in range(k + 1, min(k + 1 + MAXBAR, len(h))):
                    vh, vl = h[m][2], h[m][3]
                    if alta:
                        if vl <= s: fimr, saida = 'stop', s; break
                        if vh >= alv: fimr, saida = 'alvo', alv; break
                    else:
                        if vh >= s: fimr, saida = 'stop', s; break
                        if vl <= alv: fimr, saida = 'alvo', alv; break
                else:
                    return None
                pos = RISCO / (risco/ent)
                mov = (saida-ent)/ent * (1 if alta else -1)
                horas = m - k
                custo = pos*TAXA*2 + pos*(horas/8)*FUND8
                q = dt.datetime.fromtimestamp(h[k][0]/1000, BRT)
                return dict(ent=ent, stop=s, alvo=alv, fim=fimr,
                            bruto=pos*mov, custo=custo, liq=pos*mov-custo,
                            risco_pct=risco/ent*100, q=q, ano=q.year,
                            espera=k-fim, k=k, alta=alta)
        tp = (hi + lo + cl) / 3
        pv += tp * h[k][5]; vv += h[k][5]
    return None


def ps(v):
    return max((len(list(g)) for k, g in
                itertools.groupby(v, key=lambda x: x <= 0) if k), default=0)


def painel(rot, sel, larg=38):
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
          f"{statistics.mean(o['bruto'] for o in sel):>+9.1f}"
          f"{-statistics.mean(o['custo'] for o in sel):>8.1f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+10.0f}{dd:>8.0f}{ps(v):>5}"
          f"{(statistics.mean(p25) if p25 else 0):>+9.1f}"
          f"{(statistics.mean(p26) if p26 else 0):>+9.1f}{z:>7}")


def cab(larg=38):
    print(f"{'':<{larg}}{'n':>6}{'acerto':>9}{'bruto':>9}{'taxa':>8}"
          f"{'líq/op':>9}{'total':>10}{'rb':>8}{'seq':>5}"
          f"{'2025':>9}{'2026':>9}{'z':>7}")


BASE = dict(sigma=2.5, vol=1.5, janela=20, ancora='inicio', validade=24,
            stop='pct', stop_pct=1.0, stop_atr=0.5, alvo=1.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--tf', default='1')
    ap.add_argument('--corte', type=float, default=0.32)
    a = ap.parse_args()
    cru = []
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400 and \
                statistics.median(v[4]*v[5] for v in h) >= a.corte*1e6:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h))
    print(f"{len(cru)} moedas com volume mediano ≥ {a.corte:.2f} M USD/h")
    print(f"ponto de empate com stop de 1%: ~55% de acerto no alvo 1:1\n")

    variantes = [
        ('vela única · 1:1 · stop 1% · 24h', dict(BASE)),
        ('vela única · 1:1 · stop 1% · 12h', dict(BASE, validade=12)),
        ('vela única · 1:1 · stop 1% · 48h', dict(BASE, validade=48)),
        ('vela única · 1:1 · stop 0,5 vol', dict(BASE, stop='atr')),
        ('vela única · 1:1 · stop na origem', dict(BASE, stop='origem')),
        ('vela única · 1:1,5 · stop 1%', dict(BASE, alvo=1.5)),
        ('vela única · 1:2 · stop 1%', dict(BASE, alvo=2.0)),
        ('vela única · âncora no extremo', dict(BASE, ancora='extremo')),
        ('vela única · stop 2%', dict(BASE, stop_pct=2.0)),
    ]
    for tf in [int(x) for x in a.tf.split(',')]:
        for nome, ger in (('CHOQUE DE VELA ÚNICA', choques_vela),
                          ('CHOQUE DE PERNADA (3 a 8 velas)', choques_perna)):
            print(f"\n{'='*130}\n  H{tf} — {nome}\n{'='*130}")
            cab()
            for rot, cfg in variantes:
                ops = []
                for sim, h1 in cru:
                    hg = juntar(h1, tf)
                    if len(hg) < 120:
                        continue
                    ag, mvg = atr(hg, 14), medvol(hg, 20)
                    for ini, f, alta in ger(hg, ag, mvg, cfg):
                        g = seguir(hg, ag, ini, f, alta, cfg)
                        if g:
                            ops.append(dict(g, sim=sim))
                ops.sort(key=lambda o: o['q'])
                painel(rot.replace('vela única · ', ''), ops)


if __name__ == '__main__':
    main()
