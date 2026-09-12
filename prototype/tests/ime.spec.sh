#!/usr/bin/env bash
# 中文輸入法：組字中 Enter 只選字不送出；組字結束後 Enter 才送出；英文一次送出
source "$(dirname "$0")/lib.sh"
open_case02
echo "ime"
js "window.__sent=0; const _o=asstSend; window.asstSend=function(){ window.__sent++; return _o.apply(this, arguments); }; 1" >/dev/null
KD() { js "(()=>{const el=document.querySelector('#asstIn'); el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',keyCode:$2,isComposing:$1,bubbles:true,cancelable:true})); return window.__sent;})()"; }
js "document.querySelector('#asstIn').value='ㄗㄨㄥ'; document.querySelector('#asstIn').dispatchEvent(new CompositionEvent('compositionstart',{bubbles:true})); 1" >/dev/null
check "I1 組字中 Enter（isComposing=true）不送出" "$(KD true 229) === 0"
check "I1b 組字中 Enter（Safari：isComposing=false、keyCode 229）不送出" "$(KD false 229) === 0"
js "document.querySelector('#asstIn').value='本案爭點有哪些'; document.querySelector('#asstIn').dispatchEvent(new CompositionEvent('compositionend',{bubbles:true})); 1" >/dev/null
check "I4 compositionend 同一拍的 Enter 不送出" "$(KD false 13) === 0"
sleep 0.2
check "I2 組字結束後再按 Enter 才送出" "$(KD false 13) === 1"
js "document.querySelector('#asstIn').value='hello'; 1" >/dev/null; sleep 0.2
check "I3 英文 Enter 一次送出" "$(KD false 13) === 2"
check "輸入框已清空（送出後）" "document.querySelector('#asstIn').value === ''"
report "ime"
