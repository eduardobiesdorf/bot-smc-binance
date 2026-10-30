# -*- coding: utf-8 -*-
"""
Radar de setups para o Telegram -- NAO opera, so avisa.

Monitora a cesta e manda duas coisas:

  RADAR   -- o setup esta se formando: houve CHOCH, a VWAP foi ancorada,
             o reteste FALHOU e o preco se afastou. Falta a rejeicao.
             Serve para voce ja abrir o grafico e acompanhar.

  GATILHO -- a vela de rejeicao acabou de fechar no 15min. Vem com
             entrada, stop, alvo, R:R e um grafico da situacao.

Roda em H1 para a estrutura e 15min para o gatilho, igual ao backtest.
Nao repete alerta do mesmo setup (estado em alertas_enviados.json).

Variaveis de ambiente:
    TELEGRAM_TOKEN    token do bot (BotFather)
    TELEGRAM_CHAT_ID  seu chat id

Uso:
    python bot_alertas.py              # escaneia e envia
    python bot_alertas.py --teste      # so imprime, nao envia
"""
import argparse
import bisect
import json
import os
import time
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))      # horario de Brasilia

import requests

ATIVOS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
          'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT']

BASE_URL = "https://data-api.binance.vision/api/v3"
ESTADO = "alertas_enviados.json"

MS_TF = {'1h': 3600000, '30m': 1800000, '15m': 900000, '5m': 300000}

CFG = dict(pivo_esq=3, pivo_dir=3, sigma=1.5, impulso_min=2, afasta_min=1,
           corpo_min=0.5, stop_buffer=2.0, rr_fixo=2.0, espera_max=30,
           janela_falha=20, atr_periodo=14,
           tf_estrutura='30m', tf_gatilho='15m')


# ------------------------------------------------------------------ dados
def buscar(simbolo, interval, limite=500):
    r = requests.get(f"{BASE_URL}/klines",
                     params={'symbol': simbolo, 'interval': interval, 'limit': limite},
                     timeout=20)
    r.raise_for_status()
    agora = int(time.time() * 1000)
    return [(int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5]))
            for c in r.json() if int(c[6]) < agora]       # so velas FECHADAS


def top_pares(n=20):
    """Os n pares USDT com maior volume em 24h, direto da Binance."""
    r = requests.get(f"{BASE_URL}/ticker/24hr", timeout=40)
    r.raise_for_status()
    # fora: stablecoin contra stablecoin (volume alto, movimento nenhum)
    fora = {'USDC', 'FDUSD', 'TUSD', 'BUSD', 'DAI', 'USDP', 'AEUR', 'EURI',
            'EUR', 'XUSD', 'USD1', 'PYUSD'}
    cand = []
    for d in r.json():
        s = d.get('symbol', '')
        if not s.endswith('USDT') or s[:-4] in fora:
            continue
        try:
            cand.append((float(d['quoteVolume']), s))
        except (KeyError, ValueError):
            continue
    cand.sort(reverse=True)
    return [x[1] for x in cand[:n]]


def atr(v, p=14):
    tr = [v[0][2] - v[0][3]]
    for k in range(1, len(v)):
        c0 = v[k - 1][4]
        tr.append(max(v[k][2] - v[k][3], abs(v[k][2] - c0), abs(v[k][3] - c0)))
    out, s = [], 0.0
    for k, x in enumerate(tr):
        s += x
        if k >= p:
            s -= tr[k - p]
            out.append(s / p)
        else:
            out.append(s / (k + 1))
    return out


def pivos(v, esq, dir_):
    altas, baixas = {}, {}
    for k in range(esq, len(v) - dir_):
        h, l = v[k][2], v[k][3]
        if (all(v[k - m][2] < h for m in range(1, esq + 1)) and
                all(v[k + m][2] <= h for m in range(1, dir_ + 1))):
            altas.setdefault(k + dir_, []).append((k, h))
        if (all(v[k - m][3] > l for m in range(1, esq + 1)) and
                all(v[k + m][3] >= l for m in range(1, dir_ + 1))):
            baixas.setdefault(k + dir_, []).append((k, l))
    return altas, baixas


def tipico(c):
    return (c[2] + c[3] + c[4]) / 3


