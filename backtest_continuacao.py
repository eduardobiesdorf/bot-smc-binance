# -*- coding: utf-8 -*-
"""
Continuacao de tendencia: rompimento -> reteste de POI -> entrada a favor.

TESE: o preco nao incorpora informacao nova de uma vez. Rompimento sinaliza
informacao entrando; o reteste e a chance de entrar antes do ajuste terminar.
E a versao em SERIE TEMPORAL do mesmo mecanismo do momentum transversal --
que e a unica tese que sobreviveu ao teste nulo ate aqui.

Sequencia:
  1. filtro de tendencia: preco acima da media longa (ex 200)
  2. rompimento: fecha acima da maxima das ultimas N barras
  3. reteste: preco volta ao POI
  4. entrada limite no POI, stop abaixo, alvo em multiplo de risco

Tres definicoes de POI (--poi):
  ma      - a media curta (ex 20)
  ob      - order block: ultima vela de baixa antes do rompimento
  poc     - point of control: faixa de preco com mais volume na janela
            (volume profile aproximado a partir de OHLCV)

Le dados/<SIMBOLO>_<tf>.csv. Nao acessa a rede.

Uso:
    python backtest_continuacao.py --tf 1h
    python backtest_continuacao.py --tf 1h --painel
    python backtest_continuacao.py --tf 1h --poi poc --montecarlo 200
"""
import argparse
import csv
import glob
import itertools
import math
import os
import random
import statistics
from datetime import datetime, timezone

PASTA = "dados"


# ------------------------------------------------------------------ dados
def carregar(tf, ativos=None):
    saida = {}
    for caminho in sorted(glob.glob(os.path.join(PASTA, f"*_{tf}.csv"))):
        simbolo = os.path.basename(caminho).rsplit(f"_{tf}.csv", 1)[0]
        if ativos and simbolo not in ativos:
            continue
        linhas = []
        with open(caminho, encoding='utf-8') as f:
            for r in csv.DictReader(f):
                try:
                    linhas.append((int(r['abertura_ms']), float(r['abertura']),
                                   float(r['maxima']), float(r['minima']),
                                   float(r['fechamento']), float(r['volume'])))
                except (ValueError, KeyError):
                    continue
        if len(linhas) >= 500:
            linhas.sort(key=lambda x: x[0])
            saida[simbolo] = linhas
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


def media(valores, janela):
    out, s = [], 0.0
    for k, v in enumerate(valores):
        s += v
        if k >= janela:
            s -= valores[k - janela]
            out.append(s / janela)
        else:
            out.append(s / (k + 1))
    return out


def ponto_de_controle(velas, ini, fim, bins=50):
    """
    Volume profile aproximado: distribui o volume de cada barra uniformemente
    pela faixa dela e devolve o preco da faixa com mais volume acumulado.
    Usa somente barras ate 'fim' -- sem lookahead.
    """
    jan = velas[ini:fim + 1]
    if not jan:
        return None
    lo = min(v[3] for v in jan)
    hi = max(v[2] for v in jan)
    if hi <= lo:
        return None
    largura = (hi - lo) / bins
    hist = [0.0] * bins
    for v in jan:
        b0 = max(0, min(bins - 1, int((v[3] - lo) / largura)))
        b1 = max(0, min(bins - 1, int((v[2] - lo) / largura)))
        n = b1 - b0 + 1
        parte = v[5] / n
        for b in range(b0, b1 + 1):
            hist[b] += parte
    melhor = max(range(bins), key=lambda b: hist[b])
    return lo + (melhor + 0.5) * largura


