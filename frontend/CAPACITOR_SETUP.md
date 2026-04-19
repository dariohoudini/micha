# MICHA Express — Capacitor Mobile Build

## Prerequisites
- Node 18+ ✅
- Android Studio (for Android)
- Xcode 14+ (for iOS, Mac only)

## First-time setup

### 1. Install Capacitor plugins
```bash
cd /Users/azemua/MICHA/frontend
npm install @capacitor/splash-screen @capacitor/status-bar @capacitor/keyboard
```

### 2. Build the web app
```bash
npm run build
```

### 3. Add Android platform
```bash
npx cap add android
npx cap sync
```

### 4. Add iOS platform (Mac only)
```bash
npx cap add ios
npx cap sync
```

### 5. Open in Android Studio
```bash
npx cap open android
```
Then press Run (▶) to launch on a connected device or emulator.

### 6. Open in Xcode (Mac only)
```bash
npx cap open ios
```
Then press Run in Xcode.

---

## Daily dev workflow

```bash
# After making frontend changes:
npm run build
npx cap sync

# Then run from Android Studio or Xcode
```

## Live reload during development (optional)
```bash
# In vite.config.js, temporarily add:
# server: { host: '0.0.0.0' }

# Then in capacitor.config.json, temporarily add:
# "server": { "url": "http://YOUR_MAC_IP:5173", "cleartext": true }

npm run dev
npx cap run android --livereload
```

---

## Production build checklist
- [ ] Set `VITE_API_BASE_URL` to production Django URL
- [ ] Remove `webContentsDebuggingEnabled: true` from capacitor.config.json
- [ ] Add app icons to `android/app/src/main/res/` and `ios/App/App/Assets.xcassets/`
- [ ] Add splash screen image
- [ ] Sign APK with release keystore
- [ ] Test on real devices (Android 8+ and iOS 14+)
