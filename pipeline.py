#!/usr/bin/env python3
"""
Voice Pipeline: STT → OpenClaw → TTS

Listens for audio input, transcribes it, sends to OpenClaw for processing,
and speaks the response aloud.

Supports:
  STT: Whisper (local), Deepgram (API), custom endpoint
  TTS: Edge (free), Deepgram (API), ElevenLabs (streaming), custom endpoint
"""

import asyncio
import json
import logging
import os
import sys
import wave
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────
STT_PROVIDER = os.getenv("STT_PROVIDER", "whisper")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en")
STT_URL = os.getenv("STT_URL", "")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY", "")
DEEPGRAM_MODEL = os.getenv("DEEPGRAM_MODEL", "nova-3")

OPENCLAW_GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "")
OPENCLAW_AGENT_ID = os.getenv("OPENCLAW_AGENT_ID", "main")

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge")
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")
TTS_LANG = os.getenv("TTS_LANG", "en-US")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
DEEPGRAM_TTS_VOICE = os.getenv("DEEPGRAM_TTS_VOICE", "aura-asteria-en")
TTS_URL = os.getenv("TTS_URL", "")

AUDIO_SAMPLE_RATE = int(os.getenv("AUDIO_SAMPLE_RATE", "16000"))
AUDIO_CHANNELS = int(os.getenv("AUDIO_CHANNELS", "1"))
PIPELINE_MODE = os.getenv("PIPELINE_MODE", "stream")
SILENCE_THRESHOLD_MS = int(os.getenv("SILENCE_THRESHOLD_MS", "1500"))
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "./output")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("voice-pipeline")


# ── STT Module ─────────────────────────────────────────────
class STTEngine:
    def __init__(self):
        self.provider = STT_PROVIDER
        self.model = None

    def load(self):
        if self.provider == "whisper":
            import whisper
            log.info(f"Loading Whisper model: {WHISPER_MODEL}")
            self.model = whisper.load_model(WHISPER_MODEL)
            log.info("Whisper model loaded.")
        elif self.provider == "deepgram":
            if not DEEPGRAM_API_KEY:
                raise ValueError("DEEPGRAM_API_KEY is required for Deepgram STT")
            log.info(f"Using Deepgram STT ({DEEPGRAM_MODEL})")
        else:
            log.info(f"Using remote STT at {STT_URL}")

    def transcribe(self, audio_path: str) -> str:
        if self.provider == "whisper":
            result = self.model.transcribe(audio_path, language=WHISPER_LANGUAGE)
            return result["text"].strip()
        elif self.provider == "deepgram":
            return self._transcribe_deepgram(audio_path)
        else:
            import requests
            with open(audio_path, "rb") as f:
                resp = requests.post(STT_URL, files={"audio": f})
                resp.raise_for_status()
                return resp.json()["text"].strip()

    def _transcribe_deepgram(self, audio_path: str) -> str:
        import requests
        with open(audio_path, "rb") as f:
            resp = requests.post(
                f"https://api.deepgram.com/v1/listen?model={DEEPGRAM_MODEL}&punctuate=true",
                headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
                data=f,
                headers={"Content-Type": "audio/wav"},
            )
            resp.raise_for_status()
            result = resp.json()
            return result["results"]["channels"][0]["alternatives"][0]["transcript"].strip()


# ── OpenClaw Module ────────────────────────────────────────
class OpenClawClient:
    def __init__(self):
        self.url = OPENCLAW_GATEWAY_URL
        self.token = OPENCLAW_TOKEN
        self.agent_id = OPENCLAW_AGENT_ID

    async def send_message(self, text: str) -> str:
        """Send a message to OpenClaw and get the response."""
        ws_url = self.url.replace("http", "ws").rstrip("/") + "/ws"

        connect_msg = {
            "type": "connect",
            "auth": {"token": self.token},
        }

        agent_msg = {
            "type": "agent.turn",
            "agentId": self.agent_id,
            "message": text,
            "sessionTarget": "isolated",
        }

        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps(connect_msg))
            auth_resp = json.loads(await ws.recv())
            if not auth_resp.get("ok"):
                raise ConnectionError(f"Auth failed: {auth_resp}")

            await ws.send(json.dumps(agent_msg))

            response_text = ""
            while True:
                raw = await ws.recv()
                msg = json.loads(raw)
                if msg.get("type") == "agent.chunk":
                    response_text += msg.get("content", "")
                elif msg.get("type") == "agent.done":
                    break
                elif msg.get("type") == "error":
                    raise RuntimeError(f"OpenClaw error: {msg.get('message')}")

            return response_text.strip()


