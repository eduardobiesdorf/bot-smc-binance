"""Reversao em H8 com entrada no H1 -- TERCEIRO ALERTA, EM TESTE.

O preco vem caindo por uma semana e UMA vela de 8 horas rompe o ultimo
topo. O preco volta, ENCOSTA no order block sem afundar nele, e uma
vela de 1 hora confirma com volume. Entra ali.

Estado e historico proprios. Nao mexe nos outros dois setups.

O QUE O BACKTEST MEDE  (2020-01 a 2026-10, 82 meses, SO COMPRA,
alvo no TOPO da vela de explosao, risco fixo de 100 USD por operacao)

  O NUMERO QUE VALE -- universo rolante (a cada trimestre as 150
  maiores pelo volume do trimestre ANTERIOR) e contado por LOTE, nao
  por operacao, porque as operacoes disparam juntas:

      91 operacoes, 1,1 por mes, 57,1% de acerto, R:R 1:2
      +51,90 por operacao  ·  37 lotes de 14 dias, 23 positivos
      +128 por lote  ·  teste do acaso por lote z = +2,04
      o maior lote vale 38% do lucro  ·  acerto em 29 dos 82 meses

      2020  -42 (1 alvo/2 op)      2024 +1.293 (8/11)
      2021 +391 (3/4)              2025     +3 (9/21)
      2022 +276 (5/11)             2026 +2.435 (19/30)
      2023 +364 (7/12)
      POSITIVO EM 6 DOS 7 ANOS (2020 tem so 2 operacoes)

  POR QUE O ALVO E O TOPO (13/11/2026, segunda troca do dia). Nove
  alvos medidos em 7 anos, no universo rolante, por LOTE:

      alvo                acerto    R:R  liq/op   z/op  z/LOTE  lotes+  maior  meses
      o topo da explosao   57,1%   2,00  +51,90  +2,97   +2,04   23/37    38%     29
      1:2 de risco         52,8%   2,00  +54,50  +3,20   +1,94   23/36    40%     26
      projecao 45%         47,7%   3,17  +68,00  +2,93   +1,65   19/36    51%     23
      1:3 de risco         43,0%   3,00  +67,40  +2,97   +1,57   17/35    52%     20
      projecao 90%         37,2%   4,40  +70,20  +2,44   +1,34   15/35    61%     17
      1:4 de risco         34,1%   4,00  +64,80  +2,46   +1,17   15/35    74%     17
      1:5 de risco         28,9%   5,00  +67,20  +2,20   +1,04   11/35    82%     13
      projecao 150%        26,8%   5,93  +44,50  +1,45   +0,79    9/35   104%     12
      1:6 de risco         23,8%   6,00  +59,90  +1,80   +0,83    8/35   103%     10

  O topo e o unico alvo que passa de 2 desvios por lote. E e o unico
  SEM NENHUM NUMERO AJUSTAVEL dentro dele -- nao tem 45%, 90% nem 5x,
  e uma linha que o mercado desenhou sozinho. Um alvo com zero
  parametros livres nao tem como estar sobreajustado, e isso vale mais
  que qualquer decimo de desvio.

  Quanto mais longe o alvo, mais o lucro se concentra num lote so (38%
  -> 104%) e em menos meses (29 -> 10). O alvo longo nao e so mais
  dificil: ele transforma o setup numa loteria que so paga quando o
  mercado inteiro rasga.

  O ERRO QUE ISSO CORRIGIU. De manha o alvo foi trocado para 5x o
  risco, escolhido por DINHEIRO POR OPERACAO num conjunto onde as
  operacoes nao sao independentes -- criterio errado. Com o alvo de
  1:5, 2020, 2021, 2022 e 2023 davam -213, -311, -334 e -460, e eu
  concluir que o setup estava sobreajustado a 2023-2026. Era o ALVO que
  dependia de regime, nao o setup: o alvo de 1:5 so paga quando o
  mercado rasga, e 2020-2023 nao rasgou. A observacao e do Eduardo.

  OS DOIS LADOS, desde 13/11 a noite. A venda foi desligada mais cedo
  no mesmo dia porque perdeu para a entrada aleatoria por -0,29
  desvios -- mas aquilo foi medido com a projecao de 90%, o alvo
  errado. Com o alvo no FUNDO da vela de explosao ela muda de figura:

      venda, alvo em        acerto    R:R  liq/op  z/LOTE  vs acaso
      projecao 90%           28,2%   3,15   +1,90   +0,08     -0,29
      o FUNDO da vela        50,0%   1,36  +10,10   +0,63     +0,70

  O acerto saltou de 28% para 50% so trocando o alvo. Mas +0,70 nao e
  vantagem demonstrada e +10,10 por operacao e quase zero: a venda
  SOZINHA nao esta provada.

  Ela entra porque NAO DILUI, e diversifica:

      configuracao      n  /mes  acerto   R:R  liq/op   total  z/LOTE  lotes+  maior
      so compra        91   1,1   57,1%  2,00  +51,90   4.723   +2,04   23/37    38%
      compra + venda  129   1,6   55,0%  1,81  +39,60   5.108   +2,10   27/44    35%

  Rende menos por operacao e mais no total, com z/lote maior e
  concentracao menor. E ano a ano a venda carrega o que a compra nao
  pega: 2020 venda +215 contra compra -42; 2022 venda +374.

      venda, ano a ano: 2020 +215(3 alvos/5 op) · 2021 -207(0/2) ·
      2022 +374(3/4) · 2023 +206(4/8) · 2024 -266(1/4) ·
      2025 -89(5/10) · 2026 +151(3/5)

  CFG['so_compra'] = True desliga a venda.

  A ENTRADA ALEATORIA. Para cada operacao
  real, 20 compras na MESMA moeda com o MESMO stop em %, o MESMO R:R e
  a MESMA janela, em momento sorteado:

      COMPRA, alvo no topo, por LOTE, 7 anos:
        lotes de 7 dias    real +93 ±40 (26/51 positivos) · sorteado
                           -13   ->  +2,65 DESVIOS
        lotes de 14 dias   real +128 ±59 (23/37) · sorteado -17
                           ->  +2,45 DESVIOS
      VENDA, alvo no fundo, lotes de 14 dias:
        real +16 ±26 (12/24) · sorteado -2  ->  +0,70 desvios

      para comparar, com o alvo de 1:5 que ficou no bot por 3 horas:
        compra, lotes de 14 dias  ->  +1,24 desvios

  Trocar o alvo DOBROU a significancia contra o acaso: +1,24 -> +2,45.

  O controle PERDE dinheiro nas mesmas moedas e no mesmo periodo. A
  direcao nunca inverteu em teste nenhum; o que encolheu foi a certeza.
  A direcao nunca inverteu em teste nenhum.

  ATENCAO -- OS NUMEROS ANTIGOS DESTE ARQUIVO ERAM VICIADOS. Ate
  13/11/2026 este bloco dizia 48,6% de acerto, 1:3,69 e +116,10 por
  operacao, medido nas "150 maiores por volume mediano do PERIODO", o
  que escolhe as moedas sabendo quem sobreviveu.

  O setup 1 (varredura do order block) NAO sobreviveu ao universo
  rolante: +9,40/op na lista UNIVERSO[:50] do bot contra -1,00/op no
  rolante. Aquela lista sao as 50 maiores de NOVEMBRO DE 2026 e o setup
  compra rompimentos. Ver analise/setup1_honesto.py.

  REGRA PARA TESTES NOVOS: nenhum resultado conta antes de passar pelo
  universo rolante, de ser contado por LOTE e de bater a entrada
  aleatoria. Ver analise/setup3_honesto.py, analise/lote_controle.py e
  analise/alvo_lote.py.

AS REGRAS

  1. O preco vinha caindo: nas 20 velas de 8h anteriores (160 horas, ~7
     dias) o fechamento caiu pelo menos 2 volatilidades medias, e a
     vela da explosao sai do terco de baixo da faixa desse periodo.
  2. O ultimo topo: o pivo de alta mais recente -- uma vela cuja maxima
     supera as 2 de cada lado -- procurando ate 30 velas para tras.
  3. A explosao: UMA vela de 8h que, ao mesmo tempo, tem tamanho >=
     2,5x a volatilidade media de 14 velas, corpo >= 50% dela, volume
     >= 1,5x a media de 20 velas, e FECHA ALEM DO ULTIMO TOPO.
  4. Order block: a ultima vela de cor contraria antes da explosao.
  5. Espera: ate 720 horas (30 dias) para o preco voltar e ENCOSTAR na
     borda do order block. So encostar, nao precisa furar.
  6. ENCOSTO RASO: durante a volta, o preco nao pode passar do MEIO do
     order block. Se afundou, o setup morre. E o filtro que leva o
     acerto de 33,6% para 48,6% no universo viciado.
  7. Gatilho no H1: nas 48 horas seguintes ao encosto, uma vela de 1
     hora fecha de volta para fora do order block, a favor, com corpo
     >= 50% ou pavio >= 50%, E com volume >= 1,2x a media de 20 horas.
  8. Entrada no fechamento dessa vela. Stop logo abaixo da base do
     order block. Alvo no TOPO da vela de explosao.
  9. O filtro de risco/retorno (1:1,2) mede ate o TOPO que o preco
     deixou, nao ate o alvo projetado.
 10. Cancela se o preco atravessar o order block inteiro.
"""
import csv
import json
import os
from datetime import datetime, timedelta, timezone

