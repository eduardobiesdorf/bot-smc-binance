"""SETUP 5 ao vivo -- rompimento falso com falha do topo, em H1.

A regra, na ordem em que o codigo checa:

  1. CONTEXTO     a faixa esta inteira acima de um topo JA ROMPIDO (ou
                  abaixo de um fundo perdido). O topo e um pivo de 20
                  velas de cada lado, procurado nas 300 velas anteriores,
                  e a faixa tem de estar limpa dele por meia altura dela
  2. LATERALIDADE 60 velas de H1, estreita, sem deriva e cruzando o meio
  3. A IDA        fecha para fora da faixa e anda >= 0.25 da altura dela,
                  com o volume medio 1.3x o da faixa
  4. FORCA CONTRARIA  vela contra o movimento, >= 2 volatilidades, corpo
                  de 50%. E o ALERTA -- e o aviso de radar sai aqui
  5. A FALHA      nao faz nova maxima e PERDE O EXTREMO DA PROPRIA VELA
                  DE FORCA. E a ENTRADA
  6. STOP acima da maxima da ida  ·  ALVO na ultima piscina de liquidez
     nao consumida alem de TODA a faixa

Rompeu para cima e falhou -> VENDE. Para baixo -> COMPRA. A operacao e
sempre A FAVOR do contexto.

Medido no universo ROLANTE (as 150 maiores re-sorteadas a cada trimestre
pelo volume do trimestre anterior, para nao olhar o futuro), com risco
fixo de 100 por operacao:

                      7 anos          de 2025 para ca
  operacoes           299 (3.6/mes)   113 (5.1/mes)
  acerto              51.8%           51.3%
  risco/retorno       1:2.05          1:2.16
  por operacao        +48.10          +54.70
  z por LOTE          +2.46           +2.01
  maior lote          26%             39%
  rebaixamento        -1,015          -718
  anos positivos      6 de 7          2 de 2

O contexto e o que carrega tudo: de 2025 para ca, SEM ele o setup da
-1.00 por operacao e CONTRA ele -6.40. O z por LOTE agrupa o que cai
dentro de 14 dias, porque as entradas disparam em bloco -- a pior
sequencia foi 8 moedas stopando no mesmo dia.

O que ainda NAO esta provado: 2024 sozinho carrega 46% do lucro; 2021
foi negativo; 2020 e 2022 foram empate disfarcado. Por isso entra EM
TESTE, sem dinheiro, igual a reversao de 8h entrou.
"""
import csv
import json
import os
from datetime import datetime, timedelta, timezone

import explosao8 as exp8

BRT = timezone(timedelta(hours=-3))
ARQUIVO = "falha5_estado.json"
HISTORICO = "historico_falha5.csv"
MAX_BARRAS = 240          # velas de 1h segurando a operacao (10 dias)

CFG = dict(
    lat_jan=60,        # velas da lateralidade. 150 perdeu nas oito
                       # combinacoes testadas; 30 nao e faixa, e ruido
    aperto=1.00,       # a faixa tem de ser mais estreita que o passeio
                       # normal de L velas, que e ~raiz(L) volatilidades.
                       # O limite e aperto*raiz(L): aqui 7.7 volatilidades
    deriva_max=0.35,   # 10 primeiros fechamentos x 10 ultimos, medido na
                       # altura da faixa. Sem isto, TENDENCIA entra como faixa
    toques_div=18,     # cruzamentos minimos do meio da faixa = L/18, min 3
    ida_max=24, ida_min=2,
    ida_min_alt=0.25,  # o quanto a ida anda para fora da faixa
    vol_sobe=1.3,      # volume medio da ida / volume medio da faixa
    forca_sigma=2.0, forca_corpo=0.5,
    forca_apos=99,     # velas que a forca pode chegar depois da maxima.
                       # Travar em 3-5 parecia melhor no universo viciado,
                       # mas NAO replicou no rolante: sem trava da 6 de 7
                       # anos positivos contra 5 de 7
    falha_max=16,      # velas para a falha acontecer
    pre_jan=300, pre_pivo=20, pre_folga=0.5,
    stop_folga=0.15,
    rr_min=1.2,
    liq_janela=120,    # ate onde procurar a piscina
)


