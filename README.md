# bot-smc-binance

Laboratório de backtest de estratégias em cripto. O foco aqui é **testar se uma
estratégia tem edge de verdade**, não produzir um número bonito.

## Arquivos

| Arquivo | O que é |
|---|---|
| `baixar_dados.py` | Baixa o histórico da Binance e salva em `dados/*.csv` |
| `backtest_h4.py` | Backtest SMC H4 — zona de order block persistente + varredura de liquidez |
| `backteste_momentum.py` | Backtest de momentum transversal (carteira long/short) |
| `arquivo/` | Versões antigas, mantidas só por histórico |

## Workflows (aba Actions)

| Workflow | Para quê |
|---|---|
| **Baixar dados** | Roda uma vez e commita os CSVs em `dados/` |
| **Backtest SMC H4** | modos: `filtros`, `unica`, `montecarlo` |
| **Backtest Momentum** | modos: `completo`, `unica`, `montecarlo`, `grade` |

## Como ler um resultado

Três números importam, nesta ordem:

1. **Percentil no Monte Carlo.** Compara a estratégia com o acaso pagando o mesmo
   custo. Entre 5 e 95 significa que não há edge — e aí nenhum outro número importa.
2. **Expectativa por operação (R) ou Sharpe**, com intervalo de confiança.
3. **Max drawdown**, que define o tamanho de posição possível.

Win rate isolado não diz nada: encurte o alvo e ele sobe sem que a estratégia melhore.

## Armadilhas já encontradas neste repo

- **Alvo inalcançável.** A primeira versão colocava o take profit no nível que o
  CHOCH acabava de romper. Nenhum sinal passava.
- **Equilíbrio calculado errado.** Usar o R:R médio de todos os trades infla a
  margem. O correto é o R:R que os vencedores entregaram.
- **`| tee` mascarando erro.** Em pipeline o bash devolve o status do `tee`, e o
  traceback vai para o stderr. Job verde e resultado vazio. Todos os workflows
  daqui usam `set -o pipefail` e `2>&1`.
- **Grade de parâmetros.** Em dados aleatórios, a melhor de 12 combinações deu
  Sharpe 0,73. Olhe a média por dimensão, nunca a melhor célula.
- **Viés de sobrevivência.** O universo são os pares que existem hoje.

## Status das estratégias

**SMC H4 — sem edge demonstrável.** 738 operações em 2026, expectativa de
−0,011R sem custo e −0,082R com 0,10% por operação. Nenhum dos seis filtros
testados (varredura de liquidez, premium/discount, FVG, força do impulso,
tendência diária, horário) separou vencedores de perdedores. A varredura de
liquidez, que era a tese central, ficou com kl/kw de 0,994 — o mesmo que filtrar
por sorteio.

**Momentum transversal — sinal demonstrado, magnitude incerta.** 2023–2026,
carteira long/short semanal: Sharpe 0,80, retorno de 14,8% a.a. já líquido de
custo, max drawdown de 22,6%. No Monte Carlo com 200 carteiras de ranking
sorteado, o resultado real ficou acima de todas (p < 0,005). Sobrevive à
concentração (Sharpe estável de 2+2 até 8+8) e não depende de lançamentos
recentes. Falta na conta: funding e viés de sobrevivência. O t de 1,56 significa
que 3,8 anos não bastam para cravar a magnitude — um Sharpe de 0,80 precisa de
cerca de 6 anos para atingir significância.

**Sobre alavancagem.** Ela multiplica retorno e risco pelo mesmo fator: o Sharpe
não muda. O que muda é a chance de zerar a conta. Com drawdown histórico de
22,6%, 5x levaria a 113% — liquidação. E o arrasto de volatilidade cresce ao
quadrado: a 5x o retorno composto é menor que a 3x, e a 10x fica negativo.