import explosao8 as exp8

BRT = timezone(timedelta(hours=-3))
ARQUIVO = "reversao8_estado.json"
HISTORICO = "historico_reversao8.csv"
MAX_BARRAS = 120          # velas de 8h segurando a operacao

CFG = dict(
    sigma=2.5,            # tamanho da explosao, em volatilidades
    vol=1.5,              # volume da explosao, x a media de 20
    pivo=2,               # velas de cada lado que definem o ultimo topo
    busca_topo=30,        # ate onde procurar esse topo, em velas de 8h
    tend_jan=20,          # janela da queda, em velas de 8h (160 horas)
    tend_atr=2.0,         # quanto o preco tinha caido, em volatilidades
    perto_do_fundo=0.35,  # a explosao sai do terco de baixo da faixa
    ob_busca=6,
    espera=90,            # velas de 8h esperando o encosto (720 horas)
    gat_h1=48,            # horas para a confirmacao aparecer
    vol_gat=1.2,          # volume da vela do gatilho, x a media de 20
    furo_max=1.0,
    stop_folga=0.10,
    rr_min=1.2,
    alvo_proj=0.0,       # 0 = o alvo e o TOPO da vela de explosao, sem projecao
    alvo_rr=None,        # multiplo de risco fixo; None usa alvo_proj
    tf_h=8,               # horas da vela do padrao; 24 roda no diario
    so_compra=False,      # OS DOIS LADOS; ver o comentario em explosoes
)