# ------------------------------------------------------------- piscina
def piscina(h, i, compra, ref, janela):
    """Distancia ate a liquidez nao consumida mais proxima de `ref`.

    Copia da que esta no bot_varredura. Fica aqui para este modulo nao
    importar o bot, que importa este -- seria circular.
    """
    melhor = None
    for k in range(max(3, i - janela), i - 3):
        if compra:
            ext = all(h[k][3] < h[k-m][3] for m in (1, 2, 3)) and \
                  all(h[k][3] < h[k+m][3] for m in (1, 2, 3))
            if not ext or h[k][3] >= ref:
                continue
            if any(h[j][3] <= h[k][3] for j in range(k+4, i+1)):
                continue                      # ja foi consumida
            d = ref - h[k][3]
        else:
            ext = all(h[k][2] > h[k-m][2] for m in (1, 2, 3)) and \
                  all(h[k][2] > h[k+m][2] for m in (1, 2, 3))
            if not ext or h[k][2] <= ref:
                continue
            if any(h[j][2] >= h[k][2] for j in range(k+4, i+1)):
                continue
            d = h[k][2] - ref
        if melhor is None or d < melhor:
            melhor = d
    return melhor


# ----------------------------------------------------------- montagens
def _montagens(h, cfg, a, mv, desde):
    """As montagens cujo rompimento comecou em `desde` ou depois.

    Devolve, da mais recente para a mais velha, o dicionario da faixa +
    ida + vela de forca. A ENTRADA nao entra aqui: quem decide e achar().
    """
    L = cfg['lat_jan']
    teto = cfg['aperto'] * (L ** 0.5)
    cruz_min = max(3, round(L / cfg['toques_div']))
    q = cfg['pre_pivo']
    out = []
    for i in range(max(L + 20, desde), len(h) - 1):
        if a[i-1] <= 0 or mv[i-1] <= 0:
            continue
        faixa = h[i-L:i]
        topo = max(x[2] for x in faixa)
        base = min(x[3] for x in faixa)
        alt = topo - base
        if alt <= 0 or alt > teto*a[i-1]:
            continue
        ini = sum(x[4] for x in faixa[:10])/10
        fim = sum(x[4] for x in faixa[-10:])/10
        if abs(fim - ini)/alt > cfg['deriva_max']:
            continue                       # isto e tendencia, nao faixa
        meio = (topo + base)/2
        cruz = sum(1 for n in range(1, L)
                   if (faixa[n-1][4] - meio)*(faixa[n][4] - meio) < 0)
        if cruz < cruz_min:
            continue
        # 1) o CONTEXTO: a faixa esta em cima de um pivo ja rompido?
        ctx = None
        p0, p1 = max(q, i - L - cfg['pre_jan']), i - L - q
        for k in range(p0, max(p0, p1)):
            if ctx:
                break
            if all(h[k][2] >= h[k-m][2] and h[k][2] >= h[k+m][2]
                   for m in range(1, q+1)) \
                    and base > h[k][2] + cfg['pre_folga']*alt:
                ctx = 'alta'
            elif all(h[k][3] <= h[k-m][3] and h[k][3] <= h[k+m][3]
                     for m in range(1, q+1)) \
                    and topo < h[k][3] - cfg['pre_folga']*alt:
                ctx = 'baixa'
        if ctx is None:
            continue
        cl = h[i][4]
        if cl > topo:
            alta = True
        elif cl < base:
            alta = False
        else:
            continue
        # a operacao e sempre A FAVOR do contexto: a ida e o rompimento
        # FALSO, entao ela aponta para o lado contrario ao contexto
        if not ((ctx == 'alta' and not alta) or (ctx == 'baixa' and alta)):
            continue
        vol_lat = sum(x[5] for x in faixa)/len(faixa)
        ext, k_ext, k_forca = (h[i][2] if alta else h[i][3]), i, None
        for k in range(i+1, min(i+1+cfg['ida_max'], len(h))):
            ok, hk, lk, ck = h[k][1], h[k][2], h[k][3], h[k][4]
            if (hk > ext) if alta else (lk < ext):
                ext, k_ext = (hk if alta else lk), k
            if k - i < cfg['ida_min']:
                continue
            rk = hk - lk
            if rk > 0 and rk >= cfg['forca_sigma']*a[k-1] \
                    and abs(ck-ok)/rk >= cfg['forca_corpo'] \
                    and ((ck < ok) if alta else (ck > ok)) \
                    and k - k_ext <= cfg['forca_apos']:
                k_forca = k
                break
        if k_forca is None:
            continue
        if ((ext - topo) if alta else (base - ext))/alt < cfg['ida_min_alt']:
            continue                       # a ida foi um pavio, nao sweep
        vol_ida = sum(x[5] for x in h[i:k_forca+1])/(k_forca+1-i)
        if vol_lat <= 0 or vol_ida/vol_lat < cfg['vol_sobe']:
            continue
        out.append(dict(lado='venda' if alta else 'compra', alta=alta,
                        i=i, topo=topo, base=base, alt=alt, ext=ext,
                        k_ext=k_ext, k_forca=k_forca, ctx=ctx, cruz=cruz,
                        vol_x=vol_ida/vol_lat, forca_ms=h[k_forca][0],
                        forca_lim=h[k_forca][3] if alta else h[k_forca][2],
                        excur=((ext-topo) if alta else (base-ext))/alt,
                        lat_atr=alt/a[i-1]))
    return out[::-1]


