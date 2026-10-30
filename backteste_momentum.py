# -*- coding: utf-8 -*-
"""
Momentum transversal em cripto -- backtest de carteira long/short.

Como funciona:
  1. a cada rebalanceamento, ranqueia o universo pelo retorno dos ultimos
     LOOKBACK dias, pulando os ultimos SKIP dias (evita reversao de curtissimo prazo)
  2. compra os N melhores, vende os N piores, mesmo valor em dolar nos dois lados
  3. cada posicao vale 1/(2N) do capital -> exposicao bruta 100%, liquida 0%
  4. segura ate o proximo rebalanceamento; a saida e por calendario, nao por preco
  5. risco controlado pelo TAMANHO da posicao, nao por stop

Rodar:
  python backtest_momentum.py --inicio 2023-01-01
  python backtest_momentum.py --inicio 2023-01-01 --montecarlo 200
  python backtest_momentum.py --inicio 2023-01-01 --grade
  python backtest_momentum.py --inicio 2023-01-01 --so-comprado
"""
import argparse
import csv
import math
import random
import statistics
import time
from datetime import datetime, timedelta, timezone

import requests

# Universo fixo. ESCOLHA ANTES de olhar performance -- ver aviso de vies no final.
UNIVERSO = [
    'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT',
    'DOGEUSDT', 'AVAXUSDT', 'DOTUSDT', 'LINKUSDT', 'UNIUSDT', 'ATOMUSDT',
    'LTCUSDT', 'BCHUSDT', 'NEARUSDT', 'FILUSDT', 'APTUSDT', 'ARBUSDT',
    'OPUSDT', 'INJUSDT', 'SUIUSDT', 'TIAUSDT', 'RUNEUSDT', 'AAVEUSDT',
    'GRTUSDT', 'SANDUSDT', 'AXSUSDT', 'ALGOUSDT', 'EGLDUSDT', 'FTMUSDT',
    'THETAUSDT', 'XLMUSDT', 'VETUSDT', 'ICPUSDT', 'HBARUSDT', 'MANAUSDT',
    'CHZUSDT', 'ENJUSDT', 'ZILUSDT', 'CRVUSDT',
]

BASE_URL = "https://data-api.binance.vision/api/v3"
MS_DIA = 24 * 60 * 60 * 1000
CSV_SAIDA = "momentum_periodos.csv"
_CACHE = {}


def ms(d):
    return int(datetime.strptime(d, "%Y-%m-%d")
               .replace(tzinfo=timezone.utc).timestamp() * 1000)


def dia(ts):
    return datetime.fromtimestamp(ts / 1000, timezone.utc).strftime('%Y-%m-%d')


# ------------------------------------------------------------------ dados
def buscar_diario(simbolo, inicio_ms, fim_ms, tentativas=3):
    chave = (simbolo, inicio_ms, fim_ms)
    if chave in _CACHE:
        return _CACHE[chave]
    agora = int(time.time() * 1000)
    fim_ms = min(fim_ms, agora)
    saida, cursor, visto = {}, inicio_ms, set()
    while cursor < fim_ms:
        dados = None
        for t in range(tentativas):
            try:
                r = requests.get(f"{BASE_URL}/klines",
                                 params={'symbol': simbolo, 'interval': '1d',
                                         'startTime': cursor, 'endTime': fim_ms,
                                         'limit': 1000}, timeout=20)
                if r.status_code == 429:
                    time.sleep(5 * (t + 1))
                    continue
                if r.status_code == 400:
                    return {}                      # par inexistente
                r.raise_for_status()
                dados = r.json()
                break
            except Exception:
                if t == tentativas - 1:
                    return {}
                time.sleep(2 * (t + 1))
        if not dados:
            break
        for c in dados:
            if int(c[0]) not in visto and int(c[6]) < agora:
                visto.add(int(c[0]))
                saida[dia(int(c[0]))] = float(c[4])
        ultimo = int(dados[-1][0])
        if len(dados) < 1000 and ultimo + MS_DIA >= fim_ms:
            break
        cursor = ultimo + MS_DIA
        time.sleep(0.2)
    _CACHE[chave] = saida
    return saida