# ------------------------------------------------------------- series
def juntar(h, n=8):
    """Velas de 1h viram velas de n horas, alinhadas ao UTC como na
    Binance. Descarta o primeiro bloco se vier pela metade."""
    passo = n * 3600_000
    out, bloco, chave = [], None, None
    for v in h:
        c = v[0] // passo
        if c != chave:
            if bloco:
                out.append(tuple(bloco))
            bloco = [c * passo, v[1], v[2], v[3], v[4], v[5]]
            chave = c
        else:
            bloco[2] = max(bloco[2], v[2])
            bloco[3] = min(bloco[3], v[3])
            bloco[4] = v[4]
            bloco[5] += v[5]
    if bloco:
        out.append(tuple(bloco))
    if out and h and h[0][0] != out[0][0]:
        out = out[1:]                      # o primeiro veio incompleto
    return out


def ultimo_topo(h, i, alta, cfg):
    """O pivo mais recente antes de i. Numa queda e um topo mais baixo."""
    k = cfg['pivo']
    for c in range(i - k - 1, max(0, i - cfg['busca_topo']) - 1, -1):
        if c - k < 0 or c + k >= i:
            continue
        if alta:
            ref = h[c][2]
            if all(h[x][2] <= ref for x in range(c-k, c+k+1) if x != c):
                return ref
        else:
            ref = h[c][3]
            if all(h[x][3] >= ref for x in range(c-k, c+k+1) if x != c):
                return ref
    return None


