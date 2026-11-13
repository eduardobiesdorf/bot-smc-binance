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
trimestre anterior), **só compra**, **alvo a 5× o risco**, nenhuma
informação do futuro, risco fixo de $100:

- **63 operações · 1,4 por mês · 33,3% de acerto · 1:5**
- **+$93,50 por operação** · total +$5.888
- rebaixamento $1.143 = **11× o risco de uma entrada**
- pior sequência: **11 stops seguidos** (esperado com 33% de acerto)
- z = +2,39 · 2023 +15(5) · 2024 +74(10) · 2025 +28(18) · 2026 +152(30)
- **positivo nos quatro anos**

Passa em três testes independentes:

1. **sobrevive à troca de universo**, com gradiente suave: +$113,20
   (150 do período) → +$91,90 (rolante 50) → +$45,90 (rolante 150) →
   +$33,40 (rolante 300) → +$22,90 (todas as 461). Medido com o alvo
   antigo e os dois lados, que era a configuração da auditoria. Cai a
   intensidade, nunca o sinal.
2. **positivo em todos os quatro anos** com a configuração de hoje.
3. **bate entrada aleatória por +4,51 desvios**: 836 compras nas mesmas
   moedas, mesmo stop%, mesmo R:R, momento sorteado → −$25,60/op com
   13,2% de acerto. Comprar essas moedas a esmo **não paga**, nem com a
   maré a favor. (Com o alvo antigo eram +4,89 desvios.)

Com $60 arriscando $1,50 por entrada, o pior momento do histórico custa
$17 (28% da conta).

### O alvo mudou em 13/11: de projeção para 5× o risco

As **mesmas 63-65 operações**, nenhum filtro de entrada mexido — só
onde colher:

| alvo da compra | n | acerto | líq/op | total | rebaix. | z | anos+ |
|---|---|---|---|---|---|---|---|
| projeção 90% (antes) | 65 | 40,0% | +$69,40 | +$4.508 | $1.521 | +2,24 | 3/4 |
| 1:4 de risco | 64 | 37,5% | +$81,70 | +$5.228 | $1.143 | +2,71 | 3/4 |
| **1:5 de risco** | 63 | 33,3% | **+$93,50** | **+$5.888** | **$1.143** | +2,39 | **4/4** |
| 1:6 de risco | 60 | 28,3% | +$91,80 | +$5.505 | $1.670 | +2,27 | 4/4 |

1:4, 1:5 e 1:6 são **todos** melhores que a projeção, então é platô e
não pico de sorte. O 1:5 ganha 35% mais dinheiro, **derruba** o
rebaixamento e é o único que fecha os quatro anos no positivo.

### Só compra — e o que decidiu foi o aleatório

| | n | acerto | méd/op |
|---|---|---|---|
| a venda do setup | 31 | 29,0% | −$3,30 |
| venda em momento sorteado | 580 | 31,9% | **+$5,60** |

**−0,29 desvios.** A venda sorteada se saiu melhor que a do setup. São
31 operações, então não prova que a venda é ruim — prova que não há
indício de que ela leia nada. A compra bate o aleatório por +4,51.

O argumento de manter a venda era 2023 ficar negativo sem ela. Mas o
2023 negativo era **alvo curto**: com o alvo em 1:5 a compra sozinha faz
2023 = +$15. O problema foi resolvido pelo lado certo.

A hipótese de que o alvo projetado era injusto com a venda (uma queda
não passa de 100%, uma alta não tem teto) estava **errada na direção**:
encurtar o alvo da venda piora de forma monótona — 90% −$3,30, 75%
−$10,60, 60% −$17,80, 45% −$25,00, 30% −$33,10, o extremo sem projeção
−$16,90. O acerto mal se mexe (fica entre 26% e 30%), então encurtar não
transforma perdedora em ganhadora, só corta o prêmio das que iam longe.

### Avisos no Telegram — dois momentos

- **🟡 ENCOSTOU** — o preço tocou a borda do order block, e a janela de
  48h do gatilho começou. Traz o bloco, o **meio do bloco** (a linha que
  mata o setup) e quanto já afundou, as horas que faltam, stop, alvo,
  R:R e a mão. Provisório, medido no preço do momento.
  **2,8 por mês · 60% viram entrada · 7h de antecedência na mediana.**
- **🟢 GATILHO** — a vela de 1h confirmou. Números finais e entrada.

Uma montagem avisa uma vez. Avisos de encosto usam status `avisado`,
então não entram no placar nem no CSV.

### A espera de 30 dias já é o número certo

| espera | n | acerto | líq/op | total |
|---|---|---|---|---|
| **30 dias (hoje)** | 65 | **40,0%** | **+$69,40** | +$4.508 |
| 60 dias | 77 | 39,0% | +$55,80 | +$4.293 |
| 90 dias | 88 | 35,2% | +$39,30 | +$3.454 |
| 120 dias | 89 | 34,8% | +$37,60 | +$3.348 |
| 150 dias | 89 | 34,8% | +$37,60 | +$3.348 |

150 = 120 porque **nenhuma montagem demora mais que ~120 dias** para
encostar. E as operações extras são ruins: de 30 para 90 dias ganha 23
operações e perde $30 por operação. Elas caem em 2023, quando o encosto
demorava porque o preço continuava caindo. O total em dinheiro **cai**.
(Medido com só compra e o alvo antigo.)

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
- **Testar a hipótese do funding de 8h** — medir se o resultado muda
  conforme a explosão acontece na vela que fecha no funding ou em outra.
  É o que explicaria a descontinuidade entre 8h e 12h.
- Refazer a varredura da espera com a configuração de hoje (a medida
  atual é com o alvo antigo).
- Oracle Cloud (removeria a fila do GitHub Actions, ~6 min por rodada).
- Bug conhecido: `analise/trailing_tf.py` calcula rebaixamento por par,
  não em ordem cronológica.

## Placar ao vivo (setup 1)

8 fechados · 3 gain / 5 loss (38%) · +4,98R · 0 abertos
