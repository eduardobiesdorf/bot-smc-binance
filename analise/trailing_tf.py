# -*- coding: utf-8 -*-
"""Compara o trailing da estrutura A-B-C-D-E-F em varios tempos graficos.

Roda DENTRO do Actions, onde o dado de 3m existe sem precisar ir para o
repositorio. Reusa a logica do proprio bot (bot_varredura) para achar as
operacoes, e so troca a serie onde a estrutura e procurada.

    python analise/trailing_tf.py dados_amp dados_15m dados_3m
"""
import bisect
import csv
import datetime as dt
import math
import os
import statistics
import sys

import bot_varredura as B

BRT = dt.timezone(dt.timedelta(hours=-3))
CUSTO = 0.0010        # taker ida e volta
FUND8 = 0.0001


def ler(p):
    out = []
    with open(p) as f:
        for r in csv.DictReader(f):
            out.append([int(r['abertura_ms']), float(r['abertura']),
                        float(r['maxima']), float(r['minima']),
                        float(r['fechamento']), float(r['volume'])])
    return out


def detector(h, k=3, esp_varr=20, esp_rompe=12):
    """A-B-C-D-E-F. Devolve {indice_de_F: evento}, sem olhar o futuro."""
    piv, pend, out = [], [], {}
    for i in range(k, len(h)):
        c = i - k
        if c >= k:
            eT = (all(h[c][2] > h[c-j][2] for j in range(1, k+1)) and
                  all(h[c][2] >= h[c+j][2] for j in range(1, k+1)))
            eF = (all(h[c][3] < h[c-j][3] for j in range(1, k+1)) and
                  all(h[c][3] <= h[c+j][3] for j in range(1, k+1)))
            for t, ok in (('T', eT), ('F', eF)):
                if not ok:
                    continue
                if piv and piv[-1][1] == t:
                    j, _ = piv[-1]
                    if (t == 'T' and h[c][2] > h[j][2]) or \
                       (t == 'F' and h[c][3] < h[j][3]):
                        piv[-1] = (c, t)
                else:
                    piv.append((c, t))
                if len(piv) >= 4:
                    (a, ta), (b, tb), (cc, tc), (d, td) = piv[-4:]
                    tip = ta + tb + tc + td
                    if tip == 'FTFT' and h[cc][3] > h[a][3] and h[d][2] > h[b][2]:
                        pend.append(dict(alta=True, C=cc, D=d, nasceu=i,
                                         E=None, ext=None))
                    elif tip == 'TFTF' and h[cc][2] < h[a][2] and h[d][3] < h[b][3]:
                        pend.append(dict(alta=False, C=cc, D=d, nasceu=i,
                                         E=None, ext=None))
        vivos = []
        for p in pend:
            if p['E'] is None:
                if i - p['nasceu'] > esp_varr:
                    continue
                if (h[i][3] < h[p['C']][3]) if p['alta'] else (h[i][2] > h[p['C']][2]):
                    p['E'] = i
                    p['ext'] = h[i][3] if p['alta'] else h[i][2]
                vivos.append(p)
                continue
            p['ext'] = min(p['ext'], h[i][3]) if p['alta'] else max(p['ext'], h[i][2])
            if i - p['E'] > esp_rompe:
                continue
            rompeu = (h[i][4] > h[p['D']][2]) if p['alta'] else (h[i][4] < h[p['D']][3])
            if rompeu and i > p['E']:
                out[i] = dict(alta=p['alta'], extremo=p['ext'])
                continue
            vivos.append(p)
        pend = vivos
    return out


def operacoes(h, cfg):
    """As operacoes do bot, do jeito que ele acha hoje."""
    a = B.atr(h, cfg['atr_periodo'])
    mv = B.media_volume(h, cfg['vol_periodo'])
    out = []
    for imp in B.achar_impulsos(h, a, mv, cfg):
        g = B.seguir(h, a, imp, cfg, mv)
        if not g or g.get('fase') != 'gatilho':
            continue
        if g['rr'] < cfg['rr_min'] or g.get('vol_varr', 0) < cfg['vol_varr_min']:
            continue
        out.append(g)
    return out


