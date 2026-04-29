#!/bin/bash
# 🚀 Deployment Script: CogniForge -> Oracle Cloud VPS (Ubuntu 22.04 LTS)
# This script prepares the server, installs dependencies, configures UFW,
# and sets up the services for the CogniForge application (Frontend & Backend).

set -euo pipefail

# --- Configuration ---
REPO_DIR="/opt/cogniforge"
FRONTEND_PORT=3000
BACKEND_PORT=8000
APP_USER="appuser"

echo "==========================================================="
echo "  🚀 Starting CogniForge Deployment on Oracle Cloud VPS"
echo "==========================================================="

# --- 1. System Updates & Prerequisites ---
echo "⚙️ [1/7] Updating system and installing basic dependencies..."
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y software-properties-common curl git ufw build-essential libpq-dev procps iproute2

echo "⚙️ Adding Python 3.12 PPA (Required for Ubuntu 22.04)..."
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3-pip

# --- 2. Install Node.js & PM2 ---
echo "⚙️ [2/7] Installing Node.js 20 LTS and PM2..."
if ! command -v node > /dev/null 2>&1; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi
sudo npm install -g npm@latest
sudo npm install -g pm2

# --- 3. Configure UFW Firewall ---
echo "⚙️ [3/7] Configuring UFW Firewall..."
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow $BACKEND_PORT/tcp
sudo ufw allow $FRONTEND_PORT/tcp
echo "y" | sudo ufw enable

# --- 4. Setup User & Directory ---
echo "⚙️ [4/7] Setting up user and project directory..."
if ! id "$APP_USER" &>/dev/null; then
    sudo useradd -m -s /bin/bash "$APP_USER"
fi

if [ ! -d "$REPO_DIR" ]; then
    echo "Creating directory $REPO_DIR. Please clone the repository into this directory manually if not already done."
    sudo mkdir -p "$REPO_DIR"
    sudo chown -R "$APP_USER":"$APP_USER" "$REPO_DIR"
fi

# Note: In a real automated setup, you would clone the repo here:
# sudo -u "$APP_USER" git clone <your-repo-url> "$REPO_DIR"

# --- 5. Backend Setup (Python / FastAPI / Uvicorn) ---
echo "⚙️ [5/7] Setting up Backend Environment..."
sudo -u "$APP_USER" bash -c "cd $REPO_DIR && python3.12 -m venv .venv"
sudo -u "$APP_USER" bash -c "cd $REPO_DIR && source .venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"

# Create systemd service for the backend
SERVICE_FILE="/etc/systemd/system/cogniforge-backend.service"
echo "Creating systemd service file at $SERVICE_FILE..."
sudo bash -c "cat > $SERVICE_FILE" <<EOF
[Unit]
Description=CogniForge FastAPI Backend
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$REPO_DIR
Environment="PATH=$REPO_DIR/.venv/bin"
Environment="PYTHONPATH=$REPO_DIR"
# Critical WebSocket Settings for Stability
ExecStart=$REPO_DIR/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --ws websockets --ws-ping-interval 20 --ws-ping-timeout 20
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable cogniforge-backend.service
sudo systemctl restart cogniforge-backend.service

# --- 6. Frontend Setup (Next.js / PM2) ---
echo "⚙️ [6/7] Setting up Frontend Environment..."
# Assuming frontend is in the 'frontend' directory inside the repo
FRONTEND_DIR="$REPO_DIR/frontend"

echo "⚠️  Ensure your .env files are configured correctly before building the frontend."
echo "Press ENTER to continue or Ctrl+C to abort and configure them manually."
read -r

if [ -d "$FRONTEND_DIR" ]; then
    sudo -u "$APP_USER" bash -c "cd $FRONTEND_DIR && npm install"
    sudo -u "$APP_USER" bash -c "cd $FRONTEND_DIR && npm run build"

    # Start with PM2
    sudo -u "$APP_USER" bash -c "cd $FRONTEND_DIR && pm2 start npm --name 'cogniforge-frontend' -- start -- --port $FRONTEND_PORT --hostname 0.0.0.0"
    sudo -u "$APP_USER" bash -c "pm2 save"
    sudo env PATH=$PATH:/usr/bin /usr/lib/node_modules/pm2/bin/pm2 startup systemd -u $APP_USER --hp /home/$APP_USER
else
    echo "⚠️ Frontend directory not found at $FRONTEND_DIR. Skipping frontend setup."
fi

# --- 7. Final Verification ---
echo "⚙️ [7/7] Deployment complete. Verifying services..."
sudo systemctl status cogniforge-backend.service --no-pager || true
sudo -u "$APP_USER" pm2 status || true

echo "==========================================================="
echo "✅ CogniForge deployed successfully!"
echo "Backend: http://<your-vps-ip>:$BACKEND_PORT"
echo "Frontend: http://<your-vps-ip>:$FRONTEND_PORT"
echo "==========================================================="
