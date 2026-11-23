#!/usr/bin/env bash
# ==============================================================================
# DegenBot AWS EC2 Automated Deployment Script (Ubuntu 22.04 / 24.04 LTS)
# Sets up Python 3 venv, Node.js, builds Next.js UI, configures systemd & Nginx
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo " Starting DegenBot EC2 Setup..."
echo "=========================================================="

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USER_NAME="$(whoami)"

echo "Detected app directory: ${APP_DIR}"
echo "Current user: ${USER_NAME}"

# 1. Update OS packages and install core build tools
echo "--> Updating system packages..."
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git curl nginx build-essential

# 2. Add 2GB Swapfile if physical RAM is <= 1.5GB (Prevents OOM on t3.micro)
TOTAL_RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
if [ "${TOTAL_RAM_MB}" -le 1500 ] && [ ! -f /swapfile ]; then
    echo "--> Detected ${TOTAL_RAM_MB}MB RAM on t3.micro. Configuring 2GB virtual swap..."
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "--> 2GB swap active."
fi

# 3. Install Node.js 20 LTS if not present
if ! command -v node >/dev/null 2>&1; then
    echo "--> Installing Node.js 20 LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
else
    echo "--> Node.js $(node -v) already installed."
fi

# 3. Setup Python Virtual Environment
echo "--> Setting up Python environment..."
cd "${APP_DIR}"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi

# 4. Ensure data directories exist
mkdir -p "${APP_DIR}/data"
mkdir -p "${APP_DIR}/results"

# 5. Build Next.js Web Dashboard
echo "--> Building Next.js Web Dashboard..."
cd "${APP_DIR}/web"
npm install
npm run build

# 6. Configure systemd services
echo "--> Configuring systemd services..."
sudo cp "${APP_DIR}/deploy/degen-bot.service" /etc/systemd/system/
sudo cp "${APP_DIR}/deploy/degen-web.service" /etc/systemd/system/

# Adjust user/paths for systemd service files
sudo sed -i "s|User=ubuntu|User=${USER_NAME}|g" /etc/systemd/system/degen-bot.service
sudo sed -i "s|/home/ubuntu/degen-bot|${APP_DIR}|g" /etc/systemd/system/degen-bot.service
sudo sed -i "s|User=ubuntu|User=${USER_NAME}|g" /etc/systemd/system/degen-web.service
sudo sed -i "s|/home/ubuntu/degen-bot|${APP_DIR}|g" /etc/systemd/system/degen-web.service

sudo systemctl daemon-reload

# 7. Configure Nginx Reverse Proxy (Exposes Dashboard on Port 80 HTTP)
echo "--> Configuring Nginx reverse proxy on port 80..."
sudo cp "${APP_DIR}/deploy/nginx.conf" /etc/nginx/sites-available/degen-bot
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/degen-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx

# 8. Start & Enable DegenBot Services
echo "--> Starting DegenBot and Web Dashboard..."
sudo systemctl enable degen-bot
sudo systemctl restart degen-bot
sudo systemctl enable degen-web
sudo systemctl restart degen-web

echo "=========================================================="
echo " Setup Complete!"
echo " Both services are running 24/7 with auto-restart."
echo ""
echo " Dashboard is live at: http://$(curl -s ifconfig.me || echo '<EC2_PUBLIC_IP>')"
echo ""
echo " Useful Commands:"
echo "   sudo systemctl status degen-bot   # Check bot daemon"
echo "   sudo systemctl status degen-web   # Check website"
echo "   journalctl -u degen-bot -f        # View live trading logs"
echo "=========================================================="