def _numeros(h, m, k, a, cfg, ent):
    """Stop, alvo e R:R de uma montagem, com a entrada em `ent`."""
    alta = m['alta']
    stop = m['ext'] + a[k]*cfg['stop_folga'] if alta else \
           m['ext'] - a[k]*cfg['stop_folga']
    if (stop <= ent) if alta else (stop >= ent):
        return None
    borda = m['base'] if alta else m['topo']
    d = piscina(h, k, alta, borda, min(len(h), cfg['liq_janela']))
    if d is None:
        return None                        # sem liquidez parada: sem alvo
    alvo = borda - d if alta else borda + d
    risco = abs(ent - stop)
    dist = (ent - alvo) if alta else (alvo - ent)
    if risco <= 0 or dist <= 0 or dist/risco < cfg['rr_min']:
        return None
    return dict(entrada=ent, stop=stop, alvo=alvo, rr=dist/risco,
                risco_pct=risco/ent*100)


# ------------------------------------------------------------- achar
def achar(h, cfg=None, atraso_max=1):
    """O gatilho que acabou de fechar, se houver."""
    cfg = cfg or CFG
    if len(h) < cfg['lat_jan'] + cfg['pre_jan'] + 60:
        return None
    a, mv = exp8.atr(h, 14), exp8.medvol(h, 20)
    desde = len(h) - cfg['lat_jan'] - cfg['ida_max'] - cfg['falha_max'] - 4
    for m in _montagens(h, cfg, a, mv, max(0, desde)):
        alta = m['alta']
        for k in range(m['k_forca']+1,
                       min(m['k_forca']+1+cfg['falha_max'], len(h))):
            hk, lk, ck = h[k][2], h[k][3], h[k][4]
            if (hk > m['ext']) if alta else (lk < m['ext']):
                break                      # retomou: nao houve falha
            if not ((ck < m['forca_lim']) if alta else (ck > m['forca_lim'])):
                continue
            n = _numeros(h, m, k, a, cfg, ck)
            if not n:
                break
            atraso = len(h) - 1 - k
            if atraso > atraso_max:
                return None                # o gatilho mais recente e velho
            g = dict(m, **n)
            g.update(idx=k, vela_ms=h[k][0], atraso=atraso,
                     velas_forca=k - m['k_forca'])
            return g
    return None


