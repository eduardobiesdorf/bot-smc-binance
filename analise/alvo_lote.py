"""Qual alvo da mais SIGNIFICANCIA, nao qual da mais dinheiro.

Observacao do Eduardo: o alvo fixo de 5x o risco so paga quando o
movimento e gigante, e movimento gigante nao acontece espacado --
acontece quando o mercado inteiro rasga, em todas as moedas de uma vez.
Entao o proprio alvo de 1:5 pode ser o que CRIA o aglomerado. O alvo
projetado (ou o topo da explosao) acompanha o tamanho da vela: perto
onde explodiu pouco, longe onde explodiu muito -- e isso espalha os
acertos no tempo em vez de junta-los no mesmo mes.

Eu escolhi o 1:5 comparando dinheiro POR OPERACAO, num conjunto onde as
operacoes nao sao independentes. Criterio errado. Este script compara
cada alvo nos dois eixos:

  por operacao   dinheiro e z, como eu media antes
  por LOTE       dinheiro, z, quantos lotes positivos, e a concentracao
                 (quanto o maior lote vale do total)
  espalhamento   em quantos meses distintos caiu um acerto

Uso:  python3 alvo_lote.py <pasta> [--n 150]
"""
import argparse, glob, os, random, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler, curva, RISCO, TAXA, FUND8
from lista_operacoes import vol, TRI, BRT


def ops_alvo(h1, sim, proj=None, rr_fixo=None):
    """proj: projecao do tamanho da vela (0.0 = o topo exato).
    rr_fixo: multiplo de risco. Um dos dois."""
    cfg = dict(rev.CFG)
    cfg['alvo_rr'] = None
    if proj is not None:
        cfg['alvo_proj'] = proj
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
        horas = (m-i)*cfg['tf_h']
        mov = (saida-g['entrada'])/g['entrada']*(1 if compra else -1)
        pos = RISCO/(risco/g['entrada'])
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        out.append(dict(sim=sim, ms=g['vela_ms'], q=q, fim=fim,
                        rr=dist/risco, dias=horas/24,
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return out


def z_de(v, sem=4000):
    if len(v) < 8:
        return 0.0
    random.seed(5)
    nu = [statistics.mean([x if random.random() < .5 else -x for x in v])
          for _ in range(sem)]
    return (statistics.mean(v)-statistics.mean(nu))/(statistics.pstdev(nu) or 1e-9)


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
    janelas = []
    t = t0 + TRI
    while t < t1:
        janelas.append((t, sorted(serie,
                                  key=lambda s: -vol(serie[s], t-TRI, t))[:a.n]))
        t += TRI

    def rolante(**kw):
        cache, ops = {}, []
        for t, jan in janelas:
            for s in jan:
                if s not in cache:
                    cache[s] = ops_alvo(serie[s], s, **kw)
                for o in cache[s]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"universo rolante de {a.n} · só compra · "
          f"{(t1-t0)/(1000*3600*24*30.4):.0f} meses\n")
    print(f"{'alvo':<22}{'n':>4}{'acerto':>8}{'R:R':>6}"
          f"{'  POR OPERAÇÃO':>16}{'':>6}"
          f"{'      POR LOTE (14 dias)':>26}{'':>8}{'maior':>7}{'meses':>7}")
    print(f"{'':<22}{'':>4}{'':>8}{'':>6}{'líq/op':>10}{'z':>12}"
          f"{'lotes':>8}{'pos':>6}{'méd':>8}{'z':>8}{'lote':>9}{'c/ acerto':>9}")

    VAR = [('o topo da explosão', dict(proj=0.0)),
           ('projeção 45%',       dict(proj=0.45)),
           ('projeção 90%',       dict(proj=0.90)),
           ('projeção 150%',      dict(proj=1.50)),
           ('1:2 de risco',       dict(rr_fixo=2.0)),
           ('1:3 de risco',       dict(rr_fixo=3.0)),
           ('1:4 de risco',       dict(rr_fixo=4.0)),
           ('1:5 de risco (hoje)', dict(rr_fixo=5.0)),
           ('1:6 de risco',       dict(rr_fixo=6.0))]
    for rot, kw in VAR:
        ops = rolante(**kw)
        if not ops:
            print(f"{rot:<22}{'—':>4}"); continue
        v = [o['liq'] for o in ops]
        g = [o for o in ops if o['fim'] == 'alvo']
        tot = sum(v)
        # lotes de 14 dias
        lotes, at = [], [ops[0]]
        for o in ops[1:]:
            if (o['q'] - at[-1]['q']).days <= 14:
                at.append(o)
            else:
                lotes.append(at); at = [o]
        lotes.append(at)
        lv = [sum(y['liq'] for y in L) for L in lotes]
        maior = max(lv)/tot*100 if tot else 0
        meses = len({o['q'].strftime('%Y-%m') for o in g})
        print(f"{rot:<22}{len(ops):>4}{len(g)/len(ops)*100:>7.1f}%"
              f"{statistics.mean(o['rr'] for o in ops):>6.2f}"
              f"{statistics.mean(v):>+10.1f}{z_de(v):>+12.2f}"
              f"{len(lotes):>8}{sum(1 for x in lv if x>0):>6}"
              f"{statistics.mean(lv):>+8.0f}{z_de(lv):>+8.2f}"
              f"{maior:>8.0f}%{meses:>7}")
    print(f"\n  'maior lote' = quanto do lucro total vem do melhor lote."
          f"\n  'meses c/ acerto' = em quantos meses distintos caiu um alvo."
          f"\n  O que decide e o z POR LOTE, nao o por operação.")


if __name__ == '__main__':
    main()
