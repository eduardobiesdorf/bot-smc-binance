"""Cada par na grade do SEU ciclo de funding, no momento de cada operacao.

A descoberta: dos 471 pares, 309 estao hoje em ciclo de 4 horas, 154 em
8, 6 em 1 e 2 em 2 -- e 177 trocaram de ciclo em algum momento. A
Binance foi migrando pares de 8h para 4h ao longo dos anos.

Isso reinterpreta o teste de manha. "A reversao em H4" deu -16,50/op,
mas misturava os pares de ciclo 8h (onde H4 e MEIO ciclo, grade errada)
com os de ciclo 4h (onde H4 e o ciclo INTEIRO, grade certa).

Ja esta estabelecido que a grade tem de TERMINAR na cobranca (deslocar
mede +3,23 desvios pior) e cobrir o ciclo INTEIRO (encurtar piora).
Entao a previsao, feita ANTES de olhar: a versao CASADA -- cada par na
grade do ciclo que estava em vigor naquele momento -- bate tanto o
sempre-H8 quanto o sempre-H4.

Uso:  python3 ciclo_casado.py <klines> <funding>
"""
import argparse, bisect, csv, glob, os, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler, RISCO, TAXA, FUND8
from lista_operacoes import vol, TRI, BRT
from alvo_lote import z_de
from venda_topo import lotes_de


def ler_funding(p):
    """[(tempo_ms, intervalo_h, taxa)] ordenado."""
    out = []
    try:
        with open(p) as f:
            for r in csv.DictReader(f):
                out.append((int(r['tempo_ms']), int(float(r['intervalo_h'])),
                            float(r['taxa'])))
    except Exception:
        return []
    out.sort()
    return out


def ciclo_em(fund, ts, tempos):
    """O intervalo de funding vigente em ts."""
    if not fund:
        return 8
    i = bisect.bisect_right(tempos, ts) - 1
    return fund[max(0, i)][1]


