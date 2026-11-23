# AWS EC2 Deployment Guide for DegenBot

This guide walks you through deploying both the **Python Trading Bot Daemon** and the **Next.js Web Trading Terminal** to your AWS EC2 instance so they run 24/7 with automatic restarts on reboot.

---

## 1. Configure AWS EC2 Security Group (Firewall)

In the AWS EC2 Console, open your instance's **Security Group** and add the following **Inbound Rules**:

| Type | Protocol | Port Range | Source | Purpose |
| :--- | :---: | :---: | :---: | :--- |
| **SSH** | TCP | `22` | `My IP` | Secure SSH console access |
| **HTTP** | TCP | `80` | `0.0.0.0/0` | Web Dashboard (served via Nginx) |
| **Custom TCP** (Optional) | TCP | `3000` | `0.0.0.0/0` | Direct Next.js port |

---

## 2. Transfer Code to Your EC2 Instance

You can either clone your Git repository or transfer files directly using `rsync` from your local machine:

### Option A: Using Git (Fastest)
SSH into your EC2 instance:
```bash
ssh -i /path/to/your-key.pem ubuntu@<EC2_PUBLIC_IP>
```
Clone the repository:
```bash
git clone <YOUR_GIT_REPO_URL> degen-bot
cd degen-bot
```

### Option B: Using Rsync (Direct from your computer)
Run this command from your local machine inside the `degen-bot` directory:
```bash
rsync -avz -e "ssh -i /path/to/your-key.pem" \
  --exclude '.venv' \
  --exclude 'node_modules' \
  --exclude '.next' \
  --exclude '.git' \
  ./ ubuntu@<EC2_PUBLIC_IP>:~/degen-bot/
```

---

## 3. Run the Automated 1-Click Setup Script

SSH into your EC2 server and run the setup script:
```bash
cd ~/degen-bot
bash deploy/setup_ec2.sh
```

### What this script automatically configures:
1. Installs Python 3, pip, venv, and Node.js 20 LTS.
2. Builds the Next.js Web Dashboard (`npm run build`).
3. Installs and starts two `systemd` background services:
   * **`degen-bot.service`**: The autonomous trading bot daemon (`src/main.py`).
   * **`degen-web.service`**: The Next.js web application.
4. Configures **Nginx** reverse proxy to route standard HTTP (port 80) directly to the web dashboard.
5. Enables both services to start automatically if the EC2 instance reboots.

---

## 4. Accessing Your Live Dashboard

Open your web browser and navigate to:
```
http://<EC2_PUBLIC_IP>
```
*(No need to add `:3000` because Nginx routes port 80 directly to the app!)*

---

## 5. Monitoring & Managing Services

### Check Service Status
```bash
sudo systemctl status degen-bot    # Status of trading bot
sudo systemctl status degen-web    # Status of web terminal
```

### View Live Trading Logs (Streaming)
```bash
journalctl -u degen-bot -f         # Watch scanner and paper trades live
journalctl -u degen-web -f         # Watch web terminal logs
```

### Restart or Stop Services
```bash
sudo systemctl restart degen-bot   # Restart trading bot
sudo systemctl restart degen-web   # Restart web terminal
sudo systemctl stop degen-bot      # Stop trading bot
```