def simular(ops, h, serie, ev, a_serie, trail, folga):
    """serie = onde o preco e acompanhado; ev = eventos nessa serie."""
    t = [c[0] for c in serie]
    res = []
    for g in ops:
        compra = g['lado'] == 'compra'
        ent, stop, alvo = g['entrada'], g['stop'], g['alvo']
        risco0 = abs(ent - stop)
        m0 = bisect.bisect_right(t, h[g['idx']][0])
        lim = int(120 * 60 / ((serie[1][0] - serie[0][0]) / 60000))
        saiu = None
        movs = 0
        for m in range(m0, min(m0 + lim, len(serie))):
            hi, lo = serie[m][2], serie[m][3]
            if compra:
                if lo <= stop:
                    saiu = (stop - ent) / risco0; break
                if hi >= alvo:
                    saiu = (alvo - ent) / risco0; break
            else:
                if hi >= stop:
                    saiu = (ent - stop) / risco0; break
                if lo <= alvo:
                    saiu = (ent - alvo) / risco0; break
            if trail and m in ev:
                e = ev[m]
                if e['alta'] != compra:
                    continue
                novo = (e['extremo'] - a_serie[m] * folga if compra
                        else e['extremo'] + a_serie[m] * folga)
                if (novo > stop) if compra else (novo < stop):
                    stop = novo; movs += 1
        if saiu is None:
            continue
        horas = (m - m0) * ((serie[1][0] - serie[0][0]) / 3600000)
        res.append(dict(r=saiu - (CUSTO + (horas / 8) * FUND8) * ent / risco0,
                        movs=movs, horas=horas,
                        q=dt.datetime.fromtimestamp(g['vela_ms'] / 1000, BRT)))
    return res


def linha(rot, sel):
    if not sel:
        print(f"  {rot:<28} nada"); return
    rs = [o['r'] for o in sel]
    g = [x for x in rs if x > 0]
    p = [x for x in rs if x <= 0]
    sd = statistics.stdev(rs) if len(rs) > 1 else 0
    tt = statistics.mean(rs) / (sd / math.sqrt(len(rs))) if sd else 0
    acc = pico = dd = 0.0
    for v in rs:
        acc += v; pico = max(pico, acc); dd = min(dd, acc - pico)
    a5 = [o['r'] for o in sel if o['q'].year == 2025]
    a6 = [o['r'] for o in sel if o['q'].year == 2026]
    mex = sum(1 for o in sel if o['movs'] > 0)
    tot_mov = sum(o['movs'] for o in sel)
    print(f"  {rot:<28} n={len(rs):<4} acerto={len(g)/len(rs)*100:4.1f}%  "
          f"ganho {statistics.mean(g) if g else 0:+.2f}R  "
          f"perda {statistics.mean(p) if p else 0:+.2f}R  "
          f"R/op={statistics.mean(rs):+.3f}  tot={sum(rs):+6.1f}R  "
          f"reb={abs(dd):4.1f}R  t={tt:+5.2f}  "
          f"mexeu em {mex:>2} ({tot_mov} movs)  "
          f"| 25 {statistics.mean(a5) if a5 else 0:+.3f} "
          f"26 {statistics.mean(a6) if a6 else 0:+.3f}")


def main():
    d1h, pastas = sys.argv[1], sys.argv[2:]
    cfg = dict(B.CFG)
    nucleo = list(B.UNIVERSO[:20])
    acum = {}
    for sim in nucleo:
        p1 = f'{d1h}/{sim}_1h.csv'
        if not os.path.exists(p1):
            continue
        h = ler(p1)
        if len(h) < 400:
            continue
        ops = operacoes(h, cfg)
        if not ops:
            continue
        for pasta in pastas:
            iv = pasta.split('_')[-1]
            p = f'{pasta}/{sim}_{iv}.csv'
            if not os.path.exists(p):
                continue
            s = ler(p)
            if len(s) < 500:
                continue
            a_s = B.atr(s, 14)
            ev = detector(s)
            acum.setdefault((iv, 'fixo'), []).extend(
                simular(ops, h, s, ev, a_s, False, 0))
            for folga in (0.10, 0.25, 0.50):
                acum.setdefault((iv, folga), []).extend(
                    simular(ops, h, s, ev, a_s, True, folga))
    print(f"\n=== TRAILING DA ESTRUTURA POR TEMPO GRÁFICO — núcleo 20, 22 meses ===")
    for iv in [p.split('_')[-1] for p in pastas]:
        print(f"\n  -- estrutura procurada no {iv} --")
        linha('stop fixo (como é hoje)', acum.get((iv, 'fixo'), []))
        for folga in (0.10, 0.25, 0.50):
            linha(f'trailing, folga {folga:.2f} ATR', acum.get((iv, folga), []))


if __name__ == '__main__':
    main()
