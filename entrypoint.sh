#!/bin/bash
set -e

echo "🎙️ Voice Pipeline starting..."
echo "  STT: ${STT_PROVIDER:-whisper} (${WHISPER_MODEL:-small})"
echo "  OpenClaw: ${OPENCLAW_GATEWAY_URL:-ws://host.docker.internal:18789}"
echo "  TTS: ${TTS_PROVIDER:-edge} (${TTS_VOICE:-en-US-GuyNeural})"
echo "  Mode: ${PIPELINE_MODE:-stream}"

exec python pipeline.py "$@"
