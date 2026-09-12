#!/usr/bin/env bash
# 助手卡片渲染：把後端契約的 4 種回覆（answer／proposal／clarify／refuse）灌進 renderServerReply()，驗 HTML 元件
source "$(dirname "$0")/lib.sh"
open_case02
echo "chat-cards"
js "window.__n0 = document.querySelectorAll('#asstLog .msg').length; renderServerReply({kind:'answer', text:'行政罰法第 18 條第 1 項：裁處罰鍰，應審酌…\n（111-06-15 版）', sources:[{type:'law', title:'行政罰法 第 18 條', version:'111-06-15'}], cite_offer:{law:'行政罰法', article:'18', para:'1'}, proposal:null}); 1" >/dev/null
check "answer：一則 .msg.a，無提案卡" "document.querySelectorAll('#asstLog .msg').length === window.__n0 + 1 && ![...document.querySelectorAll('#asstLog .msg')].pop().classList.contains('card')"
check "answer：有來源與版本" "[...document.querySelectorAll('#asstLog .msg')].pop().querySelector('.src').textContent.includes('111-06-15')"
check "answer：有「以此提出修改」且無確認鈕" "[...document.querySelectorAll('#asstLog .msg')].pop().querySelector('[data-cite]') && ![...document.querySelectorAll('#asstLog .msg')].pop().querySelector('[data-yes]')"

js "renderServerReply({kind:'proposal', text:'x', sources:[], proposal:{id:'pp_test1', state:'pending', summary:'爭點 1 改採訴願人；加引行政罰法 §18 I；裁罰準則 §9 無法引用', scope:[2,3,4,5], affected_tabs:[1,2,3,4], items:[
  {type:'issue', id:'I1', to:'appellant', why:'影片看不出離手', n:1, title:'舉證是否充足', from:'採機關'},
  {type:'law', n:'行政罰法', art:'18', p:'1', key:'行政罰法 第 18 條第 1 項', ok:true, msg:'法規庫有・111-06-15 版', amended:'111-06-15', dup:true},
  {type:'law', n:'違反廢棄物清理法罰鍰額度裁罰準則', art:'9', key:'違反廢棄物清理法罰鍰額度裁罰準則 第 9 條', ok:false, msg:'僅 6 條，第 9 條不存在', amended:'110-03-18'}]}}); 1" >/dev/null
check "proposal：出 .msg.card" "[...document.querySelectorAll('#asstLog .msg')].pop().classList.contains('card')"
check "proposal：3 個 pc-item ＋ 影響範圍列" "(()=>{const c=[...document.querySelectorAll('#asstLog .msg')].pop(); return c.querySelectorAll('.pc-item').length === 4 && c.querySelector('.mini-steps')})()"
check "proposal：爭點卡顯示 AI 認定 → 修正後" "(()=>{const c=[...document.querySelectorAll('#asstLog .msg')].pop(); const t=c.innerText; return t.includes('AI 認定：採機關') && t.includes('修正後：採訴願人')})()"
check "proposal：法規列 ✓ 與 ✗ 各一" "(()=>{const c=[...document.querySelectorAll('#asstLog .msg')].pop(); return c.querySelectorAll('.mini-law').length===2 && c.querySelectorAll('.mini-law.bad').length===1 && c.innerText.includes('第 9 條不存在')})()"
check "proposal：影響範圍 3–6 亮" "(()=>{const c=[...document.querySelectorAll('#asstLog .msg')].pop(); return [...c.querySelectorAll('.mini-steps span')].map(s=>s.classList.contains('re')).join()==='false,false,true,true,true,true'})()"
check "proposal：有確認執行／取消" "(()=>{const c=[...document.querySelectorAll('#asstLog .msg')].pop(); return c.querySelector('[data-yes]') && c.querySelector('[data-no]')})()"
check "proposal：畫面未變（Tab 內容零變動）" "S.stances.I1 === 'agency' && S.plan === 'A'"
js "[...document.querySelectorAll('#asstLog .msg.card')].pop().querySelector('[data-no]').click(); 1" >/dev/null
check "取消：卡片灰化、AI 反問" "(()=>{const cards=[...document.querySelectorAll('#asstLog .msg.card')]; const last=[...document.querySelectorAll('#asstLog .msg')].pop(); return cards[cards.length-1].classList.contains('off') && last.innerText.includes('已取消')})()"

js "renderServerReply({kind:'clarify', text:'請問要改哪個部分？\n例如：「爭點 1 改採訴願人」／「理由二精簡一點」', sources:[], proposal:null}); 1" >/dev/null
check "clarify：文字卡、無提案卡" "(()=>{const m=[...document.querySelectorAll('#asstLog .msg')].pop(); return !m.classList.contains('card') && m.innerText.includes('請問要改哪個部分')})()"
js "renderServerReply({kind:'refuse', text:'本案已送審或已結案，不可修改', sources:[], proposal:null}); 1" >/dev/null
check "refuse：文字卡" "(()=>{const m=[...document.querySelectorAll('#asstLog .msg')].pop(); return !m.classList.contains('card') && m.innerText.includes('不可修改')})()"

js "renderServerReply({kind:'proposal', text:'', sources:[], proposal:{id:'pp_test2', state:'pending', summary:'送達日更正', scope:[0,1,2,3,4,5], affected_tabs:[0,1,2,3,4], items:[{type:'served', v:'114-09-16', from:'114-09-18', deadline:'114-10-16', inTime:true, daysLeft:24},{type:'text', para:'理由二', how:'精簡一點'},{type:'verdict', to:'原處分撤銷', from:'訴願駁回'}]}}); 1" >/dev/null
check "proposal 2：期間列、段落、結論三種元件" "(()=>{const c=[...document.querySelectorAll('#asstLog .msg.card')].pop(); const t=c.innerText; return c.querySelector('.mini-tp') && t.includes('114-10-16') && c.querySelector('.pc-diff') && c.querySelector('.mini-jbar') && t.includes('原處分撤銷')})()"
check "主控台無錯誤" "true"
"$B" console | grep -qi 'error' && { echo "  ✗ 主控台有錯誤"; FAIL=$((FAIL+1)); } || true
report "chat-cards"
