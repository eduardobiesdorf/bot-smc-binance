# -*- coding: utf-8 -*-
"""
SMC H4 v4 -- order block como ZONA PERSISTENTE + piscina de liquidez.

Regras (conforme definido):
  - zona do OB = topo ao fundo da vela inteira (pavio incluso)
  - a zona nasce quando o impulso que saiu dela QUEBRA a estrutura (so entao ela
    passa a ser conhecida -- sem lookahead) e fica viva ate ser tocada
  - o primeiro toque consome a zona: vira o trade e a zona morre
  - alvo = ultimo fundo confirmado (venda) ou ultimo topo confirmado (compra)
  - piscina de liquidez = agrupamento de topos/fundos iguais dentro de uma
    tolerancia; opcionalmente exige-se que ela tenha sido pega no caminho ate a zona

Rodar:
  python smc_v4.py --inicio 2026-01-01
  python smc_v4.py --inicio 2026-08-01 --ativos MEGAUSDT --listar
  python smc_v4.py --inicio 2026-01-01 --comparar
  python smc_v4.py --inicio 2026-01-01 --montecarlo 100 --mc-bloco 20
"""
import argparse
import csv
import itertools
import math
import random
import time
from datetime import datetime, timezone

import requests

ATIVOS = ['UNIUSDT', 'SHIBUSDT', 'NEARUSDT', 'BTCUSDT',
          'POLUSDT', 'BCHUSDT', 'ADAUSDT', 'DOTUSDT', 'LINKUSDT']

BASE_URL = "https://data-api.binance.vision/api/v3"
INTERVALO = '4h'
MS_VELA = 4 * 60 * 60 * 1000
CSV_SAIDA = "trades_smc.csv"
_CACHE = {}


def O(c): return float(c[1])
def H(c): return float(c[2])
def L(c): return float(c[3])
def C(c): return float(c[4])
def T(c): return int(c[0])


