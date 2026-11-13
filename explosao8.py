"""Explosao de vela unica -- DESLIGADO. Reavaliado e ENCERRADO 13/11/2026.

Saiu do bot em 12/11 a pedido do Eduardo (32% de acerto, dinheiro
vindo de poucas operacoes grandes). Em 13/11 foi reavaliado com TUDO o
que o dia ensinou -- universo rolante de 7 anos, contagem por LOTE,
alvo no EXTREMO da estrutura, filtro de encosto raso na altura do
proprio bloco, em H2, H4 e H8, e alvos projetados ate 300%.

VINTE E NOVE variantes. Todas negativas no liquido, e o BRUTO tambem
negativo ou nulo em quase todas -- nao e taxa, nao ha vantagem antes
de qualquer custo.

      H4 · projecao  90%   22,7% acerto, 1:4,22, bruto +2,50, liq -2,00
      H4 · projecao 100%   22,0%,        1:4,45, bruto +3,70, liq -0,80
      H4 · projecao 125%   19,9%,        1:5,05, bruto +4,00, liq -0,70
      H4 · alvo no extremo 37,4%,        1:2,08, bruto -0,50, liq -4,10
      H8 · alvo no extremo 37,8%,        1:2,03, bruto -3,10, liq -6,50
      H2 · alvo no extremo 36,0%,        1:2,08, bruto -5,80, liq -10,30

  O alvo no extremo levanta o acerto de 21,5% para 37,8% -- e derruba o
  R:R de 4,2 para 2,0. Troca seis por meia duzia.

  A melhor celula das 29 (H4, projecao 125%, encosto <= 0,25x) da +0,10
  por operacao e bate entrada aleatoria por apenas +1,10 desvios. A
  regua, marcada ANTES de rodar, era liquido positivo E mais de 2
  desvios por lote. Nao passou em nenhuma das duas.

A CAUSA, e e a licao que se repete: FREQUENCIA. Sao 17 a 21 operacoes
por mes no H4 (e 44 no H2). Com 100 USD de risco isso da quase 90 USD
por mes so de corretagem, e a vantagem bruta e de 4. O setup 3 da 1,6
operacao por mes com bruto de +43 -- dez vezes menos operacoes, dez
vezes mais vantagem em cada uma.

E A CONCLUSAO QUE VALE MAIS QUE O TESTE: o setup 2 E o setup 3 sem os
filtros que fazem o setup 3 funcionar. A diferenca entre eles e
exatamente o contexto -- a queda previa de sete dias, a explosao
saindo do terco de baixo da faixa, e o rompimento do ULTIMO PIVO em vez
do extremo de 20 velas. Esses tres filtros levam de 10 operacoes por
mes para 1,6, e de negativo para +39,60 por operacao. O contexto do
setup 3 nao e decoracao: e ele que carrega o resultado inteiro.

NAO RETESTAR sem dado novo. Ver analise/setup2_novo.py.

Nao mexe no setup que ja roda. Tem estado e historico proprios, para o
placar da varredura nao se misturar com o que ainda esta sendo medido.

O que ESTE codigo mede no historico (71 moedas com volume mediano >=
0,32 M USD/h, 23 meses, risco fixo de 100 USD por operacao):

      99 operacoes, 4,3 por mes, 32,3% de acerto
      +31,40 por operacao  ·  2025 +45,40  ·  2026 +18,20  ·  z +1,41
      pior sequencia 12 stops  ·  pior rebaixamento 1.544

  no terco maior (23 moedas): 33 operacoes, 42,4% de acerto,
      +55,90 por operacao  ·  2025 +68,90  ·  2026 +38,40
      pior sequencia 4 stops  ·  pior rebaixamento 541

  A mediana e um stop cheio: mais da metade das operacoes perde tudo o
  que arriscou. O dinheiro vem de poucas operacoes grandes.

  O codigo de pesquisa media +41,60 e +69,90 nos mesmos cortes, porque
  detectava o encosto no order block dentro da hora. O bot so enxerga
  velas de 8h fechadas, entao entrega ~25% menos. Os numeros acima sao
  os do bot, que sao os que valem.

As regras:
  1. UMA vela de 8h que, ao mesmo tempo: e >= 2,5x a volatilidade media
     de 14 velas, tem corpo >= 50% do tamanho dela, tem volume >= 1,5x a
     media de 20 velas, e fecha alem do extremo das ultimas 20 velas.
     A volatilidade e o volume sao medidos ANTES dela.
  2. Filtros: RSI(14) depois da explosao >= 70 (na direcao da operacao)
     e a vela estendeu >= 0,5 volatilidade alem do proprio fechamento
     antes de comecar a voltar.
  3. Order block: ultima vela de cor contraria antes da explosao.
  4. O preco volta e ENCOSTA no order block (nao precisa furar).
  5. Nas 4 velas seguintes, uma fecha de volta para fora do order block,
     a favor, com corpo >= 50% ou pavio >= 50%. Entrada no fechamento.
  6. Stop logo abaixo da base do order block.
  7. Alvo: topo da vela de explosao + 90% do tamanho dela.
  8. O filtro de risco/retorno (1:1,2) mede ate o TOPO da explosao, nao
     ate o alvo projetado. E assim que o backtest foi medido: o filtro
     julga a geometria do setup, e o alvo so decide onde colher.
  9. Cancela se o preco atravessar o order block inteiro.
"""
import csv
import json
import os
from datetime import datetime, timedelta, timezone

