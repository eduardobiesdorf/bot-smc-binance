"""Cada operacao da reversao, uma a uma, com dinheiro e tempo.

Universo rolante e config AO VIVO (reversao8.CFG). Mostra as duas
convencoes de dinheiro:

  risco $100     o padrao dos backtests: a posicao e $100 dividido pelo
                 stop em %, entao um stop de 5% compra $2.000 de posicao
                 e uma perda cheia custa $100 (mais taxa).
  posicao $100   $100 de posicao sempre, sem alavancagem extra: a perda
                 e so o stop em % de $100.

Uso:  python3 lista_operacoes.py <pasta> [--n 150]
"""
import argparse, glob, os, statistics, sys
import datetime as dt
import csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler, curva, RISCO, TAXA, FUND8

BRT = dt.timezone(dt.timedelta(hours=-3))
TRI = 90*24*3600_000


def vol(h, ini=None, fim=None):
    v = [x[4]*x[5] for x in h
         if (ini is None or x[0] >= ini) and (fim is None or x[0] < fim)]
    return statistics.median(v) if len(v) >= 100 else 0.0


def ops_de(h1, sim):
    cfg = rev.CFG
    hp = rev.juntar(h1, cfg['tf_h'])
    if len(hp) < 60:
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
        horas = (m-i)*cfg['tf_h']
        mov = (saida-g['entrada'])/g['entrada']*(1 if compra else -1)
        pos_r = RISCO/(risco/g['entrada'])          # risco $100
        liq_r = pos_r*mov - pos_r*TAXA*2 - pos_r*(horas/8)*FUND8
        liq_p = 100*mov - 100*TAXA*2 - 100*(horas/8)*FUND8   # posicao $100
        # dias entre a explosao e a entrada
        espera_d = (g['vela_ms'] - e['exp_ms'])/86400_000
        out.append(dict(
            sim=sim, ms=g['vela_ms'],
            q=dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT),
            lado=g['lado'], entrada=g['entrada'], stop=g['stop'],
            alvo=g['alvo'], stop_pct=g['risco_pct'], rr=g['rr'], fim=fim,
            horas=horas, dias=horas/24, espera_d=espera_d,
            pos_r=pos_r, liq_r=liq_r, liq_p=liq_p, mov=mov*100))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    a = ap.parse_args()
    serie = {}
    for p in sorted(glob.glob(os.path.join(a.pasta, '*_1h.csv'))):
        h = ler(p)
        if len(h) >= 400:
            serie[os.path.basename(p).replace('_1h.csv', '')] = h
    t0 = min(h[0][0] for h in serie.values())
    t1 = max(h[-1][0] for h in serie.values())
    cache, ops = {}, []
    t = t0 + TRI
    while t < t1:
        jan = sorted(serie, key=lambda s: -vol(serie[s], t-TRI, t))[:a.n]
        for s in jan:
            if s not in cache:
                cache[s] = ops_de(serie[s], s)
            for o in cache[s]:
                if t <= o['ms'] < t + TRI:
                    ops.append(o)
        t += TRI
    ops.sort(key=lambda o: o['q'])

    with open('operacoes_reversao.csv', 'w', newline='',
              encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['n', 'data_brasilia', 'par', 'lado', 'entrada', 'stop',
                    'alvo', 'stop_pct', 'risco_retorno', 'desfecho',
                    'dias_posicionado', 'dias_explosao_ate_entrada',
                    'variacao_pct', 'posicao_risco100', 'result_risco100',
                    'result_posicao100'])
        for k, o in enumerate(ops, 1):
            w.writerow([k, f"{o['q']:%Y-%m-%d %H:%M}", o['sim'], o['lado'],
                        f"{o['entrada']:.8g}", f"{o['stop']:.8g}",
                        f"{o['alvo']:.8g}", f"{o['stop_pct']:.2f}",
                        f"{o['rr']:.2f}", o['fim'], f"{o['dias']:.1f}",
                        f"{o['espera_d']:.1f}", f"{o['mov']:.2f}",
                        f"{o['pos_r']:.0f}", f"{o['liq_r']:.2f}",
                        f"{o['liq_p']:.2f}"])

    print(f"{len(ops)} operações · universo rolante de {a.n} · config ao vivo\n")
    print(f"{'#':>3} {'data':<16} {'par':<12} {'stop%':>6} {'desf':<5}"
          f"{'dias':>6}{'  risco$100':>12}{'  pos.$100':>11}"
          f"{'  acum.$100risco':>17}")
    ac = 0.0
    for k, o in enumerate(ops, 1):
        ac += o['liq_r']
        print(f"{k:>3} {o['q']:%d/%m/%y %H:%M} {o['sim']:<12} "
              f"{o['stop_pct']:>5.2f}% {'ALVO ' if o['fim']=='alvo' else 'stop '}"
              f"{o['dias']:>6.1f}{o['liq_r']:>+12.2f}{o['liq_p']:>+11.2f}"
              f"{ac:>+17.0f}")

    g = [o for o in ops if o['fim'] == 'alvo']
    p = [o for o in ops if o['fim'] != 'alvo']
    tot, dd = curva([o['liq_r'] for o in ops])
    print(f"\n{'='*100}")
    print(f"  {len(ops)} operações · {len(g)} alvos ({len(g)/len(ops)*100:.1f}%)"
          f" · {len(p)} stops")
    print(f"  risco $100 por operação: {tot:+.0f} no total, "
          f"{statistics.mean(o['liq_r'] for o in ops):+.2f} por operação")
    print(f"  posição $100 por operação: "
          f"{sum(o['liq_p'] for o in ops):+.2f} no total, "
          f"{statistics.mean(o['liq_p'] for o in ops):+.2f} por operação")
    print(f"  pior rebaixamento (risco $100): {dd:.0f}")
    print(f"\n  TEMPO POSICIONADO")
    for rot, sel in (('as que bateram o ALVO', g), ('as que bateram o stop', p),
                     ('todas', ops)):
        if not sel:
            continue
        d = sorted(o['dias'] for o in sel)
        print(f"    {rot:<24} mediana {d[len(d)//2]:>5.1f} dias · "
              f"média {statistics.mean(d):>5.1f} · "
              f"de {min(d):.1f} a {max(d):.1f}")
    print(f"\n  DA EXPLOSÃO ATÉ A ENTRADA (a espera pelo encosto)")
    d = sorted(o['espera_d'] for o in ops)
    print(f"    mediana {d[len(d)//2]:.1f} dias · média "
          f"{statistics.mean(d):.1f} · de {min(d):.1f} a {max(d):.1f}")
    print(f"\n  POSIÇÃO ABERTA (risco $100): de "
          f"{min(o['pos_r'] for o in ops):,.0f} a "
          f"{max(o['pos_r'] for o in ops):,.0f} USDT · "
          f"mediana {statistics.median(o['pos_r'] for o in ops):,.0f}")


if __name__ == '__main__':
    main()
