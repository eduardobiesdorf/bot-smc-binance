"""Explosao de vela unica: uma vela so rompe o topo, o preco volta ao
order block, encosta, da o gatilho e sai de novo.

Diferente do setup que esta no bot: la a pernada tem 3 a 8 velas e o
preco FURA o order block. Aqui e uma vela so, e basta ENCOSTAR.

  explosao   = 1 vela, tamanho >= sigma x volatilidade media (medida ANTES
               dela), corpo >= 50% da vela, volume >= mult x a media de 20,
               e fecha alem da maxima (ou minima) das ultimas 20 velas
  order block= a ultima vela de cor contraria antes da explosao
  alvo       = o topo que ela deixou (maior maxima da explosao ate encostar)
  stop       = abaixo do order block
  entrada    = fechamento da vela de gatilho, depois de encostar no OB

Uso:  python3 explosao.py <pasta> [--tf 1,4,8,12,24] [--rot nome]
"""
import sys, os, glob, csv, math, random, statistics, argparse
import datetime as dt

BRT = dt.timezone(dt.timedelta(hours=-3))
RISCO = 100.0            # dolar que morre em cada stop
TAXA = 0.0005            # taker por lado
FUND8 = 0.0001           # funding por 8h
MAXBAR = 120             # ate quantas velas segurar a operacao


# ----------------------------------------------------------------- dados
def ler(p):
    h = []
    with open(p, newline='', encoding='utf-8') as f:
        r = csv.reader(f)
        next(r, None)
        for L in r:
            if len(L) < 7:
                continue
            try:
                h.append((int(L[0]), float(L[2]), float(L[3]),
                          float(L[4]), float(L[5]), float(L[6])))
            except ValueError:
                continue
    return h                      # (ms, abertura, maxima, minima, fecha, vol)


def juntar(h, n):
    """1h -> velas de n horas, alinhadas ao UTC como na Binance."""
    if n == 1:
        return h
    passo = n * 3600_000
    out, bloco, chave = [], None, None
    for v in h:
        c = v[0] // passo
        if c != chave:
            if bloco:
                out.append(bloco)
            bloco = [c * passo, v[1], v[2], v[3], v[4], v[5]]
            chave = c
        else:
            bloco[2] = max(bloco[2], v[2])
            bloco[3] = min(bloco[3], v[3])
            bloco[4] = v[4]
            bloco[5] += v[5]
    if bloco:
        out.append(bloco)
    return [tuple(x) for x in out]


def atr(h, n=14):
    tr, a = [], [0.0] * len(h)
    for i, v in enumerate(h):
        if i == 0:
            tr.append(v[2] - v[3])
        else:
            pc = h[i-1][4]
            tr.append(max(v[2]-v[3], abs(v[2]-pc), abs(v[3]-pc)))
        if i >= n:
            a[i] = a[i-1] + (tr[i] - a[i-1]) / n
        elif i == n - 1:
            a[i] = sum(tr[:n]) / n
    return a


def medvol(h, n=20):
    m = [0.0] * len(h)
    s = 0.0
    for i, v in enumerate(h):
        s += v[5]
        if i >= n:
            s -= h[i-n][5]
        if i >= n - 1:
            m[i] = s / n
    return m


# ------------------------------------------------------------- o gatilho
def achar(h, cfg):
    """Devolve a lista de operacoes encontradas nessa serie."""
    a, mv = atr(h, 14), medvol(h, 20)
    jan, ops = cfg['janela'], []
    i = max(jan, 21) + 1
    while i < len(h) - 2:
        o, hi, lo, cl, vol = h[i][1], h[i][2], h[i][3], h[i][4], h[i][5]
        rng = hi - lo
        av, mvv = a[i-1], mv[i-1]          # medidos ANTES da vela
        if rng <= 0 or av <= 0 or mvv <= 0:
            i += 1; continue
        if rng < cfg['sigma'] * av or abs(cl - o) / rng < cfg['corpo']:
            i += 1; continue
        if vol < cfg['vol'] * mvv:
            i += 1; continue
        alta = cl > o
        # "rompeu o topo": fecha alem do extremo das ultimas <janela> velas
        if jan > 0:
            if alta:
                if cl <= max(x[2] for x in h[i-jan:i]):
                    i += 1; continue
            else:
                if cl >= min(x[3] for x in h[i-jan:i]):
                    i += 1; continue
        # order block: ultima vela de cor contraria antes da explosao
        j, ob = i - 1, None
        while j >= max(0, i - cfg['ob_busca']):
            sobe = h[j][4] > h[j][1]
            if sobe != alta:
                ob = j; break
            j -= 1
        if ob is None:
            i += 1; continue
        ob_base, ob_topo = h[ob][3], h[ob][2]
        borda = ob_topo if alta else ob_base      # onde o preco encosta

        g = seguir(h, a, i, alta, ob_base, ob_topo, borda, cfg)
        if g:
            ops.append(g)
            i = g['k'] + 1
        else:
            i += 1
    return ops


