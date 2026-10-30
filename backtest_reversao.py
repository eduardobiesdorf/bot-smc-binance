# -*- coding: utf-8 -*-
"""
Reversao apos movimento forcado (caca a liquidacao).

TESE: um movimento violento e rapido em poucas barras costuma ser fluxo FORCADO
-- liquidacao de posicoes, chamada de margem, saida obrigatoria. Quem compra ali
nao compra por querer, compra por ser obrigado. Quando o fluxo forcado se esgota,
nao sobra comprador voluntario naquele preco e o movimento reverte.
Operar contra = ser pago por fornecer liquidez a quem tem urgencia.

Le os CSVs de dados/ (gerados por baixar_dados.py). Nao acessa a rede.

Uso:
    python backtest_reversao.py --tf 1h
    python backtest_reversao.py --tf 30m --lado venda --alvo retorno_total
    python backtest_reversao.py --tf 1h --painel
    python backtest_reversao.py --tf 1h --montecarlo 200
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
    """Le dados/<SIMBOLO>_<tf>.csv -> {simbolo: [(ms, o,h,l,c,v), ...]}"""
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
        if len(linhas) >= 300:
            linhas.sort(key=lambda x: x[0])
            saida[simbolo] = linhas
    return saida


def atr(velas, periodo=14):
    tr = [velas[0][2] - velas[0][3]]
    for k in range(1, len(velas)):
        c0 = velas[k - 1][4]
        tr.append(max(velas[k][2] - velas[k][3],
                      abs(velas[k][2] - c0), abs(velas[k][3] - c0)))
    out, soma = [], 0.0
    for k, v in enumerate(tr):
        soma += v
        if k >= periodo:
            soma -= tr[k - periodo]
            out.append(soma / periodo)
        else:
            out.append(soma / (k + 1))
    return out


def media_movel(valores, janela):
    out, soma = [], 0.0
    for k, v in enumerate(valores):
        soma += v
        if k >= janela:
            soma -= valores[k - janela]
            out.append(soma / janela)
        else:
            out.append(soma / (k + 1))
    return out


# ------------------------------------------------------------------ sinal
def gerar(velas, cfg):
    """
    Detecta o movimento forcado e monta a operacao contra ele.
    Usa somente dados ate a barra i -- sem lookahead.
    """
    n = len(velas)
    a = atr(velas, cfg['atr_periodo'])
    vols = [v[5] for v in velas]
    vol_med = media_movel(vols, cfg['vol_janela'])
    trades = []
    i = cfg['barras'] + cfg['atr_periodo'] + cfg['vol_janela'] + 2
    ultimo_fim = -1

    while i < n - 1:
        if i <= ultimo_fim:                      # sem operacoes sobrepostas
            i += 1
            continue

        ini = i - cfg['barras']
        p_ini, p_fim = velas[ini][4], velas[i][4]
        if p_ini <= 0 or a[i] <= 0:
            i += 1
            continue

        desloc = p_fim - p_ini
        em_atr = abs(desloc) / a[i]
        if em_atr < cfg['sigma']:
            i += 1
            continue

        # eficiencia: o movimento foi direcional ou foi vaivem?
        caminho = sum(abs(velas[k][4] - velas[k - 1][4]) for k in range(ini + 1, i + 1))
        if caminho <= 0 or abs(desloc) / caminho < cfg['eficiencia']:
            i += 1
            continue

        # pico de volume: fluxo forcado deixa rastro
        if cfg['vol_mult'] > 0:
            vm = max(vol_med[i], 1e-12)
            if max(vols[ini + 1:i + 1]) < cfg['vol_mult'] * vm:
                i += 1
                continue

        subiu = desloc > 0
        compra = not subiu                        # opera CONTRA o movimento
        if cfg['lado'] == 'venda' and compra:
            i += 1
            continue
        if cfg['lado'] == 'compra' and not compra:
            i += 1
            continue

        entrada = p_fim
        extremo = max(velas[k][2] for k in range(ini, i + 1)) if subiu else \
                  min(velas[k][3] for k in range(ini, i + 1))
        if compra:
            stop = min(extremo, entrada) - a[i] * cfg['stop_atr']
        else:
            stop = max(extremo, entrada) + a[i] * cfg['stop_atr']
        risco = abs(entrada - stop)
        if risco <= 0:
            i += 1
            continue

        if cfg['alvo'] == 'retorno_total':
            alvo = p_ini                          # volta ao inicio do movimento
        elif cfg['alvo'] == 'fib50':
            alvo = p_fim - desloc * 0.5
        else:
            alvo = entrada + risco * cfg['rr_fixo'] * (1 if compra else -1)

        if (compra and alvo <= entrada) or (not compra and alvo >= entrada):
            i += 1
            continue
        rr = abs(alvo - entrada) / risco
        if rr < cfg['rr_min'] or (cfg['rr_max'] and rr > cfg['rr_max']):
            i += 1
            continue

        res, dur = simular(velas, i, compra, entrada, stop, alvo, cfg)
        custo = (entrada * cfg['custo_pct'] / 100) / risco
        r = (rr - custo) if res == 'win' else (-1.0 - custo) if res == 'loss' else \
            (res_parcial(velas, i + dur, compra, entrada, risco) - custo)

        trades.append({
            'data': datetime.fromtimestamp(velas[i][0] / 1000, timezone.utc).strftime('%Y-%m-%d %H:%M'),
            'lado': 'compra' if compra else 'venda', 'em_atr': round(em_atr, 2),
            'entrada': entrada, 'stop': stop, 'alvo': alvo, 'rr': rr,
            'resultado': res, 'barras': dur, 'r': r})
        ultimo_fim = i + dur
        i += 1

    return trades


def res_parcial(velas, j, compra, entrada, risco):
    """Saida por tempo: fecha a mercado, resultado proporcional em R."""
    j = min(j, len(velas) - 1)
    saida = velas[j][4]
    return ((saida - entrada) if compra else (entrada - saida)) / risco


def simular(velas, i, compra, entrada, stop, alvo, cfg):
    limite = min(len(velas) - 1, i + cfg['tempo_max'])
    for j in range(i + 1, len(velas)):
        hi, lo = velas[j][2], velas[j][3]
        bate_stop = lo <= stop if compra else hi >= stop
        bate_alvo = hi >= alvo if compra else lo <= alvo
        if bate_stop and bate_alvo:
            return 'loss', j - i          # conservador
        if bate_stop:
            return 'loss', j - i
        if bate_alvo:
            return 'win', j - i
        if j >= limite:
            return 'tempo', j - i
    return 'tempo', len(velas) - 1 - i


# ------------------------------------------------------------------ metricas
def medir(trades):
    fech = [t for t in trades if t['resultado'] in ('win', 'loss', 'tempo')]
    if len(fech) < 10:
        return None
    w = sum(1 for t in fech if t['resultado'] == 'win')
    l = sum(1 for t in fech if t['resultado'] == 'loss')
    tp = sum(1 for t in fech if t['resultado'] == 'tempo')
    rs = [t['r'] for t in fech]
    media = sum(rs) / len(rs)
    dp = statistics.stdev(rs) if len(rs) > 1 else 0
    se = dp / math.sqrt(len(rs)) if dp else 1e-9
    rr_w = (sum(t['rr'] for t in fech if t['resultado'] == 'win') / w) if w else 0
    acc = pico = dd = 0.0
    for t in sorted(fech, key=lambda x: x['data']):
        acc += t['r']
        pico = max(pico, acc)
        dd = min(dd, acc - pico)
    return {'n': len(fech), 'w': w, 'l': l, 'tempo': tp,
            'wr': w / len(fech) * 100, 'rr_w': rr_w, 'exp': media,
            'total': sum(rs), 'z': media / se, 'dd': dd,
            'ic': (media - 1.96 * se, media + 1.96 * se)}


def medir_por_dia(trades):
    """
    Em panico, TODOS os pares disparam juntos: as operacoes nao sao
    independentes. A unidade correta de amostra e o DIA de evento.
    """
    fech = [t for t in trades if t['resultado'] in ('win', 'loss', 'tempo')]
    if len(fech) < 5:
        return None
    por_dia = {}
    for t in fech:
        d = t['data'][:10]
        por_dia.setdefault(d, []).append(t['r'])
    dias = {d: sum(v) / len(v) for d, v in por_dia.items()}
    vals = list(dias.values())
    if len(vals) < 3:
        return None
    media = sum(vals) / len(vals)
    dp = statistics.stdev(vals) if len(vals) > 1 else 0
    se = dp / math.sqrt(len(vals)) if dp else 1e-9
    soma_dia = {d: sum(v) for d, v in por_dia.items()}
    top3 = sorted(soma_dia.values(), reverse=True)[:3]
    return {'dias': len(vals), 'por_dia': len(fech) / len(vals), 'media': media,
            'z': media / se, 'ic': (media - 1.96 * se, media + 1.96 * se),
            'top3': sum(top3), 'total': sum(soma_dia.values())}


def imprimir_dias(md):
    if not md:
        print("  (eventos insuficientes para a conta por dia)")
        return
    print(f"\n  AMOSTRA REAL -- cada DIA de evento conta uma vez")
    print(f"    {md['dias']} dias de evento | {md['por_dia']:.1f} pares por dia em media")
    print(f"    media {md['media']:+.3f}R por dia | z {md['z']:+.2f} | "
          f"IC95% [{md['ic'][0]:+.3f} , {md['ic'][1]:+.3f}]")
    print("    " + (">> dentro do acaso" if abs(md['z']) < 1.96 else "(significativo)"))
    resto = md['total'] - md['top3']
    print(f"    os 3 melhores dias somam {md['top3']:+.1f}R | "
          f"os outros {md['dias']-3} dias somam {resto:+.1f}R")
    if md['total'] > 0 and resto <= 0:
        print("    >> SEM esses 3 dias a estrategia e PERDEDORA: sao eventos, nao edge")


def imprimir(m, titulo):
    if not m:
        print(f"{titulo}: operacoes insuficientes")
        return
    be = 1 / (1 + m['rr_w']) * 100 if m['rr_w'] else float('nan')
    print(f"\n{titulo}")
    print(f"  {m['n']} operacoes | wins {m['w']} | losses {m['l']} | por tempo {m['tempo']}")
    print(f"  win rate {m['wr']:.1f}% | R:R dos wins 1:{m['rr_w']:.2f} | equilibrio {be:.1f}%")
    print(f"  expectativa {m['exp']:+.3f}R | total {m['total']:+.1f}R | maxDD {m['dd']:.1f}R")
    print(f"  z {m['z']:+.2f} | IC95% [{m['ic'][0]:+.3f} , {m['ic'][1]:+.3f}]", end="")
    print("  >> dentro do acaso" if abs(m['z']) < 1.96 else "  (significativo)")


def linha(nome, m, md=None):
    if not m:
        print(f"{nome:>22} |     -")
        return
    extra = f" {md['dias']:>5} {md['z']:>+6.2f}" if md else ""
    print(f"{nome:>22} | {m['n']:>5} {m['wr']:>6.1f}% 1:{m['rr_w']:>5.2f} "
          f"{m['exp']:>+7.3f}R {m['total']:>+8.1f}R {m['z']:>+6.2f}{extra}")


def cabecalho():
    print(f"\n{'configuracao':>22} | {'n':>5} {'WR':>7} {'RRwin':>7} {'exp':>8} "
          f"{'total':>9} {'z':>6} {'dias':>5} {'z/dia':>6}")
    print("-" * 84)


# ------------------------------------------------------------------ main
def rodar_tudo(dados, cfg, por_ativo=False):
    todos = []
    for simbolo, velas in sorted(dados.items()):
        t = gerar(velas, cfg)
        for x in t:
            x['ativo'] = simbolo
        todos.extend(t)
        if por_ativo:
            linha(simbolo.replace('USDT', ''), medir(t))
    return todos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tf', default='1h', help='intervalo dos CSVs em dados/')
    ap.add_argument('--ativos', default='')
    ap.add_argument('--barras', type=int, default=3, help='barras do movimento')
    ap.add_argument('--sigma', type=float, default=3.0, help='tamanho minimo em ATR')
    ap.add_argument('--eficiencia', type=float, default=0.6,
                    help='direcional/caminho total (1.0 = linha reta)')
    ap.add_argument('--vol-mult', type=float, default=2.0,
                    help='pico de volume exigido (0 = nao exige)')
    ap.add_argument('--vol-janela', type=int, default=50)
    ap.add_argument('--atr-periodo', type=int, default=14)
    ap.add_argument('--lado', choices=['ambos', 'venda', 'compra'], default='compra',
                    help='venda = so opera contra movimento de ALTA')
    ap.add_argument('--alvo', choices=['retorno_total', 'fib50', 'rr_fixo'],
                    default='fib50')
    ap.add_argument('--rr-fixo', type=float, default=1.7)
    ap.add_argument('--stop-atr', type=float, default=0.5)
    ap.add_argument('--rr-min', type=float, default=0.5)
    ap.add_argument('--rr-max', type=float, default=0.0, help='0 = sem teto')
    ap.add_argument('--tempo-max', type=int, default=24, help='barras ate sair a mercado')
    ap.add_argument('--custo-pct', type=float, default=0.10)
    ap.add_argument('--painel', action='store_true', help='varre sigma x alvo x lado')
    ap.add_argument('--montecarlo', type=int, default=0)
    ap.add_argument('--trimestres', action='store_true')
    a = ap.parse_args()

    cfg = {k: getattr(a, k) for k in
           ('barras', 'sigma', 'eficiencia', 'vol_mult', 'vol_janela', 'atr_periodo',
            'lado', 'alvo', 'rr_fixo', 'stop_atr', 'rr_min', 'rr_max', 'tempo_max',
            'custo_pct')}

    ativos = {x.strip().upper() for x in a.ativos.split(',') if x.strip()} or None
    dados = carregar(a.tf, ativos)
    if not dados:
        print(f"Nenhum CSV *_{a.tf}.csv em {PASTA}/. Rode o workflow 'Baixar dados'.")
        return

    barras = sum(len(v) for v in dados.values())
    d0 = min(datetime.fromtimestamp(v[0][0] / 1000, timezone.utc) for v in dados.values())
    d1 = max(datetime.fromtimestamp(v[-1][0] / 1000, timezone.utc) for v in dados.values())
    print("=" * 70)
    print(f"REVERSAO APOS MOVIMENTO FORCADO | {a.tf} | {len(dados)} pares")
    print(f"{d0:%Y-%m-%d} -> {d1:%Y-%m-%d} | {barras:,} barras")
    print(f"mov={a.barras} barras >= {a.sigma} ATR | eficiencia>={a.eficiencia} | "
          f"volume>={a.vol_mult}x | lado={a.lado}")
    print(f"stop={a.stop_atr} ATR | alvo={a.alvo} | saida por tempo={a.tempo_max} barras | "
          f"custo={a.custo_pct}%")
    print("=" * 70)

    if a.painel:
        for lado in ('venda', 'compra'):
            print(f"\n### operando contra movimento de "
                  f"{'ALTA' if lado == 'venda' else 'BAIXA'}")
            cabecalho()
            for sig, alvo in itertools.product((2.0, 3.0, 4.0, 5.0),
                                               ('retorno_total', 'fib50', 'rr_fixo')):
                c = dict(cfg, sigma=sig, alvo=alvo, lado=lado)
                t = rodar_tudo(dados, c)
                linha(f"{sig:.0f}ATR {alvo}", medir(t), medir_por_dia(t))
        print("\nOlhe z/dia, NAO o z por operacao. Em panico os 10 pares disparam")
        print("juntos, entao 10 operacoes sao 1 evento. O z por operacao mente.")
        return

    cabecalho()
    todos = rodar_tudo(dados, cfg, por_ativo=True)
    m = medir(todos)
    imprimir(m, "TOTAL")
    if not m:
        return
    imprimir_dias(medir_por_dia(todos))

    if a.trimestres:
        print("\nPOR TRIMESTRE")
        cabecalho()
        for tri in sorted({t['data'][:7] for t in todos}):
            linha(tri, medir([t for t in todos if t['data'][:7] == tri]))

    if a.montecarlo:
        print(f"\n{'='*70}\nHIPOTESE NULA -- {a.montecarlo} series com retornos embaralhados")
        print("Preserva volatilidade e formato da barra, destroi a SEQUENCIA.")
        print("Se a tese e sobre o que acontece DEPOIS do movimento, ela tem que")
        print("ir melhor no grafico real do que no embaralhado.")
        print("=" * 70)
        rng = random.Random(42)
        amostras = []
        for s in range(a.montecarlo):
            falso = {k: embaralhar(v, rng) for k, v in dados.items()}
            mm = medir(rodar_tudo(falso, cfg))
            if mm:
                amostras.append(mm['exp'])
            if (s + 1) % 25 == 0:
                print(f"  ... {s+1}/{a.montecarlo}", flush=True)
        if len(amostras) >= 10:
            amostras.sort()
            q = lambda p: amostras[min(len(amostras) - 1, int(p * len(amostras)))]
            pct = sum(1 for x in amostras if x <= m['exp']) / len(amostras) * 100
            print(f"\nReal {m['exp']:+.3f}R | nulo: p5 {q(.05):+.3f} mediana {q(.5):+.3f} "
                  f"p95 {q(.95):+.3f}")
            print(f">>> REAL NO PERCENTIL {pct:.0f} DO NULO")
            print("    >95 = ha sinal | 5-95 = igual ao acaso | <5 = invertido")

    with open("trades_reversao.csv", 'w', newline='', encoding='utf-8') as f:
        wtr = csv.DictWriter(f, fieldnames=list(todos[0].keys()))
        wtr.writeheader()
        wtr.writerows(todos)
    print("\nCSV: trades_reversao.csv")


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
    out, preco = [velas[0]], velas[0][4]
    for pos, k in enumerate(ordem):
        preco *= math.exp(rets[k])
        o_r, h_r, l_r, vol = geo[k]
        o, h, l, c = preco * o_r, preco * h_r, preco * l_r, preco
        out.append((velas[pos + 1][0], o, max(h, o, c), min(l, o, c), c, vol))
    return out


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except Exception:
        print("\n=== ERRO ===")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
