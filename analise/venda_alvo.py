"""A venda nao funciona, ou o ALVO da venda e que esta errado?

O setup 3 virou so-compra em 13/11 porque as vendas davam -16,90 por
operacao. Mas o diagnostico aponta para o alvo, nao para a leitura:

    compras  31,9% de acerto, R:R 1:4,94, +39,60/op
    vendas   26,0% de acerto, R:R 1:2,96, -16,90/op

O alvo e 90% do tamanho da vela projetado alem do extremo. Uma queda
nao passa de 100% e uma alta nao tem teto, entao a MESMA projecao em
porcentagem e uma distancia muito maior para baixo. A venda esta sendo
obrigada a andar um caminho que a compra nao precisa andar.

Testa alvos proprios para a venda:
  - projecoes menores (20%, 30%, 45%, 60%, 75%)
  - o proprio extremo da explosao, sem projecao nenhuma
  - um alvo por multiplo de risco fixo (1:2, 1:2,5, 1:3), que e
    indiferente a assimetria da porcentagem

Tudo no universo ROLANTE, e com a compra do lado para comparar.

Uso:  python3 venda_alvo.py <pasta> [--n 150]
"""
import argparse
import glob
import os
import statistics
import sys
import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler, RISCO, TAXA, FUND8
from espera_longa import vol, painel, cab, TRI, BRT


