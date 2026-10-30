#!/usr/bin/env bash
# Radar SMC - execucao local (Linux / macOS)
export TELEGRAM_TOKEN="COLE_SEU_TOKEN_AQUI"
export TELEGRAM_CHAT_ID="COLE_SEU_CHAT_ID_AQUI"
cd "$(dirname "$0")/.."
python3 bot_alertas.py --top 50 --tf-estrutura 30m --tf-gatilho 15m --rr-fixo 2.0 \
  >> local/radar.log 2>&1