BRT = timezone(timedelta(hours=-3))
ARQUIVO = "explosao8_estado.json"
HISTORICO = "historico_explosao8.csv"
MAX_BARRAS = 120          # ate quantas velas de 8h segurar a operacao

CFG8 = dict(sigma=2.5, vol=1.5, janela=20, ob_busca=6, espera=30,
            gatilho_max=4, furo_max=1.0, rr_min=1.2, stop_folga=0.10,
            rsi_min=70.0, est_min=0.5, alvo_proj=0.9)


# ---------------------------------------------------------------- medidas
def atr(h, n=14):
    tr, a = [], [0.0] * len(h)
    for i, v in enumerate(h):
        if i == 0:
            tr.append(v[2] - v[3])
        else:
            pc = h[i-1][4]
            tr.append(max(v[2]-v[3], abs(v[2]-pc), abs(v[3]-pc)))
        if i >= n:
            a[i] = a[i-1] + (tr[i] - a[i-1]) / n
        elif i == n - 1:
            a[i] = sum(tr[:n]) / n
    return a


def medvol(h, n=20):
    m, s = [0.0] * len(h), 0.0
    for i, v in enumerate(h):
        s += v[5]
        if i >= n:
            s -= h[i-n][5]
        if i >= n - 1:
            m[i] = s / n
    return m


def rsi(h, p=14):
    r = [50.0] * len(h)
    if len(h) <= p:
        return r
    gan = per = 0.0
    for i in range(1, p + 1):
        d = h[i][4] - h[i-1][4]
        gan += max(d, 0.0); per += max(-d, 0.0)
    gan /= p; per /= p
    r[p] = 100 - 100/(1 + gan/per) if per else 100.0
    for i in range(p + 1, len(h)):
        d = h[i][4] - h[i-1][4]
        gan = (gan*(p-1) + max(d, 0.0)) / p
        per = (per*(p-1) + max(-d, 0.0)) / p
        r[i] = 100 - 100/(1 + gan/per) if per else 100.0
    return r