def achar_contexto(h, cfg=None):
    """A montagem armada, esperando a falha. E o aviso de radar."""
    cfg = cfg or CFG
    if len(h) < cfg['lat_jan'] + cfg['pre_jan'] + 60:
        return None
    a, mv = exp8.atr(h, 14), exp8.medvol(h, 20)
    desde = len(h) - cfg['lat_jan'] - cfg['ida_max'] - cfg['falha_max'] - 4
    fim = len(h) - 1
    for m in _montagens(h, cfg, a, mv, max(0, desde)):
        alta = m['alta']
        espera = fim - m['k_forca']
        if espera < 0 or espera > cfg['falha_max']:
            continue                       # ja passou da janela
        morreu = False
        for k in range(m['k_forca']+1, fim+1):
            hk, lk, ck = h[k][2], h[k][3], h[k][4]
            if (hk > m['ext']) if alta else (lk < m['ext']):
                morreu = True; break       # retomou a maxima: acabou
            if (ck < m['forca_lim']) if alta else (ck > m['forca_lim']):
                morreu = True; break       # ja disparou; nao e mais aviso
        if morreu:
            continue
        n = _numeros(h, m, fim, a, cfg, m['forca_lim'])
        if not n:
            continue
        g = dict(m, **n)
        g.update(idx=fim, ref=h[fim][4], horas=espera,
                 falta=cfg['falha_max'] - espera, vela_ms=h[fim][0])
        return g
    return None


# ----------------------------------------------------------- mensagens
def _cab():
    return ("🧪 <b>EM TESTE</b> — rompimento falso (H1)   "
            "<i>sem dinheiro, só para medir</i>\n\n")


def _ctx(g):
    return ("topo anterior rompido" if g['ctx'] == 'alta'
            else "fundo anterior perdido")


def msg(sim, g, quando, fmt, msg_mao):
    seta = "🟢" if g['lado'] == 'compra' else "🔴"
    lado_ida = "para cima" if g['alta'] else "para baixo"
    return (
        _cab() +
        f"{seta} <b>{sim.replace('USDT', '/USDT')}</b> — "
        f"<b>{g['lado'].upper()}</b>\n"
        f"gatilho na vela de 1h de {quando(g['vela_ms'])} (Brasília)"
        + ("  <i>⚠️ chegou atrasado</i>" if g.get('atraso') else "") + "\n"
        f"<i>falhou o {'topo' if g['alta'] else 'fundo'}: perdeu o extremo "
        f"da vela de força {g['velas_forca']} vela(s) depois dela</i>\n\n"
        f"faixa  <code>{fmt(g['base'])}</code> a "
        f"<code>{fmt(g['topo'])}</code>   "
        f"<i>60 velas, {g['cruz']} cruzamentos</i>\n"
        f"<i>em cima de {_ctx(g)} — o contexto é a favor desta "
        f"{g['lado']}</i>\n"
        f"<i>rompeu {lado_ida} andando {g['excur']:.2f}x a altura da faixa, "
        f"com {g['vol_x']:.1f}x o volume dela, e falhou</i>\n\n"
        f"entrada  <code>{fmt(g['entrada'])}</code>\n"
        f"stop     <code>{fmt(g['stop'])}</code>   "
        f"risco <b>{g['risco_pct']:.2f}%</b>   "
        f"<i>(acima da máxima da ida)</i>\n"
        f"alvo     <code>{fmt(g['alvo'])}</code>   "
        f"<b>R:R 1:{g['rr']:.2f}</b>\n"
        f"<i>o alvo é a piscina: o último {'fundo' if g['alta'] else 'topo'} "
        f"não consumido além de toda a faixa</i>\n"
        + msg_mao(g['risco_pct']) +
        f"\n\n<i>No universo rolante de 7 anos: 52% de acerto, "
        f"risco/retorno 1:2,05, 3,6 alertas por mês, +48 para cada 100 "
        f"arriscados. De 2025 para cá, +55. Sem o filtro de contexto o "
        f"mesmo padrão perde. Em teste: anota, não opera.</i>")


