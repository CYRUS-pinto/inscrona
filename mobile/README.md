# Inscrona Mobile - Teacher Grading App

Native iOS/Android app for teachers to photograph student answer sheets and get AI-graded results. Pairs with local Inscrona FastAPI backend via QR code.

## Features

- 📱 **Native iOS & Android** via Expo + EAS Build
- 🔗 **QR Code Pairing** — scan laptop terminal to connect
- 📷 **Camera + Gallery** — capture or select answer sheets (HEIC/JPEG)
- ⚡ **Real-time Progress** — WebSocket updates: Upload → OCR → Grading → Done
- 📊 **Results** — Marks, confidence pills, feedback, collapsible OCR transcript
- 📋 **History** — Local cache + backend sync, pending queue, CSV export
- 🔒 **Offline-First** — Queued uploads auto-sync when backend reachable
- 🎨 **Stitch/Notion Design** — Consistent with web UI
- 📦 **Sentry** — Crash reporting + performance monitoring

## Quick Start (Teacher)

### Prerequisites
- **Laptop**: Python 3.10+, Ollama with `glm-ocr` and `llama3.2:3b`
- **Phone**: iOS 15+ or Android 8+

### 1. Start Backend (Laptop)
```bash
cd Inscrona  # your FastAPI repo
python start.py
# Terminal shows QR code + pairing URL
```

### 2. Install App (Phone)
**Option A: EAS Build (recommended)**
```bash
cd mobile
eas build --profile preview --platform all
# Install .apk (Android) or .ipa via TestFlight (iOS)
```

**Option B: Expo Go (development)**
```bash
cd mobile
npx expo install
npx expo start
# Scan QR with Expo Go app
```

### 3. Pair & Grade
1. Open app → "Pair with Backend"
2. Scan QR code from laptop terminal
3. Tap "Camera" → photograph answer sheet
4. Edit rubric if needed → "Submit for Grading"
5. Watch real-time progress → view result

## Architecture

```
Phone (Expo RN)                    Laptop (FastAPI + Ollama)
┌─────────────────────┐            ┌─────────────────────────┐
│ Camera → Resize     │  HTTPS     │ POST /grade             │
│ (≤2000px)           │───────────▶│   ↓ GLM-OCR (keep_alive=0)│
│                     │            │   ↓ Llama 3.2:3B        │
│ WebSocket Progress  │◀───────────│   ↓ Return JSON         │
│ (OCR → Grade → OK)  │            │                         │
│ Results + History   │            │ Local FS: uploads/      │
│ Offline Queue       │            │ results/{id}_grade.json │
└─────────────────────┘            └─────────────────────────┘
```

## Project Structure

```
mobile/
├── app/
│   ├── _layout.tsx              # Root stack + providers
│   ├── index.tsx                # Pairing screen (QR scan)
│   ├── (tabs)/
│   │   ├── _layout.tsx          # Tab navigator
│   │   ├── camera.tsx           # Camera + gallery capture
│   │   ├── history.tsx          # Results list + pending queue
│   │   └── settings.tsx         # Backend URL, auto-sync, notifications
│   ├── camera.tsx               # Camera screen
│   ├── review/[id].tsx          # Review image + rubric
│   ├── processing/[id].tsx      # Real-time progress
│   └── result/[id].tsx          # Grade result + OCR transcript
├── src/
│   ├── api/client.ts            # API + WebSocket client
│   ├── store/
│   │   ├── authStore.ts         # Pairing + settings (Zustand + persist)
│   │   └── uploadStore.ts       # Offline queue + results
│   ├── components/UI/           # Button, Card, Badge, Input, Progress
│   ├── hooks/                   # Custom hooks
│   ├── types/index.ts           # TypeScript types
│   └── utils/theme.ts           # Stitch/Notion design tokens
├── assets/                      # Icons, splash screens
├── app.config.ts                # Expo config
├── eas.json                     # EAS Build profiles
└── package.json
```

## Design System (Stitch/Notion Tokens)

| Token | Light | Dark |
|-------|-------|------|
| Primary | `#5645d4` | `#5645d4` |
| Navy | `#0a1530` | `#070f24` |
| Canvas | `#ffffff` | `#0a0a0a` |
| Surface | `#f6f5f4` | `#131313` |
| Ink | `#1a1a1a` | `#ffffff` |
| Success | `#1aae39` / `#d9f3e1` | — |
| Warning | `#dd5b00` / `#ffe8d4` | — |
| Error | `#e03131` / `#ffebeb` | — |
| Radius | 8px (btn/input), 12px (card), 9999px (badge) |
| Fonts | Inter (UI), JetBrains Mono (numbers) |

## EAS Build Commands

```bash
# Preview builds (internal distribution)
eas build --profile preview --platform android  # .apk
eas build --profile preview --platform ios      # .ipa via TestFlight

# Production builds (App Store / Play Store)
eas build --profile production --platform all
eas submit --platform all
```

## Environment Variables

Create `.env` (not committed):
```bash
# Sentry (optional)
EXPO_PUBLIC_SENTRY_DSN=https://xxx@o123.ingest.sentry.io/456

# Backend (set via pairing, not env)
# BACKEND_URL=https://xxx.pinggy.link
# PAIRING_TOKEN=abc123
```

## Offline Behavior

- Pending uploads stored in `AsyncStorage` with image URI + rubric
- Background sync every 30s when app foregrounded
- Manual retry for failed uploads (max 3 retries)
- Visual badges show pending count in tab bar

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Camera permission denied | Settings → App → Camera → Allow |
| QR scan not working | Ensure laptop terminal shows QR; good lighting |
| Backend connection failed | Check Pinggy tunnel running; same network or public URL |
| Upload stuck | Check Ollama running; `ollama ps` should be empty |
| Build fails | `eas build --clear-cache` |

## License

MIT — Built for teachers, powered by local AI.