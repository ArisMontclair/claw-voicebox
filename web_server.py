#!/usr/bin/env python3
"""
Claw Voicebox — Web UI Server

Serves a browser-based voice interface for OpenClaw agents.
Uses WebRTC for audio capture, WebSocket for real-time communication.
"""

import asyncio
import json
import logging
import os
import tempfile
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

load_dotenv()

# ── Config ─────────────────────────────────────────────────
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))
OPENCLAW_GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "")
OPENCLAW_AGENT_ID = os.getenv("OPENCLAW_AGENT_ID", "main")
STT_PROVIDER = os.getenv("STT_PROVIDER", "whisper")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-3")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge")
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")
TTS_LANG = os.getenv("TTS_LANG", "en-US")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
DEEPGRAM_TTS_VOICE = os.getenv("DEEPGRAM_TTS_VOICE", "aura-asteria-en")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("claw-voicebox")

app = FastAPI(title="Claw Voicebox", version="1.0.0")

# ── STT Engine (loaded once) ──────────────────────────────
stt_model = None

def load_stt():
    global stt_model
    if STT_PROVIDER == "whisper":
        import whisper
        log.info(f"Loading Whisper model: {WHISPER_MODEL}")
        stt_model = whisper.load_model(WHISPER_MODEL)
        log.info("Whisper loaded.")

def transcribe(audio_path: str) -> str:
    if STT_PROVIDER == "whisper":
        result = stt_model.transcribe(audio_path, language=WHISPER_LANGUAGE)
        return result["text"].strip()
    elif STT_PROVIDER == "deepgram":
        import requests
        with open(audio_path, "rb") as f:
            resp = requests.post(
                f"https://api.deepgram.com/v1/listen?model={DEEPGRAM_MODEL}&punctuate=true",
                headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
                data=f,
            )
            resp.raise_for_status()
            return resp.json()["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    return ""

# ── TTS Engine ─────────────────────────────────────────────
async def synthesize(text: str, output_path: str):
    if TTS_PROVIDER == "edge":
        import edge_tts
        communicate = edge_tts.Communicate(text, TTS_VOICE, lang=TTS_LANG)
        await communicate.save(output_path)
    elif TTS_PROVIDER == "deepgram":
        import requests
        resp = requests.post(
            f"https://api.deepgram.com/v1/speak?model={DEEPGRAM_TTS_VOICE}",
            headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
            json={"text": text},
        )
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
    elif TTS_PROVIDER == "elevenlabs":
        import requests
        resp = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/stream",
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            json={"text": text, "model_id": "eleven_multilingual_v2"},
        )
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024):
                f.write(chunk)

# ── OpenClaw Client ────────────────────────────────────────
async def ask_openclaw(text: str) -> str:
    import websockets
    ws_url = OPENCLAW_GATEWAY_URL.replace("http", "ws").rstrip("/") + "/ws"

    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"type": "connect", "auth": {"token": OPENCLAW_TOKEN}}))
        auth = json.loads(await ws.recv())
        if not auth.get("ok"):
            raise ConnectionError(f"Auth failed: {auth}")

        await ws.send(json.dumps({
            "type": "agent.turn",
            "agentId": OPENCLAW_AGENT_ID,
            "message": text,
            "sessionTarget": "isolated",
        }))

        response = ""
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("type") == "agent.chunk":
                response += msg.get("content", "")
            elif msg.get("type") == "agent.done":
                break
            elif msg.get("type") == "error":
                raise RuntimeError(msg.get("message"))
        return response.strip()

# ── Routes ─────────────────────────────────────────────────
@app.get("/")
async def index():
    return HTMLResponse(content=WEB_UI_HTML)

@app.get("/health")
async def health():
    return {"status": "ok", "stt": STT_PROVIDER, "tts": TTS_PROVIDER}

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("Client connected")

    try:
        while True:
            # Receive audio data from browser
            data = await ws.receive_bytes()

            # Save to temp file
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(data)
                audio_path = f.name

            try:
                # Convert to WAV for STT
                wav_path = audio_path.replace(".webm", ".wav")
                os.system(f"ffmpeg -y -i {audio_path} -ar 16000 -ac 1 {wav_path} 2>/dev/null")

                if not os.path.exists(wav_path) or os.path.getsize(wav_path) < 1000:
                    await ws.send_json({"type": "error", "message": "Audio too short"})
                    continue

                # STT
                await ws.send_json({"type": "status", "message": "Transcribing..."})
                text = transcribe(wav_path)
                if not text:
                    await ws.send_json({"type": "error", "message": "No speech detected"})
                    continue
                await ws.send_json({"type": "transcript", "text": text})

                # OpenClaw
                await ws.send_json({"type": "status", "message": "Thinking..."})
                response = await ask_openclaw(text)
                if not response or response == "NO_REPLY":
                    await ws.send_json({"type": "error", "message": "No response"})
                    continue
                await ws.send_json({"type": "response", "text": response})

                # TTS
                await ws.send_json({"type": "status", "message": "Speaking..."})
                tts_path = audio_path.replace(".webm", "_response.mp3")
                await synthesize(response, tts_path)

                # Send audio back
                with open(tts_path, "rb") as f:
                    await ws.send_bytes(f.read())

                await ws.send_json({"type": "done"})

            finally:
                # Cleanup
                for p in [audio_path, wav_path, tts_path]:
                    try:
                        os.unlink(p)
                    except:
                        pass

    except WebSocketDisconnect:
        log.info("Client disconnected")
    except Exception as e:
        log.error(f"Error: {e}")
        await ws.close()

