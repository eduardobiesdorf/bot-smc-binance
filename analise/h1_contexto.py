"""O H1 vira positivo com as variaveis novas (funding e teto de volume)?

O setup 3 no H1 mede BRUTO -1,50 -- negativo antes de qualquer taxa.
Nao e corretagem comendo o lucro: nao ha lucro. Botar filtro em cima
de zero nao produz numero positivo.

Mas o H1 nunca foi testado com funding nem com teto de volume. Elas
nao sao parametro do padrao, sao contexto de mercado, e no mapa foram
os dois sinais mais fortes:

  funding acima de +0,10% por cobranca -> +0,56% em 8h, +2,45% em 3 dias
  volume acima de 4x a media -> a UNICA celula negativa do mapa inteiro

A pergunta, e so ela: alguma dessas faz o BRUTO do H1 virar positivo?
Se virar, o H1 abre uma base larga (2,9 eventos/mes nas 150, mais nas
471). Se nao virar em nenhuma, o H1 esta fechado.

Uso:  python3 h1_contexto.py <klines> <funding>
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


def ops_tf(h1, sim, tf, fnd, tmp):
    cfg = dict(rev.CFG)
    cfg['tf_h'] = tf
    cfg['alvo_proj'] = 0.0
    cfg['alvo_rr'] = None
    cfg['so_compra'] = False
    hp = rev.juntar(h1, tf) if tf > 1 else h1
    if len(hp) < 120:
        return []
    mv1 = e8.medvol(h1, 20)
    mvp = e8.medvol(hp, 20)
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
        # contexto na vela da EXPLOSAO
        ie = e['i']
        volx = hp[ie][5]/mvp[ie] if mvp[ie] > 0 else 0.0
        tx = None
        if tmp:
            k = bisect.bisect_right(tmp, e['exp_ms']) - 1
            if k >= 0:
                tx = fnd[k][1]
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
                        lado=g['lado'], volx=volx, tx=tx,
                        stop_pct=g['risco_pct'], bruto=pos*mov,
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return out


def painel(rot, ops, meses, larg=34):
    if not ops:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in ops]
    b = [o['bruto'] for o in ops]
    g = [o for o in ops if o['fim'] == 'alvo']
    L = lotes_de(ops)
    lv = [sum(y['liq'] for y in x) for x in L]
    print(f"{rot:<{larg}}{len(ops):>5}{len(ops)/meses:>6.1f}"
          f"{statistics.mean(b):>+10.1f}"
          f"{len(g)/len(ops)*100:>8.1f}%"
          f"{statistics.mean(o['rr'] for o in ops):>6.2f}"
          f"{statistics.mean(v):>+9.1f}{sum(v):>+9.0f}{z_de(v):>+7.2f}"
          f"{len(L):>6}{z_de(lv):>+8.2f}")


def cab(larg=34):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'BRUTO':>10}{'acerto':>8}"
          f"{'R:R':>6}{'líq/op':>9}{'total':>9}{'z/op':>7}{'lotes':>6}"
          f"{'z/LOTE':>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('klines')
    ap.add_argument('funding')
    a = ap.parse_args()
    serie, fnd, tmp = {}, {}, {}
    for p in sorted(glob.glob(os.path.join(a.klines, '*_1h.csv'))):
        s = os.path.basename(p).replace('_1h.csv', '')
        h = ler(p)
        if len(h) < 400:
            continue
        serie[s] = h
        f = []
        try:
            with open(os.path.join(a.funding, f'{s}_funding.csv')) as fh:
                for r in csv.DictReader(fh):
                    f.append((int(r['tempo_ms']), float(r['taxa'])))
        except Exception:
            pass
        f.sort()
        fnd[s] = f
        tmp[s] = [x[0] for x in f]
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    meses = (t1-t0)/(1000*3600*24*30.4)
    janelas = []
    t = t0 + TRI
    while t < t1:
        janelas.append((t, sorted(serie,
                                  key=lambda s: -vol(serie[s], t-TRI, t))))
        t += TRI
    cache = {}

    def rolante(tf, n, filtro=None):
        ops = []
        for t, jan in janelas:
            for s in jan[:n]:
                k = (s, tf)
                if k not in cache:
                    cache[k] = ops_tf(serie[s], s, tf, fnd[s], tmp[s])
                for o in cache[k]:
                    if not (t <= o['ms'] < t + TRI):
                        continue
                    if filtro and not filtro(o):
                        continue
                    ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    FILTROS = [
        ('sem filtro novo', None),
        ('funding > 0', lambda o: o['tx'] is not None and o['tx'] > 0),
        ('funding > +0,01%', lambda o: o['tx'] is not None and o['tx'] > .0001),
        ('funding > +0,05%', lambda o: o['tx'] is not None and o['tx'] > .0005),
        ('funding < 0 (ao contrário)',
         lambda o: o['tx'] is not None and o['tx'] < 0),
        ('volume da explosão <= 4x', lambda o: o['volx'] <= 4),
        ('volume da explosão <= 3x', lambda o: o['volx'] <= 3),
        ('volume <= 4x E funding > 0',
         lambda o: o['volx'] <= 4 and o['tx'] is not None and o['tx'] > 0),
        ('volume <= 3x E funding > +0,01%',
         lambda o: o['volx'] <= 3 and o['tx'] is not None and o['tx'] > .0001),
    ]
    print(f"{len(serie)} pares · {meses:.0f} meses · setup 3 · "
          f"o que importa é a coluna BRUTO\n")
    for tf in (1, 2, 8):
        for n in (150, 471):
            print(f"{'='*132}\n  H{tf} · as {n if n < 471 else 'TODAS as'} "
                  f"moedas\n{'='*132}")
            cab()
            for rot, f in FILTROS:
                painel(rot, rolante(tf, n, f), meses)
            print()


if __name__ == '__main__':
    main()
