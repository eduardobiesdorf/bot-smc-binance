"""Setup 1 (varredura do order block): o que valeria a pena mudar.

O setup esta com dinheiro e mede -1,00 por operacao no universo
rolante. Antes de desligar, testa as tres alavancas GRANDES que nunca
foram puxadas -- nao ajuste de parametro:

  A. TEMPO GRAFICO. O setup so rodou em H1. A reversao de 8h mostrou
     que o comportamento vive na escala de 8 horas (H8 funciona, 12h
     e 5min nao). Roda a varredura em H1, H2, H4 e H8.

  B. PROFUNDIDADE DO FURO medida contra o TAMANHO DO BLOCO, nao em
     ATR. No setup 3 o filtro decisivo foi "o recuo nao pode passar do
     MEIO do order block" -- profundidade relativa ao proprio bloco.
     Aqui o furo_max esta em 2,5 ATR, que quase nao filtra. Mede o furo
     como fracao da altura do bloco: 0,25x, 0,5x, 1x, 2x.

  C. OS OITO FILTROS. Volume na varredura, piscina de liquidez, R:R
     minimo, espera... todos calibrados em 2026. Mede a versao PELADA
     contra a filtrada no universo honesto. Se empatar, os filtros sao
     decoracao.

Tudo no universo ROLANTE, 7 anos, contado por OPERACAO e por LOTE.

Uso:  python3 setup1_fundo.py <pasta> [--n 150]
"""
import argparse, glob, os, statistics, sys
import datetime as dt
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bot_varredura as bot
import reversao8 as rev
from explosao import ler, RISCO, TAXA, FUND8
from lista_operacoes import vol, TRI, BRT
from alvo_lote import z_de
from venda_topo import lotes_de

MAXBAR = 120


def ops_setup1(h1, sim, tf=1, cfg_extra=None, furo_ob=None):
    """tf: horas da vela. furo_ob: furo maximo como fracao da altura do
    order block (substitui o furo_max em ATR)."""
    cfg = dict(bot.CFG)
    if cfg_extra:
        cfg.update(cfg_extra)
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
        # o extremo da varredura, reconstruido do stop
        ext = g['stop'] + a[k]*cfg['stop_folga'] if compra else \
              g['stop'] - a[k]*cfg['stop_folga']
        alt = imp['ob_topo'] - imp['ob_base']
        if furo_ob is not None and alt > 0:
            fundura = ((imp['ob_base'] - ext) if compra else
                       (ext - imp['ob_topo'])) / alt
            if fundura > furo_ob:
                continue
        risco = abs(g['entrada'] - g['stop'])
        if risco <= 0:
            continue
        fim = saida = None
        for m in range(k+1, min(k+1+MAXBAR, len(h))):
            hi, lo = h[m][2], h[m][3]
            if compra:
                if lo <= g['stop']: fim, saida = 'stop', g['stop']; break
                if hi >= g['alvo']: fim, saida = 'alvo', g['alvo']; break
            else:
                if hi >= g['stop']: fim, saida = 'stop', g['stop']; break
                if lo <= g['alvo']: fim, saida = 'alvo', g['alvo']; break
        if fim is None:
            continue
        horas = (m-k)*tf
        mov = (saida-g['entrada'])/g['entrada']*(1 if compra else -1)
        pos = RISCO/(risco/g['entrada'])
        q = dt.datetime.fromtimestamp(g['vela_ms']/1000, BRT)
        out.append(dict(sim=sim, ms=g['vela_ms'], q=q, fim=fim,
                        rr=g['rr'], stop_pct=g['risco_pct'],
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
    anos = sorted({o['q'].year for o in ops})
    bons = sum(1 for y in anos
               if statistics.mean([o['liq'] for o in ops if o['q'].year == y]) > 0)
    print(f"{rot:<{larg}}{len(ops):>5}{len(ops)/meses:>6.1f}"
          f"{len(g)/len(ops)*100:>7.1f}%"
          f"{statistics.mean(o['rr'] for o in ops):>6.2f}"
          f"{statistics.mean(v):>+9.1f}{tot:>+9.0f}{z_de(v):>+8.2f}"
          f"{len(L):>6}{sum(1 for x in lv if x>0):>5}{z_de(lv):>+8.2f}"
          f"{max(lv)/tot*100 if tot>0 else 0:>7.0f}%{bons}/{len(anos)}")


def cab(larg=30):
    print(f"{'':<{larg}}{'n':>5}{'/mês':>6}{'acerto':>8}{'R:R':>6}"
          f"{'líq/op':>9}{'total':>9}{'z/op':>8}{'lotes':>6}{'pos':>5}"
          f"{'z/LOTE':>8}{'maior':>8}{'anos+':>6}")


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

    def rolante(**kw):
        ch = tuple(sorted((k, str(v)) for k, v in kw.items()))
        ops = []
        for t, jan in janelas:
            for s in jan:
                key = (s, ch)
                if key not in cache:
                    cache[key] = ops_setup1(serie[s], s, **kw)
                for o in cache[key]:
                    if t <= o['ms'] < t + TRI:
                        ops.append(o)
        return sorted(ops, key=lambda o: o['q'])

    print(f"universo rolante de {a.n} · {meses:.0f} meses · setup 1\n")

    print(f"{'='*134}\n  A) O TEMPO GRÁFICO — nunca saiu do H1\n{'='*134}")
    cab()
    for tf in (1, 2, 4, 8):
        painel(f'H{tf}' + ('  ← hoje' if tf == 1 else ''),
               rolante(tf=tf), meses)

    print(f"\n{'='*134}\n  B) PROFUNDIDADE DO FURO, medida no TAMANHO DO BLOCO\n"
          f"     (hoje o limite é 2,5 ATR, que quase não filtra)\n{'='*134}")
    cab()
    for tf in (1, 4):
        painel(f'H{tf} · sem o filtro novo', rolante(tf=tf), meses)
        for f in (0.25, 0.5, 1.0, 2.0):
            painel(f'H{tf} · furo <= {f:.2f}x o bloco',
                   rolante(tf=tf, furo_ob=f), meses)
        print()

    print(f"{'='*134}\n  C) OS OITO FILTROS valem o que custam?\n{'='*134}")
    cab()
    painel('tudo ligado (hoje)', rolante(tf=1), meses)
    for rot, ex in (
            ('sem volume na varredura', dict(vol_varr_min=0.0)),
            ('sem piscina de liquidez', dict(liq_max_r=9e9)),
            ('sem R:R mínimo',          dict(rr_min=0.0)),
            ('sem limite de furo',      dict(furo_max=9e9)),
            ('espera do gatilho 8',     dict(max_espera_gatilho=8)),
            ('PELADO (os quatro off)',  dict(vol_varr_min=0.0, liq_max_r=9e9,
                                             rr_min=0.0, furo_max=9e9))):
        painel(rot, rolante(tf=1, cfg_extra=ex), meses)


if __name__ == '__main__':
    main()
