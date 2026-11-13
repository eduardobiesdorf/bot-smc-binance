"""A reversao em H1, H2, H4 e H8 -- com o ALVO NOVO e por LOTE.

A reversao em H4, H2 e H1 foi rejeitada semanas atras. Mas aquilo foi
medido com a projecao de 90% (o alvo errado), no universo viciado,
contado por operacao e nas 150 moedas. O mesmo alvo errado ja produziu
tres conclusoes falsas hoje:

  - "o setup esta sobreajustado a 2023-2026"  (era o alvo)
  - "a venda nao funciona"                    (era o alvo)
  - "o z e +1,24"                             (era o alvo, e +2,45)

A rejeicao do H1 e a quarta candidata e nunca foi refeita.

E ha logica a favor: o alvo projetado pedia uma distancia fixa em
porcentagem. No H1 as velas sao pequenas, entao a projecao dava um alvo
perto -- mas o stop tambem, e a taxa comia tudo. Com o alvo no EXTREMO
da propria vela a geometria muda inteira.

Mede duas leituras das janelas:
  fractal   as mesmas CONTAGENS de vela (queda em 20 velas, pivo +-2)
  ancorado  os mesmos TEMPOS do H8 (queda em 160 horas, pivo +-16h)

Uso:  python3 rev_tempos.py <pasta>
"""
import argparse, glob, os, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler, RISCO, TAXA, FUND8
from lista_operacoes import vol, TRI, BRT
from alvo_lote import z_de
from venda_topo import lotes_de


def ops_tf(h1, sim, tf, modo):
    cfg = dict(rev.CFG)
    cfg['tf_h'] = tf
    cfg['alvo_proj'] = 0.0
    cfg['alvo_rr'] = None
    cfg['so_compra'] = False
    if modo == 'ancorado' and tf != 8:
        cfg['tend_jan'] = max(5, round(160/tf))
        cfg['busca_topo'] = max(5, round(240/tf))
        cfg['pivo'] = max(1, round(16/tf))
        cfg['espera'] = max(10, round(720/tf))
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
                        stop_pct=g['risco_pct'], bruto=pos*mov,
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return out


def painel(rot, ops, meses, larg=28):
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
          f"{statistics.mean(o['stop_pct'] for o in ops):>7.2f}%"
          f"{statistics.mean(o['bruto'] for o in ops):>+8.1f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{z_de(v):>+7.2f}"
          f"{len(L):>6}{sum(1 for x in lv if x>0):>5}{z_de(lv):>+8.2f}"
          f"{max(lv)/tot*100 if tot>0 else 0:>7.0f}%")


def cab(larg=28):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>8}{'R:R':>6}{'stop':>8}"
          f"{'bruto':>8}{'líq/op':>9}{'total':>9}{'z/op':>7}{'lotes':>6}"
          f"{'pos':>5}{'z/LOTE':>8}{'maior':>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    a = ap.parse_args()
    serie = {}
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            serie[os.path.basename(p).replace('_1h.csv', '')] = h
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

    def rolante(tf, modo, n):
        ops = []
        for t, jan in janelas:
            for s in jan[:n]:
                k = (s, tf, modo)
                if k not in cache:
                    cache[k] = ops_tf(serie[s], s, tf, modo)
                for o in cache[k]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"{len(serie)} pares · {meses:.0f} meses · alvo no EXTREMO da "
          f"vela · os dois lados\n")
    for modo in ('fractal', 'ancorado'):
        print(f"{'='*142}\n  JANELAS {modo.upper()}" +
              ("  (as mesmas contagens de vela do H8)" if modo == 'fractal'
               else "  (os mesmos tempos do H8: queda em 160h, pivô ±16h)") +
              f"\n{'='*142}")
        for n in (20, 50, 150):
            cab()
            for tf in (1, 2, 4, 8):
                painel(f'as {n} maiores · H{tf}'
                       + ('  ← hoje' if (tf == 8 and n == 150) else ''),
                       rolante(tf, modo, n), meses)
            print()
        if modo == 'fractal':
            print()


if __name__ == '__main__':
    main()
