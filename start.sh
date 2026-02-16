#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# Pretty Good AI — Voice Bot Tester
# Single-command launcher: starts ngrok + server, then runs all test calls.
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

PORT="${SERVER_PORT:-8765}"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SERVER_LOG=""
NGROK_LOG=""
cleanup() {
    echo -e "\n${YELLOW}Shutting down...${NC}"
    [ -n "${NGROK_PID:-}" ] && kill "$NGROK_PID" 2>/dev/null || true
    [ -n "${SERVER_PID:-}" ] && kill "$SERVER_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    [ -n "${SERVER_LOG:-}" ] && [ -f "$SERVER_LOG" ] && rm -f "$SERVER_LOG"
    [ -n "${NGROK_LOG:-}" ] && [ -f "$NGROK_LOG" ] && rm -f "$NGROK_LOG"
    echo -e "${GREEN}Done.${NC}"
}
trap cleanup EXIT

# ── Preflight checks ───────────────────────────────────────────────────
echo -e "${GREEN}Pretty Good AI — Voice Bot Tester${NC}"
echo "================================================"

if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found.${NC}"
    echo "Run:  cp .env.example .env   and fill in your API keys."
    exit 1
fi

if ! command -v ngrok &>/dev/null; then
    echo -e "${RED}ERROR: ngrok not found.${NC}"
    exit 1
fi

if ! command -v python3 &>/dev/null; then
    echo -e "${RED}ERROR: python3 not found.${NC}"
    exit 1
fi

# Check dependencies are installed
python3 -c "import fastapi, uvicorn, websockets, httpx, twilio, openai, dotenv" 2>/dev/null || {
    echo -e "${YELLOW}Installing dependencies...${NC}"
    pip install -r requirements.txt -q
}

# ── Start ngrok ─────────────────────────────────────────────────────────
# Use authtoken from .env if set (ngrok reads NGROK_AUTHTOKEN)
if [ -f .env ]; then
    _tok=$(grep -E '^NGROK_AUTHTOKEN=' .env 2>/dev/null | cut -d= -f2- | sed "s/^['\"]//;s/['\"]$//" | tr -d '\r')
    [ -n "$_tok" ] && export NGROK_AUTHTOKEN="$_tok"
fi
echo -e "\n${YELLOW}[1/3] Starting ngrok on port ${PORT}...${NC}"
NGROK_LOG=$(mktemp)
ngrok http "$PORT" --log=stdout >> "$NGROK_LOG" 2>&1 &
NGROK_PID=$!
sleep 4

NGROK_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for t in data.get('tunnels', []):
        if t.get('proto') == 'https':
            print(t['public_url'])
            break
except: pass
" 2>/dev/null)

if [ -z "$NGROK_URL" ]; then
    echo ""
    echo -e "${RED}════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  EXIT REASON: ngrok did not provide a public URL${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Possible causes:"
    echo "  • ngrok not signed in — run:  ngrok config add-authtoken YOUR_TOKEN"
    echo "    (Get token at https://dashboard.ngrok.com/get-started/your-authtoken)"
    echo "  • Port ${PORT} already in use — try another port or free the port"
    echo "  • ngrok process failed to start (see output below)"
    echo ""
    echo -e "${YELLOW}ngrok output:${NC}"
    cat "$NGROK_LOG" 2>/dev/null || echo "(no output)"
    echo ""
    exit 1
fi
echo -e "${GREEN}  ngrok ready: ${NGROK_URL}${NC}"

# ── Start the server ────────────────────────────────────────────────────
echo -e "\n${YELLOW}[2/3] Starting voice bot server...${NC}"
SERVER_LOG=$(mktemp)
python3 main.py > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!
sleep 3

# Health check
if ! curl -sf "http://localhost:${PORT}/health" > /dev/null 2>&1; then
    echo ""
    echo -e "${RED}════════════════════════════════════════════════════════════${NC}"
    echo -e "${RED}  EXIT REASON: voice bot server did not start${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════${NC}"
    echo ""
    echo "Usually this means .env is missing required API keys or values are wrong."
    echo "Required: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER,"
    echo "          DEEPGRAM_API_KEY, OPENAI_API_KEY"
    echo ""
    echo -e "${YELLOW}Server output:${NC}"
    cat "$SERVER_LOG"
    echo ""
    exit 1
fi
echo -e "${GREEN}  Server ready on port ${PORT}${NC}"

# ── Run tests ───────────────────────────────────────────────────────────
echo -e "\n${YELLOW}[3/3] Running test calls...${NC}"
echo ""
python3 run_tests.py "$@"

echo -e "\n${GREEN}All done! Transcripts are in: transcripts/${NC}"
