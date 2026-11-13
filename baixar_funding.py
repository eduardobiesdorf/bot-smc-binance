"""Baixa o historico de TAXA DE FUNDING de todos os pares, do CDN.

A API de futuros devolve 451 nos runners do GitHub, mas o CDN de
arquivos passa. Cada linha do arquivo e

    [timestamp_ms, intervalo_em_horas, taxa]

A segunda coluna diz o CICLO do par naquele momento -- 8 na maioria,
mas 4 (e as vezes 1) nos mais volateis. E isso que permite testar a
ideia: num par de ciclo de 4h, a vela de 4h e a unidade natural, e sao
6 observacoes por dia em vez de 3.

Uso:  python3 baixar_funding.py --pasta dados_funding [--inicio 2020-01]
"""
import argparse
import csv
import io
import os
import sys
import zipfile
import datetime as dt
from concurrent.futures import ThreadPoolExecutor

import requests

BASE = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
LISTA = ("https://data.binance.vision/?prefix=data/futures/um/monthly/"
         "fundingRate/")


def meses(ini):
    a, m = [int(x) for x in ini.split('-')]
    hoje = dt.date.today()
    out = []
    while (a, m) <= (hoje.year, hoje.month):
        out.append(f"{a:04d}-{m:02d}")
        m += 1
        if m > 12:
            a, m = a + 1, 1
    return out


def um_par(sim, ms, pasta):
    linhas = []
    for mes in ms:
        u = f"{BASE}/{sim}/{sim}-fundingRate-{mes}.zip"
        try:
            r = requests.get(u, timeout=40)
            if r.status_code != 200:
                continue
            z = zipfile.ZipFile(io.BytesIO(r.content))
            with z.open(z.namelist()[0]) as f:
                for row in csv.reader(io.TextIOWrapper(f, 'utf-8')):
                    if row and row[0].isdigit():
                        linhas.append(row[:3])
        except Exception:
            continue
    if not linhas:
        return sim, 0
    linhas.sort(key=lambda r: int(r[0]))
    with open(os.path.join(pasta, f"{sim}_funding.csv"), 'w', newline='',
              encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['tempo_ms', 'intervalo_h', 'taxa'])
        w.writerows(linhas)
    return sim, len(linhas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pasta', default='dados_funding')
    ap.add_argument('--inicio', default='2020-01')
    ap.add_argument('--pares', default='',
                    help='lista separada por vírgula; vazio = usa os '
                         'nomes da pasta de klines em --klines')
    ap.add_argument('--klines', default='dados_universo')
    a = ap.parse_args()
    os.makedirs(a.pasta, exist_ok=True)
    if a.pares.strip():
        pares = [x.strip().upper() for x in a.pares.split(',') if x.strip()]
    else:
        import glob
        pares = sorted(os.path.basename(p).replace('_1h.csv', '')
                       for p in glob.glob(os.path.join(a.klines, '*_1h.csv')))
    ms = meses(a.inicio)
    print(f"{len(pares)} pares · {len(ms)} meses · {a.inicio} em diante",
          flush=True)
    n_ok = n_vazio = 0
    with ThreadPoolExecutor(max_workers=int(os.environ.get('THREADS', 12))) as ex:
        for k, (sim, n) in enumerate(ex.map(lambda s: um_par(s, ms, a.pasta),
                                            pares), 1):
            if n:
                n_ok += 1
            else:
                n_vazio += 1
            if k % 50 == 0:
                print(f"  {k}/{len(pares)} · {n_ok} com dado", flush=True)
    print(f"\n{n_ok} pares com funding, {n_vazio} sem")

    # o retrato dos ciclos
    import glob
    from collections import Counter
    c_final, c_mudou = Counter(), 0
    for p in glob.glob(os.path.join(a.pasta, '*_funding.csv')):
        with open(p) as f:
            rows = [r for r in csv.DictReader(f)]
        if not rows:
            continue
        vis = {r['intervalo_h'] for r in rows}
        c_final[rows[-1]['intervalo_h']] += 1
        if len(vis) > 1:
            c_mudou += 1
    print(f"\nCICLO DE FUNDING, pelo último registro de cada par:")
    for iv, n in sorted(c_final.items(), key=lambda x: -x[1]):
        print(f"  {iv}h: {n} pares")
    print(f"  {c_mudou} pares mudaram de ciclo em algum momento")


if __name__ == '__main__':
    main()