# ---------------------------------------------------------------- padrao
def seguir(h, a, i, alta, cfg):
    """Da explosao em i ate o gatilho. Devolve None se nao chegou la."""
    ob_base = ob_topo = None
    j = i - 1
    while j >= max(0, i - cfg['ob_busca']):
        if (h[j][4] > h[j][1]) != alta:
            ob_base, ob_topo = h[j][3], h[j][2]
            break
        j -= 1
    if ob_base is None:
        return None
    borda = ob_topo if alta else ob_base
    topo = h[i][2] if alta else h[i][3]
    tam = h[i][2] - h[i][3]
    morte = (ob_base - a[i]*cfg['furo_max']) if alta else \
            (ob_topo + a[i]*cfg['furo_max'])

    pico = topo
    tocou = extremo = None
    for k in range(i + 1, min(i + 1 + cfg['espera'], len(h))):
        hi, lo, o, cl = h[k][2], h[k][3], h[k][1], h[k][4]
        if tocou is None:
            pico = max(pico, hi) if alta else min(pico, lo)
            if (lo <= borda) if alta else (hi >= borda):
                tocou, extremo = k, (lo if alta else hi)
            else:
                continue
        else:
            extremo = min(extremo, lo) if alta else max(extremo, hi)
        if (extremo < morte) if alta else (extremo > morte):
            return None
        if k - tocou > cfg['gatilho_max']:
            return None
        if (hi >= pico) if alta else (lo <= pico):
            return None            # foi para o alvo sem a gente
        rng = hi - lo
        dentro = (cl > borda) if alta else (cl < borda)
        if rng <= 0 or not dentro:
            continue
        favor = (cl > o) if alta else (cl < o)
        corpo = abs(cl - o) / rng
        pavio = ((min(o, cl) - lo) if alta else (hi - max(o, cl))) / rng
        if not (favor and (corpo >= 0.5 or pavio >= 0.5)):
            continue

        ent = cl
        # a folga usa a volatilidade da vela da EXPLOSAO, nao a do
        # gatilho -- e assim que o backtest mediu
        stop = (ob_base - a[i]*cfg['stop_folga']) if alta else \
               (ob_topo + a[i]*cfg['stop_folga'])
        risco = abs(ent - stop)
        if risco <= 0:
            return None
        # o filtro mede ate o TOPO; o alvo vai alem dele
        ate_topo = (pico - ent) if alta else (ent - pico)
        if ate_topo <= 0 or ate_topo / risco < cfg['rr_min']:
            return None
        alvo = (topo + cfg['alvo_proj']*tam) if alta else \
               (topo - cfg['alvo_proj']*tam)
        dist = (alvo - ent) if alta else (ent - alvo)
        if dist <= 0:
            return None
        return dict(lado='compra' if alta else 'venda', entrada=ent,
                    stop=stop, alvo=alvo, rr=dist/risco, rr_topo=ate_topo/risco,
                    risco_pct=risco/ent*100, idx=k, vela_ms=h[k][0],
                    topo=pico, exp_ms=h[i][0], exp_idx=i,
                    # 13/11/2026: expostos para a reavaliacao em
                    # analise/setup2_novo.py -- o filtro de profundidade do
                    # encosto precisa do bloco e do extremo, e o alvo no
                    # extremo da explosao precisa de exp_topo
                    ob_base=ob_base, ob_topo=ob_topo, extremo=extremo,
                    exp_topo=topo, tam=tam)


def achar(h, cfg=None, atraso_max=1):
    """O gatilho que acabou de fechar, se houver. Aceita tambem a vela
    anterior: o Actions as vezes pula uma hora agendada."""
    cfg = cfg or CFG8
    if len(h) < 70:
        return None
    a, mv, rs = atr(h, 14), medvol(h, 20), rsi(h, 14)
    jan = cfg['janela']
    for i in range(len(h) - 2, max(jan, 21), -1):
        o, hi, lo, cl, vol = h[i][1], h[i][2], h[i][3], h[i][4], h[i][5]
        rng = hi - lo
        if rng <= 0 or a[i-1] <= 0 or mv[i-1] <= 0:
            continue
        if rng < cfg['sigma']*a[i-1] or abs(cl-o)/rng < 0.5:
            continue
        if vol < cfg['vol']*mv[i-1]:
            continue
        alta = cl > o
        if alta and cl <= max(x[2] for x in h[i-jan:i]):
            continue
        if not alta and cl >= min(x[3] for x in h[i-jan:i]):
            continue
        # filtro 1: o RSI depois da explosao, na direcao da operacao
        r = rs[i] if alta else 100 - rs[i]
        if r < cfg['rsi_min']:
            continue
        g = seguir(h, a, i, alta, cfg)
        if not g:
            continue
        # filtro 2: estendeu alem do proprio fechamento antes de voltar
        est = abs(g['topo'] - h[i][4]) / a[i] if a[i] else 0.0
        if est < cfg['est_min']:
            continue
        atraso = len(h) - 1 - g['idx']
        if atraso > atraso_max:
            return None       # o gatilho mais recente ja e velho
        g['atraso'] = atraso
        g['rsi'] = r
        g['estendeu'] = est
        return g
    return None