# ── Web UI HTML ────────────────────────────────────────────
WEB_UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🗣️ Claw Voicebox</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
    color: #eee;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
  }
  .container { text-align: center; max-width: 600px; padding: 2rem; }
  h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }
  .subtitle { color: #888; margin-bottom: 2rem; }
  .mic-btn {
    width: 120px; height: 120px;
    border-radius: 50%;
    border: 4px solid #e94560;
    background: rgba(233, 69, 96, 0.1);
    color: #e94560;
    font-size: 3rem;
    cursor: pointer;
    transition: all 0.2s;
    margin: 2rem 0;
  }
  .mic-btn:hover { background: rgba(233, 69, 96, 0.2); transform: scale(1.05); }
  .mic-btn.recording {
    background: #e94560;
    color: white;
    animation: pulse 1.5s infinite;
  }
  @keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(233, 69, 96, 0.4); }
    50% { box-shadow: 0 0 0 20px rgba(233, 69, 96, 0); }
  }
  .status { font-size: 1.1rem; color: #aaa; min-height: 2rem; margin: 1rem 0; }
  .transcript {
    background: rgba(255,255,255,0.05);
    border-radius: 12px;
    padding: 1.5rem;
    margin: 1rem 0;
    text-align: left;
    min-height: 80px;
  }
  .transcript .label { font-size: 0.8rem; color: #666; text-transform: uppercase; margin-bottom: 0.5rem; }
  .transcript .you { color: #4fc3f7; }
  .transcript .aris { color: #e94560; }
  .log { font-size: 0.85rem; color: #555; margin-top: 1rem; }
  .connected { color: #4caf50; }
  .disconnected { color: #f44336; }
</style>
</head>
<body>
<div class="container">
  <h1>🗣️ Claw Voicebox</h1>
  <p class="subtitle">Talk to your OpenClaw agent</p>

  <button class="mic-btn" id="micBtn" onclick="toggleRecording()">🎤</button>
  <div class="status" id="status">Click the microphone to start</div>

  <div class="transcript">
    <div class="label">Conversation</div>
    <div id="conversation"></div>
  </div>

  <div class="log" id="log">
    <span id="connStatus" class="disconnected">● Disconnected</span>
  </div>
</div>

<script>
let ws = null;
let mediaRecorder = null;
let isRecording = false;
let chunks = [];

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    document.getElementById('connStatus').className = 'connected';
    document.getElementById('connStatus').textContent = '● Connected';
  };

  ws.onclose = () => {
    document.getElementById('connStatus').className = 'disconnected';
    document.getElementById('connStatus').textContent = '● Disconnected';
    setTimeout(connect, 3000);
  };

  ws.onmessage = (event) => {
    if (typeof event.data === 'string') {
      const msg = JSON.parse(event.data);

      if (msg.type === 'status') {
        document.getElementById('status').textContent = msg.message;
      }
      else if (msg.type === 'transcript') {
        addConversation('you', `You: ${msg.text}`);
      }
      else if (msg.type === 'response') {
        addConversation('aris', `🦞 ${msg.text}`);
      }
      else if (msg.type === 'error') {
        document.getElementById('status').textContent = msg.message;
      }
      else if (msg.type === 'done') {
        document.getElementById('status').textContent = 'Click the microphone to start';
      }
    } else {
      // Audio response — play it
      const blob = new Blob([event.data], { type: 'audio/mp3' });
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play();
    }
  };
}

function addConversation(cls, text) {
  const div = document.createElement('div');
  div.className = cls;
  div.textContent = text;
  div.style.marginBottom = '0.5rem';
  document.getElementById('conversation').appendChild(div);
}

async function toggleRecording() {
  const btn = document.getElementById('micBtn');

  if (!isRecording) {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
    chunks = [];

    mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
    mediaRecorder.onstop = () => {
      const blob = new Blob(chunks, { type: 'audio/webm' });
      if (ws && ws.readyState === WebSocket.OPEN) {
        blob.arrayBuffer().then(buf => ws.send(buf));
      }
      stream.getTracks().forEach(t => t.stop());
    };

    mediaRecorder.start();
    isRecording = true;
    btn.classList.add('recording');
    btn.textContent = '⏹️';
    document.getElementById('status').textContent = 'Listening... (click to stop)';
  } else {
    mediaRecorder.stop();
    isRecording = false;
    btn.classList.remove('recording');
    btn.textContent = '🎤';
    document.getElementById('status').textContent = 'Processing...';
  }
}

connect();
</script>
</body>
</html>"""

# ── Startup ────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    load_stt()

if __name__ == "__main__":
    log.info(f"Starting Claw Voicebox on {HOST}:{PORT}")
    log.info(f"  STT: {STT_PROVIDER}")
    log.info(f"  TTS: {TTS_PROVIDER}")
    log.info(f"  OpenClaw: {OPENCLAW_GATEWAY_URL}")
    uvicorn.run(app, host=HOST, port=PORT)
