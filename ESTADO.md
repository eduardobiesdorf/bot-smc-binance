# Onde o projeto está — 13/11/2026

Resumo para recomeçar a conversa do zero sem perder contexto.

## O que é

Bot de Telegram que manda alerta de oportunidade em futuros USDⓈ-M da
Binance. É **radar para decisão discricionária, não robô que opera
sozinho**. Banca de teste: $60.

Alvo do Eduardo: ~50% de acerto, risco-retorno 1:3 a 1:4, e muitas
entradas. Ele rejeita explicitamente "1:1,20 com 60% de acerto, isso
parece mediano e morno".

## O que roda hoje

| | setup 1 — varredura H1 | setup 3 — reversão H8 |
|---|---|---|
| estado | **com dinheiro** | 🧪 em teste, sem dinheiro |
| pares | 50 (`UNIVERSO[:50]`) | 150 maiores |
| arquivo | `bot_varredura.py` | `reversao8.py` |
| auditoria | **REPROVOU** | **APROVOU** |

O setup 2 (explosão de 8h, `explosao8.py`) foi **desligado em
12/11/2026** a pedido do Eduardo. O arquivo fica no repo com a medição.

## A auditoria de 12-13/11 — o que mudou tudo

Todos os backtests anteriores usavam `UNIVERSO[:50]`, que são as 50
maiores por volume de futuros **de novembro de 2026**. HYPE, ENA,
TRUMP, PUMP, ASTER, PENGU, XPL, VIRTUAL, WLFI e RE estão nessa lista
**porque cresceram**. Medir 2023-2026 nela é escolher o time depois de
ver o campeonato.

**Setup 1, mesmas regras, só mudando como o universo é escolhido:**

| universo | n | acerto | líq/op | z | anos+ |
|---|---|---|---|---|---|
| lista de hoje | 399 | 34,3% | +$9,40 | +1,08 | 2/4 |
| 50 maiores do período | 435 | 31,3% | −$0,40 | −0,06 | 2/4 |
| escolhido em jan/2023 | 472 | 28,0% | −$15,90 | −2,12 | 1/4 |
| **rolante trimestral** | 459 | 31,4% | **−$1,00** | −0,11 | 2/4 |

34,3% de acerto na lista de hoje contra 28,0% na de 2023, mesmas
regras. Seis pontos vindos de receber as moedas que subiram. **O setup
1 não tem vantagem medível.** O filtro de stop mínimo, que parecia
salvá-lo (+$31,60/op, 50% de acerto), também era a lista: no rolante
dá −$5,40.

## Setup 3 — os números que valem

Universo rolante (a cada trimestre, as 150 maiores pelo volume do
trimestre anterior), **só compra**, nenhuma informação do futuro,
risco fixo de $100:

- **65 operações · 1,4 por mês · 40,0% de acerto · 1:4,17**
- **+$69,40 por operação** · total +$4.508
- rebaixamento $1.521 = **15× o risco de uma entrada**
- pior sequência: **10 stops seguidos** (esperado com 40% de acerto)
- z = +2,24 · 2023 −6(5) · 2024 +159(11) · 2025 +13(19) · 2026 +84(30)

Passa em três testes independentes:

1. **sobrevive à troca de universo**, com gradiente suave: +$183,40
   (150 do período) → +$98,10 (rolante 50) → +$69,40 (rolante 150) →
   +$55,20 (rolante 300) → +$39,60 (todas as 461). Cai a intensidade,
   nunca o sinal.
2. **positivo em todos os anos** em praticamente todos os universos
   (2023 fica −$6 sobre 5 operações no rolante — cara ou coroa).
3. **bate entrada aleatória por +4,89 desvios**: 914 compras nas mesmas
   moedas, mesmo stop%, mesmo R:R, momento sorteado → −$17,60/op com
   19,5% de acerto (precisa 21% para empatar). Comprar essas moedas a
   esmo **não paga**, nem com a maré a favor.

