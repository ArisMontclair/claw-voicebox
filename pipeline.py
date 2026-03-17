#!/usr/bin/env python3
"""
Voice Pipeline: STT → OpenClaw → TTS

Listens for audio input, transcribes it, sends to OpenClaw for processing,
and speaks the response aloud.
"""

import asyncio
import json
import logging
import os
import sys
import tempfile
import wave
from pathlib import Path

import edge_tts
import websockets
from dotenv import load_dotenv

load_dotenv()

# ── Config ─────────────────────────────────────────────────
STT_PROVIDER = os.getenv("STT_PROVIDER", "whisper")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "en")
STT_URL = os.getenv("STT_URL", "")

OPENCLAW_GATEWAY_URL = os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789")
OPENCLAW_TOKEN = os.getenv("OPENCLAW_TOKEN", "")
OPENCLAW_AGENT_ID = os.getenv("OPENCLAW_AGENT_ID", "main")

TTS_PROVIDER = os.getenv("TTS_PROVIDER", "edge")
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")
TTS_LANG = os.getenv("TTS_LANG", "en-US")

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
        else:
            log.info(f"Using remote STT at {STT_URL}")

    def transcribe(self, audio_path: str) -> str:
        if self.provider == "whisper":
            result = self.model.transcribe(audio_path, language=WHISPER_LANGUAGE)
            return result["text"].strip()
        else:
            import requests
            with open(audio_path, "rb") as f:
                resp = requests.post(STT_URL, files={"audio": f})
                resp.raise_for_status()
                return resp.json()["text"].strip()


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
            # Authenticate
            await ws.send(json.dumps(connect_msg))
            auth_resp = json.loads(await ws.recv())
            if not auth_resp.get("ok"):
                raise ConnectionError(f"Auth failed: {auth_resp}")

            # Send message
            await ws.send(json.dumps(agent_msg))

            # Collect response
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
            communicate = edge_tts.Communicate(text, TTS_VOICE, lang=TTS_LANG)
            await communicate.save(output_path)
            log.info(f"TTS saved to {output_path}")

            # Play if possible
            self._play(output_path)
            return output_path
        else:
            import requests
            resp = requests.post(TTS_URL, json={"text": text})
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                f.write(resp.content)
            return output_path

    @staticmethod
    def _play(path: str):
        """Try to play audio file."""
        for cmd in ["mpv", "ffplay -nodisp -autoexit", "aplay"]:
            try:
                os.system(f"{cmd} {path} >/dev/null 2>&1 &")
                return
            except Exception:
                continue
        log.warning("No audio player found. File saved but not played.")


# ── Audio Recorder ─────────────────────────────────────────
class AudioRecorder:
    """Record audio from microphone until silence detected."""

    def __init__(self):
        self.sample_rate = AUDIO_SAMPLE_RATE
        self.channels = AUDIO_CHANNELS

    def record_until_silence(self, output_path: str) -> str:
        """Record audio until silence threshold is reached."""
        import pyaudio
        import numpy as np

        chunk = 1024
        format = pyaudio.paInt16

        p = pyaudio.PyAudio()
        stream = p.open(
            format=format,
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
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

                # Simple silence detection
                audio_data = np.frombuffer(data, dtype=np.int16)
                volume = np.abs(audio_data).mean()

                if volume < 500:  # silence threshold
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

        # Save to WAV
        wf = wave.open(output_path, "wb")
        wf.setnchannels(self.channels)
        wf.setsampwidth(p.get_sample_size(format))
        wf.setframerate(self.sample_rate)
        wf.writeframes(b"".join(frames))
        wf.close()

        log.info(f"Audio saved to {output_path}")
        return output_path

    def record_from_file(self, file_path: str, output_path: str) -> str:
        """Copy file for processing."""
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
        """Run the full pipeline: STT → OpenClaw → TTS"""
        # 1. Transcribe
        log.info("Transcribing...")
        text = self.stt.transcribe(audio_path)
        if not text:
            log.info("No speech detected, skipping.")
            return
        log.info(f"Heard: {text}")

        # 2. Send to OpenClaw
        log.info("Sending to OpenClaw...")
        response = await self.openclaw.send_message(text)
        if not response or response == "NO_REPLY":
            log.info("OpenClaw returned no response.")
            return
        log.info(f"OpenClaw: {response}")

        # 3. Speak response
        log.info("Speaking response...")
        await self.tts.speak(response)

    async def run_stream(self):
        """Continuous listening mode."""
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
        """Single file processing mode."""
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
    asyncio.run(main())