def carregar(universo, inicio_ms, fim_ms, verbose=True):
    precos, faltando = {}, []
    for s in universo:
        d = buscar_diario(s, inicio_ms, fim_ms)
        if len(d) >= 120:
            precos[s] = d
        else:
            faltando.append(s)
    if verbose and faltando:
        print(f"Sem historico suficiente ({len(faltando)}): {', '.join(faltando)}")
    return precos


def calendario(precos, ini_str):
    dias = sorted({d for p in precos.values() for d in p})
    return [d for d in dias if d >= ini_str], dias


# ------------------------------------------------------------------ carteira
def volatilidade(serie, datas, pos, janela):
    rets = []
    for k in range(max(1, pos - janela + 1), pos + 1):
        a, b = serie.get(datas[k - 1]), serie.get(datas[k])
        if a and b and a > 0:
            rets.append(b / a - 1)
    if len(rets) < 5:
        return None
    try:
        return statistics.stdev(rets)
    except statistics.StatisticsError:
        return None


def montar_pesos(precos, datas, pos, cfg, aleatorio=None):
    """Devolve {simbolo: peso} para o rebalanceamento no indice pos."""
    sinais = []
    for s, serie in precos.items():
        i_fim = pos - cfg['skip']
        i_ini = i_fim - cfg['lookback']
        if i_ini < 0:
            continue
        p0, p1, pa = serie.get(datas[i_ini]), serie.get(datas[i_fim]), serie.get(datas[pos])
        if not p0 or not p1 or not pa or p0 <= 0:
            continue
        vol = volatilidade(serie, datas, pos, cfg['vol_janela'])
        if cfg['peso'] == 'invvol' and (vol is None or vol <= 0):
            continue
        sinais.append((s, p1 / p0 - 1, vol))

    if len(sinais) < cfg['n_pos'] * 2:
        return {}

    if aleatorio is not None:               # hipotese nula: ranking sorteado
        aleatorio.shuffle(sinais)
    else:
        sinais.sort(key=lambda x: x[1], reverse=True)

    longs = sinais[:cfg['n_pos']]
    shorts = [] if cfg['so_comprado'] else sinais[-cfg['n_pos']:]

    pesos = {}
    def aloca(grupo, sinal):
        if not grupo:
            return
        if cfg['peso'] == 'invvol':
            inv = [1 / g[2] for g in grupo]
            tot = sum(inv)
            for g, iv in zip(grupo, inv):
                pesos[g[0]] = pesos.get(g[0], 0) + sinal * (iv / tot) * cfg['lado_bruto']
        else:
            for g in grupo:
                pesos[g[0]] = pesos.get(g[0], 0) + sinal * cfg['lado_bruto'] / len(grupo)

    aloca(longs, +1)
    aloca(shorts, -1)
    return pesos


def rodar(precos, datas, cfg, ini_str, aleatorio=None):
    """Devolve lista de periodos: (data_ini, data_fim, retorno_liquido, giro)."""
    primeiro = cfg['lookback'] + cfg['skip'] + 2
    periodos, pesos_ant = [], {}

    pos = primeiro
    while pos + cfg['rebal'] < len(datas):
        if datas[pos] < ini_str:
            pos += cfg['rebal']
            continue
        pesos = montar_pesos(precos, datas, pos, cfg, aleatorio)
        if not pesos:
            pos += cfg['rebal']
            continue

        bruto = 0.0
        for s, w in pesos.items():
            pa = precos[s].get(datas[pos])
            pb = precos[s].get(datas[pos + cfg['rebal']])
            if not pa or not pb or pa <= 0:
                continue
            bruto += w * (pb / pa - 1)

        giro = sum(abs(pesos.get(s, 0) - pesos_ant.get(s, 0))
                   for s in set(pesos) | set(pesos_ant))
        custo = giro * cfg['custo_pct'] / 100
        periodos.append((datas[pos], datas[pos + cfg['rebal']], bruto - custo, giro))
        pesos_ant = pesos
        pos += cfg['rebal']

    return periodos


