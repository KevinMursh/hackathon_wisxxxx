#!/usr/bin/env bash
# mock 案的本機意圖規則：問句不出卡、改句出卡、模糊反問（後端 classify_intent 的前端對應）
source "$(dirname "$0")/lib.sh"
open_case02
echo "intent"
ask() { js "document.querySelector('#asstIn').value=$1; asstSend(); [...document.querySelectorAll('#asstLog .msg')].pop().className"; }
for q in "'送達日在哪份文件？'" "'期間有沒有逾期？'" "'爭點 1 的卷證在哪？'" "'行政罰法第 18 條第 1 項'" "'有沒有撤銷的案例？'" "'答辯書引了哪些法條？'" "'本案判定與風險？'" "'相似案例的結論分布？'" "'撤銷的案例有幾件？'" "'本案爭點有哪些'"; do
  out="$(ask "$q")"; if [ "$out" = "msg a" ]; then PASS=$((PASS+1)); echo "  ✓ 問：$q → 文字"; else FAIL=$((FAIL+1)); echo "  ✗ 問：$q → $out"; fi
done
for q in "'爭點 1 改採訴願人，影片看不出離手'" "'加引行政罰法第 18 條第 1 項'" "'送達日改 114-09-16'" "'結論改為原處分撤銷'" "'理由二精簡一點'" "'加引裁罰準則第 9 條'"; do
  out="$(ask "$q")"; if [ "$out" = "msg a card" ]; then PASS=$((PASS+1)); echo "  ✓ 改：$q → 提案卡"; else FAIL=$((FAIL+1)); echo "  ✗ 改：$q → $out"; fi
done
out="$(ask "'改好一點'")"; if [ "$out" = "msg a" ]; then PASS=$((PASS+1)); echo "  ✓ 模糊：改好一點 → 反問"; else FAIL=$((FAIL+1)); echo "  ✗ 模糊 → $out"; fi
check "所有提案卡都未執行（stances 未變）" "S.stances.I1==='agency' && S.plan==='A'"
report "intent"