# ------------------------------------------------------------------ detector
def analisar(h1, m15, cfg):
    """
    Devolve o estado ATUAL de cada setup vivo:
      {'fase': 'radar'|'gatilho', ...}
    Olha so o que esta acontecendo agora, nao o historico inteiro.
    """
    n = len(h1)
    a = atr(h1, cfg['atr_periodo'])
    altas, baixas = pivos(h1, cfg['pivo_esq'], cfg['pivo_dir'])
    a15 = atr(m15, 14)
    t15 = [x[0] for x in m15]
    sh = sl = None
    tendencia = 'indefinida'
    vivos = []

    for i in range(n - 1):
        for k, p in altas.get(i, []):
            if sh is None or k > sh[0]:
                sh = (k, p)
        for k, p in baixas.get(i, []):
            if sl is None or k > sl[0]:
                sl = (k, p)
        c = h1[i][4]
        lado = None
        if sh is not None and c > sh[1]:
            ev = 'choch' if tendencia == 'baixa' else 'bos'
            lado, ref = 'compra', sh
            tendencia, sh = 'alta', None
        elif sl is not None and c < sl[1]:
            ev = 'choch' if tendencia == 'alta' else 'bos'
            lado, ref = 'venda', sl
            tendencia, sl = 'baixa', None
        if lado is None or ev != 'choch' or a[i] <= 0:
            continue
        if n - i > cfg['espera_max'] + cfg['janela_falha']:
            continue                                   # CHOCH velho demais

        compra = lado == 'compra'
        jan = range(max(0, ref[0]), i + 1)
        ancora = min(jan, key=lambda k: h1[k][3]) if compra else \
                 max(jan, key=lambda k: h1[k][2])
        if i - ancora < cfg['impulso_min']:
            continue
        desloc = (h1[i][4] - h1[ancora][3]) if compra else (h1[ancora][2] - h1[i][4])
        if desloc <= 0 or desloc / a[i] < cfg['sigma']:
            continue

        est = acompanhar(h1, m15, t15, a15, i, ancora, compra, cfg,
                         MS_TF[cfg['tf_estrutura']])
        if est:
            est.update(choch_ms=h1[i][0], ancora_ms=h1[ancora][0])
            vivos.append(est)
    return vivos


def acompanhar(h1, m15, t15, a15, i, ancora, compra, cfg, dur_ms):
    n = len(h1)
    pv = vv = 0.0
    for k in range(ancora, i + 1):
        pv += tipico(h1[k]) * h1[k][5]
        vv += h1[k][5]
    if vv <= 0:
        return None
    base = h1[ancora][3] if compra else h1[ancora][2]
    tocou = falhou = False
    afastou = 0

    for k in range(i + 1, n):
        vw = pv / max(vv, 1e-12)
        o, h, l, cl = h1[k][1], h1[k][2], h1[k][3], h1[k][4]
        if not tocou:
            if k - i > cfg['espera_max']:
                return None
            tocou = (l <= vw) if compra else (h >= vw)
            if tocou and ((compra and vw <= base) or (not compra and vw >= base)):
                return None
        elif not falhou:
            if (compra and cl < vw) or (not compra and cl > vw):
                falhou = True
        else:
            fora = (h < vw) if compra else (l > vw)
            if fora:
                afastou += 1
            elif afastou >= cfg['afasta_min']:
                t0, t1 = h1[k][0], h1[k][0] + dur_ms
                p0 = bisect.bisect_left(t15, t0)
                p1 = bisect.bisect_left(t15, t1)
                for m in range(p0, min(p1, len(m15))):
                    mo, mh, ml, mc = m15[m][1], m15[m][2], m15[m][3], m15[m][4]
                    rng = mh - ml
                    if rng <= 0:
                        continue
                    toca = mh >= vw if compra else ml <= vw
                    rej = (mc < vw and mc < mo) if compra else (mc > vw and mc > mo)
                    if toca and rej and abs(mc - mo) / rng >= cfg['corpo_min']:
                        return montar_gatilho(m15, a15, m, not compra, base, vw, cfg)
            if (compra and cl > vw) or (not compra and cl < vw):
                return None
        pv += tipico(h1[k]) * h1[k][5]
        vv += h1[k][5]

    vw = pv / max(vv, 1e-12)
    if falhou and afastou >= cfg['afasta_min']:
        return {'fase': 'radar', 'lado': 'venda' if compra else 'compra',
                'vwap': vw, 'alvo_ref': base, 'preco': h1[-1][4],
                'tf_leitura': cfg['tf_estrutura'].upper(),
                'fecha_ms': h1[-1][0] + dur_ms,
                'dist': abs(h1[-1][4] - vw) / max(h1[-1][4], 1e-12) * 100}
    return None