def msg_contexto(sim, g, quando, fmt, msg_mao):
    seta = "🟡" if g['lado'] == 'compra' else "🟠"
    lado_ida = "para cima" if g['alta'] else "para baixo"
    return (
        _cab() +
        f"{seta} <b>{sim.replace('USDT', '/USDT')}</b> — "
        f"<b>VEIO A FORÇA CONTRÁRIA</b>\n"
        f"<i>ainda não é entrada: agora começa a janela da falha</i>\n\n"
        f"a vela de força fechou às {quando(g['forca_ms'])} (Brasília), "
        f"há {g['horas']}h\n"
        f"<b>faltam {g['falta']} velas</b> para a falha confirmar, "
        f"senão o setup morre\n\n"
        f"faixa  <code>{fmt(g['base'])}</code> a "
        f"<code>{fmt(g['topo'])}</code>   "
        f"<i>60 velas, {g['cruz']} cruzamentos</i>\n"
        f"<i>em cima de {_ctx(g)} — o contexto é a favor de uma "
        f"{g['lado']}</i>\n"
        f"<i>rompeu {lado_ida} andando {g['excur']:.2f}x a altura da faixa, "
        f"com {g['vol_x']:.1f}x o volume dela</i>\n\n"
        f"<b>o gatilho</b> é uma vela de 1h fechando "
        f"{'abaixo' if g['alta'] else 'acima'} de "
        f"<code>{fmt(g['forca_lim'])}</code>   "
        f"<i>(o extremo da vela de força)</i>\n"
        f"<b>cancela</b> se passar de <code>{fmt(g['ext'])}</code>   "
        f"<i>(a máxima da ida)</i>\n\n"
        f"preço agora  <code>{fmt(g['ref'])}</code>\n"
        f"stop     <code>{fmt(g['stop'])}</code>   "
        f"risco <b>{g['risco_pct']:.2f}%</b>\n"
        f"alvo     <code>{fmt(g['alvo'])}</code>   "
        f"<b>R:R 1:{g['rr']:.2f}</b>\n"
        + msg_mao(g['risco_pct']) +
        f"\n\n<i>Números provisórios, calculados como se a entrada saísse "
        f"no extremo da vela de força. Se a falha vier, chega outro alerta "
        f"com os números finais.</i>")


# -------------------------------------------------------------- estado
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
                 excur=g['excur'], vol_x=g['vol_x'], ctx=g['ctx'],
                 status='aberto')
    return True


def registrar_contexto(d, sim, g):
    """Avisa uma vez por montagem. A chave e a vela de forca."""
    ch = f"ctx-{sim}-{g['forca_ms']}"
    if ch in d:
        return False
    d[ch] = dict(sim=sim, tipo='contexto', lado=g['lado'],
                 forca_ms=g['forca_ms'], stop=g['stop'], alvo=g['alvo'],
                 status='avisado')
    return True


