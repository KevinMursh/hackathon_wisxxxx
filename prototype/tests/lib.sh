#!/usr/bin/env bash
# 前端瀏覽器測試共用：gstack 無頭 Chromium ＋ 本機 http.server（file:// 被擋）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
B="${B:-$HOME/.claude/skills/gstack/browse/dist/browse}"
[ -x "$B" ] || { echo "需要 gstack browse：$B"; exit 2; }
PORT="${PORT:-8765}"
if ! curl -s -m 2 "http://localhost:$PORT/prototype/index.html" >/dev/null; then (cd "$ROOT" && python3 -m http.server "$PORT" >/dev/null 2>&1 &); sleep 1; fi
URL="http://localhost:$PORT/prototype/index.html"
PASS=0; FAIL=0
js() { "$B" js "$1"; }
check() { # check "名稱" "JS 運算式（回 true 才過）"
  local out; out="$(js "(()=>{ try { return !!($2) ? 'OK' : 'NG'; } catch(e) { return 'ERR ' + e.message; } })()")"
  if [ "$out" = "OK" ]; then PASS=$((PASS+1)); echo "  ✓ $1"; else FAIL=$((FAIL+1)); echo "  ✗ $1  → $out"; fi
}
# mock 案 case02（CASES id "B"）用 hash 路由開，不打後端；首頁示範卡是真跑（會在雲上起 job）
open_case02() { "$B" viewport 1440x900 >/dev/null; "$B" goto "$URL#/case/B" >/dev/null; js "new Promise(r=>setTimeout(()=>{document.querySelector('#asstBtn').click(); r(document.querySelector('.screen.on').id)}, 7000))" >/dev/null; }
report() { echo "$1: $PASS 通過，$FAIL 失敗"; [ "$FAIL" -eq 0 ]; }
