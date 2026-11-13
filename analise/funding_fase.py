"""O H8 funciona por causa do FUNDING, ou so por durar 8 horas?

O setup funciona em H8 (+39,60/op nas 150) e nao funciona nos vizinhos
-- H4 da -16,50 e H2 da +5,00, com o BRUTO ja negativo no H4. Vantagem
robusta nao desaparece de um degrau para o outro. Isso e a bandeira
amarela do setup e nunca teve explicacao.

A unica explicacao mecanica disponivel: na Binance o funding e cobrado
a cada 8 horas, as 00:00, 08:00 e 16:00 UTC -- exatamente onde as velas
de 8h fecham. Se a vantagem vem dai, ela e do ALINHAMENTO, nao da
duracao.

O teste separa as duas coisas: monta velas de 8 horas DESLOCADAS,
comecando 1, 2, ... 7 horas depois. Mesma duracao, mesmas regras,
mesmo dado -- so muda a fase da grade. O deslocamento 0 e o unico
alinhado ao funding; os outros sete tem um funding no MEIO da vela.

  so o 0 funciona      -> e o funding, e a descontinuidade tem causa
  os 8 funcionam igual -> e a duracao, a hipotese morre, o efeito fica
  baguncado            -> o H8 pode ser sorte

Uso:  python3 funding_fase.py <pasta>
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

PASSO = 8 * 3600_000


def juntar_off(h, off_h):
    """Velas de 8h com a grade deslocada off_h horas.
    off_h=0 alinha com o funding (00:00, 08:00, 16:00 UTC)."""
    d = off_h * 3600_000
    out, bloco, chave = [], None, None
    for v in h:
        c = (v[0] - d) // PASSO
        if c != chave:
            if bloco:
                out.append(tuple(bloco))
            bloco = [c*PASSO + d, v[1], v[2], v[3], v[4], v[5]]
            chave = c
        else:
            bloco[2] = max(bloco[2], v[2])
            bloco[3] = min(bloco[3], v[3])
            bloco[4] = v[4]
            bloco[5] += v[5]
    if bloco:
        out.append(tuple(bloco))
    # descarta o primeiro bloco se veio pela metade
    if out and h and h[0][0] != out[0][0]:
        out = out[1:]
    return out


def ops_off(h1, sim, off):
    cfg = dict(rev.CFG)
    cfg['alvo_proj'] = 0.0
    cfg['alvo_rr'] = None
    cfg['so_compra'] = False
    hp = juntar_off(h1, off)
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
        horas = (m-i)*8
        mov = (saida-g['entrada'])/g['entrada']*(1 if compra else -1)
        pos = RISCO/(risco/g['entrada'])
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        out.append(dict(sim=sim, ms=g['vela_ms'], q=q, fim=fim, rr=g['rr'],
                        stop_pct=g['risco_pct'], bruto=pos*mov,
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return out


def painel(rot, ops, meses, larg=30):
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


def cab(larg=30):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>8}{'R:R':>6}"
          f"{'bruto':>9}{'líq/op':>9}{'total':>9}{'z/op':>7}{'lotes':>6}"
          f"{'pos':>5}{'z/LOTE':>8}")


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

    def rolante(off, n):
        ops = []
        for t, jan in janelas:
            for s in jan[:n]:
                k = (s, off)
                if k not in cache:
                    cache[k] = ops_off(serie[s], s, off)
                for o in cache[k]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"{len(serie)} pares · {meses:.0f} meses · velas de 8 HORAS com a "
          f"grade deslocada\n")
    print(f"  deslocamento 0 = velas fechando às 00:00, 08:00 e 16:00 UTC,")
    print(f"  que é exatamente quando a Binance cobra o funding.")
    print(f"  Os outros sete têm um funding no MEIO da vela.\n")
    res = {}
    for n in (50, 150):
        print(f"{'='*128}\n  AS {n} MAIORES\n{'='*128}")
        cab()
        for off in range(8):
            ops = rolante(off, n)
            rot = (f"desloc. {off}h" +
                   ("  ← o funding / o de hoje" if off == 0 else ""))
            painel(rot, ops, meses)
            if ops:
                res.setdefault(n, []).append(
                    (off, statistics.mean(o['liq'] for o in ops)))
        print()

    print(f"{'='*128}\n  O VEREDITO\n{'='*128}")
    for n, v in res.items():
        zero = dict(v)[0]
        outros = [x for o, x in v if o != 0]
        m = statistics.mean(outros)
        dp = statistics.pstdev(outros) or 1e-9
        print(f"  as {n} maiores: alinhado {zero:+.1f} · "
              f"os 7 deslocados {m:+.1f} (desvio {dp:.1f}) · "
              f"positivos: {sum(1 for x in outros if x > 0)}/7")
        print(f"    o alinhado está a {(zero-m)/dp:+.2f} desvios dos outros")


if __name__ == '__main__':
    main()