# ------------------------------------------------------------------ sinal
def gerar(velas, cfg):
    n = len(velas)
    fech = [v[4] for v in velas]
    vols = [v[5] for v in velas]
    a = atr(velas, cfg['atr_periodo'])
    ma_l = media(fech, cfg['ma_longa']) if cfg['ma_longa'] else None
    ma_c = media(fech, cfg['ma_curta'])
    vol_m = media(vols, 50)

    trades = []
    inicio = max(cfg['ma_longa'], cfg['ma_curta'], cfg['rompimento'],
                 cfg['poc_janela'], 60) + 2
    ultimo_fim = -1
    i = inicio

    while i < n - 2:
        if i <= ultimo_fim:
            i += 1
            continue
        c = fech[i]
        if a[i] <= 0:
            i += 1
            continue

        for compra in ((True, False) if cfg['lado'] == 'ambos'
                       else ((True,) if cfg['lado'] == 'compra' else (False,))):
            # --- 1. tendencia
            if ma_l is not None:
                if compra and c <= ma_l[i]:
                    continue
                if not compra and c >= ma_l[i]:
                    continue
                if cfg['ma_inclinada']:
                    if compra and ma_l[i] <= ma_l[i - cfg['ma_curta']]:
                        continue
                    if not compra and ma_l[i] >= ma_l[i - cfg['ma_curta']]:
                        continue

            # --- 2. rompimento de continuacao
            jan = range(i - cfg['rompimento'], i)
            if compra:
                if c <= max(velas[k][2] for k in jan):
                    continue
            else:
                if c >= min(velas[k][3] for k in jan):
                    continue

            # --- 3. volume confirmando o rompimento
            if cfg['vol_mult'] > 0 and vols[i] < cfg['vol_mult'] * max(vol_m[i], 1e-12):
                continue

            # --- 4. POI onde esperar o reteste
            if cfg['poi'] == 'ma':
                poi = ma_c[i]
            elif cfg['poi'] == 'ob':
                poi = None
                for k in range(i - 1, max(-1, i - 1 - cfg['ob_busca']), -1):
                    if (compra and fech[k] < velas[k][1]) or \
                       (not compra and fech[k] > velas[k][1]):
                        poi = velas[k][3] if compra else velas[k][2]
                        break
                if poi is None:
                    continue
            else:
                poi = ponto_de_controle(velas, i - cfg['poc_janela'], i)
                if poi is None:
                    continue

            # o POI tem de estar ATRAS do preco (e um reteste, nao perseguicao)
            if (compra and poi >= c) or (not compra and poi <= c):
                continue
            dist = abs(c - poi) / a[i]
            if dist > cfg['dist_max']:
                continue

            entrada = poi
            stop = (poi - a[i] * cfg['stop_atr']) if compra else \
                   (poi + a[i] * cfg['stop_atr'])
            risco = abs(entrada - stop)
            if risco <= 0:
                continue
            alvo = entrada + risco * cfg['rr'] * (1 if compra else -1)

            res, dur = simular(velas, i, compra, entrada, stop, alvo, cfg)
            if res == 'nao_ativou':
                continue
            custo = (entrada * cfg['custo_pct'] / 100) / risco
            r = (cfg['rr'] - custo) if res == 'win' else \
                (-1.0 - custo) if res == 'loss' else \
                (parcial(velas, i + dur, compra, entrada, risco) - custo)

            trades.append({
                'data': datetime.fromtimestamp(velas[i][0] / 1000, timezone.utc)
                        .strftime('%Y-%m-%d %H:%M'),
                'lado': 'compra' if compra else 'venda',
                'entrada': entrada, 'stop': stop, 'alvo': alvo, 'rr': cfg['rr'],
                'dist_atr': round(dist, 2), 'resultado': res, 'barras': dur, 'r': r})
            ultimo_fim = i + dur
            break
        i += 1
    return trades


def parcial(velas, j, compra, entrada, risco):
    j = min(j, len(velas) - 1)
    s = velas[j][4]
    return ((s - entrada) if compra else (entrada - s)) / risco


def simular(velas, i, compra, entrada, stop, alvo, cfg):
    ativado = False
    limite_fill = min(len(velas) - 1, i + cfg['espera_max'])
    for j in range(i + 1, len(velas)):
        hi, lo = velas[j][2], velas[j][3]
        if not ativado:
            if j > limite_fill:
                return 'nao_ativou', j - i
            if (compra and lo <= entrada) or (not compra and hi >= entrada):
                ativado = True
                if (compra and lo <= stop) or (not compra and hi >= stop):
                    return 'loss', j - i
                limite_saida = min(len(velas) - 1, j + cfg['tempo_max'])
            continue
        bate_stop = lo <= stop if compra else hi >= stop
        bate_alvo = hi >= alvo if compra else lo <= alvo
        if bate_stop and bate_alvo:
            return 'loss', j - i
        if bate_stop:
            return 'loss', j - i
        if bate_alvo:
            return 'win', j - i
        if j >= limite_saida:
            return 'tempo', j - i
    return ('tempo' if ativado else 'nao_ativou'), len(velas) - 1 - i


# ------------------------------------------------------------------ metricas
def medir(trades):
    fech = [t for t in trades if t['resultado'] in ('win', 'loss', 'tempo')]
    if len(fech) < 10:
        return None
    w = sum(1 for t in fech if t['resultado'] == 'win')
    rs = [t['r'] for t in fech]
    m = sum(rs) / len(rs)
    dp = statistics.stdev(rs) if len(rs) > 1 else 0
    se = dp / math.sqrt(len(rs)) if dp else 1e-9
    acc = pico = dd = 0.0
    for t in sorted(fech, key=lambda x: x['data']):
        acc += t['r']
        pico = max(pico, acc)
        dd = min(dd, acc - pico)
    return {'n': len(fech), 'w': w, 'wr': w / len(fech) * 100, 'exp': m,
            'total': sum(rs), 'z': m / se, 'dd': dd,
            'ic': (m - 1.96 * se, m + 1.96 * se)}


