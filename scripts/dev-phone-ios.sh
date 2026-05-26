#!/usr/bin/env bash
# scripts/dev-phone-ios.sh
# ─────────────────────────
# Full iOS native shell setup for MICHA. Configures Xcode + CocoaPods +
# Capacitor live-reload, then opens Xcode pointed at the dev server.
#
# Workflow:
#   1. ./scripts/dev-phone.sh        — backend + frontend over LAN
#   2. ./scripts/dev-phone-ios.sh    — Xcode opens with live-reload
#   3. In Xcode: pick simulator OR connected iPhone → ▶ Run
#
# To exit live-reload mode (revert capacitor.config.json):
#   ./scripts/dev-phone-ios.sh --reset
#
# Required: macOS, Xcode app installed at /Applications/Xcode.app

set -e

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
RESET='\033[0m'

CAP_CFG="$ROOT/frontend/capacitor.config.json"
CAP_CFG_BAK="$ROOT/frontend/capacitor.config.json.prod.bak"


# ── Subcommand: --reset reverts capacitor.config.json to prod ──
if [ "$1" = "--reset" ]; then
  if [ -f "$CAP_CFG_BAK" ]; then
    mv "$CAP_CFG_BAK" "$CAP_CFG"
    echo "${GREEN}✓ Reverted capacitor.config.json (production-safe).${RESET}"
  else
    echo "Nothing to reset — already in production-safe mode."
  fi
  exit 0
fi


# ── Step 1: Xcode-select pointing at full Xcode ────────────────
echo "${BOLD}${BLUE}[1/5]${RESET} Checking Xcode setup…"

if [ ! -d "/Applications/Xcode.app" ]; then
  echo "${RED}✗ Xcode.app not found at /Applications/Xcode.app${RESET}"
  echo "   Install Xcode from the Mac App Store (~12 GB), then re-run."
  exit 1
fi

CURRENT_DEV_DIR=$(xcode-select -p)
if [ "$CURRENT_DEV_DIR" != "/Applications/Xcode.app/Contents/Developer" ]; then
  echo "${YELLOW}   xcode-select currently points to: $CURRENT_DEV_DIR${RESET}"
  echo "${YELLOW}   Switching to the full Xcode (will prompt for sudo password)…${RESET}"
  sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
fi

# Accept Xcode license if needed (no-op if already accepted).
sudo xcodebuild -license accept 2>/dev/null || true

echo "${GREEN}   ✓ Xcode developer dir: $(xcode-select -p)${RESET}"


# ── Step 2: CocoaPods ──────────────────────────────────────────
echo "${BOLD}${BLUE}[2/5]${RESET} Checking CocoaPods…"

if ! command -v pod >/dev/null 2>&1; then
  echo "${YELLOW}   Installing CocoaPods (will prompt for sudo password)…${RESET}"
  if command -v brew >/dev/null 2>&1; then
    brew install cocoapods
  else
    sudo gem install cocoapods
  fi
fi

echo "${GREEN}   ✓ CocoaPods: $(pod --version 2>/dev/null | head -1)${RESET}"


# ── Step 3: Detect LAN IP ──────────────────────────────────────
echo "${BOLD}${BLUE}[3/5]${RESET} Detecting LAN IP for live-reload…"

LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
if [ -z "$LAN_IP" ]; then
  LAN_IP=$(ifconfig 2>/dev/null | awk '/inet / && !/127.0.0.1/ && !/172.17/ {print $2; exit}')
fi

if [ -z "$LAN_IP" ]; then
  echo "${RED}✗ Could not detect LAN IP. Are you on WiFi?${RESET}"
  exit 1
fi

echo "${GREEN}   ✓ LAN IP: $LAN_IP${RESET}"


# ── Step 4: Patch capacitor.config.json for live-reload ────────
echo "${BOLD}${BLUE}[4/5]${RESET} Configuring live-reload…"

# Backup the prod config (only on first run; preserve any existing).
if [ ! -f "$CAP_CFG_BAK" ]; then
  cp "$CAP_CFG" "$CAP_CFG_BAK"
  echo "${GREEN}   ✓ Backed up production config to capacitor.config.json.prod.bak${RESET}"
fi

# Use Python for clean JSON edit (jq isn't always installed).
python3 - <<PY
import json, pathlib
p = pathlib.Path("$CAP_CFG")
cfg = json.loads(p.read_text())
cfg["server"] = {
    "url":       "http://${LAN_IP}:5173",
    "cleartext": True,
    "androidScheme": cfg.get("server", {}).get("androidScheme", "https"),
}
p.write_text(json.dumps(cfg, indent=2) + "\n")
PY

echo "${GREEN}   ✓ Capacitor will load from http://${LAN_IP}:5173${RESET}"


# ── Step 5: Build, sync, open ──────────────────────────────────
echo "${BOLD}${BLUE}[5/5]${RESET} Building + syncing + opening Xcode…"

cd "$ROOT/frontend"

if [ ! -d "node_modules" ]; then
  echo "${YELLOW}   Installing npm dependencies…${RESET}"
  npm install
fi

# Even with live-reload, Capacitor's sync expects webDir to exist.
echo "   Building web bundle…"
npm run build > /tmp/micha-phone-ios-build.log 2>&1 || {
  echo "${RED}✗ npm run build failed. See /tmp/micha-phone-ios-build.log${RESET}"
  exit 1
}

echo "   Running cap sync ios (this runs pod install — slow first time)…"
npx cap sync ios

# Open Xcode.
echo "${GREEN}✓ Opening Xcode…${RESET}"
npx cap open ios


# ── Final instructions ─────────────────────────────────────────
cat <<EOF

${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}
${BOLD}Next steps in Xcode${RESET}
${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}

1. ${BOLD}Before Run:${RESET} make sure the dev server is running.
   In another terminal:

     ${BOLD}make phone${RESET}

2. ${BOLD}Pick a target${RESET} from the toolbar dropdown:
   • iPhone 15 Simulator (no setup needed)
   • Your iPhone (plug in via USB → enable Developer Mode in
     Settings → Privacy & Security)

3. ${BOLD}Signing (real device only)${RESET}:
   • Click "App" in the left sidebar → Signing & Capabilities
   • Team: select yours (free Apple ID works for personal testing)
   • Bundle identifier: leave as ao.micha.express
   • On the iPhone after first install: trust the developer cert
     under Settings → General → VPN & Device Management

4. ${BOLD}Press ▶ (or Cmd+R)${RESET} to build + run.

5. The app launches and connects to the Vite dev server at
   ${GREEN}http://${LAN_IP}:5173${RESET}. Edit code → save → see changes
   live on your phone.

${BOLD}When done with dev:${RESET}
${BOLD}  ./scripts/dev-phone-ios.sh --reset${RESET}
…reverts capacitor.config.json to production-safe (no server.url).

${YELLOW}⚠  Production builds MUST have server.url removed, otherwise
   App Store review rejects + users can't open the app offline.${RESET}

EOF