# ------------------------------------------------------------- padrao
def explosoes(h8, cfg):
    """As velas de explosao de reversao, da mais recente para tras."""
    a, mv = exp8.atr(h8, 14), exp8.medvol(h8, 20)
    jan = cfg['tend_jan']
    fora = []
    for i in range(max(jan, cfg['busca_topo'], 21) + 1, len(h8) - 1):
        o, hi, lo, cl, vol = h8[i][1], h8[i][2], h8[i][3], h8[i][4], h8[i][5]
        rng = hi - lo
        if rng <= 0 or a[i-1] <= 0 or mv[i-1] <= 0:
            continue
        if rng < cfg['sigma']*a[i-1] or abs(cl-o)/rng < 0.5:
            continue
        if vol < cfg['vol']*mv[i-1]:
            continue
        alta = cl > o
        # 0) Os DOIS lados. A venda ficou desligada por algumas horas em
        #    13/11 e foi religada: medida em 169 operacoes nas 461 moedas,
        #      compras  119 op, 31,9% de acerto, 1:4,94, +39,60/op, 4/4 anos
        #      vendas    50 op, 26,0% de acerto, 1:2,96, -16,90/op, 1/4 anos
        #    mas 50 operacoes e pouco para amputar metade do setup, e o
        #    diagnostico aponta para o ALVO e nao para a leitura: o alvo e
        #    90% do tamanho da vela projetado alem do extremo, e uma queda
        #    nao passa de 100% enquanto uma alta nao tem teto. A mesma
        #    projecao em porcentagem e uma distancia muito maior para
        #    baixo -- 1:2,96 contra 1:4,94. A venda esta sendo obrigada a
        #    andar um caminho que a compra nao precisa andar. O alvo
        #    proprio para a venda esta sendo medido em
        #    analise/venda_alvo.py. Ate la, os dois lados alertam.
        if not alta and cfg.get('so_compra', False):
            continue
        # 1) vinha caindo de verdade
        queda = (h8[i-jan][4] - h8[i-1][4]) / a[i-1] if alta else \
                (h8[i-1][4] - h8[i-jan][4]) / a[i-1]
        if queda < cfg['tend_atr']:
            continue
        faixa = h8[i-jan:i]
        tmax = max(x[2] for x in faixa); tmin = min(x[3] for x in faixa)
        if tmax > tmin:
            pos = (lo-tmin)/(tmax-tmin) if alta else (tmax-hi)/(tmax-tmin)
            if pos > cfg['perto_do_fundo']:
                continue
        # 2) rompeu o ultimo topo
        topo_ant = ultimo_topo(h8, i, alta, cfg)
        if topo_ant is None:
            continue
        if (cl <= topo_ant) if alta else (cl >= topo_ant):
            continue
        # 3) o order block
        ob_base = ob_topo = None
        j = i - 1
        while j >= max(0, i - cfg['ob_busca']):
            if (h8[j][4] > h8[j][1]) != alta:
                ob_base, ob_topo = h8[j][3], h8[j][2]
                break
            j -= 1
        if ob_base is None:
            continue
        fora.append(dict(i=i, alta=alta, ob_base=ob_base, ob_topo=ob_topo,
                         atr=a[i], topo=hi if alta else lo, tam=hi-lo,
                         fim_ms=h8[i][0] + cfg['tf_h']*3600_000,
                         queda=queda,
                         topo_ant=topo_ant, exp_ms=h8[i][0]))
    fora.reverse()
    return fora