# ------------------------------------------------------------------ metricas
def metricas(periodos, rebal):
    if len(periodos) < 5:
        return None
    rets = [p[2] for p in periodos]
    n = len(rets)
    media = sum(rets) / n
    dp = statistics.stdev(rets) if n > 1 else 0.0
    por_ano = 365 / rebal
    equity, acc, pico, dd = [], 1.0, 1.0, 0.0
    for r in rets:
        acc *= (1 + r)
        equity.append(acc)
        pico = max(pico, acc)
        dd = min(dd, acc / pico - 1)
    sharpe = (media / dp * math.sqrt(por_ano)) if dp > 0 else 0.0
    t = (media / (dp / math.sqrt(n))) if dp > 0 else 0.0
    # capital zerado: nao da para anualizar (raiz de numero negativo)
    anual = (acc ** (por_ano / n) - 1) if (acc > 0 and n) else -1.0
    return {'n': n, 'media': media, 'dp': dp, 'sharpe': sharpe, 't': t,
            'total': acc - 1, 'anual': anual,
            'vol_anual': dp * math.sqrt(por_ano), 'maxdd': dd,
            'pos': sum(1 for r in rets if r > 0) / n,
            'giro': sum(p[3] for p in periodos) / n, 'equity': equity}


def aplicar_alavancagem(periodos, L, vol_alvo=None, vol_lb=13, lev_max=5.0):
    """
    Devolve (retornos_alavancados, alavancagem_usada_media, quebrou).
    vol_alvo (anual, ex 0.40) liga o dimensionamento por volatilidade:
    a alavancagem sobe quando o mercado acalma e cai quando agita.
    """
    rets = [p[2] for p in periodos]
    saida, usadas, equity = [], [], 1.0
    for i, r in enumerate(rets):
        if vol_alvo:
            jan = rets[max(0, i - vol_lb):i]
            if len(jan) < 5:
                lev = 1.0
            else:
                dp = statistics.stdev(jan)
                alvo_periodo = vol_alvo / math.sqrt(52)
                lev = min(lev_max, alvo_periodo / dp) if dp > 0 else 1.0
        else:
            lev = L
        usadas.append(lev)
        bruto = 1 + lev * r
        if bruto <= 0:                      # liquidacao: nao ha volta
            saida.append(-1.0)
            return saida, sum(usadas) / len(usadas), True
        saida.append(lev * r)
        equity *= bruto
    return saida, (sum(usadas) / len(usadas) if usadas else 0), False


def painel_alavancagem(periodos, rebal, n_sim=2000, semente=42):
    """Quanto cada nivel de alavancagem entrega -- e quanto arrisca."""
    rets = [p[2] for p in periodos]
    if len(rets) < 20:
        print("Periodos insuficientes.")
        return
    por_ano = 365 / rebal
    rng = random.Random(semente)

    print("\n" + "=" * 74)
    print("ALAVANCAGEM -- o que acontece com o MESMO sinal em cada nivel")
    print("=" * 74)
    print(f"{'alav':>5} {'retorno/ano':>12} {'vol/ano':>9} {'maxDD':>8} "
          f"{'P(ruina 1a)':>12} {'P(cair>50%)':>12}")
    print("-" * 64)

    for L in (1, 2, 3, 5, 10):
        # caminho historico
        eq, pico, dd, quebrou = 1.0, 1.0, 0.0, False
        for r in rets:
            bruto = 1 + L * r
            if bruto <= 0:
                quebrou = True
                break
            eq *= bruto
            pico = max(pico, eq)
            dd = min(dd, eq / pico - 1)
        if quebrou:
            print(f"{L:>4}x {'LIQUIDADO no historico -- conta zerada, sem recuperacao':>58}")
            continue
        anual = eq ** (por_ano / len(rets)) - 1
        vol = statistics.stdev(rets) * L * math.sqrt(por_ano)

        # bootstrap: 1 ano de semanas sorteadas do proprio historico
        ruina = caiu50 = 0
        passos = int(round(por_ano))
        for _ in range(n_sim):
            e, pk, pior = 1.0, 1.0, 0.0
            for _ in range(passos):
                r = rng.choice(rets)
                b = 1 + L * r
                if b <= 0:
                    e = 0.0
                    break
                e *= b
                pk = max(pk, e)
                pior = min(pior, e / pk - 1)
            if e <= 0.0 or pior <= -0.95:
                ruina += 1
            if pior <= -0.50:
                caiu50 += 1
        print(f"{L:>4}x {anual*100:>+11.1f}% {vol*100:>8.1f}% {dd*100:>7.1f}% "
              f"{ruina/n_sim*100:>11.1f}% {caiu50/n_sim*100:>11.1f}%")

    print("\nA alavancagem multiplica retorno E risco pelo mesmo fator: o Sharpe")
    print("nao muda. O que muda e a chance de a conta zerar antes de a estrategia")
    print("se recuperar -- e conta zerada nao volta, por melhor que seja o sinal.")
    print("P(ruina) usa reamostragem das SUAS proprias semanas, nada inventado.")