def ms(d):
    return int(datetime.strptime(d, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp() * 1000)


def quando(c):
    return datetime.fromtimestamp(T(c) / 1000, timezone.utc).strftime('%Y-%m-%d %H:%M')


# ------------------------------------------------------------------ dados
def buscar_candles(simbolo, inicio_ms, fim_ms, tentativas=3):
    chave = (simbolo, inicio_ms, fim_ms)
    if chave in _CACHE:
        return _CACHE[chave]
    agora = int(time.time() * 1000)
    fim_ms = min(fim_ms, agora)
    velas, cursor, visto = [], inicio_ms, set()
    while cursor < fim_ms:
        dados = None
        for t in range(tentativas):
            try:
                r = requests.get(f"{BASE_URL}/klines",
                                 params={'symbol': simbolo, 'interval': INTERVALO,
                                         'startTime': cursor, 'endTime': fim_ms,
                                         'limit': 1000}, timeout=20)
                if r.status_code == 429:
                    time.sleep(5 * (t + 1))
                    continue
                r.raise_for_status()
                dados = r.json()
                break
            except Exception:
                if t == tentativas - 1:
                    raise
                time.sleep(2 * (t + 1))
        if not dados:
            break
        for c in dados:
            if T(c) not in visto and int(c[6]) < agora:
                visto.add(T(c))
                velas.append(c)
        ultimo = T(dados[-1])
        if len(dados) < 1000 and ultimo + MS_VELA >= fim_ms:
            break
        cursor = ultimo + MS_VELA
        time.sleep(0.25)
    velas.sort(key=T)
    _CACHE[chave] = velas
    return velas


def carregar_todos(ini, fim):
    aquec = ini - 250 * MS_VELA          # zonas antigas precisam de historico
    dados = {}
    for s in ATIVOS:
        try:
            c = buscar_candles(s, aquec, fim)
            if len(c) >= 100:
                dados[s] = c
        except Exception as e:
            print(f"[{s}] ERRO: {e}")
    return dados


# ------------------------------------------------------------------ estrutura
def detectar_pivos(candles, esq, dir_):
    """Pivos fractais, indexados pela vela em que passam a ser CONHECIDOS."""
    altas, baixas = {}, {}
    for k in range(esq, len(candles) - dir_):
        h, l = H(candles[k]), L(candles[k])
        if (all(H(candles[k - m]) < h for m in range(1, esq + 1)) and
                all(H(candles[k + m]) <= h for m in range(1, dir_ + 1))):
            altas.setdefault(k + dir_, []).append((k, h))
        if (all(L(candles[k - m]) > l for m in range(1, esq + 1)) and
                all(L(candles[k + m]) >= l for m in range(1, dir_ + 1))):
            baixas.setdefault(k + dir_, []).append((k, l))
    return altas, baixas


def calcular_atr(candles, periodo=14):
    """ATR simples (media movel do true range). atr[i] usa dados ate i."""
    tr = [H(candles[0]) - L(candles[0])]
    for k in range(1, len(candles)):
        c0 = C(candles[k - 1])
        tr.append(max(H(candles[k]) - L(candles[k]),
                      abs(H(candles[k]) - c0), abs(L(candles[k]) - c0)))
    atr, soma = [], 0.0
    for k, v in enumerate(tr):
        soma += v
        if k >= periodo:
            soma -= tr[k - periodo]
            atr.append(soma / periodo)
        else:
            atr.append(soma / (k + 1))
    return atr


def tendencia_diaria(candles, esq=2, dir_=2):
    """
    Agrega H4 -> D1 e devolve, para cada indice H4, a direcao da ultima quebra
    de estrutura no diario JA CONFIRMADA (so dias fechados antes da vela i).
    """
    dias, atual, dia_ref = [], None, None
    idx_dia = []                      # para cada vela H4, quantos dias fechados antes
    for i, c in enumerate(candles):
        d = datetime.fromtimestamp(T(c) / 1000, timezone.utc).strftime('%Y-%m-%d')
        if d != dia_ref:
            if atual:
                dias.append(atual)
            dia_ref = d
            atual = [T(c), O(c), H(c), L(c), C(c)]
        else:
            atual[2] = max(atual[2], H(c))
            atual[3] = min(atual[3], L(c))
            atual[4] = C(c)
        idx_dia.append(len(dias))
    if atual:
        dias.append(atual)

    d_candles = [[d[0], str(d[1]), str(d[2]), str(d[3]), str(d[4]), "1", d[0]] for d in dias]
    tend_por_dia = ['indefinida'] * len(d_candles)
    if len(d_candles) > esq + dir_ + 2:
        altas, baixas = detectar_pivos(d_candles, esq, dir_)
        sh = sl = None
        estado = 'indefinida'
        for j in range(len(d_candles)):
            for k, p in altas.get(j, []):
                if sh is None or k > sh[0]:
                    sh = (k, p)
            for k, p in baixas.get(j, []):
                if sl is None or k > sl[0]:
                    sl = (k, p)
            c = C(d_candles[j])
            if sh is not None and c > sh[1]:
                estado, sh = 'alta', None
            elif sl is not None and c < sl[1]:
                estado, sl = 'baixa', None
            tend_por_dia[j] = estado

    # para a vela H4 i, usa o estado do ultimo dia FECHADO
    return [tend_por_dia[max(0, idx_dia[i] - 1)] if tend_por_dia else 'indefinida'
            for i in range(len(candles))]


def tem_fvg(candles, ini, fim, alta):
    """Gap de valor justo dentro do impulso (deslocamento institucional)."""
    for j in range(max(ini + 1, 1), min(fim, len(candles) - 1)):
        if alta and H(candles[j - 1]) < L(candles[j + 1]):
            return True
        if not alta and L(candles[j - 1]) > H(candles[j + 1]):
            return True
    return False


def agrupar_piscinas(niveis, tol):
    """Agrupa topos (ou fundos) proximos: [(preco, n_toques)]."""
    if not niveis:
        return []
    ordenados = sorted(p for _, p in niveis)
    grupos, atual = [], [ordenados[0]]
    for p in ordenados[1:]:
        if abs(p - atual[-1]) <= atual[-1] * tol:
            atual.append(p)
        else:
            grupos.append(atual)
            atual = [p]
    grupos.append(atual)
    return [(sum(g) / len(g), len(g)) for g in grupos]


# ------------------------------------------------------------------ motor
def gerar_trades(candles, cfg, motivos, diario=None):
    """
    Varre o grafico uma vez, mantendo:
      - zonas de OB vivas (nascem na quebra de estrutura, morrem no 1o toque)
      - topos/fundos confirmados -> piscinas de liquidez
    Devolve os trades, cada um ja simulado.
    """
    altas, baixas = detectar_pivos(candles, cfg['pivo_esq'], cfg['pivo_dir'])
    atr = calcular_atr(candles)
    tend = tendencia_diaria(candles) if cfg['htf'] else None
    sh_lista, sl_lista = [], []      # [(idx, preco)] confirmados ate agora
    sh_ativo = sl_ativo = None       # nivel ainda nao rompido
    zonas = []                       # OBs vivos
    trades = []
    n = len(candles)
    ctx = {'atr': atr, 'tend': tend}

    for i in range(n):
        # --- 1. novos pivos confirmados nesta vela
        for k, p in altas.get(i, []):
            sh_lista.append((k, p))
            if sh_ativo is None or k > sh_ativo[0]:
                sh_ativo = (k, p)
        for k, p in baixas.get(i, []):
            sl_lista.append((k, p))
            if sl_ativo is None or k > sl_ativo[0]:
                sl_ativo = (k, p)

        c = C(candles[i])

        # --- 2. quebra de estrutura: nasce uma zona de OB
        if sl_ativo is not None and c < sl_ativo[1]:
            # impulso de baixa: OB de VENDA = ultima vela de alta antes do impulso
            for k in range(i, max(-1, i - cfg['impulso_max']), -1):
                if C(candles[k]) > O(candles[k]):
                    zonas.append({'lado': 'venda', 'nasceu': i, 'idx': k,
                                  'zh': H(candles[k]), 'zl': L(candles[k]),
                                  'fvg': tem_fvg(candles, k, i, False),
                                  'forca': abs(O(candles[k]) - c) / max(atr[i], 1e-12)})
                    break
            sl_ativo = None
        if sh_ativo is not None and c > sh_ativo[1]:
            for k in range(i, max(-1, i - cfg['impulso_max']), -1):
                if C(candles[k]) < O(candles[k]):
                    zonas.append({'lado': 'compra', 'nasceu': i, 'idx': k,
                                  'zh': H(candles[k]), 'zl': L(candles[k]),
                                  'fvg': tem_fvg(candles, k, i, True),
                                  'forca': abs(c - O(candles[k])) / max(atr[i], 1e-12)})
                    break
            sh_ativo = None

        # --- 3. zonas vencidas
        zonas = [z for z in zonas if i - z['nasceu'] <= cfg['zona_validade']]

        # --- 4. toque numa zona viva -> consome a zona
        hi, lo = H(candles[i]), L(candles[i])
        restantes = []
        for z in zonas:
            if i <= z['nasceu']:
                restantes.append(z)
                continue
            compra = z['lado'] == 'compra'
            # venda: preco SOBE ate a zona (toca a borda inferior)
            tocou = (hi >= z['zl']) if not compra else (lo <= z['zh'])
            if not tocou:
                restantes.append(z)
                continue

            motivos['tocadas'] += 1
            t = _montar(candles, i, z, cfg, motivos, sh_lista, sl_lista, diario, ctx)
            if t:
                trades.append(t)
            # consumida de qualquer forma (primeiro toque)
        zonas = restantes

    return trades


def _montar(candles, i, z, cfg, motivos, sh_lista, sl_lista, diario, ctx):
    compra = z['lado'] == 'compra'
    zh, zl = z['zh'], z['zl']
    amp = zh - zl
    if amp <= 0:
        return None

    # ---- FILTRO 4: qualidade do deslocamento que criou a zona
    if cfg['exigir_fvg'] and not z.get('fvg'):
        motivos['sem_fvg'] += 1
        return None
    if cfg['forca_min'] > 0 and z.get('forca', 0) < cfg['forca_min']:
        motivos['impulso_fraco'] += 1
        return None

    # ---- FILTRO 6: horario do gatilho (hora UTC de abertura da vela)
    if cfg['horas']:
        hora = datetime.fromtimestamp(T(candles[i]) / 1000, timezone.utc).hour
        if hora not in cfg['horas']:
            motivos['fora_horario'] += 1
            return None

    # ---- FILTRO 5: alinhamento com o diario
    if cfg['htf'] and ctx['tend'] is not None:
        t_d1 = ctx['tend'][i]
        if (compra and t_d1 != 'alta') or (not compra and t_d1 != 'baixa'):
            motivos['contra_d1'] += 1
            return None

    d = cfg['entrada']
    entrada = (zh - d * amp) if compra else (zl + d * amp)

    # ---- FILTRO 1: stop desacoplado do tamanho da zona
    stop_zona = (zl - amp * cfg['stop_buffer']) if compra else (zh + amp * cfg['stop_buffer'])
    atr_i = ctx['atr'][i]
    stop_atr = (entrada - atr_i * cfg['atr_mult']) if compra else \
               (entrada + atr_i * cfg['atr_mult'])
    if cfg['stop_modo'] == 'atr':
        stop = stop_atr
    elif cfg['stop_modo'] == 'misto':
        stop = min(stop_zona, stop_atr) if compra else max(stop_zona, stop_atr)
    else:
        stop = stop_zona

    # piso minimo de risco em % do preco
    if cfg['risco_min_pct'] > 0:
        minimo = entrada * cfg['risco_min_pct'] / 100
        if abs(entrada - stop) < minimo:
            stop = entrada - minimo if compra else entrada + minimo

    risco = abs(entrada - stop)
    if risco <= 0:
        return None

    # ---- FILTRO 2: premium / discount do range vigente
    if cfg['premium']:
        jan = range(max(0, i - cfg['range_lookback']), i + 1)
        r_hi = max(H(candles[k]) for k in jan)
        r_lo = min(L(candles[k]) for k in jan)
        meio = (r_hi + r_lo) / 2
        if (compra and entrada > meio) or (not compra and entrada < meio):
            motivos['lado_errado_range'] += 1
            return None

    # --- piscina de liquidez pega no caminho ate a zona?
    if cfg['exigir_pool']:
        if compra:
            piscinas = agrupar_piscinas([x for x in sl_lista if x[0] < i], cfg['pool_tol'])
            ok = any(cnt >= cfg['pool_min'] and p > zh and
                     min(L(candles[k]) for k in range(z['nasceu'], i + 1)) < p
                     for p, cnt in piscinas)
        else:
            piscinas = agrupar_piscinas([x for x in sh_lista if x[0] < i], cfg['pool_tol'])
            ok = any(cnt >= cfg['pool_min'] and p < zl and
                     max(H(candles[k]) for k in range(z['nasceu'], i + 1)) > p
                     for p, cnt in piscinas)
        if not ok:
            motivos['sem_pool'] += 1
            return None

    # --- alvo: ultimo topo (compra) / ultimo fundo (venda) confirmado
    if cfg['alvo'] == 'rr_fixo':
        alvo = entrada + risco * cfg['rr_fixo'] * (1 if compra else -1)
    else:
        fonte = [p for k, p in (sh_lista if compra else sl_lista) if k < i]
        if not fonte:
            motivos['sem_alvo'] += 1
            return None
        alvo = fonte[-1]

    if (compra and alvo <= entrada) or (not compra and alvo >= entrada):
        motivos['alvo_invalido'] += 1
        return None

    rr = abs(alvo - entrada) / risco
    if rr < cfg['rr_min']:
        motivos['rr_baixo'] += 1
        return None

    res, dur = _simular(candles, i, compra, entrada, stop, alvo, cfg['fill'])
    custo_r = (entrada * cfg['custo_pct'] / 100) / risco
    r = (rr - custo_r) if res == 'win' else (-1.0 - custo_r) if res == 'loss' else 0.0

    if diario is not None and T(candles[i]) >= cfg.get('ini_ms', 0):
        diario.append(
            f"  {quando(candles[i])} {'COMPRA' if compra else 'VENDA ':6} "
            f"zona nasceu {quando(candles[z['nasceu']])} "
            f"(vela OB {quando(candles[z['idx']])}, {i - z['nasceu']:>3} velas depois) "
            f"| zona {zl:.6g}-{zh:.6g} | ent {entrada:.6g} stop {stop:.6g} "
            f"alvo {alvo:.6g} | RR 1:{rr:.2f} -> {res}")

    return {'data': quando(candles[i]), 'mes': quando(candles[i])[:7],
            'lado': 'compra' if compra else 'venda',
            'espera': i - z['nasceu'], 'entrada': entrada, 'stop': stop,
            'alvo': alvo, 'rr': rr, 'resultado': res, 'velas': dur, 'r': r,
            'risco_pct': risco / entrada * 100, 'forca': round(z.get('forca', 0), 2),
            'fvg': int(bool(z.get('fvg')))}


def _simular(candles, i, compra, entrada, stop, alvo, fill):
    """A vela i e a do toque/fill. Resolve o resto adiante."""
    otim = fill == 'otimista'
    inicio = i + 1 if otim else i
    for j in range(inicio, len(candles)):
        hi, lo = H(candles[j]), L(candles[j])
        bate_stop = lo <= stop if compra else hi >= stop
        bate_alvo = hi >= alvo if compra else lo <= alvo
        if bate_stop and bate_alvo:
            return ('win' if otim else 'loss'), j - i
        if bate_stop:
            return 'loss', j - i
        if bate_alvo:
            return 'win', j - i
    return 'aberto', len(candles) - 1 - i


# ------------------------------------------------------------------ execucao
def rodar(cfg, ini, fim, verbose=True, dados=None, listar=False):
    todos = []
    motivos = {k: 0 for k in ('tocadas', 'sem_pool', 'sem_alvo', 'rr_baixo',
                              'alvo_invalido', 'sem_fvg', 'impulso_fraco',
                              'contra_d1', 'lado_errado_range', 'fora_horario')}
    fonte = dados if dados is not None else carregar_todos(ini, fim)

    for simbolo in ATIVOS:
        candles = fonte.get(simbolo)
        if not candles or len(candles) < 100:
            continue
        diario = [] if listar else None
        trades = gerar_trades(candles, cfg, motivos, diario)
        trades = [t for t in trades if t['data'] >= datetime.fromtimestamp(
            ini / 1000, timezone.utc).strftime('%Y-%m-%d')]
        for t in trades:
            t['ativo'] = simbolo
        todos.extend(trades)
        if verbose:
            bloco(f"[{simbolo.replace('USDT', '/USDT'):>10}] sinais {len(trades):>3}", trades)
        if diario:
            for linha in diario:
                print(linha)
    return todos, motivos


def bloco(titulo, trades):
    fech = [t for t in trades if t['resultado'] in ('win', 'loss')]
    if not fech:
        print(f"{titulo}: sem trades fechados")
        return
    w = sum(1 for t in fech if t['resultado'] == 'win')
    rt = sum(t['r'] for t in fech)
    rrm = sum(t['rr'] for t in fech) / len(fech)
    print(f"{titulo}: {len(fech)} fechados | WR {w/len(fech)*100:.1f}% | "
          f"RR 1:{rrm:.2f} | {rt:+.1f}R | exp {rt/len(fech):+.2f}R")


def resumo(todos, motivos, cfg):
    fech = [t for t in todos if t['resultado'] in ('win', 'loss')]
    print("\n" + "=" * 78)
    print(f"Zonas tocadas {motivos['tocadas']} | trades {len(todos)}")
    print(f"Descartes: {dict((k, v) for k, v in motivos.items() if k != 'tocadas')}")
    if not fech:
        print("Nenhum trade fechado.")
        return
    w = sum(1 for t in fech if t['resultado'] == 'win')
    rt = sum(t['r'] for t in fech)
    rrm = sum(t['rr'] for t in fech) / len(fech)
    media = rt / len(fech)
    er2 = sum(t['r'] ** 2 for t in fech) / len(fech)
    sd = max((er2 - media ** 2) ** 0.5, 1e-9)
    se = sd / len(fech) ** 0.5
    esp = sum(t['espera'] for t in fech) / len(fech)
    acc = pico = dd = 0.0
    for t in sorted(fech, key=lambda x: x['data']):
        acc += t['r']
        pico = max(pico, acc)
        dd = min(dd, acc - pico)
    # O equilibrio tem de usar o RR que os VENCEDORES realmente entregaram.
    # Usar o RR medio de todos os trades infla a margem e engana.
    rr_w = (sum(t['rr'] for t in fech if t['resultado'] == 'win') / w) if w else 0
    be = 1 / (1 + rr_w) * 100 if rr_w else float('nan')
    print(f"Fechados {len(fech)} | wins {w} | losses {len(fech)-w}")
    print(f"RR planejado medio 1:{rrm:.2f} | RR realizado nos wins 1:{rr_w:.2f}")
    print(f"Win rate {w/len(fech)*100:.2f}% | equilibrio REAL (RR dos wins) = {be:.2f}%")
    if rr_w and rr_w < rrm * 0.95:
        print("   (wins com RR menor que a media: os alvos distantes falham mais)")
    print(f"Resultado {rt:+.2f}R | expectativa {media:+.3f}R/trade | maxDD {dd:.1f}R")
    print(f"z {media/se:+.2f} | IC95% [{media-1.96*se:+.3f}R , {media+1.96*se:+.3f}R]")
    if abs(media / se) < 1.96:
        print(">> Nao distinguivel de zero nesta amostra.")
    print(f"Espera media da zona ate o toque: {esp:.0f} velas H4 ({esp*4/24:.1f} dias)")
    if rr_w:
        print("Expectativa por win rate, mantido o RR atual dos wins:")
        for alvo_wr in (0.30, 0.325, 0.35, 0.40):
            print(f"   WR {alvo_wr*100:>4.1f}% -> {alvo_wr*rr_w-(1-alvo_wr):+.3f}R/trade")
    print(f"Fill: {cfg['fill']} | custo: "
          + (f"{cfg['custo_pct']}%/trade" if cfg['custo_pct'] else "NENHUM"))


# ------------------------------------------------------------------ monte carlo
def embaralhar(candles, bloco_n, rng):
    rets, geo = [], []
    for k in range(1, len(candles)):
        c0, c1 = C(candles[k - 1]), C(candles[k])
        if c0 <= 0 or c1 <= 0:
            return candles
        rets.append(math.log(c1 / c0))
        geo.append((O(candles[k]) / c1, H(candles[k]) / c1, L(candles[k]) / c1))
    idx = []
    while len(idx) < len(rets):
        b = rng.randrange(len(rets))
        idx.extend(range(b, min(b + bloco_n, len(rets))))
    idx = idx[:len(rets)]
    out, preco = [list(candles[0])], C(candles[0])
    for pos, k in enumerate(idx):
        preco *= math.exp(rets[k])
        o_r, h_r, l_r = geo[k]
        o, h, l, c = preco * o_r, preco * h_r, preco * l_r, preco
        h, l = max(h, o, c), min(l, o, c)
        orig = candles[pos + 1]
        out.append([orig[0], f"{o:.10f}", f"{h:.10f}", f"{l:.10f}", f"{c:.10f}",
                    "1", orig[6]])
    return out


def _exp(saida):
    todos = saida[0] if isinstance(saida, tuple) else saida
    fech = [t for t in todos if t['resultado'] in ('win', 'loss')]
    if not fech:
        return None, 0
    return sum(t['r'] for t in fech) / len(fech), len(fech)


def montecarlo(cfg, ini, fim, n_sim, bloco_n, semente=42):
    print("\n" + "=" * 78)
    print(f"MONTE CARLO -- {n_sim} series embaralhadas (bloco={bloco_n})")
    print("=" * 78)
    dados = carregar_todos(ini, fim)
    real, n_real = _exp(rodar(cfg, ini, fim, verbose=False, dados=dados))
    if real is None:
        print("Sem trades no real.")
        return
    print(f"\nReal: {real:+.3f}R ({n_real} trades)")
    rng = random.Random(semente)
    am = []
    for s in range(n_sim):
        falso = {k: embaralhar(v, bloco_n, rng) for k, v in dados.items()}
        e, nn = _exp(rodar(cfg, ini, fim, verbose=False, dados=falso))
        if e is not None and nn >= 25:
            am.append(e)
        if (s + 1) % 20 == 0:
            print(f"  ... {s+1}/{n_sim}")
    if len(am) < 10:
        print("Poucas simulacoes validas.")
        return
    am.sort()
    media = sum(am) / len(am)
    pct = sum(1 for x in am if x <= real) / len(am) * 100
    q = lambda p: am[min(len(am) - 1, int(p * len(am)))]
    print(f"\nNulo: media {media:+.3f}R | p5 {q(.05):+.3f} | mediana {q(.5):+.3f} | "
          f"p95 {q(.95):+.3f}")
    print(f"Real no percentil {pct:.0f} do nulo.")
    print(">> Ha sinal, vale otimizar." if pct >= 95 else
          ">> Sinal invertido, testar o lado contrario." if pct <= 5 else
          ">> Rende igual em grafico embaralhado: sem edge nesta amostra.")


# ------------------------------------------------------------------ grade
FILTROS = {
    'stop ATR':      {'stop_modo': 'misto'},
    'premium/disc':  {'premium': True},
    'varredura':     {'exigir_pool': True},
    'FVG':           {'exigir_fvg': True},
    'impulso forte': {'forca_min': 1.5},
    'diario (D1)':   {'htf': True},
    'horario 8-21BR': {'horas': {12, 16, 20}},
}


def medir(cfg, ini, fim, dados):
    todos, _ = rodar(cfg, ini, fim, verbose=False, dados=dados)
    fech = [t for t in todos if t['resultado'] in ('win', 'loss')]
    if not fech:
        return None
    w = sum(1 for t in fech if t['resultado'] == 'win')
    rt = sum(t['r'] for t in fech)
    media = rt / len(fech)
    er2 = sum(t['r'] ** 2 for t in fech) / len(fech)
    sd = max((er2 - media ** 2) ** 0.5, 1e-9)
    rr_w = (sum(t['rr'] for t in fech if t['resultado'] == 'win') / w) if w else 0
    return {'n': len(fech), 'wr': w / len(fech) * 100, 'rr_w': rr_w,
            'r': rt, 'exp': media, 'z': media / (sd / len(fech) ** 0.5),
            'wins': {(t['ativo'], t['data']) for t in fech if t['resultado'] == 'win'},
            'losses': {(t['ativo'], t['data']) for t in fech if t['resultado'] == 'loss'}}


def painel_filtros(ini, fim, base):
    """Mede cada filtro ISOLADO e depois todos juntos, sobre a mesma base."""
    dados = carregar_todos(ini, fim)
    print(f"\n{'filtro':>16} | {'n':>5} {'WR':>7} {'exp':>8} {'z':>6} | "
          f"{'manteve wins':>13} {'manteve loss':>13} {'kl/kw':>6}")
    print("-" * 84)

    base_m = medir(base, ini, fim, dados)
    if not base_m:
        print("Base sem trades.")
        return
    nb_w, nb_l = len(base_m['wins']), len(base_m['losses'])
    print(f"{'nenhum (base)':>16} | {base_m['n']:>5} {base_m['wr']:>6.1f}% "
          f"{base_m['exp']:>+7.3f}R {base_m['z']:>+6.2f} | {nb_w:>13} {nb_l:>13}")

    def linha(nome, cfg):
        m = medir(cfg, ini, fim, dados)
        if not m:
            print(f"{nome:>16} |     0")
            return
        kw = len(m['wins'] & base_m['wins']) / nb_w if nb_w else 0
        kl = len(m['losses'] & base_m['losses']) / nb_l if nb_l else 0
        razao = kl / kw if kw else float('inf')
        # kl/kw < 0.856 ja leva o WR de 26,8% para 30%; < 0.681 leva a 35%
        marca = " <<" if razao < 0.856 else ""
        print(f"{nome:>16} | {m['n']:>5} {m['wr']:>6.1f}% {m['exp']:>+7.3f}R "
              f"{m['z']:>+6.2f} | {kw*100:>12.0f}% {kl*100:>12.0f}% {razao:>6.3f}{marca}")

    for nome, ajuste in FILTROS.items():
        linha(nome, dict(base, **ajuste))
    combinado = dict(base)
    for ajuste in FILTROS.values():
        combinado.update(ajuste)
    print("-" * 84)
    linha('TODOS juntos', combinado)

    print("\nkl/kw = quanto o filtro preserva de PERDEDORES dividido pelo que preserva")
    print("de VENCEDORES. Abaixo de 1 ele discrimina; quanto menor, melhor.")
    print("  < 0.856 -> leva o WR de 26,8% para ~30%   (marcado com <<)")
    print("  < 0.681 -> leva o WR para ~35%")
    print("Um filtro que corta 40% de tudo sem discriminar tem kl/kw = 1,0 e nao serve:")
    print("ele so reduz a amostra. Olhe esta coluna antes de olhar a expectativa.")


def comparar(ini, fim, base):
    dados = carregar_todos(ini, fim)
    print(f"\n{'entrada':>8} {'pool':>6} {'alvo':>9} {'fill':>11} | {'n':>4} {'WR':>6} "
          f"{'RR':>6} {'result':>9} {'exp':>7}")
    print("-" * 75)
    linhas = []
    for entrada, pool, alvo, fill in itertools.product(
            [0.0, 0.5], [False, True], ['estrutura', 'rr_fixo'],
            ['pessimista', 'otimista']):
        cfg = dict(base, entrada=entrada, exigir_pool=pool, alvo=alvo, fill=fill)
        todos, _ = rodar(cfg, ini, fim, verbose=False, dados=dados)
        fech = [t for t in todos if t['resultado'] in ('win', 'loss')]
        if not fech:
            print(f"{entrada:>8.1f} {str(pool):>6} {alvo:>9} {fill:>11} |    0")
            continue
        w = sum(1 for t in fech if t['resultado'] == 'win')
        rt = sum(t['r'] for t in fech)
        rrm = sum(t['rr'] for t in fech) / len(fech)
        print(f"{entrada:>8.1f} {str(pool):>6} {alvo:>9} {fill:>11} | {len(fech):>4} "
              f"{w/len(fech)*100:>5.1f}% 1:{rrm:>4.2f} {rt:>+8.1f}R "
              f"{rt/len(fech):>+6.2f}R")
        linhas.append((entrada, pool, alvo, fill, rt / len(fech), len(fech)))
    if linhas:
        print("\nMedia por dimensao (olhe o PADRAO, nao a melhor celula):")
        for nome, idx in (('entrada', 0), ('pool', 1), ('alvo', 2), ('fill', 3)):
            print(f"  {nome}:")
            for v in sorted({l[idx] for l in linhas}, key=str):
                g = [l for l in linhas if l[idx] == v]
                peso = sum(l[5] for l in g)
                print(f"    {str(v):>11}: {sum(l[4]*l[5] for l in g)/peso:+.3f}R")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inicio', default='2026-01-01')
    ap.add_argument('--fim', default=datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    ap.add_argument('--entrada', type=float, default=0.0,
                    help='0.0 = borda da zona (primeiro toque) ... 1.0 = extremo')
    ap.add_argument('--alvo', choices=['estrutura', 'rr_fixo'], default='estrutura',
                    help='estrutura = ultimo fundo (venda) / ultimo topo (compra)')
    ap.add_argument('--rr-fixo', type=float, default=2.0)
    ap.add_argument('--stop-buffer', type=float, default=0.10)
    ap.add_argument('--rr-min', type=float, default=1.20)
    ap.add_argument('--zona-validade', type=int, default=200,
                    help='velas que uma zona de OB fica viva esperando o toque')
    ap.add_argument('--impulso-max', type=int, default=10,
                    help='ate quantas velas atras procurar a vela do OB')
    ap.add_argument('--pivo-esq', type=int, default=2)
    ap.add_argument('--pivo-dir', type=int, default=2)
    ap.add_argument('--exigir-pool', action='store_true',
                    help='exige que uma piscina de liquidez tenha sido pega no caminho')
    ap.add_argument('--pool-min', type=int, default=2, help='topos iguais p/ formar piscina')
    ap.add_argument('--pool-tol', type=float, default=0.004)
    # --- filtro 1: stop desacoplado da zona
    ap.add_argument('--stop-modo', choices=['zona', 'atr', 'misto'], default='zona',
                    help='misto = o mais largo entre a zona e o ATR')
    ap.add_argument('--atr-mult', type=float, default=1.0)
    ap.add_argument('--risco-min-pct', type=float, default=0.0,
                    help='piso de risco em %% do preco (ex: 1.5)')
    # --- filtro 2: premium/discount
    ap.add_argument('--premium', action='store_true',
                    help='venda so na metade de cima do range, compra so na de baixo')
    ap.add_argument('--range-lookback', type=int, default=60)
    # --- filtro 4: qualidade do deslocamento
    ap.add_argument('--exigir-fvg', action='store_true')
    ap.add_argument('--forca-min', type=float, default=0.0,
                    help='tamanho minimo do impulso em multiplos de ATR (ex: 1.5)')
    # --- filtro 5: alinhamento com o diario
    ap.add_argument('--htf', action='store_true',
                    help='so opera a favor da ultima quebra de estrutura no D1')
    # --- filtro 6: horario (horas UTC de abertura da vela H4: 0,4,8,12,16,20)
    ap.add_argument('--horas', default='',
                    help='horas UTC separadas por virgula. Brasilia 8h-21h = 12,16,20')

    ap.add_argument('--custo-pct', type=float, default=0.0)
    ap.add_argument('--fill', choices=['pessimista', 'otimista'], default='pessimista')
    ap.add_argument('--filtros', action='store_true',
                    help='mede cada filtro isolado e depois todos juntos')
    ap.add_argument('--ativos', default='')
    ap.add_argument('--listar', action='store_true', help='imprime trade a trade')
    ap.add_argument('--comparar', action='store_true')
    ap.add_argument('--montecarlo', type=int, default=0)
    ap.add_argument('--mc-bloco', type=int, default=1)
    a = ap.parse_args()

    if a.ativos:
        ATIVOS[:] = [x.strip().upper() for x in a.ativos.split(',') if x.strip()]

    cfg = {k: getattr(a, k) for k in
           ('entrada', 'alvo', 'rr_fixo', 'stop_buffer', 'rr_min', 'zona_validade',
            'impulso_max', 'exigir_pool', 'pool_min', 'pool_tol', 'custo_pct', 'fill',
            'stop_modo', 'atr_mult', 'risco_min_pct', 'premium', 'range_lookback',
            'exigir_fvg', 'forca_min', 'htf')}
    cfg['horas'] = {int(x) for x in a.horas.split(',') if x.strip()} if a.horas else None
    cfg['pivo_esq'], cfg['pivo_dir'] = a.pivo_esq, a.pivo_dir
    ini, fim = ms(a.inicio), ms(a.fim) + 24 * 3600 * 1000
    cfg['ini_ms'] = ini

    print("=" * 78)
    print(f"SMC H4 v5 (zona de OB + filtros) | {a.inicio} -> {a.fim} | "
          f"{len(ATIVOS)} ativo(s)")
    print(f"entrada={a.entrada} alvo={a.alvo} stop={a.stop_buffer}xzona RRmin={a.rr_min} "
          f"zona_validade={a.zona_validade}v pool={a.exigir_pool} fill={a.fill}")
    print("=" * 78)

    if a.filtros:
        painel_filtros(ini, fim, cfg)
        return
    if a.montecarlo:
        montecarlo(cfg, ini, fim, a.montecarlo, a.mc_bloco)
        return
    if a.comparar:
        comparar(ini, fim, cfg)
        return

    todos, motivos = rodar(cfg, ini, fim, listar=a.listar)
    if not todos:
        print("\nNenhum sinal no periodo.")
        return
    print("\nPOR MES")
    for m in sorted({t['mes'] for t in todos}):
        bloco(f"  {m}", [t for t in todos if t['mes'] == m])
    print("\nPOR LADO")
    for l in ('compra', 'venda'):
        bloco(f"  {l}", [t for t in todos if t['lado'] == l])
    resumo(todos, motivos, cfg)
    with open(CSV_SAIDA, 'w', newline='', encoding='utf-8') as f:
        wtr = csv.DictWriter(f, fieldnames=list(todos[0].keys()))
        wtr.writeheader()
        wtr.writerows(todos)
    print(f"\nCSV: {CSV_SAIDA}")


if __name__ == "__main__":
    main()
