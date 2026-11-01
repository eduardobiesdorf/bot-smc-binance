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
         f"{len(usdt)} terminando em USDT, {len(perp)} perpetuos")

    # Vivo = tem arquivo diario de ontem. O CDN guarda o historico dos
    # deslistados para sempre, entao a lista bruta nao serve de nada.
    from concurrent.futures import ThreadPoolExecutor
    from datetime import timedelta
    dia = (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d')

    def vivo(s):
        u = f"{CDN_DIA}/{s}/1h/{s}-1h-{dia}.zip"
        for _ in range(2):
            try:
                if requests.head(u, timeout=30).ok:
                    return s
                return None
            except Exception:
                time.sleep(1)
        return None

    with ThreadPoolExecutor(max_workers=24) as ex:
        ativos = sorted(x for x in ex.map(vivo, perp) if x)
    diag(f"\nvivos em {dia}: {len(ativos)} de {len(perp)}")

    # Separar cripto de acao tokenizada sem lista na mao: no SPOT a acao
    # tokenizada se chama TICKER + B (AAPLB), a cripto se chama so BASE.
    try:
        r = requests.get(f"{SPOT}/exchangeInfo", timeout=60)
        r.raise_for_status()
        spot = {d['symbol'] for d in r.json().get('symbols', [])}
    except Exception as e:
        diag(f"nao consegui o exchangeInfo do spot: {e}")
        return ativos

    cripto, acao, orfao = [], [], []
    for s in ativos:
        base = s[:-4]
        if base + 'BUSDT' in spot:
            acao.append(s)
        elif s in spot:
            cripto.append(s)
        else:
            orfao.append(s)
    diag(f"  cripto (existe no spot): {len(cripto)}")
    diag(f"  acao tokenizada (existe no spot como {{T}}B): {len(acao)}")
    diag(f"  so em futuros (nao da para classificar): {len(orfao)}")
    for nome, lst in (("CRIPTO", cripto), ("ACAO TOKENIZADA", acao),
                      ("SO EM FUTUROS", orfao)):
        diag(f"\n{nome}:")
        for i in range(0, len(lst), 10):
            diag("  " + ", ".join(lst[i:i+10]))
    return cripto


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


def recente(mes):
    """Mes corrente ou o anterior: pode ainda nao ter arquivo mensal."""
    ag = datetime.now(timezone.utc)
    a, m = ag.year, ag.month
    ant = (a - 1, 12) if m == 1 else (a, m - 1)
    return mes in (f"{a:04d}-{m:02d}", f"{ant[0]:04d}-{ant[1]:02d}")


def baixar_mes(sim, iv, mes, ses=None):
    get = (ses or requests).get
    url = f"{CDN}/{sim}/{iv}/{sim}-{iv}-{mes}.zip"
    for tent in range(3):
        try:
            r = get(url, timeout=120)
        except Exception:
            time.sleep(1 + tent * 2)
            continue
        if r.status_code == 404:
            # O 404 quase sempre quer dizer que o par nao existia nesse mes.
            # So vale tentar os diarios no mes corrente/anterior, que ainda
            # nao foram fechados num arquivo mensal. Fora disso o fallback
            # gastava 30 requisicoes para nao achar nada.
            return baixar_dias(sim, iv, mes) if recente(mes) else None
        if not r.ok:
            time.sleep(1 + tent * 2)
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
        ja = sorted(pathlib.Path(PASTA).glob(f'*_{a.intervalo}.csv'))
        lista = [p.name.split('_')[0] for p in ja] or candidatos(a.top + 25)
    ms = meses(a.inicio, a.fim)
    diag(f"{len(lista)} candidatos | {len(ms)} meses | intervalo {a.intervalo}")

    # Um par por thread. Cada um grava o proprio CSV na hora e devolve so
    # o volume: guardar todas as velas de 150 pares na memoria estourava.
    from concurrent.futures import ThreadPoolExecutor
    from threading import Lock
    trava = Lock()
    feito = [0]

    def um(sim):
        ses = requests.Session()
        todas, faltou = [], 0
        for mes in ms:
            linhas = baixar_mes(sim, a.intervalo, mes, ses)
            if linhas is None:
                faltou += 1
            else:
                todas.extend(linhas)
        ses.close()
        with trava:
            feito[0] += 1
            n = feito[0]
        if len(todas) < 100:
            diag(f"  {n:>3}/{len(lista)} {sim:<14} descartado "
                 f"({len(todas)} velas, {faltou} meses sem dado)")
            return None
        todas.sort(key=lambda x: x[0])
        vol_usd = sorted(c[4] * c[5] for c in todas)[len(todas) // 2]
        caminho = f"{PASTA}/{sim}_{a.intervalo}.csv"
        with open(caminho, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['abertura_ms', 'data', 'abertura', 'maxima', 'minima',
                        'fechamento', 'volume'])
            for c in todas:
                d = datetime.fromtimestamp(c[0] / 1000, timezone.utc)
                w.writerow([c[0], d.strftime('%Y-%m-%d %H:%M'),
                            c[1], c[2], c[3], c[4], c[5]])
        diag(f"  {n:>3}/{len(lista)} {sim:<14} {len(todas):>6} velas  "
             f"volume mediano {vol_usd/1e6:>8,.1f} M USD/h")
        return (vol_usd, sim)

    with ThreadPoolExecutor(max_workers=10) as ex:
        resultados = [x for x in ex.map(um, lista) if x]

    resultados.sort(reverse=True)
    escolhidos = resultados[:a.top]
    manter = {s for _, s in escolhidos}
    for _, sim in resultados[a.top:]:
        try:
            os.remove(f"{PASTA}/{sim}_{a.intervalo}.csv")
        except OSError:
            pass
    diag(f"\nficaram os {len(escolhidos)} de maior volume de FUTUROS "
         f"({len(resultados) - len(escolhidos)} apagados)")
    diag("ordem final por volume de futuros:")
    diag("  " + ", ".join(s for _, s in escolhidos))


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        print("=== ERRO ===")
        traceback.print_exc()
        raise
