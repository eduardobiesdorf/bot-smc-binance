"""O www.binance.com/fapi serve tudo que a varredura precisa?

18/11/2026 -- o bot le SPOT porque fapi.binance.com da 451 (bloqueio legal
por IP americano, e todo runner do GitHub e americano). Mas o MESMO
endpoint de futuros, servido pelo dominio do site, respondeu 200 no teste
anterior. Se servir klines, ticker e exchangeInfo, o bot passa a ler
FUTUROS -- o mercado que o Eduardo opera e em que o backteste foi
validado -- trocando uma constante.

Roda no Actions. Daqui do contêiner a Binance e bloqueada.
"""
import json
import sys
import time
import datetime as dt
import urllib.request

B = "https://www.binance.com/fapi/v1"
BRT = dt.timezone(dt.timedelta(hours=-3))
UA = {'User-Agent': 'Mozilla/5.0'}


def pega(url, segs=40):
    req = urllib.request.Request(url, headers=UA)
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=segs) as r:
        dado = json.loads(r.read().decode())
    return dado, r.status, time.time() - t0


def hora(ms):
    return dt.datetime.fromtimestamp(ms/1000, BRT).strftime('%d/%m %H:%M')


def main():
    falhou = []

    print("=== 1. klines de 1h, limite 1300 (o que a varredura puxa) ===")
    try:
        d, st, seg = pega(f"{B}/klines?symbol=BTCUSDT&interval=1h&limit=1300")
        print(f"  HTTP {st} em {seg:.1f}s · {len(d)} velas")
        print(f"  primeira: {hora(d[0][0])} BRT")
        print(f"  última  : {hora(d[-1][0])} BRT · fecha {d[-1][4]}")
        atraso = (time.time()*1000 - d[-1][0]) / 3600000
        print(f"  a última vela começou há {atraso:.1f}h "
              f"(deve ser < 1h: é a vela em formação)")
    except Exception as e:
        print(f"  FALHOU: {e}")
        falhou.append('klines')

    print("\n=== 2. ticker de 24h de todos os pares (a fila) ===")
    try:
        d, st, seg = pega(f"{B}/ticker/24hr")
        u = [x for x in d if x['symbol'].endswith('USDT')]
        u.sort(key=lambda x: -float(x['quoteVolume']))
        print(f"  HTTP {st} em {seg:.1f}s · {len(d)} pares, "
              f"{len(u)} terminados em USDT")
        print(f"  top 8: {', '.join(x['symbol'] for x in u[:8])}")
    except Exception as e:
        print(f"  FALHOU: {e}")
        falhou.append('ticker')

    print("\n=== 3. exchangeInfo (quais são perpétuos) ===")
    try:
        d, st, seg = pega(f"{B}/exchangeInfo", 60)
        s = [x for x in d['symbols']
             if x.get('contractType') == 'PERPETUAL'
             and x.get('quoteAsset') == 'USDT'
             and x.get('status') == 'TRADING']
        print(f"  HTTP {st} em {seg:.1f}s · "
              f"{len(s)} perpétuos USDT negociando")
    except Exception as e:
        print(f"  FALHOU: {e}")
        falhou.append('exchangeInfo')

    print("\n=== 4. vinte chamadas seguidas (tem limite de taxa?) ===")
    ok, erros = 0, []
    t0 = time.time()
    for i in range(20):
        try:
            pega(f"{B}/klines?symbol=ETHUSDT&interval=1h&limit=500", 20)
            ok += 1
        except Exception as e:
            erros.append(f"{i+1}:{type(e).__name__}")
    print(f"  {ok} de 20 passaram em {time.time()-t0:.0f}s")
    if erros:
        print(f"  falhas: {', '.join(erros[:6])}")
        falhou.append('taxa')

    print("\n=== 5. o preço bate com o SPOT? (o tal do spread) ===")
    try:
        f, _, _ = pega(f"{B}/klines?symbol=BTCUSDT&interval=1h&limit=2")
        req = urllib.request.Request(
            "https://data-api.binance.vision/api/v3/klines"
            "?symbol=BTCUSDT&interval=1h&limit=2", headers=UA)
        with urllib.request.urlopen(req, timeout=30) as r:
            s = json.loads(r.read().decode())
        pf, ps = float(f[-2][4]), float(s[-2][4])
        print(f"  vela fechada de {hora(f[-2][0])} BRT")
        print(f"  futuros {pf:.2f}  ·  spot {ps:.2f}  ·  "
              f"diferença {(pf-ps)/ps*100:+.3f}%")
    except Exception as e:
        print(f"  não deu para comparar: {e}")

    print()
    if falhou:
        print(f">>> NÃO serve: falhou em {', '.join(falhou)}")
        sys.exit(1)
    print(">>> SERVE. Dá para trocar a fonte do bot para FUTUROS.")


if __name__ == '__main__':
    main()
