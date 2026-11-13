"""O stop na vela do GATILHO em vez de embaixo do bloco inteiro.

Hoje:
  setup 3  stop = base do order block - 0,10 ATR
  setup 1  stop = extremo da varredura - 0,10 ATR

Mais curto, na vela do gatilho, o risco em preco cai -- entao o
risco/retorno de cada entrada SOBE e mais montagens passam no corte de
1:1,2, mas se leva mais stop. A conta decide.

Uso:  python3 stop_gatilho.py <pasta>
"""
import argparse, glob, os, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
import bot_varredura as bot
from explosao import ler, RISCO, TAXA, FUND8
from lista_operacoes import vol, TRI, BRT
from alvo_lote import z_de
from venda_topo import lotes_de
from explosao import curva
import itertools

MAXBAR = 120


def rev_ops(h1, sim, modo, folga):
    """modo: 'bloco' (hoje) ou 'gatilho'."""
    cfg = dict(rev.CFG)
    cfg['alvo_proj'] = 0.0
    cfg['alvo_rr'] = None
    cfg['so_compra'] = False
    hp = rev.juntar(h1, 8)
    if len(hp) < 120:
        return []
    mv1 = e8.medvol(h1, 20)
    a1 = e8.atr(h1, 14)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    tp = [v[0] for v in hp]
    out = []
    for e in rev.explosoes(hp, cfg):
        g = rev.entrada(h1, mv1, e, cfg, pos1)
        if not g:
            continue
        compra = g['lado'] == 'compra'
        k = g['idx']
        if modo == 'bloco':
            stop = g['stop']
        else:
            base = h1[k][3] if compra else h1[k][2]
            stop = base - a1[k]*folga if compra else base + a1[k]*folga
        ent, alvo = g['entrada'], g['alvo']
        risco = abs(ent - stop)
        dist = (alvo-ent) if compra else (ent-alvo)
        if risco <= 0 or dist <= 0 or dist/risco < cfg['rr_min']:
            continue
        i = max(x for x, t in enumerate(tp) if t <= g['vela_ms'])
        fim = saida = None
        for m in range(i+1, min(i+1+rev.MAX_BARRAS, len(hp))):
            hi, lo = hp[m][2], hp[m][3]
            if compra:
                if lo <= stop: fim, saida = 'stop', stop; break
                if hi >= alvo: fim, saida = 'alvo', alvo; break
            else:
                if hi >= stop: fim, saida = 'stop', stop; break
                if lo <= alvo: fim, saida = 'alvo', alvo; break
        if fim is None:
            continue
        mov = (saida-ent)/ent*(1 if compra else -1)
        pos = RISCO/(risco/ent)
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        out.append(dict(sim=sim, ms=g['vela_ms'], q=q, fim=fim,
                        rr=dist/risco, stop_pct=risco/ent*100,
                        liq=pos*mov - pos*TAXA*2 - pos*((m-i)*8/8)*FUND8))
    return out


def s1_ops(h1, sim, modo, folga):
    cfg = dict(bot.CFG)
    tf = int(cfg['tf'].replace('h', ''))
    h = rev.juntar(h1, tf) if tf > 1 else h1
    if len(h) < 200:
        return []
    a = bot.atr(h, cfg['atr_periodo'])
    mv = bot.media_volume(h, cfg['vol_periodo'])
    out = []
    for imp in bot.achar_impulsos(h, a, mv, cfg):
        g = bot.seguir(h, a, imp, cfg, mv)
        if not g or g.get('fase') != 'gatilho':
            continue
        compra = g['lado'] == 'compra'
        k = g['idx']
        if modo == 'bloco':
            stop = g['stop']
        else:
            base = h[k][3] if compra else h[k][2]
            stop = base - a[k]*folga if compra else base + a[k]*folga
        ent, alvo = g['entrada'], g['alvo']
        risco = abs(ent-stop)
        dist = (alvo-ent) if compra else (ent-alvo)
        if risco <= 0 or dist <= 0 or dist/risco < cfg['rr_min']:
            continue
        fim = saida = None
        for m in range(k+1, min(k+1+MAXBAR, len(h))):
            hi, lo = h[m][2], h[m][3]
            if compra:
                if lo <= stop: fim, saida = 'stop', stop; break
                if hi >= alvo: fim, saida = 'alvo', alvo; break
            else:
                if hi >= stop: fim, saida = 'stop', stop; break
                if lo <= alvo: fim, saida = 'alvo', alvo; break
        if fim is None:
            continue
        mov = (saida-ent)/ent*(1 if compra else -1)
        pos = RISCO/(risco/ent)
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        out.append(dict(sim=sim, ms=g['vela_ms'], q=q, fim=fim,
                        rr=dist/risco, stop_pct=risco/ent*100,
                        liq=pos*mov - pos*TAXA*2 - pos*((m-k)*tf/8)*FUND8))
    return out


def painel(rot, ops, meses, larg=30):
    if not ops:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in ops]
    g = [o for o in ops if o['fim'] == 'alvo']
    L = lotes_de(ops)
    lv = [sum(y['liq'] for y in x) for x in L]
    seq = max((len(list(x)) for k, x in
               itertools.groupby(ops, key=lambda o: o['fim'] != 'alvo')
               if k), default=0)
    tot, dd = curva(v)
    print(f"{rot:<{larg}}{len(ops):>5}{len(ops)/meses:>6.1f}"
          f"{len(g)/len(ops)*100:>8.1f}%"
          f"{statistics.mean(o['rr'] for o in ops):>6.2f}"
          f"{statistics.mean(o['stop_pct'] for o in ops):>7.2f}%"
          f"{statistics.mean(v):>+9.1f}{sum(v):>+9.0f}"
          f"{dd:>8.0f}{seq:>5}{z_de(v):>+7.2f}{z_de(lv):>+8.2f}")


def cab(larg=30):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>9}{'R:R':>6}"
          f"{'stop':>8}{'líq/op':>9}{'total':>9}{'rebaix.':>8}"
          f"{'seq':>5}{'z/op':>7}{'z/LOTE':>8}")


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
    meses = (t1-t0)/(1000*3600*24*30.4)
    janelas = []
    t = t0 + TRI
    while t < t1:
        janelas.append((t, sorted(serie,
                                  key=lambda s: -vol(serie[s], t-TRI, t))[:a.n]))
        t += TRI
    cache = {}

    def rolante(fn, modo, folga):
        ops = []
        for t, jan in janelas:
            for s in jan:
                k = (s, fn.__name__, modo, folga)
                if k not in cache:
                    cache[k] = fn(serie[s], s, modo, folga)
                for o in cache[k]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"as {a.n} maiores · {meses:.0f} meses\n")
    for fn, nome in ((rev_ops, 'SETUP 3 — reversão H8'),
                     (s1_ops, 'SETUP 1 — varredura H4')):
        print(f"{'='*124}\n  {nome}\n{'='*124}")
        cab()
        painel('stop no bloco (hoje)', rolante(fn, 'bloco', 0.10), meses)
        for f in (0.0, 0.10, 0.25, 0.50, 1.00):
            painel(f'stop no gatilho + {f:.2f} ATR',
                   rolante(fn, 'gatilho', f), meses)
        print()


if __name__ == '__main__':
    main()
