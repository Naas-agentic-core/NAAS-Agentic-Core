# 🚀 CogniForge Deployment Guide: Oracle Cloud VPS

This guide provides instructions on migrating the CogniForge system from unstable GitHub Codespaces to a robust, production-like environment on an Oracle Cloud VPS. This targets an environment resolving frequent "offline" states and dropped WebSocket connections.

---

## 🏗️ 1. Environment Requirements
- **OS:** Ubuntu 22.04 LTS
- **Specs:** 2 CPU, 4GB RAM minimum (Oracle ARM Free Tier is supported)
- **Ports Needed:** `8000` (Backend API & WebSockets), `3000` (Frontend)

---

## 🐳 Option A: Docker Deployment (Optional but Preferred for Isolation)

If you prefer using Docker and Docker Compose on the VPS for parity with the existing devcontainer:

1. **Install Docker and Docker Compose:**
   ```bash
   sudo apt-get update
   sudo apt-get install -y apt-transport-https ca-certificates curl software-properties-common
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
   sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu focal stable"
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-compose
   sudo usermod -aG docker $USER
   ```
   *(Log out and log back in for group changes to take effect)*

2. **Clone and run:**
   ```bash
   git clone <repository-url> /opt/cogniforge
   cd /opt/cogniforge
   docker-compose build
   docker-compose up -d
   ```
   *Note: Ensure `.env.docker` is correctly configured based on the example in the repository.*

---

## 💻 Option B: Non-Docker Deployment (Systemd + PM2)

This approach installs dependencies directly on the host OS. This eliminates the container networking layer, providing maximum WebSocket stability and performance.

### Automated Script Setup

We've provided a deployment script that installs prerequisites, configures the firewall, creates a systemd service for the backend, and uses PM2 for the frontend.

1. **Copy the repository to the VPS:**
   ```bash
   git clone <repository-url> /opt/cogniforge
   ```

2. **Run the deployment script:**
   ```bash
   cd /opt/cogniforge
   sudo ./scripts/deploy_oracle_vps.sh
   ```

### ⚙️ Detailed Configuration (Manual Setup)

#### Uvicorn Systemd Configuration (Backend)
To maintain stable WebSockets, the Uvicorn server must be configured with explicit ping intervals. The systemd service file (`/etc/systemd/system/cogniforge-backend.service`) must look like this:

```ini
[Unit]
Description=CogniForge FastAPI Backend
After=network.target

[Service]
User=appuser
Group=appuser
WorkingDirectory=/opt/cogniforge
Environment="PATH=/opt/cogniforge/.venv/bin"
Environment="PYTHONPATH=/opt/cogniforge"
# ⚠️ Critical WebSocket Settings for Stability ⚠️
ExecStart=/opt/cogniforge/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --ws websockets --ws-ping-interval 20 --ws-ping-timeout 20
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Start the service: `sudo systemctl enable --now cogniforge-backend`

#### PM2 Configuration (Frontend)
Use PM2 to run the Next.js frontend to ensure it restarts on failure:
```bash
cd /opt/cogniforge/frontend
npm install
npm run build
pm2 start npm --name "cogniforge-frontend" -- start -- --port 3000 --hostname 0.0.0.0
pm2 save
pm2 startup
```

---

## 🐞 Debug Checklist

If you encounter connection drops or "offline" issues on the VPS, check the following:

1. [ ] **Firewall Ports:** Ensure `8000` and `3000` are open both in Ubuntu `ufw` AND the Oracle Cloud VCN Security Lists.
   * Verify on server: `sudo ufw status`
   * Test remotely: `nc -zv <VPS-IP> 8000` and `nc -zv <VPS-IP> 3000`
2. [ ] **Backend Logs:** Check Uvicorn for explicit disconnect errors:
   * `sudo journalctl -u cogniforge-backend -f`
3. [ ] **Frontend Logs:** Check PM2 logs:
   * `pm2 logs cogniforge-frontend`
4. [ ] **WebSocket Library:** Verify Uvicorn is strictly using the `websockets` library (not `wsproto`), enforced via `--ws websockets`.
5. [ ] **Ping Interval:** Confirm the Uvicorn startup command includes `--ws-ping-interval 20 --ws-ping-timeout 20`.

---

## 📈 Future Scaling Suggestions

Once the system is stable on the direct IP, consider the following production upgrades:

1. **Reverse Proxy (NGINX/Caddy):**
   - Place NGINX in front of both services on port 80/443.
   - NGINX requires specific WebSocket upgrade headers (`Upgrade $http_upgrade; Connection "upgrade";`).
   - Add SSL/TLS via Let's Encrypt for secure WebSockets (`wss://`).

2. **Redis for WebSocket Broadcasting:**
   - If scaling to multiple Uvicorn workers (e.g., `--workers 4`), in-memory WebSocket tracking will fail. Introduce a Redis Pub/Sub backend to synchronize WebSocket messages across workers.

3. **Container Orchestration:**
   - Move from raw Docker Compose to Kubernetes (or Docker Swarm) if high availability is required.
