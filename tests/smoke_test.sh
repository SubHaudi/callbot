#!/bin/bash
# tests/smoke_test.sh — 배포 직후 실행하는 스모크 테스트
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

echo "🔍 Smoke testing $BASE_URL ..."

# 1. Health check
echo -n "  Health check... "
HTTP_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/health")
if [ "$HTTP_STATUS" != "200" ]; then
    echo "❌ FAIL (HTTP $HTTP_STATUS)"
    exit 1
fi
echo "✅"

# 2. Turn API
echo -n "  Turn API... "
RESP=$(curl -sf -X POST "$BASE_URL/api/v1/turn" \
    -H "Content-Type: application/json" \
    -d '{"caller_id":"smoke-test","text":"요금 조회"}')
if echo "$RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('response_text'), 'Empty response'" 2>/dev/null; then
    echo "✅"
else
    echo "❌ FAIL: $RESP"
    exit 1
fi

# 3. WebSocket 연결
echo -n "  WebSocket... "
python3 -c "
import asyncio, websockets, json, sys
async def check():
    async with websockets.connect('${BASE_URL/http/ws}/api/v1/ws/voice') as ws:
        await ws.send(json.dumps({'type':'end'}))
        r = json.loads(await asyncio.wait_for(ws.recv(), 5))
        # end without audio → error is OK, but server didn't crash
        print('OK')
asyncio.run(check())
" 2>/dev/null && echo "✅" || { echo "❌ FAIL"; exit 1; }

echo ""
echo "🎉 All smoke tests passed!"
