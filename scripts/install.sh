#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://localhost}"
REGISTRATION_TOKEN="${REGISTRATION_TOKEN:-CHANGE_ME}"
INSTALL_DIR="$HOME/.kysscheck-agent"

mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install httpx pynacl

cat > run_agent.sh <<RUN
#!/usr/bin/env bash
source "$INSTALL_DIR/.venv/bin/activate"
python "$INSTALL_DIR/agent.py" --base-url "$BASE_URL" --registration-token "$REGISTRATION_TOKEN"
RUN
chmod +x run_agent.sh

cp "$(dirname "$0")/../agent/agent.py" "$INSTALL_DIR/agent.py"
nohup "$INSTALL_DIR/run_agent.sh" >/tmp/kysscheck-agent.log 2>&1 &

echo "KYSSCHECK agent установлен и запущен в фоне"
