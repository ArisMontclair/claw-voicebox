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
# Edit .env with your settings (see below)

# 3. Run
docker compose up --build
```

## How It Works

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌─────────┐
│  Micro  │ ──► │   STT    │ ──► │ OpenClaw │ ──► │   TTS   │ ──► Speaker
│  phone  │     │Whisper / │     │  Gateway  │     │Edge /   │
│         │     │Deepgram  │     │          │     │Deepgram │
└─────────┘     └──────────┘     └──────────┘     └─────────┘
```

1. **Listen** — Records audio until silence detected
2. **Transcribe** — Converts speech to text
3. **Process** — Sends text to OpenClaw agent for a response
4. **Speak** — Converts response to speech

## Supported Providers

### STT (Speech-to-Text)
| Provider | Latency | Cost | Notes |
|---|---|---|---|
| **Whisper** | ~1-3s | Free (local) | Runs on CPU/GPU, no API key needed |
| **Deepgram Nova-3** | ~150-300ms | ~$0.0043/min | Fastest option, streaming partials |
| Custom endpoint | Varies | Varies | Any HTTP service |

### TTS (Text-to-Speech)
| Provider | Latency | Cost | Notes |
|---|---|---|---|
| **Edge TTS** | ~500ms | Free | No API key needed, good quality |
| **Deepgram Aura** | ~100-200ms | ~$0.004/1K chars | Fastest option |
| **ElevenLabs** | ~200-400ms | ~$0.30/1K chars | Best quality, streaming |
| Custom endpoint | Varies | Varies | Any HTTP service |

## Configuration

All settings via `.env` file. See `.env.example` for all options.

### Minimal (free, no API keys)
```env
STT_PROVIDER=whisper
TTS_PROVIDER=edge
OPENCLAW_TOKEN=your-token
```

### Fastest (Deepgram for both)
```env
STT_PROVIDER=deepgram
DEEPGRAM_API_KEY=your-key
TTS_PROVIDER=deepgram
DEEPGRAM_API_KEY=your-key
OPENCLAW_TOKEN=your-token
```

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
