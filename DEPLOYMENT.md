# Inscrona Deployment Guide

## Quick Start (Local)

### Prerequisites
- Python 3.10+
- Ollama running at `http://127.0.0.1:11434`
- Models: `ollama pull glm-ocr` and `ollama pull llama3.2:3b`

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Start Server
```bash
python start.py
```
Server runs at `http://localhost:8000/`

### 3. Access Web UI
Open `http://localhost:8000/` in browser

---

## Mobile App (iOS/Android)

### Build
```bash
cd mobile
npm install
eas build --profile preview --platform all
```

### Install
- **Android**: Install `.apk` from EAS build
- **iOS**: Install via TestFlight

### Pair with Backend
1. Run `python start.py` on laptop
2. Open mobile app → "Pair with Backend"
3. Scan QR code from terminal

---

## Remote Access (Tunnel)

### Option 1: Pinggy (Recommended)
```bash
ssh -p 443 -R0:localhost:8000 free.pinggy.io
```
Copy the `https://xxx.free.pinggy.net` URL

### Option 2: Cloudflare Tunnel
```bash
cloudflared tunnel --url http://localhost:8000
```

### Option 3: LocalTunnel
```bash
npx localtunnel --port 8000
```

---

## Colab Fallback (Cloud GPU)

For machines without GPU or when local Ollama is unavailable:

1. Open `Inscrona_Colab_Remote_Inference.ipynb` in Google Colab
2. Runtime → Change runtime type → GPU (T4)
3. Add ngrok token (from https://dashboard.ngrok.com)
4. Run all cells
4. Copy ngrok URL and set in local `.env`:
   ```bash
   COLAB_INFERENCE_URL=https://xxxx.ngrok-free.app
   ```
5. Restart local server: `python start.py`

The backend will automatically fallback to Colab when local Ollama fails.

---

## Environment Variables

Create `.env` file:
```bash
# Sentry (optional)
SENTRY_DSN=https://xxx@o4511881652076544.ingest.de.sentry.io/4512032347717712
ENVIRONMENT=production

# Colab Fallback (optional)
COLAB_INFERENCE_URL=https://xxxx.ngrok-free.app

# Ollama
OLLAMA_URL=http://127.0.0.1:11434
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/` | GET | Web UI |
| `/grade` | POST | Grade image (multipart: file + rubric) |
| `/results` | GET | List all graded submissions |
| `/results/{id}` | GET | Get specific result |
| `/results/export.csv` | GET | Export all grades as CSV |
| `/ws/progress` | WS | Real-time grading progress |
| `/api/pair` | GET | Mobile pairing token |
| `/api/health` | GET | Mobile health check |
| `/api/grade` | POST | Mobile grading (authenticated) |

---

## Mobile API (Authenticated)

All mobile endpoints require `Authorization: Bearer <token>`

```bash
# Pair
curl -X GET "https://xxx.pinggy.link/api/pair" -H "Authorization: Bearer <token>"

# Grade
curl -X POST "https://xxx.pinggy.link/api/grade" \
  -H "Authorization: Bearer <token>" \
  -F "file=@answer_sheet.jpg" \
  -F "rubric=Rate 0-10 for accuracy"
```

---

## Verification Checklist

- [ ] `python start.py --check-only` passes (5/5 checks)
- [ ] `curl http://localhost:8000/health` returns `{"status":"ok"}`
- [ ] `curl http://localhost:8000/` returns HTML (200)
- [ ] `curl -X POST .../grade` with test image returns 200 + JSON
- [ ] `ollama ps` shows empty after grading (models unload)
- [ ] Web UI loads at `http://localhost:8000/`
- [ ] Mobile app pairs via QR code
- [ ] Mobile app uploads photo → shows progress → displays result
- [ ] `/results` shows history
- [ ] `/results/export.csv` downloads CSV

---

## Project Structure

```
Inscrona/
├── main.py                 # FastAPI backend
├── start.py                # Launcher with pre-flight checks
├── requirements.txt        # Python dependencies
├── templates/index.html    # Web UI (Notion design)
├── uploads/                # Uploaded images (gitignored)
├── results/                # Grade results JSON (gitignored)
├── mobile/                 # Expo React Native app
│   ├── app/                # Expo Router screens
│   ├── src/                # API, stores, components
│   ├── eas.json            # EAS Build config
│   └── README.md           # Mobile setup guide
├── Inscrona_Colab_Remote_Inference.ipynb  # Colab fallback
├── test_pipeline.py        # Test suite
├── tunnel.py               # Pinggy tunnel script
├── README.md               # Main documentation
├── TASKS.md                # Task tracker (12/12 complete)
├── PROGRESS.md             # Detailed progress log
├── DEPLOYMENT.md           # This file
└── .gitignore
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Ollama connection refused | `ollama serve` |
| Model not found | `ollama pull glm-ocr && ollama pull llama3.2:3b` |
| Port 8000 in use | Kill existing: `taskkill /F /IM uvicorn.exe` |
| HEIC not supported | Install `pillow-heif` (in requirements) |
| Image too large | Auto-resizes to 2000px max edge |
| Models don't unload | Check `keep_alive=0` in Ollama calls |
| Tunnel DNS fails | Use `run.pinggy-free.link` URL, or try Cloudflare |
| Colab fallback not working | Check `COLAB_INFERENCE_URL` in `.env`, verify ngrok tunnel |

---

## Architecture

```
┌─────────────────┐     HTTPS      ┌──────────────────┐
│  Mobile App     │ ◀────────────▶ │  FastAPI Backend │
│  (Expo RN)      │  Pair + Grade  │  (Python)        │
└─────────────────┘                └────────┬─────────┘
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼
             ┌─────────────┐         ┌─────────────┐         ┌─────────────┐
             │  GLM-OCR    │         │ Llama 3.2:3B│         │  Colab      │
             │  (Ollama)   │         │  (Ollama)   │         │  Fallback   │
             └─────────────┘         └─────────────┘         └─────────────┘
                   │                       │                       │
                   └───────────────────────┼───────────────────────┘
                                           ▼
                                    ┌─────────────┐
                                    │  Local FS   │
                                    │ uploads/    │
                                    │ results/    │
                                    └─────────────┘
```

---

## Next Steps (Post-MVP)

1. **PP-DocLayout** - Question detection for structured grading
2. **Two-pass GLM-OCR** - Retry weak pages with high-accuracy prompt
3. **BGE-M3 + Reranker** - Ensemble grading for higher accuracy
4. **Auth + Multi-tenant** - Teacher accounts, class management
5. **Push Notifications** - Grade complete alerts
6. **Background Sync** - True offline support with expo-background-fetch