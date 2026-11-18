# Regras deste repositório

## Rodar no Actions: liberado

**Pode disparar workflow direto, sem pedir aprovação.** O repositório virou
público em 16/11/2026 e os minutos do Actions passaram a ser ilimitados e
gratuitos. Até 18/11 havia uma trava de aprovação aqui, por causa da cota
paga de repositório privado; o Eduardo a removeu quando o custo zerou.

Continua valendo o bom senso: dizer o que está rodando e por quê, e não
disparar backtest pesado em paralelo com o radar sem necessidade.

## O cron do bot

`varredura.yml` roda de 2 em 2 horas (`37 */2 * * *`), nas horas ÍMPARES
em Brasília: 01h37, 03h37, 05h37 e assim por diante.

Por que 2h e não 4h: medido entre 14 e 16/11, o GitHub só disparou 44% dos
horários agendados, com atraso de 36 min a 3h12. Com 4h de espaçamento, um
horário descartado deixava 8 horas cego — e a entrada do setup 1 é ordem
limitada válida 4h, ou seja, nascia e morria entrada sem ninguém ver. A
saída foi redundância, não pontualidade.

Por que o minuto :37 e não :01: o :01 é o minuto mais disputado do GitHub.
Trocar sozinho não resolveu o descarte, mas não custa nada e ajuda.

O bot avisa sozinho quando fica fora: `batimento()` manda no Telegram
quanto tempo ficou cego ao voltar de um buraco de 3h ou mais, e uma vez por
dia manda o placar (rodadas feitas de 12). Se existir o segredo
`PING_VIGIA`, bate numa URL de vigia externo a cada rodada — é o único
jeito de pegar o caso em que o bot morre de vez e não consegue avisar de
dentro.

## Os workflows: quais estão vivos

Só QUATRO interessam. Os nomes foram prefixados para a lista do Actions
(que ordena por nome) deixar os vivos no topo:

```
00 · RODAR OS TRÊS DE UMA VEZ (manual)   varredura.yml  -- sem cron
01 · Setup 1 — varredura de liquidez     s1.yml         -- cron :05
03 · Setup 3 — reversão de 8h            s3.yml         -- cron :25
05 · Setup 5 — rompimento falso          s5.yml         -- cron :45
pesquisa · ...                           os outros 50   -- sem cron, não rodar
```

O GitHub NÃO aceita subpasta em `.github/workflows/` — tem de ser plano.
A organização é pelo nome, por isso o prefixo. Ao criar workflow novo,
seguir a convenção: vivo ganha número, pesquisa ganha `pesquisa · `.

Cada setup roda sozinho com `--sem-varredura` / `--sem-reversao8` /
`--sem-falha5`, e com `--rotulo s1|s3|s5` para ter o seu próprio
diagnóstico, resumo e batimento — senão os três brigam pelo mesmo arquivo
no git a cada hora. O acompanhamento do setup 1 (stop móvel, desfechos,
placar) só roda em quem roda o setup 1, senão sai desfecho em triplicata.

## Coisas que já me pegaram

- O dono do repositório é **eduardobiesdorf**, não `dubiesdorf`. Os
  disparos são `gh api -X POST
  /repos/eduardobiesdorf/bot-smc-binance/actions/workflows/<arquivo>/dispatches
  -f ref=main`.
- **O `git push` costuma ser rejeitado** porque o Actions commita os
  arquivos de estado do bot. A receita:
  `git checkout -- diagnostico_varredura.txt` e depois
  `git pull --rebase --autostash -q origin main`.
- **A Binance é bloqueada por geografia deste contêiner.** Todo teste que
  precise de dado ao vivo tem de rodar no Actions.
- **18/11/2026 — o bot passou a ler FUTUROS, pelo `www.binance.com/fapi/v1`.**
  Antes lia spot, enquanto todo o backteste é em perpétuo (70% de
  sobreposição de universo). `fapi.binance.com` dá **451** dos runners do
  GitHub, que ficam nos EUA. Foram testadas 9 portas: `fapi` 451,
  `fapi1/2/3` 302, `dapi` 451, `data-api.binance.vision/fapi` 404, e a que
  passa é o mesmo endpoint pelo domínio do site. **Não trocar de volta sem
  testar: essa é a única porta aberta.** O spread contra o spot no BTC deu
  -0,056%.
- **Nos futuros a ação tokenizada NÃO leva o B do spot** (`NVDAUSDT`, não
  `NVDABUSDT`), e **45 das 150 maiores do perpétuo são ação, ETF ou
  commodity**. Por isso `_ACOES_BASE` guarda o ticker puro e gera as duas
  formas, e por isso `--top` é **215**: 215 do topo rendem ~150 criptos,
  que é o universo do backteste. Quem pega o que a lista não tem é o
  `negocia_sempre()` (volume de fim de semana ≥ 12%) — num teste ele
  descartou sozinho SAMSUNG, SQQQ, NATGAS, COPPER, UVXY, XPT, CL e BZ.
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
