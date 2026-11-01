# -*- coding: utf-8 -*-
"""
Baixa o historico de USD-M Futures do repositorio publico da Binance.

Por que nao usar a API: fapi.binance.com recusa IP dos Estados Unidos, e
os runners do GitHub ficam la. Ja data.binance.vision e um CDN publico
sem bloqueio, com o mesmo dado em arquivos mensais.

    https://data.binance.vision/data/futures/um/monthly/klines/
        BTCUSDT/1h/BTCUSDT-1h-2025-01.zip

Uso:
    python baixar_futuros.py --inicio 2025-01 --intervalo 1h --top 60
"""
import argparse
import csv
import io
import os
import time
import pathlib
import zipfile
from datetime import datetime, timezone

import requests

CDN = "https://data.binance.vision/data/futures/um/monthly/klines"
CDN_DIA = "https://data.binance.vision/data/futures/um/daily/klines"
SPOT = "https://data-api.binance.vision/api/v3"
PASTA = "dados_fut"
DIAG = "diagnostico_futuros.txt"

FORA = {'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'USDP', 'AEUR', 'EURI',
        'EUR', 'XUSD', 'USD1', 'PYUSD', 'XAUT', 'PAXG', 'XAGT'}


def diag(linha):
    print(linha, flush=True)
    try:
        with open(DIAG, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def listar_cdn():
    """Todos os pares USDT com historico de futuros no CDN da Binance.

    data.binance.vision serve uma pagina HTML; o XML de listagem vem do
    bucket S3 por tras dela. Paginacao v1, por marker.
    """
    import re
    BUCKET = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
    PRE = "data/futures/um/monthly/klines/"
    pares, tok, volta = [], None, 0
    while volta < 60:
        volta += 1
        u = f"{BUCKET}?delimiter=/&prefix={PRE}"
        if tok:
            u += "&marker=" + tok
        r = requests.get(u, timeout=60)
        r.raise_for_status()
        achou = re.findall(r"<Prefix>" + re.escape(PRE) + r"([^/]+)/</Prefix>",
                           r.text)
        if not achou:
            diag(f"volta {volta}: nada. Inicio da resposta: {r.text[:300]}")
            break
        pares.extend(achou)
        if "<IsTruncated>true</IsTruncated>" not in r.text:
            break
        tok = PRE + achou[-1] + "/"
    usdt = sorted(set(x for x in pares if x.endswith('USDT')))
    perp = [x for x in usdt if '_' not in x]
    diag(f"pares no CDN de futuros USD-M: {len(set(pares))} no total, "
         f"{len(usdt)} terminando em USDT, {len(perp)} perpetuos "
         f"(sem contrato com vencimento)")
    diag("lista USDT perpetua:")
    for i in range(0, len(perp), 10):
        diag("  " + ", ".join(perp[i:i+10]))
    return perp


def candidatos(n):
    """A lista de candidatos vem do volume do SPOT, que e acessivel daqui.
    O ranking de verdade e refeito depois, com o volume dos futuros."""
    r = requests.get(f"{SPOT}/ticker/24hr", timeout=60)
    r.raise_for_status()
    cand = []
    for d in r.json():
        s = d.get('symbol', '')
        if not s.endswith('USDT'):
            continue
        base = s[:-4]
        if base in FORA:
            continue
        # acao tokenizada no spot: ticker + B. Nao existe em futuros.
        if 4 <= len(base) <= 6 and base.endswith('B') and base[:-1].isalpha():
            continue
        try:
            cand.append((float(d['quoteVolume']), s))
        except (KeyError, ValueError):
            continue
    cand.sort(reverse=True)
    return [s for _, s in cand[:n]]


def meses(ini, fim):
    a, m = int(ini[:4]), int(ini[5:7])
    fa, fm = int(fim[:4]), int(fim[5:7])
    out = []
    while (a, m) <= (fa, fm):
        out.append(f"{a:04d}-{m:02d}")
        m += 1
        if m > 12:
            a, m = a + 1, 1
    return out


def _ler_zip(r):
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        txt = z.read(z.namelist()[0]).decode('utf-8', 'ignore')
    linhas = []
    for row in csv.reader(io.StringIO(txt)):
        if not row or not row[0] or not row[0][0].isdigit():
            continue
        try:
            t = int(row[0])
            if t > 10 ** 14:
                t //= 1000
            linhas.append([t, float(row[1]), float(row[2]), float(row[3]),
                           float(row[4]), float(row[5])])
        except (ValueError, IndexError):
            continue
    return linhas


def baixar_dias(sim, iv, mes):
    """O mes corrente ainda nao tem arquivo mensal: junta os diarios."""
    from calendar import monthrange
    a, m = int(mes[:4]), int(mes[5:7])
    out = []
    for d in range(1, monthrange(a, m)[1] + 1):
        url = f"{CDN_DIA}/{sim}/{iv}/{sim}-{iv}-{mes}-{d:02d}.zip"
        try:
            r = requests.get(url, timeout=60)
        except Exception:
            continue
        if r.ok:
            out.extend(_ler_zip(r))
    return out or None


def baixar_mes(sim, iv, mes):
    url = f"{CDN}/{sim}/{iv}/{sim}-{iv}-{mes}.zip"
    for tent in range(3):
        try:
            r = requests.get(url, timeout=120)
        except Exception as e:
            time.sleep(2 + tent * 3)
            continue
        if r.status_code == 404:
            # pode ser o mes corrente, que so tem arquivo diario
            return baixar_dias(sim, iv, mes)
        if not r.ok:
            time.sleep(2 + tent * 3)
            continue
        return _ler_zip(r)
    return None


def main():
    global PASTA
    ap = argparse.ArgumentParser()
    ap.add_argument('--inicio', default='2025-01')
    ap.add_argument('--fim', default=datetime.now(timezone.utc).strftime('%Y-%m'))
    ap.add_argument('--intervalo', default='1h')
    ap.add_argument('--top', type=int, default=60)
    ap.add_argument('--ativos', default='')
    ap.add_argument('--listar', action='store_true',
                    help='so lista os pares USDT disponiveis e sai')
    ap.add_argument('--pasta', default='dados_fut',
                    help='onde gravar; use outra para nao mexer no historico')
    a = ap.parse_args()
    PASTA = a.pasta

    open(DIAG, "w").close()
    if a.listar:
        listar_cdn()
        return
    os.makedirs(PASTA, exist_ok=True)
    lista = [x.strip().upper() for x in a.ativos.split(',') if x.strip()]
    if not lista:
        # se ja existe historico baixado, usa a mesma lista: assim o recorte
        # novo bate exatamente com o que foi medido antes
        ja = sorted(pathlib.Path('dados_fut').glob('*_1h.csv'))
        lista = [p.name.split('_')[0] for p in ja] or candidatos(a.top + 25)
    ms = meses(a.inicio, a.fim)
    diag(f"{len(lista)} candidatos | {len(ms)} meses | intervalo {a.intervalo}")

    resultados = []
    for i, sim in enumerate(lista, 1):
        todas = []
        faltou = 0
        for mes in ms:
            linhas = baixar_mes(sim, a.intervalo, mes)
            if linhas is None:
                faltou += 1
            else:
                todas.extend(linhas)
        if len(todas) < 100:
            diag(f"  {i:>3}. {sim:<14} descartado ({len(todas)} velas, "
                 f"{faltou} meses sem dado)")
            continue
        todas.sort(key=lambda x: x[0])
        vol_usd = sorted(c[4] * c[5] for c in todas)[len(todas) // 2]
        resultados.append((vol_usd, sim, todas))
        diag(f"  {i:>3}. {sim:<14} {len(todas):>6} velas  "
             f"volume mediano {vol_usd/1e6:>8,.1f} M USD/h")

    resultados.sort(reverse=True)
    escolhidos = resultados[:a.top]
    diag(f"\ngravando os {len(escolhidos)} de maior volume de FUTUROS")
    for vol, sim, linhas in escolhidos:
        caminho = f"{PASTA}/{sim}_{a.intervalo}.csv"
        with open(caminho, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['abertura_ms', 'data', 'abertura', 'maxima', 'minima',
                        'fechamento', 'volume'])
            for c in linhas:
                d = datetime.fromtimestamp(c[0] / 1000, timezone.utc)
                w.writerow([c[0], d.strftime('%Y-%m-%d %H:%M'),
                            c[1], c[2], c[3], c[4], c[5]])
    diag("ordem final por volume de futuros:")
    diag("  " + ", ".join(s for _, s, _ in escolhidos))


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        print("=== ERRO ===")
        traceback.print_exc()
        raise