def historico(h, cfg=None):
    """Todos os gatilhos da serie, com a MESMA logica do alerta ao vivo.

    Serve para medir o setup exatamente como o bot vai executa-lo, sem
    depender do codigo de pesquisa.
    """
    cfg = cfg or CFG8
    if len(h) < 70:
        return []
    a, mv, rs = atr(h, 14), medvol(h, 20), rsi(h, 14)
    jan = cfg['janela']
    fora, i = [], max(jan, 21) + 1
    while i < len(h) - 2:
        o, hi, lo, cl, vol = h[i][1], h[i][2], h[i][3], h[i][4], h[i][5]
        rng = hi - lo
        if rng <= 0 or a[i-1] <= 0 or mv[i-1] <= 0 \
                or rng < cfg['sigma']*a[i-1] or abs(cl-o)/rng < 0.5 \
                or vol < cfg['vol']*mv[i-1]:
            i += 1; continue
        alta = cl > o
        if alta and cl <= max(x[2] for x in h[i-jan:i]):
            i += 1; continue
        if not alta and cl >= min(x[3] for x in h[i-jan:i]):
            i += 1; continue
        r = rs[i] if alta else 100 - rs[i]
        if r < cfg['rsi_min']:
            i += 1; continue
        g = seguir(h, a, i, alta, cfg)
        if not g:
            i += 1; continue
        est = abs(g['topo'] - h[i][4]) / a[i] if a[i] else 0.0
        if est < cfg['est_min']:
            i += 1; continue
        g['rsi'], g['estendeu'] = r, est
        fora.append(g)
        i = g['idx'] + 1
    return fora


# -------------------------------------------------------------- mensagem
def msg(sim, g, quando, fmt, msg_mao):
    seta = "🟢" if g['lado'] == 'compra' else "🔴"
    return (
        f"🧪 <b>EM TESTE</b> — explosão de 8h   "
        f"<i>sem dinheiro, só para medir</i>\n\n"
        f"{seta} <b>{sim.replace('USDT', '/USDT')}</b> — "
        f"<b>{g['lado'].upper()}</b>\n"
        f"vela de 8h fechada às {quando(g['vela_ms'])} (Brasília)"
        + ("  <i>⚠️ chegou atrasado, a rodada anterior falhou</i>"
           if g.get('atraso') else "") + "\n\n"
        f"entrada  <code>{fmt(g['entrada'])}</code>\n"
        f"stop     <code>{fmt(g['stop'])}</code>   "
        f"risco <b>{g['risco_pct']:.2f}%</b>\n"
        f"alvo     <code>{fmt(g['alvo'])}</code>   "
        f"<b>R:R 1:{g['rr']:.2f}</b>\n"
        f"<i>topo da explosão em {fmt(g['topo'])}; o alvo fica 90% do "
        f"tamanho da vela acima dele</i>\n"
        f"<i>RSI {g['rsi']:.0f} · estendeu {g['estendeu']:.1f}x a "
        f"volatilidade</i>\n"
        + msg_mao(g['risco_pct']) +
        f"\n\n<i>No histórico isso acerta 32% das vezes e a mediana é um "
        f"stop cheio — o dinheiro vem de poucas operações grandes. "
        f"Por isso está em teste: anota, não opera.</i>")


# ----------------------------------------------------------------- estado
def ler():
    try:
        with open(ARQUIVO) as f:
            return json.load(f)
    except Exception:
        return {}


def gravar(d):
    try:
        with open(ARQUIVO, "w") as f:
            json.dump(d, f, indent=1)
    except Exception:
        pass


def registrar(d, sim, g):
    ch = f"{sim}-{g['vela_ms']}"
    if ch in d:
        return False
    d[ch] = dict(sim=sim, lado=g['lado'], entrada=g['entrada'],
                 stop=g['stop'], alvo=g['alvo'], rr=g['rr'],
                 risco_pct=g['risco_pct'], vela_ms=g['vela_ms'],
                 rsi=g['rsi'], estendeu=g['estendeu'], status='aberto')
    return True


