"""O setup 2 (explosao de vela unica) com tudo o que se aprendeu em 13/11.

Ele foi desligado em 12/11 com 32,3% de acerto -- mas medido no universo
viciado, por operacao, com o alvo PROJETADO de 90% e sem filtro de
profundidade no encosto. Tres coisas que hoje se mostraram erradas:

  o ALVO     a projecao de 90% concentra o lucro e derruba a
             significancia. O alvo no EXTREMO da estrutura levou o
             setup 3 de z/lote +1,04 para +2,04.
  o UNIVERSO a lista de hoje infla o resultado; o rolante e o honesto.
  a CONTAGEM por operacao superestima; o que vale e por LOTE.

E falta o filtro que mais rendeu nos outros dois: a PROFUNDIDADE do
encosto medida na altura do PROPRIO order block. No setup 3 (encosto
raso) e no setup 1 (furo raso) foi o maior efeito de filtro unico.

O setup 2 e a mae do setup 3: mesmo esqueleto, sem exigir a queda
previa e rompendo o extremo de 20 velas em vez do ultimo pivo. Entao
ele pega CONTINUACAO onde o 3 pega reversao.

Uso:  python3 setup2_novo.py <pasta>
"""
import argparse, glob, os, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import explosao8 as e8
import reversao8 as rev
from explosao import ler, RISCO, TAXA, FUND8
from lista_operacoes import vol, TRI, BRT
from alvo_lote import z_de
from venda_topo import lotes_de

MAXBAR = 120


def ops_tf(h1, sim, tf):
    """Todos os gatilhos do setup 2 na serie de tf horas, sem filtrar.
    O alvo e a profundidade sao aplicados depois."""
    hp = rev.juntar(h1, tf) if tf > 1 else h1
    if len(hp) < 120:
        return []
    cfg = dict(e8.CFG8)
    cfg['alvo_proj'] = 0.0        # o alvo real e recalculado depois
    out = []
    for g in e8.historico(hp, cfg):
        alta = g['lado'] == 'compra'
        alt = g['ob_topo'] - g['ob_base']
        fund = (((g['ob_base'] - g['extremo']) if alta else
                 (g['extremo'] - g['ob_topo'])) / alt) if alt > 0 else 0.0
        g['fundura'] = max(0.0, fund)
        g['tf'] = tf
        g['q'] = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        g['ms'] = g['vela_ms']
        g['sim'] = sim
        g['i_hp'] = max(k for k, v in enumerate(hp) if v[0] <= g['vela_ms'])
        out.append(g)
    return out, hp


def resolver(g, hp, proj, tf):
    alta = g['lado'] == 'compra'
    alvo = (g['exp_topo'] + proj*g['tam']) if alta else \
           (g['exp_topo'] - proj*g['tam'])
    ent, stop = g['entrada'], g['stop']
    dist = (alvo-ent) if alta else (ent-alvo)
    risco = abs(ent-stop)
    if dist <= 0 or risco <= 0:
        return None
    i = g['i_hp']
    fim = saida = None
    for m in range(i+1, min(i+1+MAXBAR, len(hp))):
        hi, lo = hp[m][2], hp[m][3]
        if alta:
            if lo <= stop: fim, saida = 'stop', stop; break
            if hi >= alvo: fim, saida = 'alvo', alvo; break
        else:
            if hi >= stop: fim, saida = 'stop', stop; break
            if lo <= alvo: fim, saida = 'alvo', alvo; break
    if fim is None:
        return None
    horas = (m-i)*tf
    mov = (saida-ent)/ent*(1 if alta else -1)
    pos = RISCO/(risco/ent)
    return dict(sim=g['sim'], ms=g['ms'], q=g['q'], fim=fim,
                rr=dist/risco, fundura=g['fundura'],
                stop_pct=g['risco_pct'], bruto=pos*mov,
                liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8)


def painel(rot, ops, meses, larg=32):
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
          f"{len(L):>6}{sum(1 for x in lv if x>0):>5}{z_de(lv):>+8.2f}"
          f"{max(lv)/tot*100 if tot > 0 else 0:>7.0f}%")


