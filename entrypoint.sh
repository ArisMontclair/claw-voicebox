#!/bin/bash
set -e

echo "🗣️ Claw Voicebox starting..."
echo "  STT: ${STT_PROVIDER:-whisper} (${WHISPER_MODEL:-small})"
echo "  TTS: ${TTS_PROVIDER:-edge} (${TTS_VOICE:-en-US-GuyNeural})"
echo "  OpenClaw: ${OPENCLAW_GATEWAY_URL:-ws://host.docker.internal:18789}"
echo "  Web UI: http://0.0.0.0:${PORT:-8080}"

# Default: run web server
# Override: pass "pipeline" to run CLI mode instead
if [ "$1" = "pipeline" ]; then
    shift
    exec python pipeline.py "$@"
else
    exec python web_server.py
fi
