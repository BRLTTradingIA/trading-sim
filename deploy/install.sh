#!/usr/bin/env bash
# Installation du robot sur un serveur Ubuntu (Oracle Cloud Always Free, etc.)
# Usage :  bash deploy/install.sh            (depuis le dossier trading-sim)
set -euo pipefail
cd "$(dirname "$0")/.."
APP_DIR="$(pwd)"
USER_NAME="$(whoami)"

echo "1/4 Paquets système"
sudo apt-get update -y
sudo apt-get install -y python3 python3-venv

echo "2/4 Environnement Python"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

echo "3/4 Service qui tourne 24h/24 et redémarre tout seul"
sudo tee /etc/systemd/system/tradebot.service > /dev/null <<EOF
[Unit]
Description=Trading Sim (simulation, aucun ordre reel)
After=network-online.target
Wants=network-online.target

[Service]
User=${USER_NAME}
WorkingDirectory=${APP_DIR}
EnvironmentFile=-${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python -m tradebot.app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now tradebot

echo "4/4 Ouverture du port 8080 dans le pare-feu du serveur"
if command -v iptables >/dev/null; then
  sudo iptables -C INPUT -p tcp --dport 8080 -j ACCEPT 2>/dev/null || sudo iptables -I INPUT 6 -p tcp --dport 8080 -j ACCEPT
  sudo apt-get install -y iptables-persistent >/dev/null 2>&1 || true
  sudo netfilter-persistent save >/dev/null 2>&1 || true
fi

IP="$(curl -s -4 ifconfig.me || echo 'IP_DU_SERVEUR')"
echo
echo "Terminé. Site : http://${IP}:8080"
echo "État du robot : sudo systemctl status tradebot"
echo "Journal en direct : journalctl -u tradebot -f"
