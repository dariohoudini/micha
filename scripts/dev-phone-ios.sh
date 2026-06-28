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


# ── Helpers ────────────────────────────────────────────────────
# Detect the current LAN IPv4 (WiFi preferred). Echo to stdout, or
# echo nothing on failure — caller checks for emptiness.
detect_lan_ip() {
  local ip=""
  if command -v ipconfig >/dev/null 2>&1; then
    ip=$(ipconfig getifaddr en0 2>/dev/null || true)
    [ -n "$ip" ] && { echo "$ip"; return; }
    ip=$(ipconfig getifaddr en1 2>/dev/null || true)
    [ -n "$ip" ] && { echo "$ip"; return; }
  fi
  ifconfig 2>/dev/null \
    | awk '/inet / && !/127.0.0.1/ && !/172.17/ {print $2; exit}'
}

# Write server.url into capacitor.config.json. Idempotent — does
# nothing if the URL already matches the requested IP. Returns 0 on
# unchanged, 1 on rewritten (so callers can decide whether to sync).
patch_capacitor_url() {
  local ip="$1"
  python3 - "$CAP_CFG" "$ip" <<'PY'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
target = f"http://{sys.argv[2]}:5173"
cfg = json.loads(path.read_text())
server = cfg.get("server", {})
if server.get("url") == target:
    sys.exit(0)
server["url"] = target
server["cleartext"] = True
server.setdefault("androidScheme", "https")
cfg["server"] = server
path.write_text(json.dumps(cfg, indent=2) + "\n")
sys.exit(1)
PY
}


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


# ── Subcommand: --refresh updates the LAN IP + syncs, no Xcode ──
# Use after switching WiFi / waking from sleep when the simulator or
# device suddenly loads a blank page because capacitor.config.json
# still points at the old IP. Cheap: no CocoaPods, no Xcode reopen,
# no npm rebuild — just IP detect → JSON patch → cap sync ios.
if [ "$1" = "--refresh" ]; then
  LAN_IP=$(detect_lan_ip)
  if [ -z "$LAN_IP" ]; then
    echo "${RED}✗ Could not detect LAN IP. Are you on WiFi?${RESET}"
    exit 1
  fi
  # Backup before first mutation, same as the full setup path.
  if [ ! -f "$CAP_CFG_BAK" ]; then
    cp "$CAP_CFG" "$CAP_CFG_BAK"
  fi
  if patch_capacitor_url "$LAN_IP"; then
    echo "${GREEN}✓ Capacitor already pointed at http://${LAN_IP}:5173 — nothing to do.${RESET}"
    exit 0
  fi
  echo "${GREEN}✓ Capacitor server.url → http://${LAN_IP}:5173${RESET}"
  cd "$ROOT/frontend"
  npx cap sync ios | tail -5
  echo ""
  echo "${BOLD}Now in Xcode: Cmd+R to relaunch the app.${RESET}"
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

LAN_IP=$(detect_lan_ip)
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

patch_capacitor_url "$LAN_IP" || true  # rewrites if needed; exit code is info-only here

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
