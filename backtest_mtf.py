# -*- coding: utf-8 -*-
"""
Multi-timeframe: estrutura em H1, gatilho de rejeicao em 15min.

Estrutura (H1):
  1. CHOCH -- quebra contra a tendencia vigente
  2. VWAP ancorada no fundo estrutural de onde saiu o impulso
  3. o preco volta na VWAP e FECHA do lado errado -> reteste falhou
  4. o preco se AFASTA da VWAP e VOLTA para testar de novo

Gatilho (15min):
  5. dentro dessa janela, procura no timeframe menor a vela que toca a VWAP
     e REJEITA -- fecha de volta do lado errado, com corpo expressivo
  6. entrada na abertura da vela de 15min seguinte
  7. stop em cima da vela de rejeicao de 15min (bem mais apertado que H1)
  8. alvo: ultimo fundo deixado, ou multiplo fixo de risco

A simulacao do trade roda em 15min, nao em H1 -- com stop apertado a
resolucao importa.

Le dados/<SIMBOLO>_1h.csv e dados/<SIMBOLO>_15m.csv.

Uso:
    python backtest_mtf.py
    python backtest_mtf.py --alvo rr_fixo --rr-fixo 2.0
    python backtest_mtf.py --comparar-alvos
"""
import argparse
import bisect
import csv
import glob
import math
import os
import random
import statistics
from datetime import datetime, timezone

PASTA = "dados"
FECHADOS = ('win', 'loss', 'tempo', 'be')