def revisar(d, series8, fmt, quando):
    """Resolve as operacoes abertas contra as velas novas de 8h."""
    saidas = []
    for ch, r in d.items():
        if r.get('status') != 'aberto':
            continue
        h = series8.get(r['sim'])
        if not h:
            continue
        compra = r['lado'] == 'compra'
        fim = preco = None
        n = 0
        for v in h:
            if v[0] <= r['vela_ms']:
                continue
            n += 1
            if n > MAX_BARRAS:
                fim, preco = 'tempo', v[4]
                break
            if compra:
                if v[3] <= r['stop']: fim, preco = 'stop', r['stop']; break
                if v[2] >= r['alvo']: fim, preco = 'alvo', r['alvo']; break
            else:
                if v[2] >= r['stop']: fim, preco = 'stop', r['stop']; break
                if v[3] <= r['alvo']: fim, preco = 'alvo', r['alvo']; break
            r['ms_fim'] = v[0]
        if fim is None:
            continue
        r['status'] = fim
        r['saida'] = preco
        mov = (preco - r['entrada'])/r['entrada'] * (1 if compra else -1)
        r['resultado_pct'] = mov * 100
        r['por_100_risco'] = mov / (r['risco_pct']/100) * 100
        cara = "✅" if r['por_100_risco'] > 0 else "❌"
        saidas.append(
            f"🧪 <b>EM TESTE</b> — desfecho da explosão de 8h\n\n"
            f"{cara} <b>{r['sim'].replace('USDT', '/USDT')}</b> "
            f"{r['lado']} — bateu o <b>{fim}</b> em "
            f"<code>{fmt(preco)}</code>\n"
            f"entrada de {quando(r['vela_ms'])}: "
            f"<code>{fmt(r['entrada'])}</code>\n"
            f"movimento <b>{mov*100:+.2f}%</b>  →  "
            f"<b>{r['por_100_risco']:+.0f}</b> para cada 100 arriscados")
        _csv(r)
    return saidas


def _csv(r):
    novo = not os.path.exists(HISTORICO)
    try:
        with open(HISTORICO, "a", newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            if novo:
                w.writerow(['data_brasilia', 'par', 'lado', 'entrada', 'stop',
                            'alvo', 'stop_pct', 'risco_retorno', 'rsi',
                            'estendeu', 'fim', 'saida', 'resultado_pct',
                            'por_100_de_risco'])
            w.writerow([
                f"{datetime.fromtimestamp(r['vela_ms']/1000, BRT):%Y-%m-%d %H:%M}",
                r['sim'], r['lado'], f"{r['entrada']:.8g}",
                f"{r['stop']:.8g}", f"{r['alvo']:.8g}",
                f"{r['risco_pct']:.2f}", f"{r['rr']:.2f}",
                f"{r.get('rsi', 0):.0f}", f"{r.get('estendeu', 0):.2f}",
                r['status'], f"{r.get('saida', 0):.8g}",
                f"{r.get('resultado_pct', 0):.2f}",
                f"{r.get('por_100_risco', 0):.0f}"])
    except Exception:
        pass


def placar(d):
    fechadas = [r for r in d.values() if r.get('status') in ('stop', 'alvo',
                                                             'tempo')]
    abertas = [r for r in d.values() if r.get('status') == 'aberto']
    if not fechadas:
        return (f"🧪 explosão de 8h em teste: {len(abertas)} aberta(s), "
                f"nenhuma resolvida ainda")
    g = [r for r in fechadas if r['por_100_risco'] > 0]
    soma = sum(r['por_100_risco'] for r in fechadas)
    return (f"🧪 <b>explosão de 8h — em teste</b>\n"
            f"{len(fechadas)} resolvidas · {len(g)} acertos "
            f"({len(g)/len(fechadas)*100:.0f}%) · {len(abertas)} abertas\n"
            f"soma: <b>{soma:+.0f}</b> para cada 100 arriscados por operação\n"
            f"média: <b>{soma/len(fechadas):+.0f}</b> por operação\n"
            f"<i>o backtest esperava ~+31 por operação e 32% de acerto. "
            f"Decisão em 20 operações.</i>")
