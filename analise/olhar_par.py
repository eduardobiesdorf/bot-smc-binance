"""O que o detector da reversao ve num par AGORA, ao vivo.

Busca as velas de 1h direto da API de FUTUROS (nao a de spot, que nao
tem todos os pares) e roda o detector em varios tempos graficos,
mostrando cada condicao separadamente -- para saber se o padrao armou,
em qual vela, e o que falta para virar entrada.

Uso:  python3 olhar_par.py AKEUSDT [--tf 8,4]
"""
import argparse, os, sys
import datetime as dt
import requests
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import reversao8 as rev
import explosao8 as e8

BRT = dt.timezone(dt.timedelta(hours=-3))
FONTES = [
    ("spot (data-api)", "https://data-api.binance.vision/api/v3/klines"),
    ("futuros (fapi)", "https://fapi.binance.com/fapi/v1/klines"),
]
CDN = "https://data.binance.vision/data/futures/um/daily/klines"


def _api(url, sim, limite):
    out, fim = [], None
    while len(out) < limite:
        p = {'symbol': sim, 'interval': '1h',
             'limit': min(1500, limite-len(out))}
        if fim:
            p['endTime'] = fim
        r = requests.get(url, params=p, timeout=25)
        r.raise_for_status()
        d = r.json()
        if not d:
            break
        out = [[int(c[0]), float(c[1]), float(c[2]), float(c[3]),
                float(c[4]), float(c[5])] for c in d] + out
        fim = d[0][0] - 1
        if len(d) < p['limit']:
            break
    return out


def _cdn(sim, dias):
    """os arquivos diarios do CDN de futuros -- vao ate ontem."""
    import io, zipfile, csv as _csv
    out = []
    hoje = dt.datetime.now(dt.timezone.utc).date()
    for k in range(dias, 0, -1):
        d = hoje - dt.timedelta(days=k)
        u = f"{CDN}/{sim}/1h/{sim}-1h-{d:%Y-%m-%d}.zip"
        try:
            r = requests.get(u, timeout=25)
            if r.status_code != 200:
                continue
            z = zipfile.ZipFile(io.BytesIO(r.content))
            with z.open(z.namelist()[0]) as f:
                for row in _csv.reader(io.TextIOWrapper(f, 'utf-8')):
                    if not row or not row[0].isdigit():
                        continue
                    out.append([int(row[0]), float(row[1]), float(row[2]),
                                float(row[3]), float(row[4]), float(row[5])])
        except Exception:
            continue
    return out


def buscar(sim, limite=1500):
    erros = []
    for nome, url in FONTES:
        try:
            out = _api(url, sim, limite)
            if out:
                print(f"  (dado de {nome})")
                break
        except Exception as e:
            erros.append(f"{nome}: {str(e)[:70]}")
            out = []
    else:
        out = []
    if not out:
        print("  (as APIs falharam: " + " · ".join(erros) + ")")
        print("  (caindo nos arquivos diários do CDN de futuros — vão até ontem)")
        out = _cdn(sim, 70)
    if not out:
        raise SystemExit(f"não consegui dado nenhum de {sim}")
    out.sort(key=lambda v: v[0])
    vis = {}
    for v in out:
        vis[v[0]] = v
    out = [vis[k] for k in sorted(vis)][-limite:]
    agora = int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
    return [v for v in out if v[0] + 3600_000 <= agora]


def q(ms):
    return dt.datetime.fromtimestamp(ms/1000, BRT).strftime('%d/%m %H:%M')


