"""A HORA da entrada importa? O funding como criterio, nao como grade.

Ja se sabe que a grade de 8h tem de TERMINAR na cobranca do funding
(deslocar mede +3,23 desvios pior) e que o ciclo INTEIRO e a unidade
(encurtar a janela da menos entradas e piores).

Falta a pergunta do Eduardo, que testa o mecanismo sem mexer na grade:
a HORA em que a entrada acontece importa?

  A. o setup de hoje (padrao em H8), com o gatilho de 1h filtrado pela
     distancia ate a cobranca. Hoje o gatilho pode cair em qualquer uma
     das 48 horas apos o encosto.
  B. o padrao inteiro em H1 -- que mede -5,90/op solto -- com a
     proximidade do funding como criterio de entrada.

Distancia 0 = a vela de 1h FECHA na cobranca (07:00-08:00, 15:00-16:00,
23:00-00:00 UTC). Distancia 4 = o mais longe possivel.

Sonda tambem se os arquivos de taxa de funding do CDN sao alcancaveis.

Uso:  python3 hora_funding.py <pasta>
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


def dist_funding(ms_abertura):
    """Horas entre o FECHAMENTO da vela de 1h e a cobranca anterior.
    0 = a vela fecha exatamente na cobranca."""
    fech = ms_abertura + H
    return (fech % CICLO) // H


def ops_tf(h1, sim, tf):
    """O padrao em tf horas, gatilho no H1. tf=8 e o setup de hoje."""
    cfg = dict(rev.CFG)
    cfg['tf_h'] = tf
    cfg['alvo_proj'] = 0.0
    cfg['alvo_rr'] = None
    cfg['so_compra'] = False
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
                        d=dist_funding(g['vela_ms']),
                        stop_pct=g['risco_pct'], bruto=pos*mov,
                        liq=pos*mov - pos*TAXA*2 - pos*(horas/8)*FUND8))
    return out


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
          f"{len(L):>6}{sum(1 for x in lv if x>0):>5}{z_de(lv):>+8.2f}")


def cab(larg=32):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>8}{'R:R':>6}"
          f"{'bruto':>9}{'líq/op':>9}{'total':>9}{'z/op':>7}{'lotes':>6}"
          f"{'pos':>5}{'z/LOTE':>8}")


def sonda_cdn():
    import requests
    print(f"\n{'='*132}\n  SONDA: os arquivos de TAXA DE FUNDING do CDN "
          f"são alcançáveis?\n{'='*132}")
    base = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
    for sim in ('BTCUSDT', 'DOGEUSDT'):
        u = f"{base}/{sim}/{sim}-fundingRate-2026-09.zip"
        try:
            r = requests.get(u, timeout=25)
            print(f"  {sim}: HTTP {r.status_code}  "
                  f"({len(r.content)} bytes)")
            if r.status_code == 200:
                import io, zipfile, csv as _csv
                z = zipfile.ZipFile(io.BytesIO(r.content))
                with z.open(z.namelist()[0]) as f:
                    linhas = list(_csv.reader(io.TextIOWrapper(f, 'utf-8')))
                ok = [l for l in linhas if l and l[0].isdigit()]
                print(f"    {len(ok)} cobranças no mês "
                      f"({len(ok)/30:.1f} por dia → ciclo de "
                      f"{24/(len(ok)/30):.0f}h)")
                if ok:
                    print(f"    exemplo: {ok[0]}")
        except Exception as e:
            print(f"  {sim}: falhou — {str(e)[:80]}")


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

    def rolante(tf, n):
        ops = []
        for t, jan in janelas:
            for s in jan[:n]:
                k = (s, tf)
                if k not in cache:
                    cache[k] = ops_tf(serie[s], s, tf)
                for o in cache[k]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"{len(serie)} pares · {meses:.0f} meses · distância 0 = a vela "
          f"de 1h do gatilho FECHA na cobrança\n")

    for tf, titulo in ((8, 'A) O SETUP DE HOJE (padrão em H8) — a hora do '
                           'gatilho importa?'),
                       (1, 'B) O PADRÃO INTEIRO EM H1 — o funding como '
                           'critério de entrada')):
        for n in (50, 150):
            ops = rolante(tf, n)
            print(f"{'='*132}\n  {titulo}   ·   as {n} maiores\n{'='*132}")
            cab()
            painel('todas as horas (como é hoje)', ops, meses)
            print()
            for d in range(8):
                painel(f'  gatilho a {d}h da cobrança'
                       + ('   ← fecha NA cobrança' if d == 0 else ''),
                       [o for o in ops if o['d'] == d], meses)
            print()
            for rot, sel in (
                    ('as 3 horas coladas (7,0,1)', (7, 0, 1)),
                    ('as 5 horas coladas (6,7,0,1,2)', (6, 7, 0, 1, 2)),
                    ('as longe da cobrança (3,4,5)', (3, 4, 5))):
                painel(rot, [o for o in ops if o['d'] in sel], meses)
            print()
    sonda_cdn()


if __name__ == '__main__':
    main()
