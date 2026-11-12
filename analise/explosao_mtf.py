"""Padrao no H8 (ou H12), entrada no H1.

A explosao, o order block e o alvo sao lidos no tempo grafico grande.
Mas em vez de esperar a vela GRANDE de gatilho fechar (8 ou 12 horas de
atraso), a gente desce pro H1: assim que o preco encosta no order block,
procura ali a vela de gatilho de uma hora e entra no fechamento dela.

Compara sempre os MESMOS setups nas duas entradas, senao a comparacao
mistura "entrada melhor" com "operacoes diferentes".

Uso:  python3 explosao_mtf.py <pasta> [--tf 8,12]
"""
import sys, os, glob, statistics, random, argparse
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from explosao import (ler, juntar, atr, medvol, RISCO, TAXA, FUND8, curva)

BRT = dt.timezone(dt.timedelta(hours=-3))
MAXH = 960          # ate 960 horas (40 dias) segurando a operacao


def rsi(h, p=14):
    """RSI de Wilder, fechado em cada vela."""
    r = [50.0] * len(h)
    if len(h) <= p:
        return r
    gan = per = 0.0
    for i in range(1, p + 1):
        d = h[i][4] - h[i-1][4]
        gan += max(d, 0.0); per += max(-d, 0.0)
    gan /= p; per /= p
    r[p] = 100 - 100/(1 + gan/per) if per else 100.0
    for i in range(p + 1, len(h)):
        d = h[i][4] - h[i-1][4]
        gan = (gan*(p-1) + max(d, 0.0)) / p
        per = (per*(p-1) + max(-d, 0.0)) / p
        r[i] = 100 - 100/(1 + gan/per) if per else 100.0
    return r


def media(h, n=50):
    m = [None] * len(h)
    s = 0.0
    for i, v in enumerate(h):
        s += v[4]
        if i >= n:
            s -= h[i-n][4]
        if i >= n - 1:
            m[i] = s / n
    return m


def gatilho(v, borda, alta):
    """A vela serve de gatilho? Fecha de volta pra fora do OB, a favor."""
    o, hi, lo, cl = v[1], v[2], v[3], v[4]
    rng = hi - lo
    if rng <= 0:
        return False
    if not ((cl > borda) if alta else (cl < borda)):
        return False
    if not ((cl > o) if alta else (cl < o)):
        return False
    corpo = abs(cl - o) / rng
    pavio = ((min(o, cl) - lo) if alta else (hi - max(o, cl))) / rng
    return corpo >= 0.5 or pavio >= 0.5


def resolver1h(h1, k0, ent, stop, alvo, alta):
    for k in range(k0 + 1, min(k0 + 1 + MAXH, len(h1))):
        hi, lo = h1[k][2], h1[k][3]
        if alta:
            if lo <= stop: return 'stop', stop, k - k0
            if hi >= alvo: return 'alvo', alvo, k - k0
        else:
            if hi >= stop: return 'stop', stop, k - k0
            if lo <= alvo: return 'alvo', alvo, k - k0
    return None, None, None


def dinheiro(ent, saida, stop, alta, horas):
    risco_pct = abs(ent - stop) / ent
    pos = RISCO / risco_pct
    mov = (saida - ent) / ent * (1 if alta else -1)
    return pos * mov - pos * TAXA * 2 - pos * (horas / 8) * FUND8, risco_pct


