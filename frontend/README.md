# MICHA Express — Frontend

React + Vite mobile-first frontend for the MICHA Express marketplace.

## Stack
- **React 18** — UI library
- **Vite** — Dev server & bundler
- **Tailwind CSS** — Utility-first styling
- **React Router v6** — Client-side routing
- **Axios** — HTTP client with JWT interceptors
- **Capacitor** — Native iOS/Android packaging

## Folder Structure
```
src/
├── api/            # All Django API calls (auth, products, orders)
├── components/
│   ├── shared/     # Button, Input, BottomNav, LoadingSpinner
│   ├── onboarding/ # Splash, Welcome slides, OTP components
│   ├── buyer/      # Product cards, Feed, Cart items
│   └── seller/     # Seller dashboard components
├── context/        # AuthContext, CartContext
├── hooks/          # useApi, useCart, custom hooks
├── pages/          # One file per screen
└── styles/         # index.css (global + Tailwind)
```

## Getting Started
```bash
npm install
npm run dev
```

## Environment
Copy `.env.example` to `.env` and set:
```
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

## Build for Mobile
```bash
npm run build
npx cap sync
npx cap open android   # or ios
```

## Brand
- **Primary:** `#C9A84C` (Gold)
- **Background:** `#0A0A0A` (Black)
- **Surface:** `#141414`
- **Card:** `#1E1E1E`
- **Headings:** Playfair Display
- **Body:** DM Sans