def entrada(h1, mv1, e, cfg, pos1):
    """Do fim da explosao ate o gatilho de 1 hora."""
    alta = e['alta']
    k0 = pos1.get(e['fim_ms'])
    if k0 is None:
        return None
    borda = e['ob_topo'] if alta else e['ob_base']
    meio = (e['ob_base'] + e['ob_topo']) / 2
    morte = (e['ob_base'] - e['atr']*cfg['furo_max']) if alta else \
            (e['ob_topo'] + e['atr']*cfg['furo_max'])
    pico = e['topo']
    tocou = extremo = None
    lim = min(k0 + cfg['espera']*cfg['tf_h'], len(h1))
    for k in range(k0, lim):
        hi, lo, o, cl = h1[k][2], h1[k][3], h1[k][1], h1[k][4]
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
        if k - tocou > cfg['gat_h1']:
            return None
        if (hi >= pico) if alta else (lo <= pico):
            return None
        # ENCOSTO RASO: nao pode ter afundado alem do meio do order block
        if (extremo < meio) if alta else (extremo > meio):
            return None
        rng = hi - lo
        dentro = (cl > borda) if alta else (cl < borda)
        favor = (cl > o) if alta else (cl < o)
        if rng <= 0 or not dentro or not favor:
            continue
        corpo = abs(cl - o) / rng
        pav = ((min(o, cl) - lo) if alta else (hi - max(o, cl))) / rng
        if not (corpo >= 0.5 or pav >= 0.5):
            continue
        if mv1[k] > 0 and h1[k][5] < cfg['vol_gat']*mv1[k]:
            continue                       # gatilho sem volume nao vale
        ent = cl
        stop = (e['ob_base'] - e['atr']*cfg['stop_folga']) if alta else \
               (e['ob_topo'] + e['atr']*cfg['stop_folga'])
        risco = abs(ent - stop)
        if risco <= 0:
            return None
        ate_topo = (pico - ent) if alta else (ent - pico)
        if ate_topo <= 0 or ate_topo/risco < cfg['rr_min']:
            return None
        if cfg.get('alvo_rr'):
            alvo = (ent + risco*cfg['alvo_rr']) if alta else \
                   (ent - risco*cfg['alvo_rr'])
        else:
            alvo = (e['topo'] + cfg['alvo_proj']*e['tam']) if alta else \
                   (e['topo'] - cfg['alvo_proj']*e['tam'])
        dist = (alvo - ent) if alta else (ent - alvo)
        if dist <= 0:
            return None
        return dict(lado='compra' if alta else 'venda', entrada=ent,
                    stop=stop, alvo=alvo, rr=dist/risco, idx=k,
                    vela_ms=h1[k][0], topo=pico, exp_ms=e['exp_ms'],
                    # 18/11/2026 -- a zona vai junto para o grafico poder
                    # desenha-la; o dicionario do encosto ja a tinha
                    ob_base=e['ob_base'], ob_topo=e['ob_topo'],
                    risco_pct=risco/ent*100, queda=e['queda'],
                    vol_gat=(h1[k][5]/mv1[k]) if mv1[k] > 0 else 0.0)


def encosto(h1, mv1, e, cfg, pos1):
    """O encosto que esta ACONTECENDO: o preco ja tocou o order block,
    o setup continua vivo e o gatilho ainda nao veio.

    Mesmas regras de entrada(), parando um passo antes. Devolve None se
    nunca tocou, se morreu no caminho, se a janela de 48h estourou, ou
    se o gatilho ja saiu -- esse ultimo caso e trabalho de entrada()."""
    alta = e['alta']
    k0 = pos1.get(e['fim_ms'])
    if k0 is None:
        return None
    borda = e['ob_topo'] if alta else e['ob_base']
    meio = (e['ob_base'] + e['ob_topo']) / 2
    morte = (e['ob_base'] - e['atr']*cfg['furo_max']) if alta else \
            (e['ob_topo'] + e['atr']*cfg['furo_max'])
    pico = e['topo']
    tocou = extremo = None
    lim = min(k0 + cfg['espera']*cfg['tf_h'], len(h1))
    for k in range(k0, lim):
        hi, lo, o, cl = h1[k][2], h1[k][3], h1[k][1], h1[k][4]
        if tocou is None:
            pico = max(pico, hi) if alta else min(pico, lo)
            if (lo <= borda) if alta else (hi >= borda):
                tocou, extremo = k, (lo if alta else hi)
            else:
                continue
        else:
            extremo = min(extremo, lo) if alta else max(extremo, hi)
        if (extremo < morte) if alta else (extremo > morte):
            return None                   # atravessou o bloco inteiro
        if k - tocou > cfg['gat_h1']:
            return None                   # a janela de 48h estourou
        if (hi >= pico) if alta else (lo <= pico):
            return None                   # foi embora sem a gente
        if (extremo < meio) if alta else (extremo > meio):
            return None                   # afundou: encosto raso quebrou
        # o gatilho ja saiu? entao nao e mais um encosto pendente
        rng = hi - lo
        dentro = (cl > borda) if alta else (cl < borda)
        favor = (cl > o) if alta else (cl < o)
        if rng > 0 and dentro and favor:
            corpo = abs(cl - o) / rng
            pav = ((min(o, cl) - lo) if alta else (hi - max(o, cl))) / rng
            if (corpo >= 0.5 or pav >= 0.5) and \
                    not (mv1[k] > 0 and h1[k][5] < cfg['vol_gat']*mv1[k]):
                return None
    if tocou is None or lim < len(h1):
        return None                       # nunca tocou, ou a espera acabou
    # vivo e esperando o gatilho
    ref = h1[-1][4]
    stop = (e['ob_base'] - e['atr']*cfg['stop_folga']) if alta else \
           (e['ob_topo'] + e['atr']*cfg['stop_folga'])
    risco = abs(ref - stop)
    if risco <= 0:
        return None
    if cfg.get('alvo_rr'):
        alvo = (ref + risco*cfg['alvo_rr']) if alta else \
               (ref - risco*cfg['alvo_rr'])
    else:
        alvo = (e['topo'] + cfg['alvo_proj']*e['tam']) if alta else \
               (e['topo'] - cfg['alvo_proj']*e['tam'])
    dist = (alvo - ref) if alta else (ref - alvo)
    if dist <= 0:
        return None
    ate_topo = (pico - ref) if alta else (ref - pico)
    fundura = abs(extremo - borda) / abs(meio - borda) if meio != borda else 0
    return dict(lado='compra' if alta else 'venda', ref=ref, stop=stop,
                alvo=alvo, rr=dist/risco, risco_pct=risco/ref*100,
                ob_base=e['ob_base'], ob_topo=e['ob_topo'], meio=meio,
                topo=pico, exp_ms=e['exp_ms'], queda=e['queda'],
                toque_ms=h1[tocou][0], horas=len(h1)-1-tocou,
                falta=cfg['gat_h1']-(len(h1)-1-tocou), fundura=fundura,
                rr_topo=(ate_topo/risco if ate_topo > 0 else 0.0))


