# 🐳 Zomo Multi-Bot — Docker Edition

Scalable Zoom meeting participant bots using Playwright + headless Chromium inside Docker containers. Each container runs an independent browser instance that joins via the Zoom Web Client.

## Quick Start

### 1. Configure

```bash
# Copy and edit the env file
cp .env.example .env

# Set your actual meeting URL
# Edit MEETING_URL in .env
```

### 2. Build

```bash
docker compose build
```

### 3. Run — Single Bot

```bash
docker compose up
```

### 4. Run — Multiple Bots (Scale!)

```bash
# Spin up 5 bots simultaneously
docker compose up --scale bot=5

# Spin up 10 bots
docker compose up --scale bot=10
```

### 5. Run with Custom Names

```bash
# Run individual bots with custom names
docker compose run -e BOT_NAME="Alice" bot
docker compose run -e BOT_NAME="Bob" bot
docker compose run -e BOT_NAME="Charlie" bot
```

### 6. Stop All

```bash
docker compose down
```

## Configuration

All settings can be configured via environment variables in `.env` or passed directly:

| Variable | Default | Description |
|----------|---------|-------------|
| `MEETING_URL` | _(required)_ | Zoom meeting join link |
| `BOT_NAME` | `Participant` | Display name (auto-suffixed when scaled) |
| `CHAT_INTERVAL_MIN` | `15` | Min seconds between chat messages |
| `CHAT_INTERVAL_MAX` | `45` | Max seconds between chat messages |
| `CHAT_MESSAGES` | _(10 defaults)_ | JSON array of messages to randomly send |
| `HEADLESS` | `true` | Run browser headless (set `false` to debug) |
| `MOCK_VIDEO` | `/app/mock_face.y4m` | Path to fake webcam video file |
| `BOT_TIMEOUT` | `3600` | Auto-exit after N seconds (default: 1 hour) |

## How It Works

1. Each Docker container launches a headless Chromium browser via Playwright
2. Navigates to the Zoom Web Client join URL (`/wc/join/...`)
3. Fills in the bot name, accepts terms, clicks Join
4. Handles audio/video permission prompts using Chrome's fake media flags
5. Periodically opens the chat panel and types random messages with human-like delays
6. Monitors for meeting-end signals and exits gracefully

## Mock Video

The Dockerfile automatically generates a synthetic Y4M video at build time. Chrome uses this as the fake webcam feed via `--use-file-for-fake-video-capture`.

To use your own video:
```bash
# Convert any video to Y4M format
ffmpeg -i your_face.mp4 -pix_fmt yuv420p -s 640x480 -r 15 mock_face.y4m

# Mount it into the container
docker compose run -v ./my_video.y4m:/app/mock_face.y4m bot
```

## Resource Usage

Each bot container uses approximately:
- **RAM**: 400-800 MB (headless Chromium)
- **CPU**: 0.3-0.8 cores

Plan your scaling accordingly. For 10 bots, ensure ~8 GB RAM and 4+ CPU cores available.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot clicks wrong elements | Zoom frequently updates their web UI. Check selectors in `zoom_web_bot.py` |
| Container crashes immediately | Increase `shm_size` in `docker-compose.yml` (Chromium needs shared memory) |
| Meeting URL not working | Ensure you use the full URL with password: `https://zoom.us/j/ID?pwd=PWD` |
| Bots not chatting | Chat panel selectors may have changed. Run with `HEADLESS=false` to debug |
