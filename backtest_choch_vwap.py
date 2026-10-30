# -*- coding: utf-8 -*-
"""
CHOCH -> VWAP ancorada no fundo estrutural -> reteste -> alvo no topo do CHOCH.

Sequencia (compra; venda e espelhada):
  1. estrutura de baixa vigente (topos e fundos descendentes)
  2. CHOCH: o preco FECHA acima do ultimo topo estrutural -> muda o carater
  3. ancora a VWAP no FUNDO de onde saiu esse impulso (o fundo estrutural,
     nao a primeira vela da sequencia)
  4. o preco corrige e TOCA a VWAP ancorada -> gatilho de entrada
  5. alvo = o ultimo TOPO deixado pelo impulso do CHOCH

Diferenca para o backtest_vwap.py: la o gatilho era qualquer impulso de N
velas, o que disparava no meio de tendencia ja estabelecida. Aqui exige-se
mudanca de carater, e a ancora vai no fundo estrutural.

Le dados/<SIMBOLO>_<tf>.csv. Nao acessa a rede.

Uso:
    python backtest_choch_vwap.py --tf 1h
    python backtest_choch_vwap.py --tf 1h --painel
    python backtest_choch_vwap.py --tf 1h --montecarlo 60
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
def gerar(velas, cfg):
    """
    Maquina de estado da estrutura. So dispara em CHOCH -- quebra CONTRA
    a tendencia vigente. BOS (quebra a favor) e ignorado, a nao ser que
    cfg['evento'] peca o contrario.
    """
    n = len(velas)
    a = atr(velas, cfg['atr_periodo'])
    altas, baixas = pivos(velas, cfg['pivo_esq'], cfg['pivo_dir'])
    sh = sl = None
    tendencia = 'indefinida'
    trades = []
    ultimo_fim = -1

    for i in range(n - 2):
        for k, p in altas.get(i, []):
            if sh is None or k > sh[0]:
                sh = (k, p)
        for k, p in baixas.get(i, []):
            if sl is None or k > sl[0]:
                sl = (k, p)
        c = velas[i][4]

        evento = lado = None
        if sh is not None and c > sh[1]:
            evento = 'choch' if tendencia == 'baixa' else 'bos'
            lado, ref = 'compra', sh
            tendencia, sh = 'alta', None
        elif sl is not None and c < sl[1]:
            evento = 'choch' if tendencia == 'alta' else 'bos'
            lado, ref = 'venda', sl
            tendencia, sl = 'baixa', None
        if evento is None or i <= ultimo_fim or a[i] <= 0:
            continue
        if cfg['evento'] != 'ambos' and evento != cfg['evento']:
            continue
        if cfg['lado'] != 'ambos' and lado != cfg['lado']:
            continue

        compra = lado == 'compra'
        # --- ancora: o FUNDO estrutural de onde saiu o impulso do CHOCH
        jan = range(max(0, ref[0]), i + 1)
        ancora = min(jan, key=lambda k: velas[k][3]) if compra else \
                 max(jan, key=lambda k: velas[k][2])
        if i - ancora < cfg['impulso_min']:
            continue
        # a ancora precisa ser um FUNDO de verdade, nao meio de tendencia:
        # tem de ser a minima das ultimas N barras antes dela
        if cfg['fundo_janela'] > 0:
            ini_f = max(0, ancora - cfg['fundo_janela'])
            if compra:
                if any(velas[k][3] < velas[ancora][3] for k in range(ini_f, ancora)):
                    continue
            else:
                if any(velas[k][2] > velas[ancora][2] for k in range(ini_f, ancora)):
                    continue
        desloc = (velas[i][4] - velas[ancora][3]) if compra else \
                 (velas[ancora][2] - velas[i][4])
        if desloc <= 0 or desloc / a[i] < cfg['sigma']:
            continue

        t = montar(velas, i, ancora, compra, a, cfg)
        if t:
            t['evento'] = evento
            trades.append(t)
            ultimo_fim = i + t['barras']
    return trades


def montar(velas, i, ancora, compra, a, cfg):
    n = len(velas)
    pv = vv = 0.0
    for k in range(ancora, i + 1):
        pv += tipico(velas[k]) * velas[k][5]
        vv += velas[k][5]
    if vv <= 0:
        return None
    topo = max(velas[k][2] for k in range(ancora, i + 1)) if compra else \
           min(velas[k][3] for k in range(ancora, i + 1))
    base = velas[ancora][3] if compra else velas[ancora][2]
    limite = min(n - 1, i + cfg['espera_max'])

    for j in range(i + 1, n):
        if j > limite:
            return None
        # valores conhecidos ao FECHAR a barra j-1 (sem lookahead)
        vwap = pv / max(vv, 1e-12)
        alvo_topo = topo
        tocou = velas[j][3] <= vwap if compra else velas[j][2] >= vwap

        pv += tipico(velas[j]) * velas[j][5]
        vv += velas[j][5]
        topo = max(topo, velas[j][2]) if compra else min(topo, velas[j][3])
        if not tocou:
            continue

        # a VWAP nao pode ter afundado alem do fundo estrutural
        if (compra and vwap <= base) or (not compra and vwap >= base):
            return None

        # ===================================================================
        # MODO REJEICAO: o reteste FALHA e opera-se a favor da falha.
        #   1. preco volta na VWAP e FECHA do lado errado  -> reteste falhou
        #   2. volta para testar a VWAP de novo, agora por baixo
        #   3. REJEITA (perfura e fecha de volta do lado errado, corpo forte)
        #   4. entra na direcao OPOSTA ao CHOCH, alvo no ultimo fundo
        # ===================================================================
        if cfg['modo'] == 'rejeicao':
            falhou = False
            afastou = 0          # barras em que o preco REALMENTE saiu da VWAP
            jg = None
            vw_ref = vwap
            pv2, vv2 = pv, vv
            for k in range(j, min(n - 1, j + cfg['janela_falha']) + 1):
                o, h, l, cl = velas[k][1], velas[k][2], velas[k][3], velas[k][4]
                rng = h - l
                if not falhou:
                    if (compra and cl < vw_ref) or (not compra and cl > vw_ref):
                        falhou = True
                else:
                    # so conta como RETORNO se antes o preco se afastou da VWAP:
                    # pelo menos N barras inteiras do lado de fora dela.
                    # Sem isso, "falhou" e "rejeitou" caem em barras vizinhas e
                    # o preco nunca voltou a testar nada.
                    fora = (h < vw_ref) if compra else (l > vw_ref)
                    if fora:
                        afastou += 1
                    elif afastou >= cfg['afasta_min'] and rng > 0:
                        rejeitou = (cl < vw_ref and cl < o) if compra else \
                                   (cl > vw_ref and cl > o)
                        if rejeitou and abs(cl - o) / rng >= cfg['corpo_min']:
                            jg = k
                            break
                    if (compra and cl > vw_ref) or (not compra and cl < vw_ref):
                        return None
                pv2 += tipico(velas[k]) * velas[k][5]
                vv2 += velas[k][5]
                vw_ref = pv2 / max(vv2, 1e-12)
            if jg is None or jg + 1 >= n:
                return None

            compra = not compra              # VIRA A MAO
            entrada = velas[jg + 1][1]
            stop_ref = velas[jg][3] if compra else velas[jg][2]
            jg = jg + 1
            if cfg['stop'] == 'atr':
                stop = entrada - a[jg - 1] * cfg['stop_atr'] if compra else \
                       entrada + a[jg - 1] * cfg['stop_atr']
            else:   # referenciado na vela de rejeicao
                stop = stop_ref - a[jg - 1] * cfg['stop_atr'] * 0.2 if compra else \
                       stop_ref + a[jg - 1] * cfg['stop_atr'] * 0.2
            risco = abs(entrada - stop)
            if risco <= 0:
                return None
            # alvo = o ultimo fundo deixado (a ancora estrutural)
            alvo = base if cfg['alvo'] == 'topo' else \
                   entrada + risco * cfg['rr_fixo'] * (1 if compra else -1)
            if (compra and alvo <= entrada) or (not compra and alvo >= entrada):
                return None
            rr = abs(alvo - entrada) / risco
            if rr < cfg['rr_min'] or (cfg['rr_max'] and rr > cfg['rr_max']):
                return None
            res, dur, r_bruto = simular(velas, jg, compra, entrada, stop, alvo, cfg)
            custo = (entrada * cfg['custo_pct'] / 100) / risco
            return {'data': datetime.fromtimestamp(velas[jg][0] / 1000, timezone.utc)
                            .strftime('%Y-%m-%d %H:%M'),
                    'lado': 'compra' if compra else 'venda',
                    'entrada': entrada, 'stop': stop, 'alvo': alvo, 'rr': rr,
                    'espera': j - i, 'ancora': i - ancora, 'confirma': jg - j,
                    'resultado': res, 'barras': (jg - i) + dur, 'r': r_bruto - custo}

        # ---- GATILHO: tocar a VWAP nao basta. Espera a vela de impulsao
        # que REAGE nela -- toca/perfura e fecha de volta do lado certo,
        # com corpo expressivo. Sem isso, nao ha entrada.
        if cfg['gatilho'] == 'toque':
            jg, entrada = j, vwap
            stop_ref = vwap
        else:
            jg = None
            for k in range(j, min(n - 1, j + cfg['confirma_max']) + 1):
                o, h, l, cl = velas[k][1], velas[k][2], velas[k][3], velas[k][4]
                rng = h - l
                if rng <= 0:
                    continue
                corpo_ok = abs(cl - o) / rng >= cfg['corpo_min']
                if compra:
                    reagiu = l <= vwap and cl > vwap and cl > o
                else:
                    reagiu = h >= vwap and cl < vwap and cl < o
                if reagiu and corpo_ok:
                    jg = k
                    break
                # se fechou do lado errado da VWAP, o reteste falhou
                if (compra and cl < vwap) or (not compra and cl > vwap):
                    return None
            if jg is None or jg + 1 >= n:
                return None
            # entrada executavel: abertura da barra SEGUINTE a confirmacao
            entrada = velas[jg + 1][1]
            stop_ref = velas[jg][3] if compra else velas[jg][2]
            jg = jg + 1

        if cfg['stop'] == 'estrutura':
            stop = base - a[jg - 1] * 0.1 if compra else base + a[jg - 1] * 0.1
        elif cfg['stop'] == 'gatilho':
            stop = stop_ref - a[jg - 1] * 0.2 if compra else stop_ref + a[jg - 1] * 0.2
        else:
            stop = entrada - a[jg - 1] * cfg['stop_atr'] if compra else \
                   entrada + a[jg - 1] * cfg['stop_atr']
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

        res, dur, r_bruto = simular(velas, jg, compra, entrada, stop, alvo, cfg)
        custo = (entrada * cfg['custo_pct'] / 100) / risco
        return {'data': datetime.fromtimestamp(velas[jg][0] / 1000, timezone.utc)
                        .strftime('%Y-%m-%d %H:%M'),
                'lado': 'compra' if compra else 'venda',
                'entrada': entrada, 'stop': stop, 'alvo': alvo, 'rr': rr,
                'espera': j - i, 'ancora': i - ancora, 'confirma': jg - j,
                'resultado': res, 'barras': (jg - i) + dur, 'r': r_bruto - custo}
    return None


def simular(velas, j0, compra, entrada, stop, alvo, cfg):
    risco = abs(entrada - stop)
    parcial = False
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
        if cfg['parcial_em'] > 0 and not parcial and em_r >= cfg['parcial_em'] \
                and not bate_stop:
            parcial = True
            r_trav += cfg['parcial_frac'] * cfg['parcial_em']
            if cfg['breakeven']:
                stop_atual = entrada
                bate_stop = lo <= stop_atual if compra else hi >= stop_atual
        resto = 1.0 - (cfg['parcial_frac'] if parcial else 0.0)
        if bate_stop:
            perda = 0.0 if (parcial and cfg['breakeven']) else -1.0
            return ('be' if perda == 0 else 'loss'), k - j0, r_trav + resto * perda
        if bate_alvo:
            return 'win', k - j0, r_trav + resto * abs(alvo - entrada) / risco
        if k >= limite:
            sai = velas[k][4]
            return 'tempo', k - j0, r_trav + resto * (
                ((sai - entrada) if compra else (entrada - sai)) / risco)
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
    ap.add_argument('--pivo-esq', type=int, default=3)
    ap.add_argument('--pivo-dir', type=int, default=3)
    ap.add_argument('--evento', choices=['choch', 'bos', 'ambos'], default='choch')
    ap.add_argument('--sigma', type=float, default=1.5,
                    help='tamanho minimo do impulso do CHOCH, em ATR')
    ap.add_argument('--impulso-min', type=int, default=2,
                    help='barras minimas entre a ancora e a quebra')
    ap.add_argument('--alvo', choices=['topo', 'rr_fixo'], default='topo')
    ap.add_argument('--rr-fixo', type=float, default=2.0)
    ap.add_argument('--modo', choices=['reteste', 'rejeicao'], default='reteste',
                    help='reteste = entra a favor do CHOCH quando a VWAP segura | '
                         'rejeicao = o reteste falha, volta e rejeita -> vira a mao, '
                         'alvo no ultimo fundo')
    ap.add_argument('--afasta-min', type=int, default=1,
                    help='barras inteiras fora da VWAP entre a falha e a rejeicao -- '
                         'garante que o preco saiu e VOLTOU para testar de novo')
    ap.add_argument('--janela-falha', type=int, default=20,
                    help='barras para a falha + nova rejeicao acontecerem')
    ap.add_argument('--gatilho', choices=['toque', 'impulsao'], default='impulsao',
                    help='toque = so encostar na VWAP | impulsao = exige vela de '
                         'reacao fechando do lado certo, com corpo expressivo')
    ap.add_argument('--corpo-min', type=float, default=0.5,
                    help='corpo/range minimo da vela de impulsao')
    ap.add_argument('--confirma-max', type=int, default=3,
                    help='barras de tolerancia para a confirmacao aparecer')
    ap.add_argument('--fundo-janela', type=int, default=50,
                    help='a ancora tem de ser a minima das N barras anteriores (0=off)')
    ap.add_argument('--stop', choices=['atr', 'estrutura', 'gatilho'], default='gatilho')
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
           ('pivo_esq', 'pivo_dir', 'evento', 'sigma', 'impulso_min', 'alvo',
            'gatilho', 'corpo_min', 'confirma_max', 'fundo_janela',
            'modo', 'janela_falha', 'afasta_min',
            'rr_fixo', 'stop', 'stop_atr', 'rr_min', 'rr_max', 'espera_max',
            'tempo_max', 'atr_periodo', 'lado', 'parcial_em', 'parcial_frac',
            'breakeven', 'custo_pct')}

    ativos = {x.strip().upper() for x in a.ativos.split(',') if x.strip()} or None
    dados = carregar(a.tf, ativos)
    if not dados:
        print(f"Nenhum CSV *_{a.tf}.csv em {PASTA}/.")
        return
    d0 = min(datetime.fromtimestamp(v[0][0] / 1000, timezone.utc) for v in dados.values())
    d1 = max(datetime.fromtimestamp(v[-1][0] / 1000, timezone.utc) for v in dados.values())
    print("=" * 84)
    print(f"CHOCH -> VWAP ANCORADA NO FUNDO -> RETESTE | {a.tf} | {len(dados)} pares | "
          f"{d0:%Y-%m-%d} -> {d1:%Y-%m-%d}")
    print(f"pivo {a.pivo_esq}/{a.pivo_dir} | evento={a.evento} | impulso>={a.sigma} ATR "
          f"| fundo das ultimas {a.fundo_janela} barras")
    print(f"modo={a.modo} | gatilho={a.gatilho} (corpo>={a.corpo_min:.0%}) "
          f"| alvo={a.alvo} | stop={a.stop} | espera {a.espera_max} barras")
    print("=" * 84)

    if a.painel:
        for ev in ('choch', 'bos'):
            print(f"\n### evento = {ev}")
            cabecalho()
            for sig, alvo, st in itertools.product((1.0, 2.0), ('topo', 'rr_fixo'),
                                                   ('atr', 'estrutura')):
                c = dict(cfg, evento=ev, sigma=sig, alvo=alvo, stop=st)
                t = rodar_tudo(dados, c)
                linha(f"{sig}ATR {alvo} stop-{st}", medir(t), medir_dia(t))
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

    with open("trades_choch_vwap.csv", 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(todos[0].keys()))
        w.writeheader()
        w.writerows(todos)
    print("\nCSV: trades_choch_vwap.csv")


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except Exception:
        print("\n=== ERRO ===")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