# ── TTS Module ─────────────────────────────────────────────
class TTSEngine:
    def __init__(self):
        self.provider = TTS_PROVIDER

    async def speak(self, text: str, output_path: str | None = None) -> str:
        """Synthesize text to speech. Returns path to audio file."""
        if not output_path:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            output_path = os.path.join(OUTPUT_DIR, "response.mp3")

        if self.provider == "edge":
            import edge_tts
            communicate = edge_tts.Communicate(text, TTS_VOICE, lang=TTS_LANG)
            await communicate.save(output_path)
        elif self.provider == "deepgram":
            await self._speak_deepgram(text, output_path)
        elif self.provider == "elevenlabs":
            await self._speak_elevenlabs(text, output_path)
        else:
            import requests
            resp = requests.post(TTS_URL, json={"text": text})
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)

        log.info(f"TTS saved to {output_path}")
        self._play(output_path)
        return output_path

    async def _speak_deepgram(self, text: str, output_path: str):
        import requests
        resp = requests.post(
            f"https://api.deepgram.com/v1/speak?model={DEEPGRAM_TTS_VOICE}",
            headers={"Authorization": f"Token {DEEPGRAM_API_KEY}"},
            json={"text": text},
        )
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)

    async def _speak_elevenlabs(self, text: str, output_path: str):
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

    @staticmethod
    def _play(path: str):
        for cmd in ["mpv", "ffplay -nodisp -autoexit", "aplay"]:
            try:
                os.system(f"{cmd} {path} >/dev/null 2>&1 &")
                return
            except Exception:
                continue
        log.warning("No audio player found. File saved but not played.")


# ── Audio Recorder ─────────────────────────────────────────
class AudioRecorder:
    def __init__(self):
        self.sample_rate = AUDIO_SAMPLE_RATE
        self.channels = AUDIO_CHANNELS

    def record_until_silence(self, output_path: str) -> str:
        import pyaudio
        import numpy as np

        chunk = 1024
        format = pyaudio.paInt16
        p = pyaudio.PyAudio()
        stream = p.open(
            format=format, channels=self.channels,
            rate=self.sample_rate, input=True,
            frames_per_buffer=chunk,
        )

        frames = []
        silent_chunks = 0
        silence_limit = int(SILENCE_THRESHOLD_MS / (chunk / self.sample_rate * 1000))

        log.info("Listening... (speak now)")
        try:
            while True:
                data = stream.read(chunk, exception_on_overflow=False)
                frames.append(data)
                audio_data = np.frombuffer(data, dtype=np.int16)
                volume = np.abs(audio_data).mean()
                if volume < 500:
                    silent_chunks += 1
                    if silent_chunks > silence_limit and len(frames) > 10:
                        log.info("Silence detected, processing...")
                        break
                else:
                    silent_chunks = 0
        finally:
            stream.stop_stream()
            stream.close()
            p.terminate()

        wf = wave.open(output_path, "wb")
        wf.setnchannels(self.channels)
        wf.setsampwidth(p.get_sample_size(format))
        wf.setframerate(self.sample_rate)
        wf.writeframes(b"".join(frames))
        wf.close()
        log.info(f"Audio saved to {output_path}")
        return output_path

    def record_from_file(self, file_path: str, output_path: str) -> str:
        import shutil
        shutil.copy(file_path, output_path)
        return output_path


# ── Main Pipeline ──────────────────────────────────────────
class VoicePipeline:
    def __init__(self):
        self.stt = STTEngine()
        self.openclaw = OpenClawClient()
        self.tts = TTSEngine()
        self.recorder = AudioRecorder()

    async def setup(self):
        log.info("Setting up voice pipeline...")
        self.stt.load()
        log.info("Voice pipeline ready.")

    async def process_audio(self, audio_path: str):
        log.info("Transcribing...")
        text = self.stt.transcribe(audio_path)
        if not text:
            log.info("No speech detected, skipping.")
            return
        log.info(f"Heard: {text}")

        log.info("Sending to OpenClaw...")
        response = await self.openclaw.send_message(text)
        if not response or response == "NO_REPLY":
            log.info("OpenClaw returned no response.")
            return
        log.info(f"OpenClaw: {response}")

        log.info("Speaking response...")
        await self.tts.speak(response)

    async def run_stream(self):
        await self.setup()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        while True:
            try:
                audio_path = os.path.join(OUTPUT_DIR, "input.wav")
                self.recorder.record_until_silence(audio_path)
                await self.process_audio(audio_path)
            except KeyboardInterrupt:
                log.info("Shutting down.")
                break
            except Exception as e:
                log.error(f"Pipeline error: {e}")

    async def run_file(self, file_path: str):
        await self.setup()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        audio_path = os.path.join(OUTPUT_DIR, "input.wav")
        self.recorder.record_from_file(file_path, audio_path)
        await self.process_audio(audio_path)


async def main():
    pipeline = VoicePipeline()
    if PIPELINE_MODE == "file":
        if len(sys.argv) < 2:
            print("Usage: python pipeline.py <audio_file>")
            sys.exit(1)
        await pipeline.run_file(sys.argv[1])
    else:
        await pipeline.run_stream()


if __name__ == "__main__":
    import websockets
    asyncio.run(main())