def linha_resumo(nome, m):
    if not m:
        print(f"{nome:>26} |    -")
        return
    print(f"{nome:>26} | {m['n']:>4} {m['anual']*100:>+7.1f}% {m['vol_anual']*100:>6.1f}% "
          f"{m['sharpe']:>6.2f} {m['maxdd']*100:>7.1f}% {m['t']:>+6.2f}")


def cabecalho_tabela():
    print(f"\n{'configuracao':>26} | {'n':>4} {'ret/ano':>8} {'vol':>6} "
          f"{'Sharpe':>6} {'maxDD':>7} {'t':>6}")
    print("-" * 70)


def completo(precos, datas, cfg, a, ini_str):
    """Bateria completa: tudo que preciso para decidir, numa rodada so."""
    meio = a.split or datas[len(datas) // 2]

    print("\n" + "#" * 70)
    print("# 1. CONFIGURACAO BASE E ESTABILIDADE NO TEMPO")
    print("#" * 70)
    per = rodar(precos, datas, cfg, ini_str)
    base_m = metricas(per, cfg['rebal'])
    cabecalho_tabela()
    linha_resumo(f"base {cfg['n_pos']}+{cfg['n_pos']}", base_m)
    linha_resumo(f"  ate {meio}", metricas([p for p in per if p[0] < meio], cfg['rebal']))
    linha_resumo(f"  de {meio} adiante",
                 metricas([p for p in per if p[0] >= meio], cfg['rebal']))

    print("\n" + "#" * 70)
    print("# 2. CONCENTRACAO -- quantas posicoes cabem em capital pequeno")
    print("#" * 70)
    cabecalho_tabela()
    for k in (2, 3, 5, 8, 12):
        if k * 2 + 2 > len(precos):
            continue
        linha_resumo(f"{k}+{k} posicoes",
                     metricas(rodar(precos, datas, dict(cfg, n_pos=k), ini_str), cfg['rebal']))
    print("\nSe o Sharpe cair junto com o numero de posicoes, o que fazia o")
    print("resultado era diversificacao -- e concentrar destroi a estrategia.")

    print("\n" + "#" * 70)
    print("# 3. ROBUSTEZ DO UNIVERSO -- o resultado depende dos lancamentos novos?")
    print("#" * 70)
    # "antigo" = o par ja existia quando a janela de dados comecou.
    # Comparacao relativa, porque so enxergamos historico a partir da busca.
    inicio_dados = min(min(p) for p in precos.values())
    limite = (datetime.strptime(inicio_dados, '%Y-%m-%d')
              + timedelta(days=14)).strftime('%Y-%m-%d')
    antigos = {s: p for s, p in precos.items() if min(p) <= limite}
    cabecalho_tabela()
    linha_resumo(f"universo completo ({len(precos)})", base_m)
    if len(antigos) >= cfg['n_pos'] * 2 + 2 and len(antigos) < len(precos):
        d_ant, _ = calendario(antigos, datas[0])
        linha_resumo(f"so os ja listados ({len(antigos)})",
                     metricas(rodar(antigos, d_ant, cfg, ini_str), cfg['rebal']))
    elif len(antigos) == len(precos):
        print("  (todos os pares ja existiam no inicio -- nada a comparar;")
        print("   use --inicio mais antigo para o teste fazer sentido)")
    else:
        print(f"  (so {len(antigos)} pares antigos, insuficiente)")
    print(f"\nPares listados DEPOIS do inicio dos dados: "
          f"{len(precos)-len(antigos)} de {len(precos)}")

    print("\n" + "#" * 70)
    print("# 4. SO COMPRADO vs LONG/SHORT -- e momentum ou e beta de cripto?")
    print("#" * 70)
    cabecalho_tabela()
    linha_resumo("long/short (neutro)", base_m)
    linha_resumo("so comprado",
                 metricas(rodar(precos, datas, dict(cfg, so_comprado=True), ini_str),
                          cfg['rebal']))
    print("\nSe 'so comprado' render muito mais, voce nao esta medindo momentum,")
    print("esta medindo direcao do mercado -- e isso nao precisa de ranking nenhum.")

    if per:
        print("\n" + "#" * 70)
        print("# 5. ALAVANCAGEM E RUINA")
        print("#" * 70)
        painel_alavancagem(per, cfg['rebal'])

    if base_m:
        print("\n" + "#" * 70)
        print("# 6. HIPOTESE NULA -- ranking sorteado")
        print("#" * 70)
        rng = random.Random(42)
        sh = []
        n_sim = a.montecarlo or 200
        for s in range(n_sim):
            mm = metricas(rodar(precos, datas, cfg, ini_str, aleatorio=rng), cfg['rebal'])
            if mm:
                sh.append(mm['sharpe'])
            if (s + 1) % 50 == 0:
                print(f"  ... {s+1}/{n_sim}", flush=True)
        if len(sh) >= 20:
            sh.sort()
            q = lambda p: sh[min(len(sh) - 1, int(p * len(sh)))]
            pct = sum(1 for x in sh if x <= base_m['sharpe']) / len(sh) * 100
            print(f"\nSharpe real {base_m['sharpe']:.2f} | nulo: p5 {q(.05):.2f} "
                  f"mediana {q(.5):.2f} p95 {q(.95):.2f}")
            print(f">>> REAL NO PERCENTIL {pct:.0f} DO NULO")
            print("    acima de 95 = o ranking informa | 5-95 = igual a sorteio")


def imprimir(m, titulo="RESULTADO"):
    if not m:
        print(f"{titulo}: periodos insuficientes")
        return
    print(f"\n{titulo}")
    print(f"  periodos: {m['n']} | retorno medio {m['media']*100:+.2f}% por rebalanceio")
    print(f"  retorno total {m['total']*100:+.1f}% | anualizado {m['anual']*100:+.1f}%")
    print(f"  volatilidade anual {m['vol_anual']*100:.1f}% | Sharpe {m['sharpe']:.2f}")
    print(f"  max drawdown {m['maxdd']*100:.1f}% | periodos positivos {m['pos']*100:.0f}%")
    print(f"  giro medio {m['giro']*100:.0f}% do capital por rebalanceio")
    print(f"  t da media = {m['t']:+.2f}", end="")
    print("  >> nao distinguivel de zero" if abs(m['t']) < 1.96 else "  (significativo a 5%)")


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--inicio', default='2023-01-01')
    ap.add_argument('--fim', default=datetime.now(timezone.utc).strftime('%Y-%m-%d'))
    ap.add_argument('--lookback', type=int, default=30, help='dias do sinal de momentum')
    ap.add_argument('--skip', type=int, default=2, help='dias recentes ignorados')
    ap.add_argument('--rebal', type=int, default=7, help='dias entre rebalanceamentos')
    ap.add_argument('--n-pos', type=int, default=8, help='posicoes em CADA ponta')
    ap.add_argument('--peso', choices=['igual', 'invvol'], default='igual')
    ap.add_argument('--vol-janela', type=int, default=30)
    ap.add_argument('--lado-bruto', type=float, default=0.5,
                    help='fracao do capital em cada ponta (0.5+0.5 = 100%% bruto)')
    ap.add_argument('--so-comprado', action='store_true',
                    help='sem ponta vendida (vira aposta direcional em cripto)')
    ap.add_argument('--custo-pct', type=float, default=0.10,
                    help='taxa+slippage por unidade de giro, em %%')
    ap.add_argument('--split', default=None, help='data YYYY-MM-DD: dentro vs fora da amostra')
    ap.add_argument('--montecarlo', type=int, default=0,
                    help='N carteiras de ranking SORTEADO (hipotese nula)')
    ap.add_argument('--grade', action='store_true', help='varre lookback x rebal')
    ap.add_argument('--completo', action='store_true',
                    help='bateria completa: estabilidade, concentracao, robustez, '
                         'alavancagem e hipotese nula numa rodada so')
    ap.add_argument('--alavancagem', action='store_true',
                    help='painel de alavancagem com probabilidade de ruina')
    ap.add_argument('--vol-alvo', type=float, default=0.0,
                    help='volatilidade anual alvo (ex 0.40). Dimensiona a alavancagem '
                         'dinamicamente em vez de usar um multiplo fixo')
    ap.add_argument('--lev-max', type=float, default=3.0,
                    help='teto de alavancagem quando --vol-alvo esta ligado')
    ap.add_argument('--ativos', default='')
    a = ap.parse_args()

    universo = [x.strip().upper() for x in a.ativos.split(',') if x.strip()] or UNIVERSO
    cfg = {k: getattr(a, k) for k in
           ('lookback', 'skip', 'rebal', 'n_pos', 'peso', 'vol_janela',
            'lado_bruto', 'so_comprado', 'custo_pct')}

    ini, fim = ms(a.inicio), ms(a.fim) + MS_DIA
    # historico extra para o lookback
    aquec = ini - (a.lookback + a.skip + a.vol_janela + 10) * MS_DIA

    print("=" * 74)
    print(f"MOMENTUM TRANSVERSAL | {a.inicio} -> {a.fim}")
    print(f"lookback={a.lookback}d skip={a.skip}d rebal={a.rebal}d "
          f"{a.n_pos}+{a.n_pos} posicoes peso={a.peso} "
          f"{'SO COMPRADO' if a.so_comprado else 'long/short'} custo={a.custo_pct}%/giro")
    print("=" * 74)

    print(f"Baixando {len(universo)} pares...", flush=True)
    precos = carregar(universo, aquec, fim)
    print(f"Universo efetivo: {len(precos)} pares com historico suficiente", flush=True)
    if len(precos) < a.n_pos * 2 + 2:
        print(f"ERRO: preciso de pelo menos {a.n_pos*2+2} pares e so vieram "
              f"{len(precos)}. Reduza --n-pos ou verifique o acesso a Binance.")
        return

    datas, _ = calendario(precos, dia(aquec))

    if a.grade:
        print(f"\n{'lookback':>9} {'rebal':>6} | {'n':>4} {'anual':>8} {'vol':>7} "
              f"{'Sharpe':>7} {'maxDD':>7} {'t':>6}")
        print("-" * 60)
        for lb in (14, 30, 60, 90):
            for rb in (7, 14, 30):
                c = dict(cfg, lookback=lb, rebal=rb)
                m = metricas(rodar(precos, datas, c, a.inicio), rb)
                if not m:
                    continue
                print(f"{lb:>9} {rb:>6} | {m['n']:>4} {m['anual']*100:>+7.1f}% "
                      f"{m['vol_anual']*100:>6.1f}% {m['sharpe']:>7.2f} "
                      f"{m['maxdd']*100:>6.1f}% {m['t']:>+6.2f}")
        print("\nNAO escolha a melhor celula. Com 12 combinacoes, a melhor fica bem")
        print("acima de zero mesmo sem edge nenhum. Procure regiao inteira boa.")
        return

    if a.completo:
        completo(precos, datas, cfg, a, a.inicio)
        print("\n" + "-" * 74)
        print("VIES DE SOBREVIVENCIA: universo = pares que existem HOJE.")
        print("FUNDING nao esta na conta (momentum tende a pagar funding liquido).")
        return

    periodos = rodar(precos, datas, cfg, a.inicio)
    m = metricas(periodos, a.rebal)
    imprimir(m)

    if a.alavancagem and periodos:
        painel_alavancagem(periodos, a.rebal)

    if a.vol_alvo and periodos:
        lev_rets, lev_media, quebrou = aplicar_alavancagem(
            periodos, 1.0, vol_alvo=a.vol_alvo, lev_max=a.lev_max)
        falsos = [(p[0], p[1], r, p[3]) for p, r in zip(periodos, lev_rets)]
        print(f"\n--- COM VOL ALVO {a.vol_alvo*100:.0f}% a.a. "
              f"(teto {a.lev_max}x, alavancagem media usada {lev_media:.2f}x)")
        if quebrou:
            print("    LIQUIDADO no caminho historico.")
        else:
            imprimir(metricas(falsos, a.rebal), "RESULTADO DIMENSIONADO POR VOL")

    if a.split and periodos:
        d1 = [p for p in periodos if p[0] < a.split]
        d2 = [p for p in periodos if p[0] >= a.split]
        imprimir(metricas(d1, a.rebal), f"ATE {a.split}")
        imprimir(metricas(d2, a.rebal), f"DE {a.split} EM DIANTE")

    if a.montecarlo and m:
        print("\n" + "=" * 74)
        print(f"HIPOTESE NULA -- {a.montecarlo} carteiras com ranking SORTEADO")
        print("Mesmo universo, mesmo numero de posicoes, so o ranking e aleatorio.")
        print("=" * 74)
        rng = random.Random(42)
        sharpes = []
        for s in range(a.montecarlo):
            mm = metricas(rodar(precos, datas, cfg, a.inicio, aleatorio=rng), a.rebal)
            if mm:
                sharpes.append(mm['sharpe'])
            if (s + 1) % 50 == 0:
                print(f"  ... {s+1}/{a.montecarlo}")
        if len(sharpes) >= 20:
            sharpes.sort()
            q = lambda p: sharpes[min(len(sharpes) - 1, int(p * len(sharpes)))]
            pct = sum(1 for x in sharpes if x <= m['sharpe']) / len(sharpes) * 100
            print(f"\nSharpe real: {m['sharpe']:.2f}")
            print(f"Nulo: mediana {q(.5):.2f} | p5 {q(.05):.2f} | p95 {q(.95):.2f}")
            print(f"Real no percentil {pct:.0f} do nulo.")
            print(">> O ranking de momentum carrega informacao." if pct >= 95 else
                  ">> Ranking invertido seria melhor (momentum negativo)." if pct <= 5 else
                  ">> Mesmo desempenho de carteiras sorteadas: sem edge nesta amostra.")

    if periodos:
        with open(CSV_SAIDA, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['inicio', 'fim', 'retorno_liquido', 'giro'])
            w.writerows(periodos)
        print(f"\nCSV: {CSV_SAIDA}")

    print("\n" + "-" * 74)
    print("VIES DE SOBREVIVENCIA: o universo e a lista de pares que existem HOJE.")
    print("Moedas que foram a zero ou foram deslistadas nao estao aqui, e elas")
    print("estariam na ponta VENDIDA. O resultado e a versao otimista -- exija")
    print("margem folgada antes de acreditar.")
    print("Cripto anda junta: 40 pares nao sao 40 amostras independentes.")
    print("FUNDING: numa carteira neutra em dolar o funding quase se cancela --")
    print("a ponta comprada paga, a vendida recebe. Mas momentum compra o que subiu,")
    print("que costuma ter funding ALTO (longs aglomerados), e vende o que caiu,")
    print("que tem funding baixo. O saldo tende a ser negativo. Nao esta nesta conta.")


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except Exception:
        # imprime no stdout para o erro aparecer no resumo do job, nao so no stderr
        print("\n=== ERRO ===")
        traceback.print_exc(file=sys.stdout)
        sys.exit(1)
