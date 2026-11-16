# Regras deste repositório

## TRAVA: não rodar nada no Actions sem aprovação

**Nunca disparar um workflow sem o Eduardo aprovar antes.** Isso vale para
tudo: `workflow_dispatch`, backtest, painel, ping, download de dado. Os
minutos do Actions são pagos e a cota é limitada.

O procedimento é sempre o mesmo:

1. Dizer o que precisa rodar e **por quê**.
2. Dizer o **custo estimado em minutos** (a varredura leva 3,2 min; o
   painel ~11 min; um backtest de universo inteiro de 10 a 60 min).
3. **Esperar o ok.** Sem resposta, não roda.

Medido em novembro/2026: 2.825 min gastos no mês, dos quais 1.789 foram
pesquisa. A cota gratuita de repositório privado é 2.000 min/mês. O custo
por minuto além da cota é $0,008 (Linux).

Empurrar commit (`git push`) é de graça e não dispara nada: nenhum workflow
aqui tem gatilho `on: push`. Só o disparo de workflow precisa de aprovação.

## O cron do bot

`varredura.yml` roda de 4 em 4 horas (`1 */4 * * *`): 00/04/08/12/16/20
UTC, que em Brasília é 21h, 01h, 05h, 09h, 13h e 17h. São 6 rodadas/dia,
cobradas como 4 min cada (o GitHub arredonda para cima) = ~720 min/mês.

Não mexer nisso sem falar com ele: a frequência foi escolhida para caber na
cota, e as horas foram escolhidas para pegar todo fechamento de H4 (setup 1)
e de H8 (setup 3).

## Coisas que já me pegaram

- O dono do repositório é **eduardobiesdorf**, não `dubiesdorf`. Os
  disparos são `gh api -X POST
  /repos/eduardobiesdorf/bot-smc-binance/actions/workflows/<arquivo>/dispatches
  -f ref=main`.
- **O `git push` costuma ser rejeitado** porque o Actions commita os
  arquivos de estado do bot. A receita:
  `git checkout -- diagnostico_varredura.txt` e depois
  `git pull --rebase --autostash -q origin main`.
- **A Binance é bloqueada por geografia deste contêiner.** `fapi.binance.com`
  e `data-api.binance.vision` dão `403 Forbidden` no túnel. Todo teste que
  precise de dado ao vivo tem de rodar no Actions. O CDN público
  `data.binance.vision` funciona de dentro do Actions.
- **16/11/2026 — o histórico foi reescrito e limpo** (`git filter-repo`),
  porque o repositório ia virar público. Saíram de TODOS os 743 commits: o
  `diagnostico_telegram.txt` inteiro, o chat_id do Telegram e o sobrenome;
  e o único commit assinado com o e-mail pessoal passou a usar o
  `@users.noreply.github.com`. Nenhum token jamais foi commitado — isso foi
  verificado varrendo todos os blobs do histórico.
- **Em repositório público o log do Actions também é público.** Por isso
  `resposta_limpa()` existe em `bot_varredura.py`, `bot_alertas.py`,
  `grafico_varredura.py` e `grafico_setup.py`: a resposta do Telegram traz
  nome e id do chat dentro de `result`, e isso não pode ir para o log.
  Nunca voltar a logar `r.text` de um envio ao Telegram.

## Como ele quer as respostas

Linguagem de trader, não acadêmica, e breve. Dinheiro e porcentagem em vez
de jargão ("3R" não serve; "$300 com stop de 2%" serve). Toda data e hora
em horário de Brasília, nunca em UTC. Análise honesta antes de validação,
mas jogando a favor das ideias dele: trazer a oportunidade junto com o
problema. Ao entregar código, entregar o arquivo completo, nunca trecho.