def ops_tf(h1, sim, tf):
    cfg = dict(rev.CFG)
    cfg['tf_h'] = tf
    cfg['alvo_proj'] = 0.0
    cfg['alvo_rr'] = None
    cfg['so_compra'] = False
    hp = rev.juntar(h1, tf) if tf > 1 else h1
    if len(hp) < 120:
        return []
    mv1 = e8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    tp = [v[0] for v in hp]
    out = []
    for e in rev.explosoes(hp, cfg):
        g = rev.entrada(h1, mv1, e, cfg, pos1)
        if not g:
            continue
        compra = g['lado'] == 'compra'
        risco = abs(g['entrada'] - g['stop'])
        i = max(k for k, t in enumerate(tp) if t <= g['vela_ms'])
        fim = saida = None
        for m in range(i+1, min(i+1+rev.MAX_BARRAS, len(hp))):
            hi, lo = hp[m][2], hp[m][3]
            if compra:
                if lo <= g['stop']: fim, saida = 'stop', g['stop']; break
                if hi >= g['alvo']: fim, saida = 'alvo', g['alvo']; break
            else:
                if hi >= g['stop']: fim, saida = 'stop', g['stop']; break
                if lo <= g['alvo']: fim, saida = 'alvo', g['alvo']; break
        if fim is None:
            continue
        horas = (m-i)*tf
        mov = (saida-g['entrada'])/g['entrada']*(1 if compra else -1)
        pos = RISCO/(risco/g['entrada'])
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        out.append(dict(sim=sim, ms=g['vela_ms'], q=q, fim=fim, rr=g['rr'],
                        tf=tf, stop_pct=g['risco_pct'], bruto=pos*mov,
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return out


def painel(rot, ops, meses, larg=34):
    if not ops:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in ops]
    g = [o for o in ops if o['fim'] == 'alvo']
    L = lotes_de(ops)
    lv = [sum(y['liq'] for y in x) for x in L]
    tot = sum(v)
    print(f"{rot:<{larg}}{len(ops):>5}{len(ops)/meses:>6.1f}"
          f"{len(g)/len(ops)*100:>7.1f}%"
          f"{statistics.mean(o['rr'] for o in ops):>6.2f}"
          f"{statistics.mean(o['bruto'] for o in ops):>+9.1f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{z_de(v):>+7.2f}"
          f"{len(L):>6}{sum(1 for x in lv if x>0):>5}{z_de(lv):>+8.2f}")


def cab(larg=34):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>8}{'R:R':>6}"
          f"{'bruto':>9}{'líq/op':>9}{'total':>9}{'z/op':>7}{'lotes':>6}"
          f"{'pos':>5}{'z/LOTE':>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('klines')
    ap.add_argument('funding')
    ap.add_argument('--n', type=int, default=150)
    a = ap.parse_args()
    serie, fund, tempos = {}, {}, {}
    for p in sorted(glob.glob(os.path.join(a.klines, '*_1h.csv'))):
        s = os.path.basename(p).replace('_1h.csv', '')
        h = ler(p)
        if len(h) < 400:
            continue
        serie[s] = h
        fund[s] = ler_funding(os.path.join(a.funding, f'{s}_funding.csv'))
        tempos[s] = [x[0] for x in fund[s]]
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    meses = (t1-t0)/(1000*3600*24*30.4)

    # o retrato ano a ano
    print(f"{len(serie)} pares · {meses:.0f} meses\n")
    print(f"{'='*120}\n  QUANTOS PARES EM CADA CICLO, ANO A ANO\n{'='*120}")
    print(f"{'ano':<6}" + ''.join(f"{f'{iv}h':>10}" for iv in (1, 2, 4, 8)))
    for ano in range(2020, 2027):
        ts = int(dt.datetime(ano, 7, 1, tzinfo=dt.timezone.utc)
                 .timestamp()*1000)
        c = {1: 0, 2: 0, 4: 0, 8: 0}
        for s in serie:
            if not fund[s] or fund[s][0][0] > ts or fund[s][-1][0] < ts:
                continue
            iv = ciclo_em(fund[s], ts, tempos[s])
            if iv in c:
                c[iv] += 1
        print(f"{ano:<6}" + ''.join(f"{c[iv]:>10}" for iv in (1, 2, 4, 8)))

    janelas = []
    t = t0 + TRI
    while t < t1:
        janelas.append((t, sorted(serie,
                                  key=lambda s: -vol(serie[s], t-TRI, t))))
        t += TRI
    cache = {}

    def todas(tf, s):
        k = (s, tf)
        if k not in cache:
            cache[k] = ops_tf(serie[s], s, tf)
        return cache[k]

    def rolante(modo, n):
        """modo: 4, 8, ou 'casado'."""
        ops = []
        for t, jan in janelas:
            for s in jan[:n]:
                if modo == 'casado':
                    for tf in (4, 8):
                        for o in todas(tf, s):
                            if not (t <= o['ms'] < t + TRI):
                                continue
                            if ciclo_em(fund[s], o['ms'], tempos[s]) == tf:
                                ops.append(o)
                else:
                    for o in todas(modo, s):
                        if t <= o['ms'] < t + TRI:
                            ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    for n in (50, 150):
        print(f"\n{'='*120}\n  AS {n} MAIORES\n{'='*120}")
        cab()
        painel('sempre H8  (o setup de hoje)', rolante(8, n), meses)
        painel('sempre H4', rolante(4, n), meses)
        painel('CASADO — cada par no seu ciclo', rolante('casado', n), meses)
        print()
        # e separando por ciclo
        for iv in (4, 8):
            for tf in (4, 8):
                sel = [o for o in rolante(tf, n)
                       if ciclo_em(fund[o['sim']], o['ms'],
                                   tempos[o['sim']]) == iv]
                painel(f'  pares de ciclo {iv}h · lidos em H{tf}'
                       + ('   ← casa' if iv == tf else ''), sel, meses)


if __name__ == '__main__':
    main()