def varrer(sim, h1, tf, cfg):
    """Devolve os setups do tempo grande, cada um com os dois resultados."""
    hg = juntar(h1, tf)
    if len(hg) < 120:
        return []
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    ag, mvg = atr(hg, 14), medvol(hg, 20)
    mv1 = medvol(h1, 20) if cfg.get('vol_h1') else None
    a1 = atr(h1, 14) if cfg.get('forca_h1') else None
    rs, ma = rsi(hg, 14), media(hg, 50)
    jan, passo = cfg['janela'], tf * 3600_000
    out, i = [], max(jan, 21) + 1
    while i < len(hg) - 2:
        o, hi, lo, cl, vol = hg[i][1], hg[i][2], hg[i][3], hg[i][4], hg[i][5]
        rng, av, mvv = hi - lo, ag[i-1], mvg[i-1]
        if rng <= 0 or av <= 0 or mvv <= 0:
            i += 1; continue
        if rng < cfg['sigma'] * av or abs(cl - o) / rng < 0.5 \
                or vol < cfg['vol'] * mvv:
            i += 1; continue
        alta = cl > o
        if alta:
            if cl <= max(x[2] for x in hg[i-jan:i]): i += 1; continue
        else:
            if cl >= min(x[3] for x in hg[i-jan:i]): i += 1; continue
        j, ob = i - 1, None
        while j >= max(0, i - cfg['ob_busca']):
            if (hg[j][4] > hg[j][1]) != alta:
                ob = j; break
            j -= 1
        if ob is None:
            i += 1; continue
        ob_base, ob_topo = hg[ob][3], hg[ob][2]
        borda = ob_topo if alta else ob_base
        morte = ob_base - ag[i]*cfg['furo_max'] if alta else \
                ob_topo + ag[i]*cfg['furo_max']

        # --- caminha no H1 a partir do fim da vela explosiva
        k1 = pos1.get(hg[i][0] + passo)
        if k1 is None:
            i += 1; continue
        pico = hi if alta else lo
        tocou = kg = None
        ent_g = ent_1 = None
        fim_h = min(k1 + cfg['espera'] * tf, len(h1))
        extremo = None
        for k in range(k1, fim_h):
            vh, vl = h1[k][2], h1[k][3]
            if tocou is None:
                pico = max(pico, vh) if alta else min(pico, vl)
                if (vl <= borda) if alta else (vh >= borda):
                    tocou, extremo = k, (vl if alta else vh)
                else:
                    continue
            else:
                extremo = min(extremo, vl) if alta else max(extremo, vh)
            if (extremo < morte) if alta else (extremo > morte):
                break
            if (vh >= pico) if alta else (vl <= pico):
                break              # foi pro alvo sem nos
            if k - tocou > cfg['gat_h1']:
                break
            if ent_1 is None and gatilho(h1[k], borda, alta):
                ok = True
                if mv1 and mv1[k] > 0 and h1[k][5] < cfg['vol_h1'] * mv1[k]:
                    ok = False          # gatilho sem volume não convence
                if ok and a1 is not None:
                    marg = abs(h1[k][4] - borda)
                    if marg < cfg['forca_h1'] * a1[k]:
                        ok = False      # fechou em cima da borda, não além
                if ok:
                    ent_1 = (k, h1[k][4], extremo)
                    break
        # --- e o gatilho no proprio tempo grande, pros mesmos setups
        if tocou is not None:
            kg0 = (h1[tocou][0] - hg[0][0]) // passo
            ex_g = None
            for kg_ in range(int(kg0), min(int(kg0) + cfg['gat_g'] + 1, len(hg))):
                vh, vl = hg[kg_][2], hg[kg_][3]
                ex_g = (min(ex_g, vl) if alta else max(ex_g, vh)) \
                    if ex_g is not None else (vl if alta else vh)
                if (ex_g < morte) if alta else (ex_g > morte):
                    break
                if gatilho(hg[kg_], borda, alta):
                    kk = pos1.get(hg[kg_][0] + passo - 3600_000)
                    if kk is not None:
                        ent_g = (kk, hg[kg_][4], ex_g)
                    break
        if ent_1 is None and ent_g is None:
            i += 1; continue

        # medidas conhecidas NA HORA da explosao, pra filtrar depois
        rp, rq = rs[i-1], rs[i]
        if not alta:                       # "exausto do lado contrario"
            rp, rq = 100 - rp, 100 - rq
        reg = dict(sim=sim, alta=alta, pico=pico, ob_base=ob_base,
                   ob_topo=ob_topo, atr=ag[i], i=i,
                   rsi_antes=rp, rsi_depois=rq,
                   estende=abs(pico - hg[i][4]) / ag[i] if ag[i] else 0.0,
                   dist_ma=((hg[i][4] - ma[i]) / ag[i] * (1 if alta else -1))
                   if ma[i] and ag[i] else None,
                   espera_h=(h1[tocou][0] - hg[i][0] - passo) / 3600_000
                   if tocou is not None else None,
                   ms_exp=hg[i][0])
        for rot, e in (('grande', ent_g), ('h1', ent_1)):
            if e is None:
                reg[rot] = None; continue
            k, p, ex = e
            s = (ob_base - ag[i]*0.10) if alta else (ob_topo + ag[i]*0.10)
            if cfg['stop'] == 'volta':
                s = (min(s, ex - ag[i]*0.10) if alta
                     else max(s, ex + ag[i]*0.10))
            risco = abs(p - s)
            # alvo: por padrao o topo que a explosao deixou. Com 'proj',
            # projeta o tamanho da explosao a partir do fundo do recuo --
            # a medida classica, que fica ALEM daquele topo.
            alvo_r = pico
            if cfg.get('proj'):
                tam = hg[i][2] - hg[i][3]
                if cfg.get('proj_de') == 'topo':
                    # segurar ALEM do topo: o topo mais um tanto do
                    # tamanho da explosao
                    alvo_r = pico + cfg['proj']*tam if alta else \
                             pico - cfg['proj']*tam
                else:
                    fundo = min(h1[x][3] for x in range(k1, k+1)) if alta \
                            else max(h1[x][2] for x in range(k1, k+1))
                    alvo_r = fundo + cfg['proj']*tam if alta else \
                             fundo - cfg['proj']*tam
            dist = (alvo_r - p) if alta else (p - alvo_r)
            # Com 'rr_no_topo', o filtro de risco/retorno usa o topo da
            # explosao mesmo quando o alvo e projetado. Assim as variantes
            # de alvo pegam EXATAMENTE as mesmas operacoes, e a comparacao
            # mede so a saida, nao um conjunto diferente de trades.
            dist_f = ((pico - p) if alta else (p - pico)) \
                if cfg.get('rr_no_topo') else dist
            if risco <= 0 or dist <= 0 or dist_f <= 0 \
                    or dist_f/risco < cfg['rr_min']:
                reg[rot] = None; continue
            f, saida, horas = resolver1h(h1, k, p, s, alvo_r, alta)
            if f is None:
                reg[rot] = None; continue
            liq, rp = dinheiro(p, saida, s, alta, horas)
            q = dt.datetime.fromtimestamp(h1[k][0]/1000, BRT)
            reg[rot] = dict(ent=p, stop=s, rr=dist/risco, fim=f, liq=liq,
                            risco_pct=rp*100, q=q, ano=q.year, horas=horas,
                            alvo=alvo_r, topo=pico)
        out.append(reg)
        i = max(i + 1, int((h1[tocou][0] - hg[0][0]) // passo) + 1) \
            if tocou else i + 1
    return out


def painel(rot, ops):
    v = [o['liq'] for o in ops]
    if not v:
        print(f"{rot:<30}{'—':>6}"); return
    g = [x for x in v if x > 0]; p = [x for x in v if x <= 0]
    tot, dd = curva(v)
    print(f"{rot:<30}{len(v):>6}{len(g)/len(v)*100:>8.1f}%"
          f"{(statistics.mean(g) if g else 0):>+10.0f}"
          f"{(statistics.mean(p) if p else 0):>+10.0f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+10.0f}{dd:>9.0f}"
          f"{statistics.mean(o['risco_pct'] for o in ops):>8.1f}%"
          f"{statistics.mean(o['rr'] for o in ops):>7.2f}")


def cab():
    print(f"{'':<30}{'n':>6}{'acerto':>9}{'gain méd':>10}{'loss méd':>10}"
          f"{'méd/op':>9}{'total':>10}{'pior rb':>9}{'stop méd':>9}{'R:R':>7}")


BASE = dict(sigma=2.5, vol=1.5, janela=20, ob_busca=6, espera=30,
            gat_g=4, gat_h1=24, furo_max=1.0, rr_min=1.2, stop='ob')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--tf', default='8,12')
    a = ap.parse_args()
    arqs = sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv')))
    cru = []
    for p in arqs:
        h = ler(p)
        if len(h) >= 400:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h))
    print(f"{len(cru)} pares em {a.pasta}")

    variantes = [('', BASE)]
    for v in (1.2, 1.5, 2.0):
        variantes.append((f' · gatilho H1 com volume ≥ {v:.1f}x',
                          dict(BASE, vol_h1=v)))
    for f in (0.25, 0.5):
        variantes.append((f' · gatilho H1 fecha {f:.2f} ATR além da borda',
                          dict(BASE, forca_h1=f)))
    for j in (6, 12):
        variantes.append((f' · só até {j}h depois de encostar',
                          dict(BASE, gat_h1=j)))
    variantes.append((' · volume ≥ 1.5x E 12h', dict(BASE, vol_h1=1.5,
                                                     gat_h1=12)))

    for tf in [int(x) for x in a.tf.split(',')]:
        for rotc, cfg in variantes:
            todos = []
            for sim, h1 in cru:
                todos += varrer(sim, h1, tf, cfg)
            amb = [r for r in todos if r['grande'] and r['h1']]
            print(f"\n{'='*116}")
            print(f"  padrão em H{tf}, entrada no H1 — {len(todos)} setups, "
                  f"{len(amb)} com entrada nos dois{rotc}")
            print('='*116)
            cab()
            painel('entrada na vela grande',
                   [r['grande'] for r in todos if r['grande']])
            painel('entrada no H1',
                   [r['h1'] for r in todos if r['h1']])
            if len(amb) < 20:
                print("   poucos setups em comum para comparar")
                continue
            print("  — só os setups que deram entrada nas duas formas —")
            painel('  vela grande', [r['grande'] for r in amb])
            painel('  H1', [r['h1'] for r in amb])
            for ano in sorted({r['h1']['ano'] for r in amb}):
                painel(f'    {ano} vela grande',
                       [r['grande'] for r in amb if r['h1']['ano'] == ano])
                painel(f'    {ano} H1',
                       [r['h1'] for r in amb if r['h1']['ano'] == ano])
            vv = [r['h1']['liq'] for r in amb]
            random.seed(11)
            nul = [statistics.mean([x if random.random() < .5 else -x
                                    for x in vv]) for _ in range(200)]
            dp = statistics.pstdev(nul) or 1e-9
            print(f"  teste nulo (H1): real {statistics.mean(vv):+.1f} vs "
                  f"acaso {statistics.mean(nul):+.1f} ± {dp:.1f}  →  "
                  f"z = {(statistics.mean(vv)-statistics.mean(nul))/dp:+.2f}")


if __name__ == '__main__':
    main()
