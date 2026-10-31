#!/usr/bin/env bash
# Instala o radar da varredura numa maquina Oracle Cloud (Ubuntu).
# Rode UMA vez, depois de conectar por SSH:
#
#     bash instalar.sh
#
set -euo pipefail

REPO_SSH="git@github.com:eduardobiesdorf/bot-smc-binance.git"
DESTINO="$HOME/bot-smc-binance"

echo "==> 1/6  Atualizando o sistema"
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git

echo "==> 2/6  Criando area de troca (a maquina gratuita tem pouca memoria)"
if [ ! -f /swapfile ]; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile >/dev/null
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo "    2 GB de swap criados"
else
  echo "    swap ja existe"
fi

echo "==> 3/6  Chave para baixar o repositorio"
if [ ! -f "$HOME/.ssh/id_ed25519" ]; then
  ssh-keygen -t ed25519 -N "" -C "oracle-radar" -f "$HOME/.ssh/id_ed25519"
  echo
  echo "  ------------------------------------------------------------"
  echo "  COPIE a chave abaixo e cadastre no GitHub em:"
  echo "    github.com/eduardobiesdorf/bot-smc-binance"
  echo "    -> Settings -> Deploy keys -> Add deploy key"
  echo "    Titulo: oracle    |  Allow write access: NAO marcar"
  echo "  ------------------------------------------------------------"
  cat "$HOME/.ssh/id_ed25519.pub"
  echo "  ------------------------------------------------------------"
  echo
  read -r -p "  Cadastrou a chave? Tecle ENTER para continuar. " _
fi
ssh-keyscan -t ed25519 github.com >> "$HOME/.ssh/known_hosts" 2>/dev/null || true

echo "==> 4/6  Baixando o codigo"
if [ -d "$DESTINO/.git" ]; then
  git -C "$DESTINO" pull --ff-only
else
  git clone --depth 1 "$REPO_SSH" "$DESTINO"
fi

echo "==> 5/6  Instalando as bibliotecas"
python3 -m venv "$DESTINO/.venv"
"$DESTINO/.venv/bin/pip" install -q --upgrade pip
"$DESTINO/.venv/bin/pip" install -q requests matplotlib

echo "==> 6/6  Credenciais do Telegram"
ENVFILE="$HOME/.radar_env"
if [ ! -f "$ENVFILE" ]; then
  read -r -p "  TOKEN do bot do Telegram: " TOK
  read -r -p "  CHAT ID: " CID
  cat > "$ENVFILE" <<EOF
export TELEGRAM_TOKEN="$TOK"
export TELEGRAM_CHAT_ID="$CID"
EOF
  chmod 600 "$ENVFILE"
  echo "    guardado em $ENVFILE (so voce consegue ler)"
else
  echo "    $ENVFILE ja existe, mantido"
fi

cat > "$DESTINO/oracle/rodar.sh" <<EOF
#!/usr/bin/env bash
# Chamado pelo cron no minuto 1 de cada hora.
set -u
source "\$HOME/.radar_env"
cd "$DESTINO"
"$DESTINO/.venv/bin/python" -u bot_varredura.py --top 20 \\
  >> "\$HOME/radar.log" 2>&1
# o log nao pode crescer para sempre
tail -n 2000 "\$HOME/radar.log" > "\$HOME/radar.log.tmp" \\
  && mv "\$HOME/radar.log.tmp" "\$HOME/radar.log"
EOF
chmod +x "$DESTINO/oracle/rodar.sh"

# cron no minuto 1, logo apos o fechamento da vela de H1
LINHA="1 * * * * $DESTINO/oracle/rodar.sh"
( crontab -l 2>/dev/null | grep -v 'oracle/rodar.sh' ; echo "$LINHA" ) | crontab -

echo
echo "================================================================"
echo "  Pronto. O radar roda no minuto 1 de cada hora."
echo
echo "  Testar agora:        $DESTINO/oracle/rodar.sh && tail -20 ~/radar.log"
echo "  Ver o log:           tail -f ~/radar.log"
echo "  Ver o agendamento:   crontab -l"
echo "  Atualizar o codigo:  git -C $DESTINO pull"
echo
echo "  IMPORTANTE: desligue o agendamento do GitHub Actions para nao"
echo "  receber o alerta duas vezes. Veja o LEIA-ME.md."
echo "================================================================"
