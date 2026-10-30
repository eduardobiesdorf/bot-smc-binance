# -*- coding: utf-8 -*-
"""
Impulso com velas sequenciais -> VWAP ancorada do fundo ao topo -> reteste -> topo.

Sequencia (compra; venda e espelhada):
  1. IMPULSO: N velas seguidas na mesma direcao, com corpos expressivos,
     somando pelo menos K x ATR
  2. ancora a VWAP no FUNDO do impulso (primeira vela da sequencia)
  3. o preco corrige e TOCA a VWAP ancorada  -> POI = entrada
  4. stop abaixo | alvo = o ultimo TOPO deixado (extremo do impulso)

VWAP ancorada = soma(preco_tipico * volume) / soma(volume), desde a ancora.
Preco tipico = (maxima + minima + fechamento) / 3.

Le dados/<SIMBOLO>_<tf>.csv. Nao acessa a rede.

Uso:
    python backtest_vwap.py --tf 1h
    python backtest_vwap.py --tf 1h --painel
    python backtest_vwap.py --tf 1h --montecarlo 60
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


def media(vals, j):
    out, s = [], 0.0
    for k, x in enumerate(vals):
        s += x
        if k >= j:
            s -= vals[k - j]
            out.append(s / j)
        else:
            out.append(s / (k + 1))
    return out


def tipico(c):
    return (c[2] + c[3] + c[4]) / 3


# ------------------------------------------------------------------ sinal
def gerar(velas, cfg):
    n = len(velas)
    a = atr(velas, cfg['atr_periodo'])
    vols = [x[5] for x in velas]
    vol_m = media(vols, 50)
    trades = []
    ultimo_fim = -1
    i = max(cfg['velas_seq'] + cfg['atr_periodo'] + 55, 60)

    while i < n - 2:
        if i <= ultimo_fim or a[i] <= 0:
            i += 1
            continue

        for compra in ((True, False) if cfg['lado'] == 'ambos'
                       else ((True,) if cfg['lado'] == 'compra' else (False,))):
            s = i - cfg['velas_seq'] + 1          # primeira vela do impulso
            if s < 1:
                continue

            # --- 1. velas sequenciais e expressivas na mesma direcao
            ok = True
            for k in range(s, i + 1):
                o, h, l, c = velas[k][1], velas[k][2], velas[k][3], velas[k][4]
                rng = h - l
                if rng <= 0:
                    ok = False
                    break
                if compra and c <= o:
                    ok = False
                    break
                if not compra and c >= o:
                    ok = False
                    break
                if abs(c - o) / rng < cfg['corpo_min']:
                    ok = False
                    break
            if not ok:
                continue

            # --- tamanho do impulso
            desloc = (velas[i][4] - velas[s][1]) if compra else (velas[s][1] - velas[i][4])
            if desloc <= 0 or desloc / a[i] < cfg['sigma']:
                continue

            # --- volume confirmando
            if cfg['vol_mult'] > 0:
                if max(vols[s:i + 1]) < cfg['vol_mult'] * max(vol_m[i], 1e-12):
                    continue

            # --- 2. ancora no fundo (compra) / topo (venda) do impulso
            ancora = s
            topo = max(velas[k][2] for k in range(s, i + 1)) if compra else \
                   min(velas[k][3] for k in range(s, i + 1))

            t = montar(velas, i, ancora, topo, compra, a, cfg)
            if t:
                trades.append(t)
                ultimo_fim = i + t['barras']
            break
        i += 1
    return trades


def montar(velas, i, ancora, topo, compra, a, cfg):
    """Acompanha a VWAP ancorada e espera o reteste dela."""
    n = len(velas)
    pv = 0.0
    vv = 0.0
    for k in range(ancora, i + 1):
        pv += tipico(velas[k]) * velas[k][5]
        vv += velas[k][5]
    if vv <= 0:
        return None

    limite = min(n - 1, i + cfg['espera_max'])
    for j in range(i + 1, n):
        if j > limite:
            return None
        # A ordem limite fica no VWAP e no TOPO conhecidos ao FECHAR a barra j-1.
        # Usar o VWAP ja incluindo a barra j seria lookahead: uma barra de queda
        # puxa o VWAP para baixo e daria uma entrada melhor do que a disponivel.
        vwap = pv / max(vv, 1e-12)
        alvo_topo = topo

        tocou = velas[j][3] <= vwap if compra else velas[j][2] >= vwap

        # so depois de decidir, a barra j entra no acumulado para a proxima volta
        pv += tipico(velas[j]) * velas[j][5]
        vv += velas[j][5]
        topo = max(topo, velas[j][2]) if compra else min(topo, velas[j][3])

        if not tocou:
            continue

        entrada = vwap
        stop = entrada - a[j - 1] * cfg['stop_atr'] if compra else \
               entrada + a[j - 1] * cfg['stop_atr']
        risco = abs(entrada - stop)
        if risco <= 0:
            return None
        alvo = alvo_topo if cfg['alvo'] == 'topo' else \
               entrada + risco * cfg['rr_fixo'] * (1 if compra else -1)
        if (compra and alvo <= entrada) or (not compra and alvo >= entrada):
            return None
        rr = abs(alvo - entrada) / risco
        if rr < cfg['rr_min'] or (cfg['rr_max'] and rr > cfg['rr_max']):
            return None

        res, dur, r_bruto = simular(velas, j, compra, entrada, stop, alvo, cfg)
        custo = (entrada * cfg['custo_pct'] / 100) / risco
        return {'data': datetime.fromtimestamp(velas[j][0] / 1000, timezone.utc)
                        .strftime('%Y-%m-%d %H:%M'),
                'lado': 'compra' if compra else 'venda',
                'entrada': entrada, 'stop': stop, 'alvo': alvo, 'rr': rr,
                'espera': j - i, 'resultado': res, 'barras': (j - i) + dur,
                'r': r_bruto - custo}
    return None


def simular(velas, j0, compra, entrada, stop, alvo, cfg):
    risco = abs(entrada - stop)
    parcial_feita = False
    r_trav = 0.0
    stop_atual = stop
    limite = min(len(velas) - 1, j0 + cfg['tempo_max'])

    if (compra and velas[j0][3] <= stop_atual) or \
       (not compra and velas[j0][2] >= stop_atual):
        return 'loss', 0, -1.0

    for k in range(j0 + 1, len(velas)):
        hi, lo = velas[k][2], velas[k][3]
        em_r = (hi - entrada) / risco if compra else (entrada - lo) / risco
        bate_stop = lo <= stop_atual if compra else hi >= stop_atual
        bate_alvo = hi >= alvo if compra else lo <= alvo

        if cfg['parcial_em'] > 0 and not parcial_feita and em_r >= cfg['parcial_em'] \
                and not bate_stop:
            parcial_feita = True
            r_trav += cfg['parcial_frac'] * cfg['parcial_em']
            if cfg['breakeven']:
                stop_atual = entrada
                bate_stop = lo <= stop_atual if compra else hi >= stop_atual

        resto = 1.0 - (cfg['parcial_frac'] if parcial_feita else 0.0)
        if bate_stop:
            perda = 0.0 if (parcial_feita and cfg['breakeven']) else -1.0
            return ('be' if perda == 0 else 'loss'), k - j0, r_trav + resto * perda
        if bate_alvo:
            return 'win', k - j0, r_trav + resto * abs(alvo - entrada) / risco
        if k >= limite:
            sai = velas[k][4]
            pr = ((sai - entrada) if compra else (entrada - sai)) / risco
            return 'tempo', k - j0, r_trav + resto * pr
    return 'tempo', len(velas) - 1 - j0, r_trav


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
            'nao_perde': sum(1 for t in f if t['r'] > -0.05) / len(f) * 100,
            'ic': (m - 1.96 * se, m + 1.96 * se)}


def medir_dia(trades):
    f = [t for t in trades if t['resultado'] in FECHADOS]
    if len(f) < 5:
        return None
    pd = {}
    for t in f:
        pd.setdefault(t['data'][:10], []).append(t['r'])
    vals = [sum(v) / len(v) for v in pd.values()]
    if len(vals) < 3:
        return None
    m = sum(vals) / len(vals)
    dp = statistics.stdev(vals) if len(vals) > 1 else 0
    se = dp / math.sqrt(len(vals)) if dp else 1e-9
    return {'dias': len(vals), 'media': m, 'z': m / se}


def cabecalho():
    print(f"\n{'configuracao':>26} | {'n':>5} {'WR':>6} {'RR':>6} {'exp':>8} "
          f"{'total':>9} {'z':>6} {'z/dia':>6}")
    print("-" * 84)


def linha(nome, m, md=None):
    if not m:
        print(f"{nome:>26} |     -")
        return
    e = f" {md['z']:>+6.2f}" if md else ""
    print(f"{nome:>26} | {m['n']:>5} {m['wr']:>5.1f}% 1:{m['rr']:>4.2f} "
          f"{m['exp']:>+7.3f}R {m['total']:>+8.1f}R {m['z']:>+6.2f}{e}")


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


def embaralhar(v, rng):
    rets, geo = [], []
    for k in range(1, len(v)):
        c0, c1 = v[k - 1][4], v[k][4]
        if c0 <= 0 or c1 <= 0:
            return v
        rets.append(math.log(c1 / c0))
        geo.append((v[k][1] / c1, v[k][2] / c1, v[k][3] / c1, v[k][5]))
    ordem = list(range(len(rets)))
    rng.shuffle(ordem)
    out, p = [v[0]], v[0][4]
    for pos, k in enumerate(ordem):
        p *= math.exp(rets[k])
        o_r, h_r, l_r, vol = geo[k]
        o, h, l, c = p * o_r, p * h_r, p * l_r, p
        out.append((v[pos + 1][0], o, max(h, o, c), min(l, o, c), c, vol))
    return out


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='1h')
    ap.add_argument('--ativos', default='')
    ap.add_argument('--velas-seq', type=int, default=3,
                    help='velas seguidas na mesma direcao')
    ap.add_argument('--corpo-min', type=float, default=0.5,
                    help='corpo/range minimo de cada vela do impulso')
    ap.add_argument('--sigma', type=float, default=2.0,
                    help='tamanho minimo do impulso em ATR')
    ap.add_argument('--vol-mult', type=float, default=0.0)
    ap.add_argument('--alvo', choices=['topo', 'rr_fixo'], default='topo')
    ap.add_argument('--rr-fixo', type=float, default=2.0)
    ap.add_argument('--stop-atr', type=float, default=1.0)
    ap.add_argument('--rr-min', type=float, default=0.3)
    ap.add_argument('--rr-max', type=float, default=0.0)
    ap.add_argument('--espera-max', type=int, default=30)
    ap.add_argument('--tempo-max', type=int, default=120)
    ap.add_argument('--atr-periodo', type=int, default=14)
    ap.add_argument('--lado', choices=['ambos', 'compra', 'venda'], default='ambos')
    ap.add_argument('--parcial-em', type=float, default=0.0)
    ap.add_argument('--parcial-frac', type=float, default=0.5)
    ap.add_argument('--breakeven', action='store_true')
    ap.add_argument('--custo-pct', type=float, default=0.10)
    ap.add_argument('--painel', action='store_true')
    ap.add_argument('--montecarlo', type=int, default=0)
    a = ap.parse_args()

    cfg = {k: getattr(a, k) for k in
           ('velas_seq', 'corpo_min', 'sigma', 'vol_mult', 'alvo', 'rr_fixo',
            'stop_atr', 'rr_min', 'rr_max', 'espera_max', 'tempo_max',
            'atr_periodo', 'lado', 'parcial_em', 'parcial_frac', 'breakeven',
            'custo_pct')}

    ativos = {x.strip().upper() for x in a.ativos.split(',') if x.strip()} or None
    dados = carregar(a.tf, ativos)
    if not dados:
        print(f"Nenhum CSV *_{a.tf}.csv em {PASTA}/.")
        return
    d0 = min(datetime.fromtimestamp(v[0][0] / 1000, timezone.utc) for v in dados.values())
    d1 = max(datetime.fromtimestamp(v[-1][0] / 1000, timezone.utc) for v in dados.values())
    print("=" * 84)
    print(f"IMPULSO -> VWAP ANCORADA -> RETESTE | {a.tf} | {len(dados)} pares | "
          f"{d0:%Y-%m-%d} -> {d1:%Y-%m-%d}")
    print(f"{a.velas_seq} velas seguidas, corpo>={a.corpo_min:.0%}, impulso>={a.sigma} ATR "
          f"| alvo={a.alvo} | stop {a.stop_atr} ATR | espera {a.espera_max} barras")
    print("=" * 84)

    if a.painel:
        for lado in ('compra', 'venda'):
            print(f"\n### {lado}")
            cabecalho()
            for seq, sig, alvo in itertools.product((2, 3, 4), (1.5, 2.5), ('topo', 'rr_fixo')):
                c = dict(cfg, lado=lado, velas_seq=seq, sigma=sig, alvo=alvo)
                t = rodar_tudo(dados, c)
                linha(f"{seq}velas {sig}ATR {alvo}", medir(t), medir_dia(t))
        print("\nOlhe z/dia e a consistencia entre anos, nao a melhor celula.")
        return

    cabecalho()
    todos = rodar_tudo(dados, cfg, por_ativo=True)
    m = medir(todos)
    if not m:
        print("\nOperacoes insuficientes.")
        return
    md = medir_dia(todos)
    print(f"\nTOTAL: {m['n']} operacoes | WR {m['wr']:.1f}% | R:R medio 1:{m['rr']:.2f}")
    print(f"  expectativa {m['exp']:+.3f}R | {m['total']:+.1f}R | maxDD {m['dd']:.1f}R")
    print(f"  nao perdeu em {m['nao_perde']:.1f}% | maior sequencia de perdas: {m['seq']}")
    print(f"  z {m['z']:+.2f} | IC95% [{m['ic'][0]:+.3f} , {m['ic'][1]:+.3f}]"
          + ("  >> dentro do acaso" if abs(m['z']) < 1.96 else "  (significativo)"))
    if md:
        print(f"  por dia: {md['dias']} dias | z/dia {md['z']:+.2f}")

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

    if a.montecarlo:
        print(f"\n{'='*84}\nHIPOTESE NULA -- {a.montecarlo} series embaralhadas")
        rng = random.Random(42)
        am = []
        for s in range(a.montecarlo):
            falso = {k: embaralhar(v, rng) for k, v in dados.items()}
            mm = medir(rodar_tudo(falso, cfg))
            if mm:
                am.append(mm['exp'])
            if (s + 1) % 20 == 0:
                print(f"  ... {s+1}/{a.montecarlo}", flush=True)
        if len(am) >= 10:
            am.sort()
            q = lambda p: am[min(len(am) - 1, int(p * len(am)))]
            pct = sum(1 for x in am if x <= m['exp']) / len(am) * 100
            print(f"\nReal {m['exp']:+.3f}R | nulo p5 {q(.05):+.3f} mediana {q(.5):+.3f} "
                  f"p95 {q(.95):+.3f}")
            print(f">>> REAL NO PERCENTIL {pct:.0f} DO NULO")

    with open("trades_vwap.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(todos[0].keys()))
        w.writeheader()
        w.writerows(todos)
    print("\nCSV: trades_vwap.csv")


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except Exception:
        print("\n=== ERRO ===")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