def revisar(d, series, fmt, quando):
    saidas = []
    for ch, r in d.items():
        if r.get('status') != 'aberto':
            continue
        h = series.get(r['sim'])
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
                fim, preco = 'tempo', v[4]; break
            if compra:
                if v[3] <= r['stop']: fim, preco = 'stop', r['stop']; break
                if v[2] >= r['alvo']: fim, preco = 'alvo', r['alvo']; break
            else:
                if v[2] >= r['stop']: fim, preco = 'stop', r['stop']; break
                if v[3] <= r['alvo']: fim, preco = 'alvo', r['alvo']; break
        if fim is None:
            continue
        r['status'] = fim
        r['saida'] = preco
        mov = (preco - r['entrada'])/r['entrada'] * (1 if compra else -1)
        r['resultado_pct'] = mov * 100
        r['por_100_risco'] = mov / (r['risco_pct']/100) * 100
        cara = "✅" if r['por_100_risco'] > 0 else "❌"
        saidas.append(
            f"🧪 <b>EM TESTE</b> — desfecho do rompimento falso\n\n"
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
                w.writerow(['data_brasilia', 'par', 'lado', 'entrada',
                            'stop', 'alvo', 'stop_pct', 'risco_retorno',
                            'excursao', 'volume_ida', 'contexto', 'fim',
                            'saida', 'resultado_pct', 'por_100_de_risco'])
            w.writerow([
                f"{datetime.fromtimestamp(r['vela_ms']/1000, BRT):%Y-%m-%d %H:%M}",
                r['sim'], r['lado'], f"{r['entrada']:.8g}",
                f"{r['stop']:.8g}", f"{r['alvo']:.8g}",
                f"{r['risco_pct']:.2f}", f"{r['rr']:.2f}",
                f"{r.get('excur', 0):.2f}", f"{r.get('vol_x', 0):.2f}",
                r.get('ctx', ''), r['status'], f"{r.get('saida', 0):.8g}",
                f"{r.get('resultado_pct', 0):.2f}",
                f"{r.get('por_100_risco', 0):.0f}"])
    except Exception:
        pass


def placar(d):
    fech = [r for r in d.values()
            if r.get('status') in ('stop', 'alvo', 'tempo')]
    abertas = [r for r in d.values() if r.get('status') == 'aberto']
    if not fech:
        return (f"🧪 rompimento falso em teste: {len(abertas)} aberta(s), "
                f"nenhuma resolvida ainda")
    g = [r for r in fech if r['por_100_risco'] > 0]
    soma = sum(r['por_100_risco'] for r in fech)
    return (f"🧪 <b>rompimento falso (H1) — em teste</b>\n"
            f"{len(fech)} resolvidas · {len(g)} acertos "
            f"({len(g)/len(fech)*100:.0f}%) · {len(abertas)} abertas\n"
            f"soma: <b>{soma:+.0f}</b> para cada 100 arriscados por operação\n"
            f"média: <b>{soma/len(fech):+.0f}</b> por operação\n"
            f"<i>o backtest esperava 52% de acerto e ~+48 por operação. "
            f"Decisão em 20 operações.</i>")


# ------------------------------------------------------------ exemplos
def exemplos(h, cfg=None):
    """Os gatilhos que esta serie contem, para reenviar como amostra.

    Pula montagens sobrepostas do mesmo jeito que o backtest faz: depois
    de uma entrada, a varredura retoma DEPOIS dela. Sem isso a mesma
    entrada aparece por dois caminhos (404 contra 230 em 83 meses).

    Devolve pares (entrada, contexto) -- o contexto montado como ele teria
    saido na hora da vela de forca, para dar para ver os dois formatos.
    """
    cfg = cfg or CFG
    if len(h) < cfg['lat_jan'] + cfg['pre_jan'] + 60:
        return []
    a, mv = exp8.atr(h, 14), exp8.medvol(h, 20)
    out, corte = [], -1
    for m in _montagens(h, cfg, a, mv, 0)[::-1]:
        if m['i'] <= corte:
            continue
        alta = m['alta']
        for k in range(m['k_forca']+1,
                       min(m['k_forca']+1+cfg['falha_max'], len(h))):
            hk, lk, ck = h[k][2], h[k][3], h[k][4]
            if (hk > m['ext']) if alta else (lk < m['ext']):
                break
            if not ((ck < m['forca_lim']) if alta else (ck > m['forca_lim'])):
                continue
            n = _numeros(h, m, k, a, cfg, ck)
            if not n:
                break
            g = dict(m, **n)
            g.update(idx=k, vela_ms=h[k][0], atraso=0,
                     velas_forca=k - m['k_forca'])
            # e o aviso de radar como ele teria saido na vela de forca
            kf = m['k_forca']
            nc = _numeros(h, m, kf, a, cfg, m['forca_lim'])
            c = None
            if nc:
                c = dict(m, **nc)
                c.update(idx=kf, ref=h[kf][4], horas=0,
                         falta=cfg['falha_max'], vela_ms=h[kf][0])
            out.append((g, c))
            corte = k
            break
    return out
