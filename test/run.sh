#!/bin/bash
# Sketchy Lab test harness: fake OpenRouter + server on :3457, then the Playwright test
cd "$(dirname "$0")/.."
fuser -k 3457/tcp 9996/tcp >/dev/null 2>&1; sleep 0.3
node test/fakeor.js test/face.png > test/fakeor.log 2>&1 &
rm -rf /tmp/sketchy-lab
DATA_DIR=/tmp/sketchy-lab OPENROUTER_BASE=http://localhost:9996/api/v1 OPENROUTER_API_KEY=k OPENAI_BASE=http://localhost:9996/v1 OPENAI_API_KEY=sk-test ADMIN_PASSWORD=pw PORT=3457 node server/index.js > test/srv.log 2>&1 &
sleep 2; FACE=test/face.png python3 ${LTEST:-test/builder.py}; fuser -k 3457/tcp 9996/tcp >/dev/null 2>&1; echo stopped
