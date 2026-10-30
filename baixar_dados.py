# -*- coding: utf-8 -*-
"""
Baixa o historico da Binance e salva em dados/ como CSV.

Serve para separar a COLETA do dado da LOGICA da estrategia:
roda uma vez, commita os CSVs, e a partir dai qualquer backtest le do disco --
rapido, reproduzivel e sem depender de rede.

Uso:
    python baixar_dados.py                          # diario, universo padrao
    python baixar_dados.py --intervalos 1d,4h
    python baixar_dados.py --inicio 2020-01-01 --ativos BTCUSDT,ETHUSDT

Formato de saida: dados/<SIMBOLO>_<INTERVALO>.csv
    abertura_ms,data,abertura,maxima,minima,fechamento,volume
"""
import argparse
import csv
import os
import time
from datetime import datetime, timezone

import requests

UNIVERSO = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT',
    'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT', 'UNIUSDT', 'ATOMUSDT',
    'LTCUSDT', 'BCHUSDT', 'NEARUSDT', 'FILUSDT', 'APTUSDT', 'ARBUSDT',
    'OPUSDT', 'INJUSDT', 'SUIUSDT', 'TIAUSDT', 'RUNEUSDT', 'AAVEUSDT',
    'GRTUSDT', 'SANDUSDT', 'AXSUSDT', 'ALGOUSDT', 'EGLDUSDT', 'FTMUSDT',
    'THETAUSDT', 'XLMUSDT', 'VETUSDT', 'ICPUSDT', 'HBARUSDT', 'MANAUSDT',
    'CHZUSDT', 'ENJUSDT', 'ZILUSDT', 'CRVUSDT', 'SHIBUSDT', 'POLUSDT',
    'TRXUSDT', 'ETCUSDT', 'IMXUSDT', 'STXUSDT', 'LDOUSDT', 'ONDOUSDT',
    'JUPUSDT', 'WIFUSDT',
]

BASE_URL = "https://data-api.binance.vision/api/v3"
PASTA = "dados"

MS = {'1d': 86400000, '4h': 14400000, '1h': 3600000,
      '30m': 1800000, '15m': 900000, '5m': 300000}


def ms_data(d):
    return int(datetime.strptime(d, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp() * 1000)


def baixar(simbolo, interval, inicio_ms, fim_ms, tentativas=3):
    passo = MS[interval]
    agora = int(time.time() * 1000)
    fim_ms = min(fim_ms, agora)
    linhas, cursor, visto = [], inicio_ms, set()

    while cursor < fim_ms:
        dados = None
        for t in range(tentativas):
            try:
                r = requests.get(f"{BASE_URL}/klines",
                                 params={'symbol': simbolo, 'interval': interval,
                                         'startTime': cursor, 'endTime': fim_ms,
                                         'limit': 1000}, timeout=25)
                if r.status_code == 429:
                    time.sleep(10 * (t + 1))
                    continue
                if r.status_code == 400:
                    return []               # par nao existe
                r.raise_for_status()
                dados = r.json()
                break
            except Exception as e:
                if t == tentativas - 1:
                    print(f"    falhou: {e}")
                    return linhas
                time.sleep(3 * (t + 1))
        if not dados:
            break

        for c in dados:
            ab = int(c[0])
            if ab in visto or int(c[6]) >= agora:   # so velas FECHADAS
                continue
            visto.add(ab)
            linhas.append([
                ab,
                datetime.fromtimestamp(ab / 1000, timezone.utc)
                        .strftime('%Y-%m-%d %H:%M'),
                c[1], c[2], c[3], c[4], c[5],
            ])

        ultimo = int(dados[-1][0])
        if len(dados) < 1000 and ultimo + passo >= fim_ms:
            break
        cursor = ultimo + passo
        time.sleep(0.2)

    linhas.sort(key=lambda x: x[0])
    return linhas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inicio', default='2021-01-01')
    ap.add_argument('--fim', default=datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    ap.add_argument('--intervalos', default='1d')
    ap.add_argument('--ativos', default='')
    a = ap.parse_args()

    universo = [x.strip().upper() for x in a.ativos.split(',') if x.strip()] or UNIVERSO
    intervalos = [x.strip() for x in a.intervalos.split(',') if x.strip()]
    for iv in intervalos:
        if iv not in MS:
            print(f"Intervalo nao suportado: {iv}")
            return

    ini, fim = ms_data(a.inicio), ms_data(a.fim) + 86400000
    os.makedirs(PASTA, exist_ok=True)

    print(f"Baixando {len(universo)} pares | intervalos {intervalos} | "
          f"{a.inicio} -> {a.fim}", flush=True)
    total_linhas = total_bytes = 0
    vazios = []

    for iv in intervalos:
        for i, s in enumerate(universo, 1):
            linhas = baixar(s, iv, ini, fim)
            if not linhas:
                vazios.append(f"{s}_{iv}")
                print(f"  [{i:>2}/{len(universo)}] {s} {iv}: sem dados", flush=True)
                continue
            caminho = os.path.join(PASTA, f"{s}_{iv}.csv")
            with open(caminho, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['abertura_ms', 'data', 'abertura', 'maxima',
                            'minima', 'fechamento', 'volume'])
                w.writerows(linhas)
            tam = os.path.getsize(caminho)
            total_linhas += len(linhas)
            total_bytes += tam
            print(f"  [{i:>2}/{len(universo)}] {s} {iv}: {len(linhas)} velas "
                  f"({linhas[0][1][:10]} -> {linhas[-1][1][:10]}) {tam/1024:.0f} KB",
                  flush=True)

    print(f"\nTotal: {total_linhas} velas | {total_bytes/1024/1024:.1f} MB em {PASTA}/")
    if vazios:
        print(f"Sem dados ({len(vazios)}): {', '.join(vazios)}")


if __name__ == "__main__":
    main()