def cab(larg=32):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>8}{'R:R':>6}"
          f"{'bruto':>9}{'líq/op':>9}{'total':>9}{'z/op':>7}{'lotes':>6}"
          f"{'pos':>5}{'z/LOTE':>8}{'maior':>8}")


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
                                  key=lambda s: -vol(serie[s], t-TRI, t))))
        t += TRI
    cache = {}

    def rolante(tf, proj, fundura_max=None, n=150):
        ops = []
        for t, jan in janelas:
            for s in jan[:n]:
                k = (s, tf)
                if k not in cache:
                    try:
                        cache[k] = ops_tf(serie[s], s, tf)
                    except Exception:
                        cache[k] = ([], [])
                gs, hp = cache[k]
                for g in gs:
                    if not (t <= g['ms'] < t + TRI):
                        continue
                    if fundura_max is not None and g['fundura'] > fundura_max:
                        continue
                    o = resolver(g, hp, proj, tf)
                    if o:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"{len(serie)} pares · {meses:.0f} meses · setup 2 "
          f"(explosão de vela única)\n")
    for n in (50, 150):
        print(f"{'='*140}\n  AS {n} MAIORES\n{'='*140}")
        for tf in (2, 4, 8):
            cab()
            painel(f'H{tf} · alvo projetado 90% (o antigo)',
                   rolante(tf, 0.90, None, n), meses)
            painel(f'H{tf} · alvo no EXTREMO',
                   rolante(tf, 0.0, None, n), meses)
            for f in (0.50, 0.25, 0.15):
                painel(f'H{tf} · extremo + encosto <= {f:.2f}x',
                       rolante(tf, 0.0, f, n), meses)
            print()
            for pr in (1.00, 1.25, 1.50, 2.00, 3.00):
                painel(f'H{tf} · projeção {pr*100:.0f}%',
                       rolante(tf, pr, None, n), meses)
            for pr in (1.00, 1.50, 2.00):
                painel(f'H{tf} · proj {pr*100:.0f}% + encosto <= 0,25x',
                       rolante(tf, pr, 0.25, n), meses)
            if n == 150:
                cands = []
                for pr in (0.90, 1.00, 1.25, 1.50, 2.00, 3.00):
                    for f in (None, 0.25):
                        o = rolante(tf, pr, f, n)
                        if o:
                            cands.append((statistics.mean(
                                x['liq'] for x in o), pr, f, o))
                if cands:
                    cands.sort(reverse=True, key=lambda c: c[0])
                    m, pr, f, o = cands[0]
                    print(f"  melhor célula do H{tf}: projeção "
                          f"{pr*100:.0f}%"
                          + (f" + encosto <= {f}x" if f else "")
                          + f" · {m:+.1f} por operação")
                    controle(o, serie, tf)
            print()


def controle(ops, serie, tf, k=200):
    """A melhor celula bate entrada aleatoria, por lote?"""
    import random as _r
    rng = _r.Random(57)
    hp = {}
    for o in ops:
        if o['sim'] not in hp:
            hp[o['sim']] = (rev.juntar(serie[o['sim']], tf) if tf > 1
                            else serie[o['sim']])
    L = lotes_de(ops)
    reais = [sum(y['liq'] for y in x) for x in L]
    sort = []
    for x in L:
        for _ in range(k):
            s_, ok = 0.0, 0
            for o in x:
                h = hp[o['sim']]
                lo_i, hi_i = 30, len(h) - MAXBAR - 1
                if hi_i <= lo_i:
                    continue
                i = rng.randrange(lo_i, hi_i)
                ent = h[i][4]
                stop = ent*(1 - o['stop_pct']/100)
                alvo = ent + (ent-stop)*o['rr']
                fim = saida = None
                for m in range(i+1, min(i+1+MAXBAR, len(h))):
                    if h[m][3] <= stop: fim, saida = 1, stop; break
                    if h[m][2] >= alvo: fim, saida = 1, alvo; break
                if fim is None:
                    continue
                pos = RISCO/(o['stop_pct']/100)
                s_ += pos*(saida-ent)/ent - pos*TAXA*2 - \
                    pos*((m-i)*tf/8)*FUND8
                ok += 1
            if ok:
                sort.append(s_*len(x)/ok)
    mr, ms_ = statistics.mean(reais), statistics.mean(sort)
    er = statistics.pstdev(reais)/len(reais)**.5
    es = statistics.pstdev(sort)/len(sort)**.5
    d = mr - ms_
    e = (er**2 + es**2) ** .5
    print(f"    lote real {mr:>+8.0f} ±{er:<5.0f}"
          f"({sum(1 for x in reais if x > 0)}/{len(reais)})  ·  "
          f"sorteado {ms_:>+8.0f}  ·  diferença {d:>+8.0f} ±{e:<5.0f}"
          f"  ->  {d/e if e else 0:+.2f} DESVIOS")


if __name__ == '__main__':
    main()