def medir_dia(trades):
    fech = [t for t in trades if t['resultado'] in ('win', 'loss', 'tempo')]
    if len(fech) < 5:
        return None
    pd = {}
    for t in fech:
        pd.setdefault(t['data'][:10], []).append(t['r'])
    vals = [sum(v) / len(v) for v in pd.values()]
    if len(vals) < 3:
        return None
    m = sum(vals) / len(vals)
    dp = statistics.stdev(vals) if len(vals) > 1 else 0
    se = dp / math.sqrt(len(vals)) if dp else 1e-9
    return {'dias': len(vals), 'media': m, 'z': m / se}


def por_ano(trades):
    """A tabela que decide: um ano bom entre cinco ruins NAO e edge."""
    ag = {}
    for t in trades:
        if t['resultado'] in ('win', 'loss', 'tempo'):
            a = t['data'][:4]
            ag.setdefault(a, []).append(t['r'])
    return {a: (len(v), sum(v), sum(v) / len(v)) for a, v in sorted(ag.items())}


def cabecalho():
    print(f"\n{'configuracao':>26} | {'n':>5} {'WR':>6} {'exp':>8} {'total':>9} "
          f"{'z':>6} {'dias':>5} {'z/dia':>6}")
    print("-" * 82)


def linha(nome, m, md=None):
    if not m:
        print(f"{nome:>26} |     -")
        return
    e = f" {md['dias']:>5} {md['z']:>+6.2f}" if md else ""
    print(f"{nome:>26} | {m['n']:>5} {m['wr']:>5.1f}% {m['exp']:>+7.3f}R "
          f"{m['total']:>+8.1f}R {m['z']:>+6.2f}{e}")


# ------------------------------------------------------------------ nulo
def embaralhar(velas, rng):
    rets, geo = [], []
    for k in range(1, len(velas)):
        c0, c1 = velas[k - 1][4], velas[k][4]
        if c0 <= 0 or c1 <= 0:
            return velas
        rets.append(math.log(c1 / c0))
        geo.append((velas[k][1] / c1, velas[k][2] / c1, velas[k][3] / c1, velas[k][5]))
    ordem = list(range(len(rets)))
    rng.shuffle(ordem)
    out, p = [velas[0]], velas[0][4]
    for pos, k in enumerate(ordem):
        p *= math.exp(rets[k])
        o_r, h_r, l_r, vol = geo[k]
        o, h, l, c = p * o_r, p * h_r, p * l_r, p
        out.append((velas[pos + 1][0], o, max(h, o, c), min(l, o, c), c, vol))
    return out


