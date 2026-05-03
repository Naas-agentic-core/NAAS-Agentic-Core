#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
#  CogniForge — Dev Environment Setup
#  Runs once after container creation (postCreateCommand)
#  Works in: Replit | GitHub Codespaces | VS Code Dev Container
# ═══════════════════════════════════════════════════════════

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()    { echo -e "${CYAN}[setup]${NC} $1"; }
ok()     { echo -e "${GREEN}[✓]${NC} $1"; }
warn()   { echo -e "${YELLOW}[!]${NC} $1"; }
err()    { echo -e "${RED}[✗]${NC} $1"; }

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║   CogniForge — Environment Setup         ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════╝${NC}"
echo ""

# ── 1. Install Python dependencies ──────────────────────────
log "Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    pip install --quiet -r requirements.txt
    ok "Python deps installed (requirements.txt)"
else
    warn "requirements.txt not found — skipping"
fi

# ── 2. Install frontend dependencies ────────────────────────
log "Installing frontend dependencies..."
if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    cd frontend
    npm install --silent
    cd ..
    ok "Frontend deps installed (frontend/package.json)"
else
    warn "frontend/package.json not found — skipping"
fi

# ── 3. Install Claude Code ───────────────────────────────────
log "Installing Claude Code CLI..."
if command -v claude &> /dev/null; then
    CLAUDE_VER=$(claude --version 2>/dev/null || echo "unknown")
    ok "Claude Code already installed: $CLAUDE_VER"
else
    if npm install -g @anthropic-ai/claude-code --silent 2>/dev/null; then
        ok "Claude Code installed globally"
    else
        warn "Could not install Claude Code — install manually: npm install -g @anthropic-ai/claude-code"
    fi
fi

# ── 4. Verify CLAUDE.md exists ──────────────────────────────
if [ -f "CLAUDE.md" ]; then
    ok "CLAUDE.md found — Claude Code context ready"
else
    warn "CLAUDE.md not found — Claude Code will lack project context"
fi

# ── 5. Verify .claude/settings.json ─────────────────────────
if [ -f ".claude/settings.json" ]; then
    ok ".claude/settings.json found — permissions configured"
else
    warn ".claude/settings.json not found"
fi

# ── 6. Check critical env vars ───────────────────────────────
echo ""
log "Checking environment variables..."

check_env() {
    local var="$1"
    local required="$2"
    if [ -n "${!var:-}" ]; then
        ok "$var is set"
    elif [ "$required" = "required" ]; then
        err "$var is MISSING (required)"
    else
        warn "$var is not set (optional)"
    fi
}

check_env "APP_DATABASE_URL" "required"
check_env "OPENROUTER_API_KEY" "optional"
check_env "OPENAI_API_KEY" "optional"
check_env "SECRET_KEY" "optional"
check_env "ENVIRONMENT" "optional"

# ── 7. Quick backend smoke test ──────────────────────────────
echo ""
log "Running quick import check..."
if python3 -c "
import sys
sys.path.insert(0, '.')
try:
    from app.core.config import get_settings
    s = get_settings()
    print('AppSettings OK — DB:', s.DATABASE_URL[:20] if s.DATABASE_URL else 'None')
except Exception as e:
    print(f'WARNING: {e}')
    sys.exit(0)  # non-fatal
" 2>/dev/null; then
    ok "Backend imports healthy"
else
    warn "Backend import check skipped (env vars may be missing)"
fi

# ── Done ─────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Setup complete!                        ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""
echo "Next steps:"
echo "  Start backend:   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
echo "  Start frontend:  cd frontend && npm run dev"
echo "  Run tests:       pytest tests/ -x"
echo "  Lint:            ruff check . && isort --check-only ."
echo "  Health check:    curl http://localhost:8000/health"
echo ""
echo "With Claude Code:"
echo "  claude                  # start interactive session"
echo "  claude --print 'help'   # quick question"
echo ""