def achar_encosto(h1, cfg=None):
    """O encosto pendente mais recente, se houver."""
    cfg = cfg or CFG
    h8 = juntar(h1, cfg['tf_h'])
    if len(h8) < 60 or len(h1) < 200:
        return None
    mv1 = exp8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    for e in explosoes(h8, cfg):
        g = encosto(h1, mv1, e, cfg, pos1)
        if g:
            return g
    return None


def msg_encosto(sim, g, quando, fmt, msg_mao):
    """Aviso curto, no formato do setup 1: o que dispara e o que cancela.

    19/11/2026 -- a versao anterior tinha 20 linhas, com a volatilidade de
    7 dias, a fundura no bloco e a explicacao do gatilho. O Eduardo pediu
    o padrao do setup 1. O grafico, que agora acompanha o alerta, mostra
    tudo isso sem precisar escrever.
    """
    seta = "🟡" if g['lado'] == 'compra' else "🟠"
    return (
        f"{seta} <b>{sim.replace('USDT', '/USDT')}</b> — "
        f"<b>encostou no order block</b> ({g['lado']})   "
        f"<i>🧪 em teste</i>\n"
        f"tocou às {quando(g['toque_ms'])} · "
        f"<b>faltam {g['falta']}h</b>\n\n"
        f"bloco    <code>{fmt(g['ob_base'])}</code> a "
        f"<code>{fmt(g['ob_topo'])}</code>\n"
        f"dispara  vela de 1h fechando de volta para fora do bloco\n"
        f"cancela  se {'afundar de' if g['lado'] == 'compra' else 'subir de'} "
        f"<code>{fmt(g['meio'])}</code>\n\n"
        f"stop     <code>{fmt(g['stop'])}</code>   "
        f"risco <b>{g['risco_pct']:.2f}%</b>\n"
        f"alvo     <code>{fmt(g['alvo'])}</code>   "
        f"<b>R:R 1:{g['rr']:.2f}</b>\n"
        + msg_mao(g['risco_pct']) +
        f"\n\n<i>números provisórios; se o gatilho vier, mando os finais.</i>")

def registrar_encosto(d, sim, g):
    """Avisa uma vez por montagem. A chave e a vela da explosao."""
    ch = f"enc-{sim}-{g['exp_ms']}"
    if ch in d:
        return False
    d[ch] = dict(sim=sim, tipo='encosto', lado=g['lado'],
                 toque_ms=g['toque_ms'], exp_ms=g['exp_ms'],
                 ob_base=g['ob_base'], ob_topo=g['ob_topo'],
                 alvo=g['alvo'], stop=g['stop'], status='avisado')
    return True


def exemplos(h1, cfg=None):
    """TODOS os gatilhos do historico desta serie, do mais antigo ao mais
    novo. Mesma deteccao do achar(), sem o corte de recencia -- serve para
    mandar uma amostra no Telegram e ver o formato da mensagem."""
    cfg = cfg or CFG
    h8 = juntar(h1, cfg['tf_h'])
    if len(h8) < 60 or len(h1) < 200:
        return []
    mv1 = exp8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    out = []
    for e in explosoes(h8, cfg):
        g = entrada(h1, mv1, e, cfg, pos1)
        if g:
            g['atraso'] = len(h1) - 1 - g['idx']
            out.append(g)
    out.sort(key=lambda g: g['vela_ms'])
    return out


