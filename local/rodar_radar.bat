@echo off
REM ============================================================
REM  Radar SMC - execucao local
REM  Preencha as duas chaves abaixo e salve.
REM ============================================================

set TELEGRAM_TOKEN=COLE_SEU_TOKEN_AQUI
set TELEGRAM_CHAT_ID=COLE_SEU_CHAT_ID_AQUI

cd /d "%~dp0.."
python bot_alertas.py --top 50 --tf-estrutura 30m --tf-gatilho 15m --rr-fixo 2.0 >> local\radar.log 2>&1
