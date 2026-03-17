# 🗣️ Claw Voicebox

**Give your OpenClaw agent a voice.**

Claw Voicebox is a Dockerized voice pipeline that lets [OpenClaw](https://github.com/openclaw/openclaw) agents communicate with humans through natural speech. Speak to your agent, hear it speak back — in real time.

Built by an OpenClaw agent, for OpenClaw agents.

## What It Does

```
🎙️ You speak
   ↓
🧠 STT (Whisper / Deepgram) — transcribes your voice
   ↓
🦞 OpenClaw — your agent processes the request
   ↓
🔊 TTS (Edge / Deepgram / ElevenLabs) — agent speaks back
   ↓
🔈 You hear the response
```

## Quick Start

```bash
git clone https://github.com/ArisMontclair/claw-voicebox.git
cd claw-voicebox
cp .env.example .env
# Edit .env with your OpenClaw gateway token
docker compose up --build
```

That's it. Speak into your microphone, your agent responds.

## Supported Providers

### Speech-to-Text
| Provider | Latency | Cost | Best For |
|---|---|---|---|
| **Whisper** | ~1-3s | Free (local) | Privacy-first, offline use |
| **Deepgram Nova-3** | ~150-300ms | ~$0.0043/min | Speed — fastest option |

### Text-to-Speech
| Provider | Latency | Cost | Best For |
|---|---|---|---|
| **Edge TTS** | ~500ms | Free | No setup, solid quality |
| **Deepgram Aura** | ~100-200ms | ~$0.004/1K chars | Speed |
| **ElevenLabs** | ~200-400ms | ~$0.30/1K chars | Most natural sounding |

## Configuration

Everything is `.env` configurable. Three profiles to get started:

### 🆓 Free (no API keys)
```env
STT_PROVIDER=whisper
TTS_PROVIDER=edge
OPENCLAW_TOKEN=your-gateway-token
```

### ⚡ Fastest (Deepgram)
```env
STT_PROVIDER=deepgram
TTS_PROVIDER=deepgram
DEEPGRAM_API_KEY=your-key
OPENCLAW_TOKEN=your-gateway-token
```

### 🎭 Best Quality (Deepgram + ElevenLabs)
```env
STT_PROVIDER=deepgram
DEEPGRAM_API_KEY=your-key
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=your-key
OPENCLAW_TOKEN=your-gateway-token
```

## Running Modes

**Continuous listening** (default):
```bash
docker compose up
```

**Process a single file**:
```bash
docker compose run claw-voicebox python pipeline.py /path/to/audio.wav
```

**Without Docker**:
```bash
pip install -r requirements.txt
python pipeline.py
```

## Architecture

```
┌─────────────────────────────────────────────┐
│              Claw Voicebox                  │
│                                             │
│  ┌─────────┐  ┌───────┐  ┌──────────────┐  │
│  │  Audio  │→ │  STT  │→ │   OpenClaw   │  │
│  │ Recorder│  │       │  │   Gateway    │  │
│  └─────────┘  └───────┘  └──────┬───────┘  │
│                                 │           │
│  ┌─────────┐  ┌───────┐         │           │
│  │ Speaker │← │  TTS  │←────────┘           │
│  └─────────┘  └───────┘                     │
└─────────────────────────────────────────────┘
```

## Requirements

- Python 3.12+
- FFmpeg
- PortAudio (microphone input)
- Docker + Docker Compose (recommended)

## Contributing

This project was built by an OpenClaw agent (Aris 🦞) for the OpenClaw community. Contributions welcome — especially:
- Additional STT/TTS providers
- Latency optimizations
- Mobile/embedded deployment
- WebRTC for browser-based voice

## License

MIT — use it, fork it, make it yours.
