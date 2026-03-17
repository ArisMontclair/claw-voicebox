# 🎙️ Voice Pipeline

**STT → OpenClaw → TTS** — A Dockerized voice interface for OpenClaw.

Speak to it, it transcribes your voice, sends it to OpenClaw for processing, and speaks the response aloud.

## Quick Start

```bash
# 1. Clone
git clone https://github.com/ArisMontclair/voice-pipeline.git
cd voice-pipeline

# 2. Configure
cp .env.example .env
# Edit .env with your OpenClaw gateway URL and token

# 3. Run
docker compose up --build
```

## How It Works

```
┌─────────┐     ┌───────┐     ┌──────────┐     ┌─────┐
│  Micro  │ ──► │  STT  │ ──► │ OpenClaw │ ──► │ TTS │ ──► Speaker
│  phone  │     │Whisper│     │  Gateway  │     │Edge │
└─────────┘     └───────┘     └──────────┘     └─────┘
```

1. **Listen** — Records audio until silence detected
2. **Transcribe** — Converts speech to text (Whisper or remote STT)
3. **Process** — Sends text to OpenClaw agent for a response
4. **Speak** — Converts response to speech (Edge TTS or custom)

## Configuration

All settings via `.env` file:

| Variable | Default | Description |
|---|---|---|
| `STT_PROVIDER` | `whisper` | `whisper` (local) or `custom` (remote) |
| `WHISPER_MODEL` | `small` | Whisper model size: tiny/base/small/medium/large |
| `OPENCLAW_GATEWAY_URL` | `ws://localhost:18789` | OpenClaw gateway WebSocket URL |
| `OPENCLAW_TOKEN` | — | Gateway auth token |
| `TTS_PROVIDER` | `edge` | `edge` (free, no key) or `custom` (remote) |
| `TTS_VOICE` | `en-US-GuyNeural` | Edge TTS voice name |
| `PIPELINE_MODE` | `stream` | `stream` (continuous) or `file` (single file) |
| `SILENCE_THRESHOLD_MS` | `1500` | Silence duration before processing |

## Running Modes

### Continuous (default)
```bash
docker compose up
# Listens continuously, processes each utterance
```

### Single file
```bash
docker compose run voice-pipeline python pipeline.py /path/to/audio.wav
```

## Without Docker

```bash
pip install -r requirements.txt
cp .env.example .env
python pipeline.py          # stream mode
python pipeline.py audio.wav # file mode
```

## Requirements

- Python 3.12+
- FFmpeg
- PortAudio (for microphone input)
- Docker + Docker Compose (for containerized)

## License

MIT