Com $60 arriscando $1 por entrada, o pior momento do histórico custa
$15 (25% da conta).

### Só compra desde 13/11

| | n | acerto | R:R | líq/op | z | anos+ |
|---|---|---|---|---|---|---|
| compras | 119 | 31,9% | 1:4,94 | +$39,60 | +1,95 | 4/4 |
| vendas | 50 | 26,0% | 1:2,96 | −$16,90 | −0,85 | 1/4 |

Não é azar, é aritmética do alvo: 90% do tamanho da vela projetado além
do extremo. Uma queda não passa de 100%, uma alta não tem teto. Na
venda o alvo é caro demais. `CFG['so_compra'] = False` volta a ponta.
**O problema da venda é o ALVO, não a leitura** — vale remedir com
outro alvo.

## O parentesco dos setups

O **setup 3 é o setup 2 consertado**, não uma ideia nova. Mesmo
esqueleto: vela única de 8h, order block, volta, encosto, gatilho,
stop abaixo do bloco, alvo em 90% da projeção. Três mudanças:

1. rompe o **último pivô**, não o extremo de 20 velas (o de 20 velas
   obriga continuação; o pivô permite reversão)
2. **exige queda antes**: 2 volatilidades em 7 dias + explosão saindo
   do terço de baixo da faixa
3. **encosto raso**: não pode afundar além do meio do order block

Isso levou 32,3% → 40% de acerto e ~1:3 → 1:4,17.

O **setup 1 não tem parentesco** com os outros dois. Cinco tentativas
de levar peças do 3 para o 1 falharam todas (contexto de queda, volume
no gatilho, alvo projetado, e as combinações). **O que faz o setup 3
funcionar não é transferível.**

## Regra de método — a lição que custou caro

**Nenhum resultado conta antes de passar pelo universo rolante E de
bater a entrada aleatória.** Dezenas de variações testadas em semanas
anteriores passaram pela lista viciada e ganharam o mesmo bônus
invisível. Scripts: `analise/setup3_honesto.py` e
`analise/setup3_controle.py`.

## Descartado — não retestar sem dado novo

IFVG · ações tokenizadas · explosão de vela única em H1/H4/H12/diário ·
moedas pequenas e médias (gradiente monótono contra) · furar o order
block na explosão · a "falha" (vender o rompimento do OB) · VWAP
ancorada (16 variantes, bruto −$0,20 em 77.803 operações) · "recusa do
topinho" (27 variantes) · alvo de movimento medido a partir do fundo ·
alvos além de +100% · a reversão em H4/H2/H1 · **a reversão em 5
minutos** · a estrutura como gatilho de entrada (R:R desaba 1:3,93 →
1:1,01) · o trailing por estrutura na reversão · emprestar o contexto
de queda para o setup 1.

**O fechamento do tempo gráfico** — bruto do mesmo padrão, mesmas 150
moedas, mesmos 4 anos: **H8 +$82** · H4 −$9 · H2 +$10 · H1 −$7 · 5 min
+$3. O desenho é fractal, o comportamento não: uma queda de uma semana
seguida de uma vela de força é um evento de 8 horas.

## Pendências

- **Decidir o que fazer com o setup 1.** Continua mandando alerta com
  dinheiro atrás, sem backtest que o sustente. Opções: desligar, ou
  tentar consertar (pista: ele precisa de um filtro de contexto que a
  lista de moedas fazia por ele de graça).
- Remedir a ponta de venda do setup 3 com um alvo próprio.
- Oracle Cloud (removeria a fila do GitHub Actions, ~6 min por rodada).
- Bug conhecido: `analise/trailing_tf.py` calcula rebaixamento por par,
  não em ordem cronológica.

## Placar ao vivo (setup 1)

8 fechados · 3 gain / 5 loss (38%) · +4,98R · 0 abertos
