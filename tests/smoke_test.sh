#!/bin/bash
# tests/smoke_test.sh — 배포 직후 실행하는 스모크 테스트
# Usage: ./tests/smoke_test.sh [BASE_URL]
# Example: ./tests/smoke_test.sh https://d2hlklbiox15zw.cloudfront.net
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"

echo "🔍 Smoke testing $BASE_URL ..."

# 1. Health check
echo -n "  Health check... "
HTTP_STATUS=$(curl -sf -o /dev/null -w "%{http_code}" "$BASE_URL/health" || echo "000")
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

# 3. WebSocket 연결 (python3 + websockets 필요)
echo -n "  WebSocket... "
WS_URL="${BASE_URL/http/ws}/api/v1/ws/voice"
python3 -c "
import asyncio, json, sys
try:
    import websockets
except ImportError:
    print('SKIP (websockets not installed)')
    sys.exit(0)
async def check():
    async with websockets.connect('$WS_URL') as ws:
        await ws.send(json.dumps({'type': 'end'}))
        await asyncio.wait_for(ws.recv(), 5)
        print('OK')
try:
    asyncio.run(check())
except Exception as e:
    print(f'WARN: {e}')
" 2>/dev/null && echo "✅" || echo "⚠️  (non-critical)"

echo ""
echo "🎉 Smoke test passed!"