def montar_gatilho(m15, a15, m, compra, base, vw, cfg):
    if m + 1 > len(m15):
        return None
    entrada = m15[m][4]                       # fechamento da vela de rejeicao
    extremo = m15[m][3] if compra else m15[m][2]
    stop = extremo - a15[m] * cfg['stop_buffer'] if compra else \
           extremo + a15[m] * cfg['stop_buffer']
    risco = abs(entrada - stop)
    if risco <= 0:
        return None
    alvo_estrut = base
    alvo_fixo = entrada + risco * cfg['rr_fixo'] * (1 if compra else -1)
    rr_e = abs(alvo_estrut - entrada) / risco
    return {'fase': 'gatilho', 'lado': 'compra' if compra else 'venda',
            'vwap': vw, 'entrada': entrada, 'stop': stop,
            'alvo_estrut': alvo_estrut, 'rr_estrut': rr_e,
            'alvo_fixo': alvo_fixo, 'rr_fixo': cfg['rr_fixo'],
            'risco_pct': risco / entrada * 100,
            'tf_leitura': cfg['tf_gatilho'],
            'fecha_ms': m15[m][0] + MS_TF[cfg['tf_gatilho']],
            'vela_ms': m15[m][0]}


# ------------------------------------------------------------------ telegram
def fmt(x):
    return f"{x:,.8f}".rstrip('0').rstrip('.') if x < 1 else f"{x:,.4f}".rstrip('0').rstrip('.')


def diag(linha):
    """Grava diagnostico num arquivo que o workflow commita (logs sao inacessiveis)."""
    print(linha, flush=True)
    try:
        with open("diagnostico_telegram.txt", "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass


def enviar(texto, html=True):
    tok = os.getenv("TELEGRAM_TOKEN") or os.getenv("TOKEN_TELEGRAM")
    chat = os.getenv("TELEGRAM_CHAT_ID") or os.getenv("CHAT_ID_TELEGRAM")
    diag(f"TOKEN: {'definido, ' + str(len(tok)) + ' chars' if tok else 'AUSENTE'}"
         f" | CHAT_ID: {'definido, ' + str(len(chat)) + ' chars' if chat else 'AUSENTE'}")
    if not tok or not chat:
        diag("-> sem credenciais, nada enviado")
        return False
    dados = {'chat_id': chat, 'text': texto}
    if html:
        dados['parse_mode'] = 'HTML'
    try:
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                          data=dados, timeout=20)
        diag(f"HTTP {r.status_code}: {r.text[:300]}")
        if not r.ok and html:
            diag("-> tentando de novo SEM formatacao HTML")
            return enviar(texto.replace('<b>', '').replace('</b>', '')
                          .replace('<i>', '').replace('</i>', '')
                          .replace('<code>', '').replace('</code>', ''), html=False)
        return r.ok
    except Exception as e:
        diag(f"ERRO de rede: {e}")
        return False


def quando(ms):
    """Fechamento da vela, no horario de Brasilia."""
    return f"{datetime.fromtimestamp(ms / 1000, BRT):%d/%m %H:%M}"


def cabecalho(sim, e, titulo, sub):
    lado = "COMPRA" if e['lado'] == 'compra' else "VENDA"
    return (f"<b>{titulo} — {sim.replace('USDT','/USDT')}</b>\n"
            f"<b>Direção: {lado}</b>\n"
            f"<i>{sub}</i>\n\n"
            f"Leitura no <b>{e['tf_leitura']}</b>\n"
            f"Vela que gerou: <b>{quando(e['fecha_ms'])}</b>\n"
            f"{'─'*26}\n")


def msg_gatilho(sim, e):
    alvo2 = (f"Alvo fixo 1:{e['rr_fixo']:.0f}:  <code>{fmt(e['alvo_fixo'])}</code>\n"
             if e['rr_fixo'] else "")
    return (cabecalho(sim, e, "GATILHO", "a vela de rejeição na VWAP já fechou") +
            f"Entrada:  <code>{fmt(e['entrada'])}</code>\n"
            f"Stop:     <code>{fmt(e['stop'])}</code>\n"
            f"Risco:    {e['risco_pct']:.2f}% do preço\n\n"
            f"Alvo estrutural (último fundo/topo):\n"
            f"          <code>{fmt(e['alvo_estrut'])}</code>  "
            f"→ <b>R:R 1:{e['rr_estrut']:.2f}</b>\n"
            f"{alvo2}\n"
            f"VWAP ancorada: <code>{fmt(e['vwap'])}</code>\n"
            f"{'─'*26}\n"
            f"<i>Confira o contexto no gráfico antes de operar. "
            f"O backtest deste setup empata no líquido — ele serve como "
            f"radar, não como ordem.</i>")