def rodar_tudo(dados, cfg, por_ativo=False):
    todos = []
    for s, v in sorted(dados.items()):
        t = gerar(v, cfg)
        for x in t:
            x['ativo'] = s
        todos.extend(t)
        if por_ativo:
            linha(s.replace('USDT', ''), medir(t), medir_dia(t))
    return todos


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='1h')
    ap.add_argument('--ativos', default='')
    ap.add_argument('--ma-longa', type=int, default=200, help='0 = sem filtro')
    ap.add_argument('--ma-curta', type=int, default=20)
    ap.add_argument('--ma-inclinada', action='store_true')
    ap.add_argument('--rompimento', type=int, default=20, help='barras da maxima rompida')
    ap.add_argument('--poi', choices=['ma', 'ob', 'poc'], default='ma')
    ap.add_argument('--poc-janela', type=int, default=120)
    ap.add_argument('--ob-busca', type=int, default=10)
    ap.add_argument('--dist-max', type=float, default=3.0,
                    help='distancia maxima preco->POI em ATR')
    ap.add_argument('--vol-mult', type=float, default=0.0)
    ap.add_argument('--stop-atr', type=float, default=1.0)
    ap.add_argument('--rr', type=float, default=1.7)
    ap.add_argument('--espera-max', type=int, default=20, help='barras ate o reteste')
    ap.add_argument('--tempo-max', type=int, default=48, help='barras no trade')
    ap.add_argument('--atr-periodo', type=int, default=14)
    ap.add_argument('--lado', choices=['ambos', 'compra', 'venda'], default='ambos')
    ap.add_argument('--custo-pct', type=float, default=0.10)
    ap.add_argument('--painel', action='store_true')
    ap.add_argument('--montecarlo', type=int, default=0)
    a = ap.parse_args()

    cfg = {k: getattr(a, k) for k in
           ('ma_longa', 'ma_curta', 'ma_inclinada', 'rompimento', 'poi', 'poc_janela',
            'ob_busca', 'dist_max', 'vol_mult', 'stop_atr', 'rr', 'espera_max',
            'tempo_max', 'atr_periodo', 'lado', 'custo_pct')}

    ativos = {x.strip().upper() for x in a.ativos.split(',') if x.strip()} or None
    dados = carregar(a.tf, ativos)
    if not dados:
        print(f"Nenhum CSV *_{a.tf}.csv em {PASTA}/.")
        return

    d0 = min(datetime.fromtimestamp(v[0][0] / 1000, timezone.utc) for v in dados.values())
    d1 = max(datetime.fromtimestamp(v[-1][0] / 1000, timezone.utc) for v in dados.values())
    print("=" * 82)
    print(f"CONTINUACAO DE TENDENCIA | {a.tf} | {len(dados)} pares | "
          f"{d0:%Y-%m-%d} -> {d1:%Y-%m-%d}")
    print(f"tendencia: preco vs MA{a.ma_longa} | rompimento de {a.rompimento} barras | "
          f"POI={a.poi}" + (f"(MA{a.ma_curta})" if a.poi == 'ma' else ""))
    print(f"stop={a.stop_atr} ATR | alvo={a.rr}R | espera={a.espera_max} barras | "
          f"lado={a.lado} | custo={a.custo_pct}%")
    print("=" * 82)

    if a.painel:
        for poi in ('ma', 'ob', 'poc'):
            print(f"\n### POI = {poi}")
            cabecalho()
            for romp, rr in itertools.product((10, 20, 40), (1.0, 1.7, 3.0)):
                c = dict(cfg, poi=poi, rompimento=romp, rr=rr)
                t = rodar_tudo(dados, c)
                linha(f"romp{romp} alvo{rr}R", medir(t), medir_dia(t))
        print("\nOlhe z/dia e a consistencia ENTRE ANOS, nao a melhor celula.")
        return

    cabecalho()
    todos = rodar_tudo(dados, cfg, por_ativo=True)
    m = medir(todos)
    if not m:
        print("\nOperacoes insuficientes.")
        return
    md = medir_dia(todos)
    print(f"\nTOTAL: {m['n']} operacoes | WR {m['wr']:.1f}% | exp {m['exp']:+.3f}R | "
          f"{m['total']:+.1f}R | maxDD {m['dd']:.1f}R")
    print(f"  z {m['z']:+.2f} | IC95% [{m['ic'][0]:+.3f} , {m['ic'][1]:+.3f}]"
          + ("  >> dentro do acaso" if abs(m['z']) < 1.96 else "  (significativo)"))
    if md:
        print(f"  por dia: {md['dias']} dias | media {md['media']:+.3f}R | "
              f"z/dia {md['z']:+.2f}")

    print("\nPOR ANO  (um ano bom entre varios ruins NAO e edge)")
    anos = por_ano(todos)
    pos = sum(1 for _, (_, R, _) in anos.items() if R > 0)
    for ano, (n, R, e) in anos.items():
        print(f"  {ano}: {n:>5} operacoes | {R:>+8.1f}R | exp {e:>+7.3f}R")
    print(f"  --> {pos} de {len(anos)} anos positivos")

    if a.montecarlo:
        print(f"\n{'='*82}\nHIPOTESE NULA -- {a.montecarlo} series embaralhadas")
        rng = random.Random(42)
        am = []
        for s in range(a.montecarlo):
            falso = {k: embaralhar(v, rng) for k, v in dados.items()}
            mm = medir(rodar_tudo(falso, cfg))
            if mm:
                am.append(mm['exp'])
            if (s + 1) % 25 == 0:
                print(f"  ... {s+1}/{a.montecarlo}", flush=True)
        if len(am) >= 10:
            am.sort()
            q = lambda p: am[min(len(am) - 1, int(p * len(am)))]
            pct = sum(1 for x in am if x <= m['exp']) / len(am) * 100
            print(f"\nReal {m['exp']:+.3f}R | nulo p5 {q(.05):+.3f} "
                  f"mediana {q(.5):+.3f} p95 {q(.95):+.3f}")
            print(f">>> REAL NO PERCENTIL {pct:.0f} DO NULO")
            print("    >95 = ha sinal | 5-95 = igual ao acaso")

    with open("trades_continuacao.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(todos[0].keys()))
        w.writeheader()
        w.writerows(todos)
    print("\nCSV: trades_continuacao.csv")


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except Exception:
        print("\n=== ERRO ===")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