def carregar(tf, ativos=None):
    saida = {}
    for caminho in sorted(glob.glob(os.path.join(PASTA, f"*_{tf}.csv"))):
        s = os.path.basename(caminho).rsplit(f"_{tf}.csv", 1)[0]
        if ativos and s not in ativos:
            continue
        v = []
        with open(caminho, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                try:
                    v.append((int(r['abertura_ms']), float(r['abertura']),
                              float(r['maxima']), float(r['minima']),
                              float(r['fechamento']), float(r['volume'])))
                except (ValueError, KeyError):
                    continue
        if len(v) >= 500:
            v.sort(key=lambda x: x[0])
            saida[s] = v
    return saida


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


# ------------------------------------------------------------------ sinal
def gerar(h1, m15, cfg):
    n = len(h1)
    # duracao da barra de estrutura, deduzida dos dados
    dur_ms = h1[1][0] - h1[0][0] if n > 1 else 3600000
    a = atr(h1, cfg['atr_periodo'])
    altas, baixas = pivos(h1, cfg['pivo_esq'], cfg['pivo_dir'])
    tempos15 = [x[0] for x in m15]
    a15 = atr(m15, 14)
    sh = sl = None
    tendencia = 'indefinida'
    trades = []
    fim_ms = -1

    for i in range(n - 2):
        for k, p in altas.get(i, []):
            if sh is None or k > sh[0]:
                sh = (k, p)
        for k, p in baixas.get(i, []):
            if sl is None or k > sl[0]:
                sl = (k, p)
        c = h1[i][4]
        evento = lado = None
        if sh is not None and c > sh[1]:
            evento = 'choch' if tendencia == 'baixa' else 'bos'
            lado, ref = 'compra', sh
            tendencia, sh = 'alta', None
        elif sl is not None and c < sl[1]:
            evento = 'choch' if tendencia == 'alta' else 'bos'
            lado, ref = 'venda', sl
            tendencia, sl = 'baixa', None
        if evento is None or h1[i][0] <= fim_ms or a[i] <= 0:
            continue
        if cfg['evento'] != 'ambos' and evento != cfg['evento']:
            continue

        compra = lado == 'compra'
        jan = range(max(0, ref[0]), i + 1)
        ancora = min(jan, key=lambda k: h1[k][3]) if compra else \
                 max(jan, key=lambda k: h1[k][2])
        if i - ancora < cfg['impulso_min']:
            continue
        desloc = (h1[i][4] - h1[ancora][3]) if compra else (h1[ancora][2] - h1[i][4])
        if desloc <= 0 or desloc / a[i] < cfg['sigma']:
            continue

        t = montar(h1, m15, tempos15, a15, i, ancora, compra, cfg, dur_ms)
        if t:
            t['evento'] = evento
            trades.append(t)
            fim_ms = t['fim_ms']
    return trades


def montar(h1, m15, tempos15, a15, i, ancora, compra, cfg, dur_ms=3600000):
    n = len(h1)
    pv = vv = 0.0
    for k in range(ancora, i + 1):
        pv += tipico(h1[k]) * h1[k][5]
        vv += h1[k][5]
    if vv <= 0:
        return None
    base = h1[ancora][3] if compra else h1[ancora][2]
    limite = min(n - 1, i + cfg['espera_max'])
    falhou = False
    afastou = 0
    tocou_1 = False

    for k in range(i + 1, min(n, limite + cfg['janela_falha'] + 1)):
        vw = pv / max(vv, 1e-12)          # conhecido ao fechar k-1
        o, h, l, cl = h1[k][1], h1[k][2], h1[k][3], h1[k][4]

        if not tocou_1:
            if k > limite:
                return None
            tocou_1 = (l <= vw) if compra else (h >= vw)
            if tocou_1 and ((compra and vw <= base) or (not compra and vw >= base)):
                return None
        elif not falhou:
            if (compra and cl < vw) or (not compra and cl > vw):
                falhou = True
        else:
            fora = (h < vw) if compra else (l > vw)
            if fora:
                afastou += 1
            elif afastou >= cfg['afasta_min']:
                # ---- desce para o 15min DENTRO desta barra de H1
                t0, t1 = h1[k][0], h1[k][0] + dur_ms
                p0 = bisect.bisect_left(tempos15, t0)
                p1 = bisect.bisect_left(tempos15, t1)
                for m in range(p0, min(p1, len(m15) - 1)):
                    mo, mh, ml, mc = m15[m][1], m15[m][2], m15[m][3], m15[m][4]
                    rng = mh - ml
                    if rng <= 0:
                        continue
                    toca = mh >= vw if compra else ml <= vw
                    rej = (mc < vw and mc < mo) if compra else (mc > vw and mc > mo)
                    if toca and rej and abs(mc - mo) / rng >= cfg['corpo_min']:
                        return fechar(m15, a15, m, not compra, base, cfg, i, ancora, k)
            if (compra and cl > vw) or (not compra and cl < vw):
                return None

        pv += tipico(h1[k]) * h1[k][5]
        vv += h1[k][5]
    return None


def fechar(m15, a15, m, compra, base, cfg, i, ancora, k):
    """m = vela de rejeicao em 15min. Entrada na seguinte, stop em cima dela."""
    if m + 1 >= len(m15):
        return None
    entrada = m15[m + 1][1]
    extremo = m15[m][3] if compra else m15[m][2]
    stop = extremo - a15[m] * cfg['stop_buffer'] if compra else \
           extremo + a15[m] * cfg['stop_buffer']
    risco = abs(entrada - stop)
    if risco <= 0:
        return None
    alvo = base if cfg['alvo'] == 'fundo' else \
           entrada + risco * cfg['rr_fixo'] * (1 if compra else -1)
    if (compra and alvo <= entrada) or (not compra and alvo >= entrada):
        return None
    rr = abs(alvo - entrada) / risco
    if rr < cfg['rr_min'] or (cfg['rr_max'] and rr > cfg['rr_max']):
        return None

    res, dur, r_bruto = simular(m15, m + 1, compra, entrada, stop, alvo, cfg)
    custo = (entrada * cfg['custo_pct'] / 100) / risco
    return {'data': datetime.fromtimestamp(m15[m + 1][0] / 1000, timezone.utc)
                    .strftime('%Y-%m-%d %H:%M'),
            'lado': 'compra' if compra else 'venda',
            'entrada': entrada, 'stop': stop, 'alvo': alvo, 'rr': rr,
            'risco_pct': risco / entrada * 100,
            'resultado': res, 'barras15': dur, 'r': r_bruto - custo,
            'fim_ms': m15[min(m + 1 + dur, len(m15) - 1)][0]}


def simular(v, j0, compra, entrada, stop, alvo, cfg):
    risco = abs(entrada - stop)
    parcial = False
    r_trav = 0.0
    sa = stop
    limite = min(len(v) - 1, j0 + cfg['tempo_max'])
    if (compra and v[j0][3] <= sa) or (not compra and v[j0][2] >= sa):
        return 'loss', 0, -1.0
    for k in range(j0 + 1, len(v)):
        hi, lo = v[k][2], v[k][3]
        em_r = (hi - entrada) / risco if compra else (entrada - lo) / risco
        bs = lo <= sa if compra else hi >= sa
        ba = hi >= alvo if compra else lo <= alvo
        if cfg['parcial_em'] > 0 and not parcial and em_r >= cfg['parcial_em'] and not bs:
            parcial = True
            r_trav += cfg['parcial_frac'] * cfg['parcial_em']
            if cfg['breakeven']:
                sa = entrada
                bs = lo <= sa if compra else hi >= sa
        resto = 1.0 - (cfg['parcial_frac'] if parcial else 0.0)
        if bs:
            perda = 0.0 if (parcial and cfg['breakeven']) else -1.0
            return ('be' if perda == 0 else 'loss'), k - j0, r_trav + resto * perda
        if ba:
            return 'win', k - j0, r_trav + resto * abs(alvo - entrada) / risco
        if k >= limite:
            s = v[k][4]
            return 'tempo', k - j0, r_trav + resto * (
                ((s - entrada) if compra else (entrada - s)) / risco)
    return 'tempo', len(v) - 1 - j0, r_trav


# ------------------------------------------------------------------ metricas
def medir(trades):
    f = [t for t in trades if t['resultado'] in FECHADOS]
    if len(f) < 10:
        return None
    w = sum(1 for t in f if t['resultado'] == 'win')
    rs = [t['r'] for t in f]
    m = sum(rs) / len(rs)
    dp = statistics.stdev(rs) if len(rs) > 1 else 0
    se = dp / math.sqrt(len(rs)) if dp else 1e-9
    acc = pico = dd = 0.0
    pior = atual = 0
    for t in sorted(f, key=lambda x: x['data']):
        acc += t['r']
        pico = max(pico, acc)
        dd = min(dd, acc - pico)
        if t['r'] < -0.05:
            atual += 1
            pior = max(pior, atual)
        else:
            atual = 0
    return {'n': len(f), 'wr': w / len(f) * 100, 'exp': m, 'total': sum(rs),
            'z': m / se, 'dd': dd, 'seq': pior,
            'rr': sum(t['rr'] for t in f) / len(f),
            'risco': sum(t['risco_pct'] for t in f) / len(f),
            'ic': (m - 1.96 * se, m + 1.96 * se)}


def linha(nome, m):
    if not m:
        print(f"{nome:>24} |     -")
        return
    print(f"{nome:>24} | {m['n']:>5} {m['wr']:>5.1f}% 1:{m['rr']:>4.2f} "
          f"{m['risco']:>5.2f}% {0.10/max(m['risco'],1e-9):>6.3f} "
          f"{m['exp']:>+7.3f}R {m['total']:>+8.1f}R {m['z']:>+6.2f}")


def cabecalho():
    print(f"\n{'configuracao':>24} | {'n':>5} {'WR':>6} {'RR':>6} {'risco':>6} "
          f"{'taxaR':>6} {'exp':>8} {'total':>9} {'z':>6}")
    print("-" * 92)


def rodar_tudo(h1s, m15s, cfg, por_ativo=False):
    todos = []
    for s in sorted(h1s):
        if s not in m15s:
            continue
        t = gerar(h1s[s], m15s[s], cfg)
        for x in t:
            x['ativo'] = s
        todos.extend(t)
        if por_ativo:
            linha(s.replace('USDT', ''), medir(t))
    return todos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf-estrutura', default='1h')
    ap.add_argument('--tf-gatilho', default='15m')
    ap.add_argument('--ativos', default='')
    ap.add_argument('--pivo-esq', type=int, default=3)
    ap.add_argument('--pivo-dir', type=int, default=3)
    ap.add_argument('--evento', choices=['choch', 'bos', 'ambos'], default='choch')
    ap.add_argument('--sigma', type=float, default=1.5)
    ap.add_argument('--impulso-min', type=int, default=2)
    ap.add_argument('--afasta-min', type=int, default=1)
    ap.add_argument('--corpo-min', type=float, default=0.5)
    ap.add_argument('--alvo', choices=['fundo', 'rr_fixo'], default='fundo')
    ap.add_argument('--rr-fixo', type=float, default=2.0)
    ap.add_argument('--stop-buffer', type=float, default=0.3,
                    help='ATR de 15min alem da vela de rejeicao')
    ap.add_argument('--rr-min', type=float, default=0.3)
    ap.add_argument('--rr-max', type=float, default=0.0)
    ap.add_argument('--espera-max', type=int, default=30)
    ap.add_argument('--janela-falha', type=int, default=20)
    ap.add_argument('--tempo-max', type=int, default=200, help='velas de 15min')
    ap.add_argument('--atr-periodo', type=int, default=14)
    ap.add_argument('--parcial-em', type=float, default=0.0)
    ap.add_argument('--parcial-frac', type=float, default=0.5)
    ap.add_argument('--breakeven', action='store_true')
    ap.add_argument('--custo-pct', type=float, default=0.10)
    ap.add_argument('--comparar-alvos', action='store_true')
    a = ap.parse_args()

    cfg = {k: getattr(a, k) for k in
           ('pivo_esq', 'pivo_dir', 'evento', 'sigma', 'impulso_min', 'afasta_min',
            'corpo_min', 'alvo', 'rr_fixo', 'stop_buffer', 'rr_min', 'rr_max',
            'espera_max', 'janela_falha', 'tempo_max', 'atr_periodo',
            'parcial_em', 'parcial_frac', 'breakeven', 'custo_pct')}

    ativos = {x.strip().upper() for x in a.ativos.split(',') if x.strip()} or None
    h1s = carregar(a.tf_estrutura, ativos)
    m15s = carregar(a.tf_gatilho, ativos)
    if not h1s or not m15s:
        print(f"Faltam CSVs. {a.tf_estrutura}: {len(h1s)} pares | "
              f"{a.tf_gatilho}: {len(m15s)} pares")
        return
    comuns = sorted(set(h1s) & set(m15s))
    print("=" * 92)
    print(f"MULTI-TIMEFRAME | estrutura {a.tf_estrutura} + gatilho {a.tf_gatilho} | "
          f"{len(comuns)} pares")
    print(f"CHOCH -> VWAP ancorada -> reteste FALHA -> afasta {a.afasta_min} barra(s) "
          f"-> rejeicao no {a.tf_gatilho}")
    print(f"stop na vela de rejeicao +{a.stop_buffer} ATR15 | alvo={a.alvo} | "
          f"custo={a.custo_pct}%")
    print("=" * 92)

    if a.comparar_alvos:
        cabecalho()
        for alvo, rr in (('fundo', 0), ('rr_fixo', 1.5), ('rr_fixo', 2.0),
                         ('rr_fixo', 3.0), ('rr_fixo', 4.0)):
            c = dict(cfg, alvo=alvo, rr_fixo=rr or 2.0)
            t = rodar_tudo(h1s, m15s, c)
            nome = "alvo no fundo" if alvo == 'fundo' else f"alvo fixo 1:{rr}"
            linha(nome, medir(t))
        return

    cabecalho()
    todos = rodar_tudo(h1s, m15s, cfg, por_ativo=True)
    m = medir(todos)
    if not m:
        print("\nOperacoes insuficientes.")
        return
    print(f"\nTOTAL: {m['n']} operacoes | WR {m['wr']:.1f}% | R:R medio 1:{m['rr']:.2f}")
    print(f"  risco medio {m['risco']:.2f}% do preco -> taxa = "
          f"{0.10/max(m['risco'],1e-9):.3f}R por operacao")
    print(f"  expectativa {m['exp']:+.3f}R | {m['total']:+.1f}R | maxDD {m['dd']:.1f}R")
    print(f"  maior sequencia de perdas: {m['seq']}")
    print(f"  z {m['z']:+.2f} | IC95% [{m['ic'][0]:+.3f} , {m['ic'][1]:+.3f}]"
          + ("  >> dentro do acaso" if abs(m['z']) < 1.96 else "  (significativo)"))

    print("\nPOR ANO")
    ag = {}
    for t in todos:
        if t['resultado'] in FECHADOS:
            ag.setdefault(t['data'][:4], []).append(t['r'])
    pos = 0
    for ano in sorted(ag):
        v = ag[ano]
        R = sum(v)
        pos += R > 0
        print(f"  {ano}: {len(v):>5} operacoes | {R:>+8.1f}R | exp {R/len(v):>+7.3f}R")
    print(f"  --> {pos} de {len(ag)} anos positivos")

    with open("trades_mtf.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(todos[0].keys()))
        w.writeheader()
        w.writerows(todos)
    print("\nCSV: trades_mtf.csv")


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except Exception:
        print("\n=== ERRO ===")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