def seguir(h, a, i, alta, ob_base, ob_topo, borda, cfg):
    pico = h[i][2] if alta else h[i][3]
    tocou = None
    for k in range(i + 1, min(i + cfg['espera'] + 1, len(h))):
        hi, lo, o, cl = h[k][2], h[k][3], h[k][1], h[k][4]
        if tocou is None:
            pico = max(pico, hi) if alta else min(pico, lo)
            # encostou no order block?
            if (lo <= borda) if alta else (hi >= borda):
                tocou = k
                extremo = lo if alta else hi
            else:
                continue
        else:
            extremo = min(extremo, lo) if alta else max(extremo, hi)
            if k - tocou > cfg['gatilho_max']:
                return None

        # morreu: atravessou o order block inteiro
        morte = ob_base - a[i] * cfg['furo_max'] if alta else \
                ob_topo + a[i] * cfg['furo_max']
        if (extremo < morte) if alta else (extremo > morte):
            return None
        # ja foi pro alvo sem nos
        if (hi >= pico) if alta else (lo <= pico):
            return None

        rng = hi - lo
        dentro = (cl > borda) if alta else (cl < borda)
        if rng <= 0 or not dentro:
            continue
        favor = (cl > o) if alta else (cl < o)
        corpo = abs(cl - o) / rng
        pavio = ((min(o, cl) - lo) if alta else (hi - max(o, cl))) / rng
        if not (favor and (corpo >= 0.5 or pavio >= 0.5)):
            continue

        ent = cl
        if cfg['stop'] == 'ob':
            s = ob_base - a[k] * 0.10 if alta else ob_topo + a[k] * 0.10
        else:                                   # minima da volta
            s = min(ob_base, extremo) - a[k] * 0.10 if alta else \
                max(ob_topo, extremo) + a[k] * 0.10
        risco = abs(ent - s)
        dist = (pico - ent) if alta else (ent - pico)
        if risco <= 0 or dist <= 0:
            return None
        rr = dist / risco
        if rr < cfg['rr_min']:
            return None
        return dict(alta=alta, ent=ent, stop=s, alvo=pico, rr=rr, k=k,
                    ms=h[k][0], risco_pct=risco / ent * 100,
                    espera=k - i, i=i)
    return None


def resolver(h, g):
    alta, ent, s, alv = g['alta'], g['ent'], g['stop'], g['alvo']
    for k in range(g['k'] + 1, min(g['k'] + 1 + MAXBAR, len(h))):
        hi, lo = h[k][2], h[k][3]
        if alta:
            if lo <= s: return 'stop', s, k - g['k']
            if hi >= alv: return 'alvo', alv, k - g['k']
        else:
            if hi >= s: return 'stop', s, k - g['k']
            if lo <= alv: return 'alvo', alv, k - g['k']
    return None, None, None


def dinheiro(g, saida, velas, horas_vela):
    pos = RISCO / (g['risco_pct'] / 100)
    mov = (saida - g['ent']) / g['ent'] * (1 if g['alta'] else -1)
    horas = velas * horas_vela
    return pos * mov - pos * TAXA * 2 - pos * (horas / 8) * FUND8, pos


# ------------------------------------------------------------- relatorio
def curva(v):
    acc = pico = dd = 0.0
    for x in v:
        acc += x; pico = max(pico, acc); dd = min(dd, acc - pico)
    return acc, abs(dd)


def linha(rot, ops, larg=34):
    if not ops:
        print(f"{rot:<{larg}}{'—':>6}"); return
    v = [o['liq'] for o in ops]
    g = [x for x in v if x > 0]; p = [x for x in v if x <= 0]
    tot, dd = curva(v)
    print(f"{rot:<{larg}}{len(v):>6}{len(g)/len(v)*100:>8.1f}%"
          f"{(statistics.mean(g) if g else 0):>+10.0f}"
          f"{(statistics.mean(p) if p else 0):>+10.0f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+10.0f}{dd:>9.0f}"
          f"{statistics.mean(o['risco_pct'] for o in ops):>8.1f}%")


def cab(larg=34):
    print(f"{'':<{larg}}{'n':>6}{'acerto':>9}{'gain méd':>10}{'loss méd':>10}"
          f"{'méd/op':>9}{'total':>10}{'pior rb':>9}{'stop méd':>9}")


BASE = dict(sigma=2.5, corpo=0.5, vol=1.5, janela=20, ob_busca=6,
            espera=30, gatilho_max=4, furo_max=1.0, rr_min=1.2, stop='ob')
