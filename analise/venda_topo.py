"""A VENDA com o alvo no FUNDO da vela de explosao.

A venda foi desligada em 13/11 porque perdeu para a entrada aleatoria
(-0,29 desvios). Mas aquilo foi medido com a projecao de 90% -- e
depois a gente descobriu que o alvo projetado distorce tudo: ele so
paga quando o mercado rasga, concentra o lucro num lote e derruba a
significancia. O alvo que mede melhor e o EXTREMO da vela de explosao,
sem projecao nenhuma.

Entao a venda foi julgada pelo alvo errado. Aqui ela e remedida:

  1. a venda com cada alvo, por operacao e por LOTE, ano a ano
  2. a venda contra ENTRADA ALEATORIA, por lote, com o alvo certo
  3. os dois lados juntos, para ver se a venda soma ou dilui

Uso:  python3 venda_topo.py <pasta> [--n 150] [--k 200]
"""
import argparse, glob, os, random, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8
from explosao import ler, RISCO, TAXA, FUND8
from lista_operacoes import vol, TRI, BRT
from alvo_lote import z_de


def ops_lado(h1, sim, lado, proj=None, rr_fixo=None):
    cfg = dict(rev.CFG)
    cfg['alvo_rr'] = None
    cfg['so_compra'] = False
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
        if lado == 'compra' and not e['alta']:
            continue
        if lado == 'venda' and e['alta']:
            continue
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
        out.append(dict(sim=sim, ms=g['vela_ms'], q=q, fim=fim, lado=g['lado'],
                        rr=dist/risco, stop_pct=g['risco_pct'],
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return out


def lotes_de(ops, dias=14):
    if not ops:
        return []
    L, at = [], [ops[0]]
    for o in ops[1:]:
        if (o['q'] - at[-1]['q']).days <= dias:
            at.append(o)
        else:
            L.append(at); at = [o]
    L.append(at)
    return L


def painel(rot, ops, larg=26):
    if not ops:
        print(f"{rot:<{larg}}{'—':>5}"); return
    v = [o['liq'] for o in ops]
    g = [o for o in ops if o['fim'] == 'alvo']
    L = lotes_de(ops)
    lv = [sum(y['liq'] for y in x) for x in L]
    tot = sum(v)
    print(f"{rot:<{larg}}{len(ops):>4}{len(g)/len(ops)*100:>7.1f}%"
          f"{statistics.mean(o['rr'] for o in ops):>6.2f}"
          f"{statistics.mean(v):>+9.1f}{z_de(v):>+8.2f}"
          f"{len(L):>7}{sum(1 for x in lv if x>0):>5}"
          f"{statistics.mean(lv):>+8.0f}{z_de(lv):>+8.2f}"
          f"{max(lv)/tot*100 if tot>0 else 0:>7.0f}%")


def cab(larg=26):
    print(f"{'':<{larg}}{'n':>4}{'acerto':>8}{'R:R':>6}{'líq/op':>9}"
          f"{'z/op':>8}{'lotes':>7}{'pos':>5}{'méd':>8}{'z/LOTE':>8}"
          f"{'maior':>8}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pasta')
    ap.add_argument('--n', type=int, default=150)
    ap.add_argument('--k', type=int, default=200)
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
                                  key=lambda s: -vol(serie[s], t-TRI, t))))
        t += TRI
    cache = {}

    def rolante(lado, **kw):
        ops = []
        for t, jan in janelas:
            for s in jan[:a.n]:
                k = (s, lado, kw.get('proj'), kw.get('rr_fixo'))
                if k not in cache:
                    cache[k] = ops_lado(serie[s], s, lado, **kw)
                for o in cache[k]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"universo rolante de {a.n} · "
          f"{(t1-t0)/(1000*3600*24*30.4):.0f} meses\n")
    print(f"{'='*118}\n  0) O TAMANHO DO UNIVERSO, com a config de hoje\n"
          f"     (o alvo no extremo da vela escala com a moeda; o "
          f"projetado não escalava)\n{'='*118}")

    def rolante_n(n, lado=None):
        """universo rolante de n moedas"""
        ops = []
        for t, jan in janelas:
            for s in jan[:n]:
                for ld in (['compra', 'venda'] if lado is None else [lado]):
                    k = (s, ld, 0.0, None)
                    if k not in cache:
                        cache[k] = ops_lado(serie[s], s, ld, proj=0.0)
                    for o in cache[k]:
                        if t <= o['ms'] < t + TRI:
                            ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    cab()
    for n in (20, 50, 150, 300, 9999):
        ops = rolante_n(n)
        rot = (f'as {n} maiores' if n < 9999 else 'TODAS as moedas')
        painel(rot + ('  ← hoje' if n == 150 else ''), ops)
    print()
    print("  e por ano, quantas operações o universo inteiro daria:")
    ops = rolante_n(9999)
    for y in range(2020, 2027):
        sel = [o for o in ops if o['q'].year == y]
        if not sel:
            continue
        al = sum(1 for o in sel if o['fim'] == 'alvo')
        print(f"    {y}: {len(sel):>3} operações ({len(sel)/12:.1f}/mês)  "
              f"{al/len(sel)*100:>4.0f}% de acerto  "
              f"{sum(o['liq'] for o in sel):>+8.0f}")
    print()

    print(f"{'='*118}\n  1) A VENDA COM CADA ALVO\n{'='*118}")
    cab()
    painel('a COMPRA, p/ comparar', rolante('compra', proj=0.0))
    print()
    for rot, kw in (('venda · o FUNDO da vela', dict(proj=0.0)),
                    ('venda · projeção 45%',   dict(proj=0.45)),
                    ('venda · projeção 90%',   dict(proj=0.90)),
                    ('venda · 1:2 de risco',   dict(rr_fixo=2.0)),
                    ('venda · 1:3 de risco',   dict(rr_fixo=3.0))):
        painel(rot, rolante('venda', **kw))

    print(f"\n{'='*118}\n  2) ANO A ANO\n{'='*118}")
    print(f"{'':<26}" + ''.join(f"{y:>13}" for y in range(2020, 2027)))
    for rot, lado, kw in (('compra · o topo', 'compra', dict(proj=0.0)),
                          ('venda · o fundo', 'venda', dict(proj=0.0)),
                          ('venda · projeção 45%', 'venda', dict(proj=0.45))):
        ops = rolante(lado, **kw)
        linha = f"{rot:<26}"
        for y in range(2020, 2027):
            sel = [o for o in ops if o['q'].year == y]
            if not sel:
                linha += f"{'—':>13}"; continue
            al = sum(1 for o in sel if o['fim'] == 'alvo')
            linha += f"{sum(o['liq'] for o in sel):>+8.0f}({al}/{len(sel)})"[-13:].rjust(13)
        print(linha)

    print(f"\n{'='*118}\n  3) OS DOIS LADOS JUNTOS\n{'='*118}")
    cab()
    comp = rolante('compra', proj=0.0)
    painel('só compra (hoje)', comp)
    for rot, kw in (('+ venda no fundo', dict(proj=0.0)),
                    ('+ venda projeção 45%', dict(proj=0.45)),
                    ('+ venda 1:2', dict(rr_fixo=2.0))):
        painel(rot, sorted(comp + rolante('venda', **kw),
                           key=lambda o: o['q']))

    print(f"\n{'='*118}\n  4) A VENDA BATE ENTRADA ALEATÓRIA, POR LOTE?\n"
          f"     (alvo no fundo da vela, 200 instantes sorteados por lote)\n"
          f"{'='*118}")
    h8 = {}
    rng = random.Random(31)
    for lado, kw, rot in (('venda', dict(proj=0.0), 'a VENDA'),
                          ('compra', dict(proj=0.0), 'a COMPRA')):
        ops = rolante(lado, **kw)
        if not ops:
            continue
        for o in ops:
            if o['sim'] not in h8:
                h8[o['sim']] = rev.juntar(serie[o['sim']], rev.CFG['tf_h'])
        L = lotes_de(ops)
        reais = [sum(y['liq'] for y in x) for x in L]
        sort = []
        compra = lado == 'compra'
        for x in L:
            for _ in range(a.k):
                s_, ok = 0.0, 0
                for o in x:
                    hp = h8[o['sim']]
                    lo_i, hi_i = 30, len(hp) - rev.MAX_BARRAS - 1
                    if hi_i <= lo_i:
                        continue
                    i = rng.randrange(lo_i, hi_i)
                    ent = hp[i][4]
                    stop = ent*(1 + (-1 if compra else 1)*o['stop_pct']/100)
                    alvo = ent + (ent-stop)*o['rr'] if compra else \
                           ent - (stop-ent)*o['rr']
                    fim = saida = None
                    for m in range(i+1, min(i+1+rev.MAX_BARRAS, len(hp))):
                        hi, lo = hp[m][2], hp[m][3]
                        if compra:
                            if lo <= stop: fim, saida = 1, stop; break
                            if hi >= alvo: fim, saida = 1, alvo; break
                        else:
                            if hi >= stop: fim, saida = 1, stop; break
                            if lo <= alvo: fim, saida = 1, alvo; break
                    if fim is None:
                        continue
                    pos = RISCO/(o['stop_pct']/100)
                    mov = (saida-ent)/ent*(1 if compra else -1)
                    s_ += pos*mov - pos*TAXA*2 - \
                        pos*((m-i)*rev.CFG['tf_h']/8)*FUND8
                    ok += 1
                if ok:
                    sort.append(s_*len(x)/ok)
        mr, ms_ = statistics.mean(reais), statistics.mean(sort)
        er = statistics.pstdev(reais)/len(reais)**.5
        es = statistics.pstdev(sort)/len(sort)**.5
        d = mr - ms_; e = (er**2 + es**2) ** .5
        print(f"  {rot}:  lote real {mr:>+7.0f} ±{er:<5.0f}"
              f"({sum(1 for x in reais if x>0)}/{len(reais)} positivos)   "
              f"lote sorteado {ms_:>+7.0f}   "
              f"diferença {d:>+7.0f} ±{e:<5.0f} →  {d/e if e else 0:+.2f} DESVIOS")


if __name__ == '__main__':
    main()
