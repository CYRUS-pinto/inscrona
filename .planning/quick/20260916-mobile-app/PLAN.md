---
title: "Inscrona Mobile App - Teacher Edition"
slug: "20260916-mobile-app"
status: "complete"
created: "2026-09-16"
completed: "2026-09-16"
target: "Deployable iOS/Android app for teachers with QR pairing to local FastAPI backend"
---

# Inscrona Mobile App - Teacher Edition

## Objective
Build a production-ready Expo React Native app that teachers can install on iOS/Android, pair with their local Inscrona FastAPI backend via QR code, photograph answer sheets, and view grades — all working offline-first with background sync.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     MOBILE APP (Expo + React Native)            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Camera    │  │   Offline   │  │   Pairing   │             │
│  │   Screen    │  │   Queue     │  │   (QR/Code) │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                    │
│         ▼                ▼                ▼                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              React Query + AsyncStorage                 │   │
│  │  • Mutations: upload, grade, sync                       │   │
│  │  • Queries: history, results, settings                  │   │
│  │  • Persist: pending uploads, paired backend URL         │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS (Pinggy tunnel or LAN)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                   FASTAPI BACKEND (Local)                       │
│  • POST /api/grade  (multipart: image + rubric)                 │
│  • GET  /api/health                                             │
│  • GET  /api/pair   (returns pairing token + QR)                │
│  • WebSocket /ws/progress (real-time grading progress)          │
└─────────────────────────────────────────────────────────────────┘
```

## Teacher Workflow

1. **Install app** → Open → "Pair with Backend"
2. **Teacher runs** `python start.py` on laptop → sees QR code in terminal + `http://localhost:8000/pair`
3. **Teacher scans QR** with phone app → app stores backend URL + token
4. **Teacher photographs** answer sheet (camera roll or live camera)
5. **App uploads** → shows real-time progress (OCR → grading) → displays result
6. **Works offline** → queues uploads → auto-syncs when backend reachable

## Tech Stack

| Layer | Choice | Reason |
|-------|--------|--------|
| Framework | Expo SDK 51 + React Native 0.76 | Mature, EAS builds, native modules |
| Navigation | Expo Router (file-based) | Type-safe, deep linking for QR |
| State/Data | TanStack Query + AsyncStorage | Offline mutations, background sync |
| Camera | expo-camera + expo-image-picker | Permission handling, HEIC support |
| QR | expo-barcode-scanner + qrcode.react | Scan pairing QR, display pairing QR |
| Styling | NativeWind (Tailwind) + Stitch tokens | Consistent with web UI design system |
| Build | EAS Build (free tier) | iOS/Android binaries, no Xcode/Android Studio needed |
| Observability | Sentry (expo-sentry) | Crash reporting, performance |

## Screens

| Screen | Route | Purpose |
|--------|-------|---------|
| Pairing | `/` (root) | Scan QR or enter code to connect backend |
| Camera | `/camera` | Live camera + gallery picker |
| Review | `/review/[id]` | Preview image, edit rubric, confirm upload |
| Processing | `/processing/[id]` | Real-time progress: OCR → Grade → Done |
| Result | `/result/[id]` | Marks, confidence, feedback, OCR transcript |
| History | `/history` | List past grades, filter, export CSV |
| Settings | `/settings` | Backend URL, auto-sync, notifications, about |

## Offline-First Design

- **AsyncStorage** persists: `backendUrl`, `pairingToken`, `pendingUploads[]`
- **React Query mutations** with `persistQueryClient` → auto-retry on reconnect
- **Background sync** via `expo-task-manager` + `expo-background-fetch`
- **Visual indicators**: pending badge, sync status in header

## Pairing Protocol

```
1. Backend generates: { url: "https://xxx.pinggy.link", token: "abc123", expires: "24h" }
2. QR encodes: inscrona://pair?url=https://xxx.pinggy.link&token=abc123
3. App scans → validates /api/health → stores → navigates to Camera
4. All requests include: Authorization: Bearer <token>
```

## Definition of Done

- [ ] Expo app builds via `eas build --platform all` (iOS + Android)
- [ ] QR pairing works end-to-end (laptop terminal → phone scan → connected)
- [ ] Camera captures HEIC/JPEG, resizes ≤2000px, uploads to `/api/grade`
- [ ] Real-time progress via WebSocket shows OCR → Grading stages
- [ ] Results display: marks, confidence pill, feedback, collapsible OCR
- [ ] History loads from local cache + backend sync
- [ ] Offline: queue uploads, auto-sync on reconnect
- [ ] Sentry captures crashes + spans
- [ ] README with teacher setup instructions (5 min)
- [ ] EAS build profiles: preview, production