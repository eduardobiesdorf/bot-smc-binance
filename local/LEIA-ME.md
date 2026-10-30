# Rodar o radar no seu computador

Mais rápido e mais pontual que o GitHub Actions, e não gasta a cota de
Actions (que, a cada 15 min, esgota em ~13 dias num repo privado).

## Windows

1. Abra `rodar_radar.bat` no Bloco de Notas e cole suas duas chaves nas
   linhas `set TELEGRAM_TOKEN=` e `set TELEGRAM_CHAT_ID=`. Salve.
2. Teste uma vez: dê dois cliques em `rodar_radar.bat`.
   O resultado aparece em `local\radar.log`.
3. Funcionando? Clique com o botão direito em `instalar_agendamento.bat`
   e escolha **Executar como administrador**.

Pronto. Roda a cada 15 minutos enquanto o computador estiver ligado.

Conferir:  `schtasks /Query /TN RadarSMC`
Remover:   `schtasks /Delete /TN RadarSMC /F`

## Linux / macOS

1. Cole as chaves em `rodar_radar.sh`.
2. Teste: `./local/rodar_radar.sh && tail local/radar.log`
3. `crontab -e` e acrescente:

       2,17,32,47 * * * * /caminho/completo/local/rodar_radar.sh

## Requisitos

- Python 3 instalado (`python --version`)
- `pip install requests`
- O computador ligado e com internet

## Importante

Enquanto rodar localmente, **desligue o agendamento do GitHub** para não
receber alerta duplicado: comente o bloco `schedule:` em
`.github/workflows/radar.yml`.

O `alertas_enviados.json` que evita repetição é local. Se rodar nos dois
lugares, cada um tem a sua memória e o mesmo setup chega duas vezes.
