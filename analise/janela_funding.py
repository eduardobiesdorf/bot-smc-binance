"""Mais entradas sem perder o alinhamento com o funding.

O achado: o H8 funciona porque a vela TERMINA na cobranca do funding
(00:00, 08:00, 16:00 UTC). A grade deslocada mede +3,23 desvios pior, e
o pior caso de todos e o funding no meio da vela.

A pergunta: o que importa e o ciclo INTEIRO de 8 horas, ou so o FINAL
dele -- as horas em que a pressao se acumula antes da liquidacao?

Da para separar: cada ciclo continua gerando uma observacao as 00:00,
08:00 e 16:00 UTC, mas a janela olha so as ultimas N horas. N=8 e o
setup de hoje. N menor mantem o alinhamento e afrouxa so o tamanho
absoluto do movimento -- numa janela de 4h a volatilidade media e
menor, entao "2,5 volatilidades" vira um evento mais comum.

E o oposto do teste da manha, onde trocar o tempo grafico QUEBROU o
alinhamento (e o bruto do H4 ficou negativo). Aqui o alinhamento fica.

Uso:  python3 janela_funding.py <pasta>
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

H = 3600_000
CICLO = 8 * H


def barras_funding(h1, n_h):
    """Uma barra por cobranca de funding, cobrindo as ULTIMAS n_h horas.

    n_h=8 e identico as velas de 8h de hoje. As barras continuam
    espacadas de 8 horas; so o que elas resumem muda.
    """
    por_ms = {v[0]: v for v in h1}
    t0 = ((h1[0][0] + CICLO - 1) // CICLO) * CICLO     # o 1o funding
    tf = (h1[-1][0] + H) // CICLO * CICLO
    out = []
    t = t0
    while t <= tf:
        velas = [por_ms.get(t - k*H) for k in range(n_h, 0, -1)]
        if all(v is not None for v in velas):
            out.append((t - n_h*H, velas[0][1],
                        max(v[2] for v in velas), min(v[3] for v in velas),
                        velas[-1][4], sum(v[5] for v in velas)))
        t += CICLO
    return out


def ops_janela(h1, sim, n_h):
    cfg = dict(rev.CFG)
    cfg['alvo_proj'] = 0.0
    cfg['alvo_rr'] = None
    cfg['so_compra'] = False
    cfg['tf_h'] = 8            # as barras continuam de 8 em 8 horas
    hp = barras_funding(h1, n_h)
    if len(hp) < 120:
        return []
    mv1 = e8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    # a entrada precisa achar o fim da barra no indice de 1h
    for i, b in enumerate(hp):
        pass
    h8 = rev.juntar(h1, 8)
    t8 = [v[0] for v in h8]
    out = []
    for e in rev.explosoes(hp, cfg):
        # fim_ms: a barra fecha na cobranca; o gatilho comeca dali
        e = dict(e)
        e['fim_ms'] = hp[e['i']][0] + n_h*H
        g = rev.entrada(h1, mv1, e, cfg, pos1)
        if not g:
            continue
        compra = g['lado'] == 'compra'
        risco = abs(g['entrada'] - g['stop'])
        i8 = max(k for k, t in enumerate(t8) if t <= g['vela_ms'])
        fim = saida = None
        for m in range(i8+1, min(i8+1+rev.MAX_BARRAS, len(h8))):
            hi, lo = h8[m][2], h8[m][3]
            if compra:
                if lo <= g['stop']: fim, saida = 'stop', g['stop']; break
                if hi >= g['alvo']: fim, saida = 'alvo', g['alvo']; break
            else:
                if hi >= g['stop']: fim, saida = 'stop', g['stop']; break
                if lo <= g['alvo']: fim, saida = 'alvo', g['alvo']; break
        if fim is None:
            continue
        horas = (m-i8)*8
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
          f"{statistics.mean(o['bruto'] for o in ops):>+9.1f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{z_de(v):>+7.2f}"
          f"{len(L):>6}{sum(1 for x in lv if x>0):>5}{z_de(lv):>+8.2f}"
          f"{max(lv)/tot*100 if tot > 0 else 0:>7.0f}%")


def cab(larg=28):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>8}{'R:R':>6}{'stop':>8}"
          f"{'bruto':>9}{'líq/op':>9}{'total':>9}{'z/op':>7}{'lotes':>6}"
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

    def rolante(n_h, n):
        ops = []
        for t, jan in janelas:
            for s in jan[:n]:
                k = (s, n_h)
                if k not in cache:
                    cache[k] = ops_janela(serie[s], s, n_h)
                for o in cache[k]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"{len(serie)} pares · {meses:.0f} meses · a janela sempre TERMINA "
          f"na cobrança do funding\n")
    for n in (50, 150):
        print(f"{'='*140}\n  AS {n} MAIORES\n{'='*140}")
        cab()
        for n_h in (2, 3, 4, 5, 6, 8, 12, 16):
            painel(f'as últimas {n_h}h do ciclo'
                   + ('  ← hoje' if n_h == 8 else ''),
                   rolante(n_h, n), meses)
        print()


if __name__ == '__main__':
    main()