def rodar(h1, sim, cfg, lado=None, proj=None, rr_fixo=None):
    """lado: 'compra', 'venda' ou None para os dois.
    proj: substitui alvo_proj. rr_fixo: alvo por multiplo de risco."""
    hp = rev.juntar(h1, cfg['tf_h'])
    if len(hp) < 60:
        return []
    mv1 = e8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    tp = [v[0] for v in hp]
    c = dict(cfg)
    c['so_compra'] = False
    if proj is not None:
        c['alvo_proj'] = proj
    ops = []
    for e in rev.explosoes(hp, c):
        if lado == 'compra' and not e['alta']:
            continue
        if lado == 'venda' and e['alta']:
            continue
        g = rev.entrada(h1, mv1, e, c, pos1)
        if not g:
            continue
        compra = g['lado'] == 'compra'
        risco = abs(g['entrada'] - g['stop'])
        alvo = g['alvo']
        if rr_fixo:
            alvo = g['entrada'] + risco*rr_fixo if compra else \
                   g['entrada'] - risco*rr_fixo
        dist = (alvo-g['entrada']) if compra else (g['entrada']-alvo)
        if dist <= 0:
            continue
        i = max(k for k, t in enumerate(tp) if t <= g['vela_ms'])
        fim = saida = None
        for m in range(i+1, min(i+1+rev.MAX_BARRAS, len(hp))):
            hi, lo = hp[m][2], hp[m][3]
            if compra:
                if lo <= g['stop']: fim, saida = 'stop', g['stop']; break
                if hi >= alvo: fim, saida = 'alvo', alvo; break
            else:
                if hi >= g['stop']: fim, saida = 'stop', g['stop']; break
                if lo <= alvo: fim, saida = 'alvo', alvo; break
        if fim is None:
            continue
        pos = RISCO/(risco/g['entrada'])
        mov = (saida-g['entrada'])/g['entrada']*(1 if compra else -1)
        horas = (m-i)*c['tf_h']
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        ops.append(dict(sim=sim, q=q, ano=q.year, rr=dist/risco,
                        stop_pct=g['risco_pct'], ms=g['vela_ms'],
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return ops


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
    print(f"{len(serie)} pares · {meses:.0f} meses · universo ROLANTE de "
          f"{a.n}\n")

    def rolante(**kw):
        cache, ops = {}, []
        for t, jan in janelas:
            for s in jan:
                k = (s, tuple(sorted((x, y) for x, y in kw.items()
                                     if y is not None)))
                if k not in cache:
                    cache[k] = rodar(serie[s], s, rev.CFG, **kw)
                for o in cache[k]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"{'='*140}\n  A COMPRA, para comparar\n{'='*140}")
    cab()
    painel('compra · alvo 90% (hoje)', rolante(lado='compra'), meses)

    print(f"\n{'='*140}\n  A VENDA com projeções menores\n{'='*140}")
    cab()
    for pr in (0.90, 0.75, 0.60, 0.45, 0.30, 0.20):
        painel(f'venda · projeção {pr*100:.0f}%'
               + ('  ← hoje' if pr == 0.90 else ''),
               rolante(lado='venda', proj=pr), meses)
    painel('venda · o extremo, sem projeção', rolante(lado='venda', proj=0.0),
           meses)

    print(f"\n{'='*140}\n  A VENDA com alvo por múltiplo de risco\n"
          f"  (indiferente à assimetria da porcentagem)\n{'='*140}")
    cab()
    for rr in (1.5, 2.0, 2.5, 3.0, 4.0):
        painel(f'venda · alvo em 1:{rr:.1f}',
               rolante(lado='venda', rr_fixo=rr), meses)

    print(f"\n{'='*140}\n  OS DOIS LADOS JUNTOS, com o melhor alvo de cada\n"
          f"{'='*140}")
    cab()
    painel('só compra (como está hoje)', rolante(lado='compra'), meses)
    painel('compra e venda · alvo 90% nos dois', rolante(), meses)
    for pr in (0.45, 0.30):
        comb = sorted(rolante(lado='compra') +
                      rolante(lado='venda', proj=pr),
                      key=lambda o: o['q'])
        painel(f'compra 90% + venda {pr*100:.0f}%', comb, meses)
    for rr in (2.0, 2.5, 3.0, 3.5, 4.0, 5.0):
        comb = sorted(rolante(lado='compra') +
                      rolante(lado='venda', rr_fixo=rr),
                      key=lambda o: o['q'])
        painel(f'compra 90% + venda 1:{rr:.1f}', comb, meses)

    print(f"\n{'='*140}\n  A COMPRA tambem quer alvo por múltiplo de risco?\n"
          f"{'='*140}")
    cab()
    painel('compra · projeção 90% (hoje)', rolante(lado='compra'), meses)
    for rr in (3.0, 4.0, 5.0, 6.0):
        painel(f'compra · alvo em 1:{rr:.1f}',
               rolante(lado='compra', rr_fixo=rr), meses)

    print(f"\n{'='*140}\n  A VENDA bate ENTRADA ALEATÓRIA?\n"
          f"  (20 vendas por operação real, mesma moeda, mesmo stop%,\n"
          f"   mesmo R:R, momento sorteado)\n{'='*140}")
    import random as _r
    from explosao import curva as _curva
    rng = _r.Random(11)
    reais = rolante(lado='venda')
    ctrl = []
    for s_ in {o['sim'] for o in reais}:
        hp = rev.juntar(serie[s_], rev.CFG['tf_h'])
        lo_i, hi_i = 30, len(hp) - rev.MAX_BARRAS - 1
        if hi_i <= lo_i:
            continue
        for o in [x for x in reais if x['sim'] == s_]:
            for _ in range(20):
                i = rng.randrange(lo_i, hi_i)
                ent = hp[i][4]
                stop = ent * (1 + o['stop_pct']/100)
                alvo = ent - (stop-ent)*o['rr']
                fim = saida = None
                for m in range(i+1, min(i+1+rev.MAX_BARRAS, len(hp))):
                    if hp[m][2] >= stop: fim, saida = 's', stop; break
                    if hp[m][3] <= alvo: fim, saida = 'a', alvo; break
                if fim is None:
                    continue
                pos = RISCO/((stop-ent)/ent)
                mov = (ent-saida)/ent
                ctrl.append(pos*mov - pos*TAXA*2 -
                            pos*((m-i)*rev.CFG['tf_h']/8)*FUND8)
    def _res(rot, v):
        if not v:
            print(f"  {rot:<34}{'—':>6}"); return
        g = [x for x in v if x > 0]
        tot, dd = _curva(v)
        print(f"  {rot:<34}{len(v):>6}{len(g)/len(v)*100:>9.1f}%"
              f"{statistics.mean(v):>+10.1f}{tot:>+10.0f}{dd:>9.0f}")
    print(f"  {'':<34}{'n':>6}{'acerto':>10}{'méd/op':>10}{'total':>10}"
          f"{'rebaix.':>9}")
    _res('a VENDA do setup', [o['liq'] for o in reais])
    _res('o CONTROLE (venda aleatória)', ctrl)
    if reais and ctrl:
        rv = [o['liq'] for o in reais]
        d = statistics.mean(rv) - statistics.mean(ctrl)
        e = (statistics.pvariance(rv)/len(rv) +
             statistics.pvariance(ctrl)/len(ctrl)) ** .5
        print(f"\n  diferença: {d:+.1f} por operação  →  "
              f"{d/e if e else 0:+.2f} desvios")


if __name__ == '__main__':
    main()