def olhar(sim, h1, tf):
    cfg = dict(rev.CFG)
    cfg['tf_h'] = tf
    hp = rev.juntar(h1, tf)
    print(f"\n{'='*78}\n  {sim} em H{tf} — {len(hp)} velas, a última fechou "
          f"{q(hp[-1][0])}\n{'='*78}")
    if len(hp) < 60:
        print("  série curta demais"); return
    a, mv = e8.atr(hp, 14), e8.medvol(hp, 20)
    i = len(hp) - 1
    # diagnostico da ultima vela
    o, hi, lo, cl, v = hp[i][1], hp[i][2], hp[i][3], hp[i][4], hp[i][5]
    rng = hi - lo
    print(f"  última vela: abriu {o:.8g} fechou {cl:.8g} "
          f"({'alta' if cl > o else 'baixa'})")
    if rng > 0 and a[i-1] > 0 and mv[i-1] > 0:
        print(f"    tamanho    {rng/a[i-1]:.2f}x a volatilidade   "
              f"(precisa >= {cfg['sigma']})  "
              f"{'OK' if rng >= cfg['sigma']*a[i-1] else 'NÃO'}")
        print(f"    corpo      {abs(cl-o)/rng*100:.0f}% da vela          "
              f"(precisa >= 50%)  "
              f"{'OK' if abs(cl-o)/rng >= .5 else 'NÃO'}")
        print(f"    volume     {v/mv[i-1]:.2f}x a média         "
              f"(precisa >= {cfg['vol']})  "
              f"{'OK' if v >= cfg['vol']*mv[i-1] else 'NÃO'}")
        jan = cfg['tend_jan']
        if i >= jan:
            alta = cl > o
            queda = (hp[i-jan][4]-hp[i-1][4])/a[i-1] if alta else \
                    (hp[i-1][4]-hp[i-jan][4])/a[i-1]
            print(f"    vinha {'caindo' if alta else 'subindo'}  "
                  f"{queda:.2f} volatilidades em {jan} velas "
                  f"({jan*tf}h)   (precisa >= {cfg['tend_atr']})  "
                  f"{'OK' if queda >= cfg['tend_atr'] else 'NÃO'}")
            faixa = hp[i-jan:i]
            tmax = max(x[2] for x in faixa); tmin = min(x[3] for x in faixa)
            if tmax > tmin:
                pos = (lo-tmin)/(tmax-tmin) if alta else (tmax-hi)/(tmax-tmin)
                print(f"    saiu a {pos*100:.0f}% do fundo da faixa      "
                      f"(precisa <= {cfg['perto_do_fundo']*100:.0f}%)  "
                      f"{'OK' if pos <= cfg['perto_do_fundo'] else 'NÃO'}")
            ta = rev.ultimo_topo(hp, i, alta, cfg)
            if ta is None:
                print(f"    último topo: não achou pivô")
            else:
                ok = (cl > ta) if alta else (cl < ta)
                print(f"    último topo em {ta:.8g}, fechou em {cl:.8g}   "
                      f"{'ROMPEU' if ok else 'não rompeu'}")

    ex = list(rev.explosoes(hp, cfg))
    if not ex:
        print("\n  nenhuma explosão armada na janela de espera.")
        return
    print(f"\n  {len(ex)} explosão(ões) armada(s) e ainda dentro dos "
          f"{cfg['espera']*tf/24:.0f} dias de espera:")
    mv1 = e8.medvol(h1, 20)
    pos1 = {x[0]: k for k, x in enumerate(h1)}
    for e in ex[:4]:
        d = (h1[-1][0] - e['exp_ms'])/86400_000
        borda = e['ob_topo'] if e['alta'] else e['ob_base']
        meio = (e['ob_base']+e['ob_topo'])/2
        agora = h1[-1][4]
        print(f"\n    explosão em {q(e['exp_ms'])} ({d:.1f} dias atrás) · "
              f"{'COMPRA' if e['alta'] else 'VENDA'}")
        print(f"      order block  {e['ob_base']:.8g} a {e['ob_topo']:.8g}")
        print(f"      a borda a tocar é {borda:.8g}; o meio (que mata) "
              f"é {meio:.8g}")
        print(f"      alvo = extremo da explosão = {e['topo']:.8g}")
        print(f"      preço agora {agora:.8g} — "
              f"{'JÁ TOCOU a borda' if ((agora <= borda) if e['alta'] else (agora >= borda)) else f'falta {abs(agora-borda)/agora*100:.1f}% até a borda'}")
        g = rev.encosto(h1, mv1, e, cfg, pos1)
        if g:
            print(f"      >>> ENCOSTADO: tocou {q(g['toque_ms'])}, "
                  f"faltam {g['falta']}h para o gatilho, "
                  f"stop {g['stop']:.8g}, R:R 1:{g['rr']:.2f}")
        ent = rev.entrada(h1, mv1, e, cfg, pos1)
        if ent:
            print(f"      >>> GATILHO em {q(ent['vela_ms'])}: "
                  f"entrada {ent['entrada']:.8g} stop {ent['stop']:.8g} "
                  f"alvo {ent['alvo']:.8g} R:R 1:{ent['rr']:.2f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('par')
    ap.add_argument('--tf', default='8,4')
    a = ap.parse_args()
    sim = a.par.upper()
    h1 = buscar(sim, 1500)
    print(f"{sim}: {len(h1)} velas de 1h, de {q(h1[0][0])} a {q(h1[-1][0])}")
    print(f"preço agora: {h1[-1][4]:.8g}")
    for tf in [int(x) for x in a.tf.split(',')]:
        olhar(sim, h1, tf)


if __name__ == '__main__':
    main()