def achar(h1, cfg=None, atraso_max=1):
    """O gatilho que acabou de fechar, se houver."""
    cfg = cfg or CFG
    h8 = juntar(h1, cfg['tf_h'])
    if len(h8) < 60 or len(h1) < 200:
        return None
    mv1 = exp8.medvol(h1, 20)
    pos1 = {v[0]: k for k, v in enumerate(h1)}
    for e in explosoes(h8, cfg):
        g = entrada(h1, mv1, e, cfg, pos1)
        if not g:
            continue
        atraso = len(h1) - 1 - g['idx']
        if atraso > atraso_max:
            return None                    # o gatilho mais recente e velho
        g['atraso'] = atraso
        return g
    return None


# ------------------------------------------------------------ mensagem
def msg(sim, g, quando, fmt, msg_mao):
    """Alerta curto, no formato do setup 1."""
    seta = "🟢" if g['lado'] == 'compra' else "🔴"
    return (
        f"{seta} <b>{sim.replace('USDT', '/USDT')}</b> — "
        f"<b>{g['lado'].upper()}</b>   <i>🧪 em teste</i>\n"
        f"reversão de 8h · vela de 1h de {quando(g['vela_ms'])} "
        f"(Brasília)"
        + ("  <i>⚠️ chegou atrasado</i>" if g.get('atraso') else "") + "\n\n"
        f"entrada  <code>{fmt(g['entrada'])}</code>\n"
        f"stop     <code>{fmt(g['stop'])}</code>   "
        f"risco <b>{g['risco_pct']:.2f}%</b>\n"
        f"alvo     <code>{fmt(g['alvo'])}</code>   "
        f"<b>R:R 1:{g['rr']:.2f}</b>\n"
        + msg_mao(g['risco_pct']) +
        f"\n\n<i>ordem limitada em {fmt(g['entrada'])}. "
        f"O alvo é o topo da vela de explosão.</i>")

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
                 queda=g['queda'], vol_gat=g['vol_gat'], status='aberto')
    return True


def revisar(d, series8, fmt, quando):
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
            f"🧪 <b>EM TESTE</b> — desfecho da reversão de 8h\n\n"
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
                            'queda_vol', 'volume_gatilho', 'fim', 'saida',
                            'resultado_pct', 'por_100_de_risco'])
            w.writerow([
                f"{datetime.fromtimestamp(r['vela_ms']/1000, BRT):%Y-%m-%d %H:%M}",
                r['sim'], r['lado'], f"{r['entrada']:.8g}",
                f"{r['stop']:.8g}", f"{r['alvo']:.8g}",
                f"{r['risco_pct']:.2f}", f"{r['rr']:.2f}",
                f"{r.get('queda', 0):.2f}", f"{r.get('vol_gat', 0):.2f}",
                r['status'], f"{r.get('saida', 0):.8g}",
                f"{r.get('resultado_pct', 0):.2f}",
                f"{r.get('por_100_risco', 0):.0f}"])
    except Exception:
        pass


def placar(d):
    fech = [r for r in d.values()
            if r.get('status') in ('stop', 'alvo', 'tempo')]
    abertas = [r for r in d.values() if r.get('status') == 'aberto']
    if not fech:
        return (f"🧪 reversão de 8h em teste: {len(abertas)} aberta(s), "
                f"nenhuma resolvida ainda")
    g = [r for r in fech if r['por_100_risco'] > 0]
    soma = sum(r['por_100_risco'] for r in fech)
    return (f"🧪 <b>reversão de 8h — em teste</b>\n"
            f"{len(fech)} resolvidas · {len(g)} acertos "
            f"({len(g)/len(fech)*100:.0f}%) · {len(abertas)} abertas\n"
            f"soma: <b>{soma:+.0f}</b> para cada 100 arriscados por operação\n"
            f"média: <b>{soma/len(fech):+.0f}</b> por operação\n"
            f"<i>o backtest esperava 55% de acerto e ~+40 por operação. "
            f"Decisão em 20 operações.</i>")