FAIXA = {}
TFS = {1: 'H1', 4: 'H4', 8: 'H8', 12: 'H12', 24: 'Diário'}


def rodar(series, cfg, tf):
    todas = []
    for sim, h in series:
        for g in achar(h, cfg):
            fim, saida, velas = resolver(h, g)
            if fim is None:
                continue
            liq, pos = dinheiro(g, saida, velas, tf)
            q = dt.datetime.fromtimestamp(g['ms']/1000, BRT)
            todas.append(dict(g, sim=sim, fim=fim, liq=liq, pos=pos,
                              q=q, ano=q.year, faixa=FAIXA.get(sim, '?')))
    todas.sort(key=lambda o: o['q'])
    return todas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--tf', default='1,4,8,12,24')
    ap.add_argument('--rot', default='')
    a = ap.parse_args()

    arqs = sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv')))
    print(f"{len(arqs)} pares em {a.pasta} {a.rot}\n")
    cru = []
    for p in arqs:
        h = ler(p)
        if len(h) >= 400:
            cru.append((os.path.basename(p).replace('_1h.csv', ''), h))

    # separa as moedas por tamanho (volume mediano em dolar por hora),
    # que e exatamente a duvida: a explosao so "segue" nas pequenas?
    vols = sorted(((statistics.median(v[4] * v[5] for v in h), s)
                   for s, h in cru), reverse=True)
    n4 = max(1, len(vols) // 4)
    for pos_, (_, s) in enumerate(vols):
        FAIXA[s] = ('1 maiores' if pos_ < n4 else
                    '2 médias' if pos_ < 2*n4 else
                    '3 pequenas' if pos_ < 3*n4 else '4 minúsculas')
    print("faixas por volume mediano (USD/h):")
    for rot in ('1 maiores', '2 médias', '3 pequenas', '4 minúsculas'):
        vv = [v for v, s in vols if FAIXA[s] == rot]
        if vv:
            print(f"  {rot:<14}{len(vv):>4} pares   "
                  f"{min(vv)/1e6:>9,.2f} M a {max(vv)/1e6:>9,.2f} M")

    for tf in [int(x) for x in a.tf.split(',')]:
        series = [(s, juntar(h, tf)) for s, h in cru]
        series = [(s, h) for s, h in series if len(h) >= 120]
        print(f"\n{'='*108}")
        print(f"  {TFS.get(tf, str(tf)+'h')}  —  {len(series)} pares, "
              f"risco fixo de ${RISCO:.0f} por operação")
        print('='*108)
        cab()
        base = rodar(series, BASE, tf)
        linha(f'padrão (2,5x · vol 1,5x · R:R 1,2)', base)
        if len(base) < 15:
            print("   amostra pequena demais para concluir")
            continue

        for s in (2.0, 3.0, 4.0):
            linha(f'tamanho {s:.1f}x', rodar(series, dict(BASE, sigma=s), tf))
        for v in (2.0, 3.0):
            linha(f'volume {v:.1f}x', rodar(series, dict(BASE, vol=v), tf))
        for r in (1.5, 2.0, 3.0):
            linha(f'R:R mínimo 1:{r:.1f}',
                  [o for o in base if o['rr'] >= r])
        linha('stop na mínima da volta',
              rodar(series, dict(BASE, stop='volta'), tf))
        linha('sem exigir romper o topo',
              rodar(series, dict(BASE, janela=0), tf))

        print(f"\n  {'por ano':<32}")
        for ano in sorted({o['ano'] for o in base}):
            linha(f'  {ano}', [o for o in base if o['ano'] == ano])
        for lado, nome in ((True, 'compras'), (False, 'vendas')):
            linha(f'  {nome}', [o for o in base if o['alta'] == lado])
        print(f"\n  {'por tamanho da moeda':<32}")
        for rot in ('1 maiores', '2 médias', '3 pequenas', '4 minúsculas'):
            sel = [o for o in base if o['faixa'] == rot]
            linha(f'  {rot}', sel)
            if len(sel) >= 30:
                for ano in sorted({o['ano'] for o in sel}):
                    linha(f'      {ano}', [o for o in sel if o['ano'] == ano])

        # teste nulo: mesma estrutura, lado sorteado
        random.seed(7)
        nulos = []
        for _ in range(200):
            v = [o['liq'] if random.random() < 0.5 else -o['liq']
                 for o in base]
            nulos.append(statistics.mean(v))
        m = statistics.mean(o['liq'] for o in base)
        dp = statistics.pstdev(nulos) or 1e-9
        print(f"\n  teste nulo (lado sorteado, 200 sorteios): "
              f"real {m:+.1f} vs acaso {statistics.mean(nulos):+.1f} "
              f"± {dp:.1f}  →  z = {(m - statistics.mean(nulos))/dp:+.2f}")


if __name__ == '__main__':
    main()