def msg_radar(sim, e):
    return (cabecalho(sim, e, "CENÁRIO", "reteste da VWAP falhou e o preço se afastou "
                      "— falta a vela de rejeição") +
            f"Preço agora: <code>{fmt(e['preco'])}</code>\n"
            f"VWAP ancorada: <code>{fmt(e['vwap'])}</code>\n"
            f"Distância até a VWAP: {e['dist']:.2f}%\n\n"
            f"Alvo de referência: <code>{fmt(e['alvo_ref'])}</code>\n"
            f"{'─'*26}\n"
            f"<i>Ainda NÃO é entrada. O gatilho só vale quando uma vela de "
            f"15min tocar a VWAP e fechar de volta com corpo forte.</i>")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--teste', action='store_true', help='nao envia, so imprime')
    ap.add_argument('--so-gatilho', action='store_true', help='nao manda RADAR')
    ap.add_argument('--ativos', default='')
    ap.add_argument('--tf-estrutura', default=CFG['tf_estrutura'],
                    choices=list(MS_TF))
    ap.add_argument('--tf-gatilho', default=CFG['tf_gatilho'], choices=list(MS_TF))
    ap.add_argument('--rr-fixo', type=float, default=CFG['rr_fixo'])
    ap.add_argument('--stop-buffer', type=float, default=CFG['stop_buffer'])
    ap.add_argument('--top', type=int, default=0,
                    help='usa os N pares USDT de maior volume em 24h '
                         '(ignora a lista fixa)')
    ap.add_argument('--ping', action='store_true',
                    help='manda uma mensagem de teste no Telegram e sai')
    a = ap.parse_args()

    CFG.update(tf_estrutura=a.tf_estrutura, tf_gatilho=a.tf_gatilho,
               rr_fixo=a.rr_fixo, stop_buffer=a.stop_buffer)

    if a.ping:
        ok = enviar("<b>Radar SMC — teste de conexão</b>\n"
                    f"Estrutura: <b>{a.tf_estrutura}</b> | "
                    f"Gatilho: <b>{a.tf_gatilho}</b> | Alvo: <b>1:{a.rr_fixo:.0f}</b>\n"
                    "<i>Se você recebeu isto, as chaves estão certas.</i>")
        print("ping enviado" if ok else "ping NAO enviado")
        return

    if a.top:
        try:
            ativos = top_pares(a.top)
            print(f"Top {a.top} por volume 24h: {', '.join(x.replace('USDT','') for x in ativos)}")
        except Exception as e:
            print(f"Falha ao buscar o ranking ({e}) -- usando a lista fixa")
            ativos = ATIVOS
    else:
        ativos = [x.strip().upper() for x in a.ativos.split(',') if x.strip()] or ATIVOS
    try:
        enviados = set(json.load(open(ESTADO)))
    except Exception:
        enviados = set()

    agora = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    n_gat = n_cen = 0
    achados = []
    print(f"=== Radar SMC | {agora} | {len(ativos)} ativos | "
          f"{CFG['tf_estrutura']}+{CFG['tf_gatilho']} | alvo 1:{CFG['rr_fixo']:.0f}")
    novos = 0

    for sim in ativos:
        try:
            h1 = buscar(sim, CFG['tf_estrutura'], 400)
            m15 = buscar(sim, CFG['tf_gatilho'], 600)
        except Exception as e:
            print(f"[{sim}] erro ao buscar: {e}")
            continue
        if len(h1) < 100 or len(m15) < 100:
            continue

        for e in analisar(h1, m15, CFG):
            if e['fase'] == 'gatilho':
                n_gat += 1
            else:
                n_cen += 1
            achados.append(f"{e['fase'].upper():>7}  {sim:<12} {e['lado']:<7}"
                           f" vela {quando(e['fecha_ms'])}")
            if e['fase'] == 'radar' and a.so_gatilho:
                continue
            chave = (f"{sim}-{e['fase']}-{e.get('vela_ms', e['choch_ms'])}"
                     f"-{e['lado']}")
            if chave in enviados:
                continue
            texto = msg_gatilho(sim, e) if e['fase'] == 'gatilho' else msg_radar(sim, e)
            print(f"\n--- {chave}\n{texto}")
            if a.teste or enviar(texto):
                enviados.add(chave)
                novos += 1
        time.sleep(0.15)

    if not a.teste:
        json.dump(sorted(enviados)[-3000:], open(ESTADO, 'w'))
    print(f"\nAlertas novos: {novos}  (gatilhos {n_gat} | cenarios {n_cen})")
    try:
        with open("resumo_radar.txt", "w", encoding="utf-8") as f:
            f.write(f"{agora}\n"
                    f"ativos escaneados: {len(ativos)}\n"
                    f"GATILHOS: {n_gat}\n"
                    f"CENARIOS: {n_cen}\n"
                    f"novos (nao repetidos): {novos}\n\n"
                    + "\n".join(achados))
    except Exception:
        pass


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except Exception:
        print("\n=== ERRO ===")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
