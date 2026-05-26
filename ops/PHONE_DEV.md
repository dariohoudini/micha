# Phone development — try MICHA on your phone

Three ways to do this, ordered by setup time.

---

## Option A — Mobile browser over WiFi (fastest, ~2 min)

You'll see the app in your phone's browser. Hot-reload works.

### Requirements
- Dev machine and phone on the **same WiFi network**
- Python venv created (`python3 -m venv venv && ./venv/bin/pip install -r requirements.txt`)
- Node modules installed (`cd frontend && npm install`)
- WiFi without "client isolation" (most home routers OK; many guest networks block phone↔laptop traffic)

### One command

```bash
make phone
```

This launches:
1. Django backend bound to `0.0.0.0:8000` with `ALLOWED_HOSTS` extended to your LAN IP
2. Vite dev server bound to `0.0.0.0:5173` with `/api` proxied to Django
3. Prints your LAN URL

You'll see something like:

```
Your dev machine LAN IP: 172.30.20.78

On your phone (same WiFi network), open:

    http://172.30.20.78:5173/
```

Type that URL into Safari / Chrome on your phone. Bookmark it.

**Press `Ctrl+C` once** to stop both servers cleanly.

### Troubleshooting

| Symptom | Fix |
|---|---|
| "Cannot connect" on phone | Confirm both devices on same WiFi. Disable VPN. Some routers block AP-isolation; try iPhone hotspot from another phone. |
| "Disallowed Host" Django error | The script auto-adds your LAN IP to ALLOWED_HOSTS. If you connected to a different WiFi (different IP), re-run `make phone`. |
| Hot reload doesn't trigger on phone | Pull-to-refresh once; the WebSocket reconnects. |
| Backend 502 from frontend | Backend probably crashed. Check `/tmp/micha-phone-dev-backend.log`. |
| Phone IP detection wrong | Set manually: `LAN_IP=192.168.1.42 ./scripts/dev-phone.sh` — feature in roadmap, for now edit script. |
| Multicaixa / FCM not working | These need real PSP credentials. UI works fine; payments will fail with PSP unavailable. Expected in dev. |

### Logging in

In dev the backend runs against SQLite by default. There are no preseeded users.
- Open `/register` on your phone → create an account
- OR run `./venv/bin/python manage.py createsuperuser` first, log in via `/login`

The new R5-A push permission prompt only fires on native (Capacitor); browser-mode skips it. The cookie consent banner WILL appear (deferred ~1.5s after first interaction).

---

## Option B — iOS native shell (Xcode, ~15 min first time)

Build the SPA into the iOS Capacitor shell and run on an iOS simulator or real device. This is the closest to the production app store experience.

### Requirements
- macOS
- Xcode installed (App Store, ~12 GB)
- (For real device) Apple Developer account + signing identity in Xcode
- (For real device) iPhone connected by USB cable, Developer Mode enabled in iOS Settings → Privacy & Security

### Steps

```bash
make phone-ios
```

This runs:
```bash
cd frontend && npm run build && npx cap sync ios && npx cap open ios
```

Xcode opens. From the toolbar:
- Pick "**iPhone 15 Simulator**" → press ▶ Run (simulator boots, app launches)
- OR plug in your iPhone → it appears in the device picker → ▶ Run

First-run on a real device: Xcode prompts you to trust the developer certificate on the phone (Settings → General → VPN & Device Management).

### Live reload while in the native shell

To avoid re-building between code changes, edit `frontend/capacitor.config.json`:

```json
{
  "server": {
    "url": "http://<your-LAN-IP>:5173",
    "cleartext": true
  }
}
```

Run `make phone` to start the dev server, then `npx cap run ios` to launch with live reload pointing at it. **Revert before shipping** — the production app must NOT have `server.url` set.

### Push notifications + camera on simulator

Both are unavailable on iOS Simulator. Test these on a real device.

---

## Option C — Android native shell (~25 min first time)

Android project isn't yet generated in this repo. One-time setup:

### Requirements
- Android Studio installed (~5 GB)
- Java JDK 17 (`brew install --cask zulu17` on macOS)
- `ANDROID_HOME` env var pointing to your Android SDK location
- (For real device) Android phone with **USB Debugging enabled**: Settings → About → tap "Build number" 7 times → enable USB Debugging in Developer options

### One-time init

```bash
make phone-android-setup
```

This runs `npx cap add android` which generates `frontend/android/` with the native Gradle project, then `npx cap sync android` to copy the latest web bundle.

### Run

```bash
make phone-android
```

Android Studio opens. Pick a device (emulator or connected phone) → ▶ Run.

### Live reload

Same pattern as iOS — set `server.url` in `capacitor.config.json` to your LAN IP, run `make phone`, then `npx cap run android`.

---

## Production note

For real users, the SPA must hit a real backend, not a dev server. Set in `frontend/.env`:

```
VITE_API_BASE_URL=https://api.micha.ao/api
```

Then `npm run build` and deploy to nginx (see `ops/nginx/micha.conf.example`).

For Capacitor production builds, the native shell can't proxy — `VITE_API_BASE_URL` MUST be the absolute production URL.

---

## What you can explore on your phone

Once it's running:

**Buyer flow:**
- `/welcome` → onboarding
- `/register` / `/login`
- `/home` → home feed
- `/explore` → search + filters (Tier 3 F10/F11)
- `/product/<id>` → PDP with new image gallery (tap to fullscreen, pinch-zoom)
- `/cart` → empty-cart recovery, free-shipping bar, sync indicator
- `/checkout` → trust banner + "do not close app" overlay
- `/order-confirmed` → push permission prompt at peak intent
- `/orders/<id>` → ETA banner + seller mini-card

**Seller flow (after registering as seller):**
- `/seller` → dashboard
- `/seller/orders` → order action flow (one CTA per state)
- `/seller/analytics-r7` → R7 dashboard with charts

**Admin flow (after creating a superuser):**
- `/admin/command-center` → live ops widgets, 30s refresh
- `/admin/moderation` → moderator queue (keyboard A/R/E + J/K)
- `/admin/chargebacks` → chargeback workflow
- `/admin/aml` → AML alert review

The cookie consent banner slides up ~1.5s after first interaction.
