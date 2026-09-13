"""提案簡報產生器（精簡版 14 頁）：內容在 _deck_content.py → HTML(16:9) → Chrome PDF；python-pptx 產出可編輯 PPTX。
架構圖使用 AWS 官方 Architecture Icons（assets/aws-icons/）。
執行：<venv 含 python-pptx>/python build_deck.py
"""
import os, subprocess, shutil, tempfile, time, signal, base64, math
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from _deck_content import S

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = f"{HERE}/assets/aws-icons"
OUT_PPT = f"{HERE}/提案簡報-訴願智審臺.pptx"
OUT_PDF = f"{HERE}/提案簡報-訴願智審臺.pdf"
OUT_ARCH = f"{HERE}/assets/aws-architecture.png"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP = tempfile.mkdtemp(prefix="deck-")
NAVY, INK, AMBER, GOLD, LIGHT, LINE, GREEN, RED = "16304F", "0F2038", "D98E04", "F2B544", "F4F6F9", "DDE3EA", "2E7D32", "B3261E"

# =====================================================================================
# 架構圖（官方圖示；每框只留服務名＋一行）
# =====================================================================================
def icon_uri(name):
    return "data:image/svg+xml;base64," + base64.b64encode(open(f"{ICON}/{name}.svg", "rb").read()).decode()

ARCH_CSS = """
.aw{position:relative;width:1150px;height:540px;font-family:"PingFang TC","Microsoft JhengHei",sans-serif;color:#0F2038;font-size:14px;line-height:1.35}
.aw .cloud{position:absolute;left:236px;top:0;width:914px;height:540px;border-radius:10px;background:#173B4C}
.aw .cloud .lab{position:absolute;left:0;top:0;display:flex;align-items:center;gap:10px;padding:10px 14px;font-weight:700;font-size:15px;color:#fff}
.aw .cloud .lab img{width:30px;height:30px;border-radius:4px}
.aw .region{position:absolute;left:252px;top:50px;width:882px;height:476px;border:1.5px dashed #4FB8B0;border-radius:8px}
.aw .region .lab{position:absolute;left:10px;top:8px;display:flex;align-items:center;gap:8px;font-size:13.5px;color:#7FD3CC;font-weight:600}
.aw .region .lab img{width:24px;height:24px}
.aw .svc{position:absolute;background:#fff;border-radius:12px;padding:14px 16px}
.aw .svc .h{display:flex;align-items:center;gap:12px;margin-bottom:8px}
.aw .svc .h img{width:46px;height:46px;flex:none;border-radius:6px}
.aw .svc .h b{font-size:17px;color:#0F2038;line-height:1.2}
.aw .svc .h small{display:block;font-weight:400;color:#5B6573;font-size:12.5px}
.aw .svc p{margin:0;font-size:14.5px;color:#0F2038}
.aw .grp{position:absolute;border:2px solid #D98E04;border-radius:12px;background:#DCEBE7}
.aw .grp .gl{position:absolute;left:14px;top:-16px;background:#FFF1D6;border-radius:6px;padding:3px 10px 3px 6px;font-size:14px;font-weight:700;color:#B36F00;display:flex;align-items:center;gap:8px}
.aw .grp .gl img{width:26px;height:26px;border-radius:4px}
.aw .grp .svc{border:1.5px solid #4FB8B0}
.aw .client{position:absolute;left:0;top:190px;width:214px;text-align:center}
.aw .client img{width:78px;height:78px}
.aw .client b{display:block;font-size:17px;margin-top:6px;color:#0F2038}
.aw .client p{margin:6px 0 0;font-size:13.5px;color:#334}
.aw svg.ar{position:absolute;left:0;top:0;width:1150px;height:540px;pointer-events:none}
.aw .ops{position:absolute;left:268px;top:456px;width:852px;height:60px;display:flex;gap:14px;align-items:center}
.aw .ops .o{display:flex;align-items:center;gap:10px;flex:1;background:#fff;border-radius:10px;padding:6px 12px;font-size:13px;color:#334;height:58px}
.aw .ops .o img{width:36px;height:36px;flex:none;border-radius:4px}
.aw .ops .o b{display:block;font-size:14px;color:#0F2038}
"""

def arch_html():
    I = icon_uri
    def arrow(x1, y1, x2, y2, label="", dash=False, ly=None):
        d = ' stroke-dasharray="6 4"' if dash else ""
        col = "#16304F" if x2 <= 268 or x1 == x2 else "#C9D6D9"
        s = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{col}" stroke-width="2" marker-end="url(#{"ah" if (x2 <= 268 or x1 == x2) else "ahl"})"{d}/>'
        if label: s += f'<text x="{(x1+x2)/2}" y="{ly}" font-size="12" fill="{"#5B6573" if x2 <= 268 else "#E6EDF5"}" text-anchor="middle">{label}</text>'
        return s
    arrows = ('<svg class="ar" viewBox="0 0 1150 540"><defs><marker id="ah" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0,0 L9,3.5 L0,7 z" fill="#16304F"/></marker><marker id="ahl" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0,0 L9,3.5 L0,7 z" fill="#C9D6D9"/></marker></defs>'
              + arrow(214, 262, 266, 262) + arrow(459, 236, 459, 254, dash=True)
              + arrow(650, 150, 700, 150) + arrow(650, 288, 700, 288) + arrow(650, 396, 700, 396) + '</svg>')
    return f'''<div class="aw">
<div class="cloud"><div class="lab"><img src="{I('AWSCloudlogo')}">AWS 競賽帳號</div></div>
<div class="region"><div class="lab"><img src="{I('Region')}">Region us-west-2　｜　S3 不公開　｜　只開放會場 IP　｜　不放金鑰</div></div>
<div class="client"><img src="{I('Client')}"><b>承辦人瀏覽器</b><p>工作台＋卷宗瀏覽器</p></div>
<div class="grp" style="left:268px;top:100px;width:382px;height:344px">
  <div class="gl"><img src="{I('AmazonEC2')}">Amazon EC2　t3.large</div>
  <div class="svc" style="left:12px;top:18px;width:356px;height:118px"><div class="h"><b>Node :80<small>畫面＋卷證分類</small></b></div><p>上傳 → 轉檔 → 分類 → 分批回傳結果</p><p>依序處理，遵守 Bedrock 呼叫頻率限制</p></div>
  <div class="svc" style="left:12px;top:158px;width:356px;height:168px"><div class="h"><b>FastAPI :8100<small>分析・助手・法規庫</small></b></div><p>固定七個步驟，每步結果保存</p><p>期間、不受理事由、條號比對（程式）</p><p>修正 → 確認 → 局部重算</p></div>
</div>
<div class="svc" style="left:700px;top:96px;width:420px;height:108px"><div class="h"><img src="{I('AmazonBedrock')}"><b>Amazon Bedrock<small>Converse・Knowledge Base</small></b></div><p>Claude Sonnet 4.5：讀文字與圖片，回固定格式</p><p>知識庫：法規／判解／函釋／98 份決定書</p></div>
<div class="svc" style="left:700px;top:236px;width:420px;height:100px"><div class="h"><img src="{I('AmazonSimpleStorageService')}"><b>Amazon S3<small>private bucket</small></b></div><p>原始卷宗・頁面圖與文字・知識庫資料</p></div>
<div class="svc" style="left:700px;top:348px;width:420px;height:92px"><div class="h"><img src="{I('AmazonDynamoDB')}"><b>Amazon DynamoDB<small>單表 appeal-cases</small></b></div><p>案件・卷證・分析結果・修改紀錄</p></div>
<div class="ops">
  <div class="o"><img src="{I('AWSIdentityandAccessManagement')}"><span><b>IAM Instance Profile</b>最小權限，無金鑰</span></div>
  <div class="o"><img src="{I('AWSSystemsManager')}"><span><b>Systems Manager</b>免 SSH 部署 30 秒</span></div>
  <div class="o"><img src="{I('AmazonCloudWatch')}"><span><b>CloudWatch Logs</b>兩個 service 的 log</span></div>
</div>{arrows}</div>'''

# =====================================================================================
# HTML → PDF
# =====================================================================================
CSS = """
@page{size:1280px 720px;margin:0}*{box-sizing:border-box}
body{margin:0;font-family:"PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;color:#0F2038;-webkit-print-color-adjust:exact}
.slide{width:1280px;height:720px;position:relative;page-break-after:always;overflow:hidden;background:#fff;padding:52px 72px 0}
.slide:last-child{page-break-after:auto}
.slide:before{content:"";position:absolute;left:0;top:0;width:100%;height:8px;background:linear-gradient(90deg,#16304F 0 78%,#D98E04 78% 100%)}
.sec{font-family:"Menlo","IBM Plex Mono",monospace;font-size:14px;letter-spacing:.16em;color:#D98E04;font-weight:500}
h3{font-size:40px;font-weight:900;color:#16304F;line-height:1.25;margin:6px 0 30px;letter-spacing:.01em}
.ft{position:absolute;left:72px;right:72px;bottom:22px;font-size:13px;color:#8A93A0;display:flex;justify-content:space-between;border-top:1px solid #E6EAF0;padding-top:8px}
.big{font-size:26px;color:#334;line-height:1.55;max-width:26em}
.bignum{font-size:120px;font-weight:900;color:#16304F;line-height:1;font-variant-numeric:tabular-nums}
.bignum small{font-size:28px;color:#5B6573;font-weight:500;margin-left:10px}
.chips{display:flex;gap:14px;flex-wrap:wrap}
.chip{background:#F4F6F9;border-radius:10px;padding:14px 20px;font-size:22px;color:#16304F;font-weight:700}
.chip small{display:block;font-size:15px;color:#5B6573;font-weight:400;margin-top:4px}
.note{position:absolute;left:72px;right:72px;bottom:64px;background:#FFF8EA;border-left:6px solid #D98E04;padding:12px 18px;font-size:20px;color:#334;border-radius:0 8px 8px 0}
.cover{background:#16304F;color:#fff;padding:0}.cover:before{display:none}
.cover .band{position:absolute;left:0;top:0;width:10px;height:100%;background:#D98E04}
.cover .blob{position:absolute;right:-160px;top:-180px;width:560px;height:560px;border-radius:50%;background:#1E3F68}
.cover .in{position:absolute;left:96px;top:150px;right:96px}
.cover .ctag{font-size:16px;letter-spacing:.22em;color:#F2B544;font-weight:700}
.cover h3{color:#fff;font-size:88px;margin:18px 0 6px}
.cover .sub{font-size:28px;color:#C9D6E6}
.cover .claim{margin-top:30px;font-size:24px;color:#E6EDF5;border-left:4px solid #D98E04;padding-left:18px;max-width:30em}
.cover .stats{position:absolute;left:96px;right:96px;bottom:70px;display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.cover .st{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:18px 22px}
.cover .st b{display:block;font-size:44px;color:#F2B544;line-height:1.1}.cover .st span{font-size:16px;color:#C9D6E6}
.p2{display:grid;grid-template-columns:1fr 70px 1.25fr;gap:16px 0;align-items:center}
.p2 .hd{font-size:15px;letter-spacing:.12em;color:#8A93A0;font-weight:700;border-bottom:2px solid #E6EAF0;padding-bottom:6px}
.p2 .l{display:flex;gap:14px;align-items:center;font-size:26px;font-weight:700;color:#16304F;padding:16px 0}
.p2 .l i{flex:none;width:44px;height:44px;border-radius:50%;background:#16304F;color:#fff;font-style:normal;display:flex;align-items:center;justify-content:center;font-size:20px}
.p2 .ar{text-align:center;color:#D98E04;font-size:38px;font-weight:900}
.p2 .r{background:#FFF8EA;border-left:6px solid #D98E04;border-radius:0 12px 12px 0;padding:16px 20px;font-size:23px;color:#0F2038;line-height:1.4}
.p2 .r small{display:block;font-size:16px;color:#5B6573;margin-top:4px}
.vs{display:grid;grid-template-columns:1fr 1fr;gap:28px;height:470px}
.vs .pan{border-radius:16px;padding:28px 32px;position:relative;display:flex;flex-direction:column}
.vs .no{background:#F4F6F9;color:#5B6573}.vs .yes{background:#16304F;color:#fff}
.vs .pan h4{margin:0 0 8px;font-size:30px}.vs .pan p{margin:0;font-size:20px;line-height:1.5}
.vs svg{width:100%;height:auto;margin-top:auto}
.flow5{display:grid;grid-template-columns:repeat(5,1fr);gap:22px;margin-top:10px}
.flow5 .c{text-align:center}
.flow5 .c .ic{width:120px;height:120px;border-radius:30px;background:#F4F6F9;margin:0 auto 16px;display:flex;align-items:center;justify-content:center}
.flow5 .c .ic svg{width:64px;height:64px}
.flow5 .c b{display:block;font-size:26px;color:#16304F}.flow5 .c span{font-size:18px;color:#5B6573}
.four{display:grid;grid-template-columns:1fr 1fr;gap:20px 36px}
.four .it{display:grid;grid-template-columns:56px 1fr;gap:14px;align-items:start;background:#F4F6F9;border-radius:14px;padding:20px 22px}
.four .it .ck{width:56px;height:56px;border-radius:50%;background:#2E7D32;color:#fff;display:flex;align-items:center;justify-content:center;font-size:32px;font-weight:900}
.four .it b{display:block;font-size:24px;color:#16304F}.four .it span{font-size:18px;color:#334}.four .it em{display:block;font-style:normal;font-size:15px;color:#8A5A00;margin-top:6px}
.ba{display:grid;grid-template-columns:1fr 80px 1fr;align-items:center}
.ba .box{border-radius:14px;padding:22px 26px;height:290px;font-family:"Menlo","IBM Plex Mono",monospace;font-size:20px;line-height:1.7}
.ba .mess{background:#F4F6F9;color:#5B6573}.ba .neat{background:#FFF8EA;color:#0F2038;border:2px solid #D98E04}
.ba .ar{text-align:center;color:#D98E04;font-size:52px;font-weight:900}
.pipe7{display:flex;gap:10px}
.pipe7 .c{flex:1;border:2px solid #DDE3EA;border-radius:12px;padding:16px 8px;text-align:center}
.pipe7 .c b{display:block;font-size:21px;color:#16304F;padding:10px 0}.pipe7 .c i{display:inline-block;font-style:normal;margin-top:8px;background:#FFF2D6;color:#B36F00;font-weight:700;border-radius:6px;padding:2px 8px;font-size:14.5px;white-space:nowrap}
.pipe7 .c.code{border-color:#2E7D32;background:#F2F8F3}.pipe7 .c.code i{background:#E0F0E2;color:#2E7D32}
.st7{display:grid;grid-template-columns:repeat(7,1fr);gap:10px}
.st7 .c{border:2px solid #DDE3EA;border-radius:12px;padding:22px 14px;min-height:250px;position:relative;background:#fff}
.st7 .c.code{border-color:#2E7D32;background:#F2F8F3}
.st7 .c i{display:flex;width:30px;height:30px;border-radius:50%;background:#16304F;color:#fff;font-style:normal;font-weight:700;font-size:15px;align-items:center;justify-content:center;margin-bottom:10px}
.st7 .c.code i{background:#2E7D32}
.st7 .c b{display:block;font-size:21px;color:#16304F;margin-bottom:12px}
.st7 .c .o{font-size:17px;color:#0F2038;line-height:1.5;margin-bottom:12px}
.st7 .c .src{font-size:14px;color:#8A93A0;line-height:1.45;border-top:1px solid #E6EAF0;padding-top:10px}
.st7 .c .src:before{content:"依據　";color:#B36F00}
.st7 .c:after{content:"";position:absolute;right:-9px;top:30px;border-left:9px solid #C5CDD8;border-top:7px solid transparent;border-bottom:7px solid transparent}
.st7 .c:last-child:after{content:""}
.props{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-top:34px}
.props .p{background:#F4F6F9;border-radius:14px;padding:24px 24px;display:grid;grid-template-columns:auto 1fr;gap:14px;align-items:center}
.props .p b{font-size:24px;color:#16304F;white-space:nowrap}.props .p span{font-size:16px;color:#334;line-height:1.45}
.gate{display:grid;grid-template-columns:repeat(4,1fr);gap:22px}
.gate .g{background:#F4F6F9;border-radius:16px;padding:26px 22px;text-align:center;min-height:330px}
.gate .g .ic{width:88px;height:88px;border-radius:50%;background:#16304F;margin:0 auto 18px;display:flex;align-items:center;justify-content:center}
.gate .g .ic svg{width:48px;height:48px}
.gate .g b{display:block;font-size:22px;color:#16304F;margin-bottom:8px}.gate .g span{font-size:18px;color:#334;line-height:1.5}
.data{display:grid;grid-template-columns:420px 1fr;gap:40px;align-items:center}
.data svg{width:100%;height:auto}
.data .ins{font-size:30px;color:#16304F;font-weight:700;line-height:1.4}
.data .ins small{display:block;font-size:20px;color:#5B6573;font-weight:400;margin-top:14px}
.ev{display:grid;grid-template-columns:240px 1fr 280px;gap:18px;align-items:start}
.ev .dz{display:flex;flex-direction:column;gap:10px}
.ev .dz .d{background:#F4F6F9;border-radius:10px;padding:12px 14px}
.ev .dz .d b{display:block;font-size:17px;color:#16304F;margin-bottom:3px}.ev .dz .d span{font-size:13.5px;color:#334;line-height:1.4}
.ev table{border-collapse:separate;border-spacing:0;width:100%;font-size:14.5px;border-radius:10px;overflow:hidden}
.ev th{background:#16304F;color:#fff;padding:10px 10px;text-align:center;font-weight:600;font-size:15px}
.ev td{border-bottom:1px solid #E6EAF0;padding:9px 6px;text-align:center;vertical-align:middle}
.ev td:first-child{font-weight:700;color:#16304F;text-align:left;white-space:nowrap;background:#F7F9FB}
.ev tr:last-child td{color:#2E7D32;font-weight:700}
.ev .hl{background:#FFF8EA;border-left:6px solid #D98E04;border-radius:0 12px 12px 0;padding:16px 18px}
.ev .hl b{display:block;font-size:17px;color:#16304F;margin-bottom:10px}
.ev .hl p{margin:0 0 8px;font-size:13.5px;color:#334;line-height:1.45;padding-left:14px;position:relative}
.ev .hl p:before{content:"";position:absolute;left:0;top:.55em;width:6px;height:6px;border-radius:50%;background:#D98E04}
.ev-foot{position:absolute;left:72px;right:72px;bottom:56px;font-size:13.5px;color:#8A93A0}
.cases{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.cases .c{border:2px solid #DDE3EA;border-radius:16px;padding:24px 22px;min-height:360px}
.cases .c .lab{font-family:"Menlo",monospace;font-size:14px;color:#D98E04;letter-spacing:.1em}
.cases .c h4{margin:6px 0 14px;font-size:26px;color:#16304F}
.cases .c .ans{display:inline-block;background:#16304F;color:#fff;border-radius:8px;padding:6px 14px;font-size:20px;font-weight:700;margin-bottom:14px}
.cases .c p{margin:0;font-size:18px;color:#334;line-height:1.5}
.board{display:grid;grid-template-columns:1fr 1fr;gap:12px 40px}
.board .it{display:flex;align-items:center;gap:14px;font-size:24px;color:#16304F;padding:10px 0;border-bottom:1px solid #E6EAF0}
.board .d{width:18px;height:18px;border-radius:50%;flex:none}
.board .on{background:#2E7D32}.board .half{background:linear-gradient(90deg,#D98E04 50%,#E6EAF0 50%)}.board .off{background:#C5CDD8}
.board small{margin-left:auto;font-size:16px;color:#5B6573}

.pil{display:grid;grid-template-columns:1fr 1fr;gap:22px 28px}
.pil .c{background:#F4F6F9;border-radius:16px;padding:24px 26px;min-height:225px;display:grid;grid-template-columns:52px 1fr;gap:16px;align-items:start}
.pil .c i{width:52px;height:52px;border-radius:50%;background:#16304F;color:#fff;font-style:normal;font-weight:900;font-size:24px;display:flex;align-items:center;justify-content:center}
.pil .c b{display:block;font-size:26px;color:#16304F;margin-bottom:8px}.pil .c p{margin:0;font-size:18px;color:#334;line-height:1.5}
.pil .c.big{align-items:center;min-height:235px;grid-template-columns:72px 1fr}.pil .c.big i{width:72px;height:72px;font-size:34px}.pil .c.big b{font-size:34px;margin:0;white-space:nowrap}
.pil .c.big small{display:block;font-size:20px;color:#8A5A00;font-weight:500;margin-top:8px}
.wf{display:grid;grid-template-columns:150px repeat(5,1fr);gap:12px 14px;align-items:center;margin-top:8px}
.wf .h{font-size:16px;letter-spacing:.1em;color:#8A93A0;font-weight:700;text-align:center;padding-bottom:6px;border-bottom:2px solid #E6EAF0}
.wf .rl{font-size:22px;font-weight:700;color:#16304F}
.wf .cell{height:120px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:700}
.wf .man{background:#F4F6F9;color:#8A93A0}.wf .ai{background:#16304F;color:#fff}.wf .hu{background:#D98E04;color:#16304F}
.subtitle{font-size:22px;color:#8A5A00;margin:-18px 0 22px;font-weight:500}
.cover .team{position:absolute;left:96px;bottom:104px;font-size:20px;color:#E6EDF5;font-weight:700}
.pil .c em{display:block;font-style:normal;font-size:15px;color:#8A5A00;margin-top:10px;border-left:3px solid #D98E04;padding-left:10px}
.fw{display:grid;grid-template-columns:1fr 1.3fr;gap:30px;align-items:start}
.fw .why{background:#F4F6F9;border-radius:14px;padding:20px 22px}
.fw .why h4{margin:0 0 10px;font-size:20px;color:#16304F}.fw .why p{margin:0 0 8px;font-size:16.5px;color:#334;line-height:1.5}
.fw svg{width:100%;height:auto}
.rv{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}
.rv .c{border:2px solid #DDE3EA;border-radius:14px;padding:18px 18px;min-height:250px;position:relative}
.rv .c i{display:flex;width:38px;height:38px;border-radius:50%;background:#16304F;color:#fff;font-style:normal;font-weight:700;font-size:18px;align-items:center;justify-content:center;margin-bottom:12px}
.rv .c b{display:block;font-size:21px;color:#16304F;margin-bottom:10px}.rv .c p{margin:0;font-size:16.5px;color:#334;line-height:1.5;white-space:pre-line}
.rv .c.hi{background:#FFF8EA;border-color:#D98E04}
.rv .c:after{content:"›";position:absolute;right:-14px;top:100px;font-size:34px;color:#C5CDD8}.rv .c:last-child:after{content:""}
.dn{display:grid;grid-template-columns:1fr 1fr;gap:40px}
.dn .it{display:flex;align-items:center;gap:12px;font-size:20px;color:#16304F;padding:8px 0;border-bottom:1px solid #E6EAF0}
.dn .d{width:16px;height:16px;border-radius:50%;flex:none}
.dn .on{background:#2E7D32}.dn .half{background:linear-gradient(90deg,#D98E04 50%,#E6EAF0 50%)}.dn .off{background:#C5CDD8}
.dn .sc{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.dn .sc .c{background:#F4F6F9;border-radius:12px;padding:16px 18px}
.dn .sc b{display:block;font-size:40px;color:#16304F;line-height:1}.dn .sc h4{margin:6px 0 4px;font-size:18px;color:#16304F}.dn .sc p{margin:0;font-size:14px;color:#334;line-height:1.4}
.score4{display:grid;grid-template-columns:repeat(4,1fr);gap:20px}
.score4 .c{background:#F4F6F9;border-radius:16px;padding:26px 22px;min-height:330px}
.score4 .c b{display:block;font-size:64px;color:#16304F;line-height:1;font-variant-numeric:tabular-nums}
.score4 .c h4{margin:10px 0 12px;font-size:24px;color:#16304F}.score4 .c p{margin:0;font-size:18px;color:#334;line-height:1.5}
.score4 .bar{height:8px;background:#E6EAF0;border-radius:4px;margin-top:18px;overflow:hidden}.score4 .bar i{display:block;height:100%;background:#D98E04}
"""

ICONS = {
    "upload": '<path d="M32 44V16M20 28l12-12 12 12"/><rect x="10" y="44" width="44" height="10" rx="3"/>',
    "list": '<rect x="10" y="10" width="44" height="44" rx="6"/><path d="M18 24h28M18 34h28M18 44h16"/>',
    "tabs": '<rect x="8" y="12" width="48" height="40" rx="5"/><path d="M8 24h48M20 12v12M36 12v12"/>',
    "chat": '<path d="M10 14h44v30H26l-10 8v-8h-6z"/><path d="M22 26h20M22 34h12"/>',
    "check": '<path d="M14 34l12 12 24-26"/>',
}
GATE_ICONS = {
    "doc": '<path d="M10 8h20l8 8v24H10z"/><path d="M16 24h16M16 32h10"/>',
    "quote": '<path d="M8 12h32v24H8z"/><path d="M14 20h20M14 28h12"/><circle cx="36" cy="34" r="6" fill="#D98E04" stroke="none"/>',
    "clock": '<circle cx="24" cy="24" r="16"/><path d="M24 12v12l8 6"/>',
    "form": '<rect x="8" y="10" width="32" height="28" rx="3"/><path d="M8 20h32M16 10v10"/>',
}

def donut_svg(parts):
    C = 2 * math.pi * 110; off = 0; out = '<circle cx="150" cy="150" r="110" fill="none" stroke="#E6EAF0" stroke-width="44"/>'
    for _, pct, col in parts:
        L = C * pct / 100
        out += f'<circle cx="150" cy="150" r="110" fill="none" stroke="#{col}" stroke-width="44" stroke-dasharray="{L:.0f} {C:.0f}" stroke-dashoffset="{-off:.0f}" transform="rotate(-90 150 150)"/>'
        off += L
    out += f'<text x="150" y="142" text-anchor="middle" font-size="58" font-weight="900" fill="#16304F">{parts[0][1]}%</text><text x="150" y="172" text-anchor="middle" font-size="18" fill="#5B6573">{parts[0][0]}</text>'
    out += f'<text x="150" y="196" text-anchor="middle" font-size="14" fill="#8A93A0">{"・".join(f"{n} {p}%" for n, p, _ in parts[1:])}</text>'
    return f'<svg viewBox="0 0 300 300">{out}</svg>'

def h_slide(i, s):
    n = len(S); k = s["kind"]
    if k in ("cover", "end"):
        top = "" if k == "cover" else 'style="top:230px"'
        h3s = "" if k == "cover" else ' style="font-size:72px"'
        inner = f'<div class="band"></div><div class="blob"></div><div class="in" {top}><div class="ctag">{s["tag"]}</div><h3{h3s}>{s["title"]}</h3>{f'<div class="sub">{s["sub"]}</div>' if s.get("sub") else ""}{f'<div class="claim">{s["claim"]}</div>' if s.get("claim") else ""}</div>'
        if k == "cover":
            inner += f'<div class="team">{s["team"]}</div><div class="ctag" style="position:absolute;left:96px;bottom:60px;letter-spacing:.05em;color:#9FB0C8">{s["url"]}</div>'
        return f'<div class="slide cover">{inner}</div>'
    b = ""
    if k == "pain":
        b = '<div class="p2"><div class="hd">困難（命題文件）</div><div></div><div class="hd">我們的設計</div>' + "".join(
            f'<div class="l"><i>{j}</i>{a}</div><div class="ar">→</div><div class="r">{c}<small>{d}</small></div>' for j, (a, c, d) in enumerate(s["rows"], 1)) + '</div>'
    elif k == "vs":
        rows = "".join(f'<rect x="20" y="{20+j*38}" width="360" height="30" rx="6" fill="#24466F"/><text x="32" y="{40+j*38}">{r}</text>' for j, r in enumerate(s["rows"]))
        y = 20 + len(s["rows"]) * 38
        b = (f'<div class="vs"><div class="pan no"><h4>❌ {s["no"][0]}</h4><p>{s["no"][1]}</p><svg viewBox="0 0 400 150"><rect x="20" y="30" width="360" height="90" rx="12" fill="#DDE3EA"/><text x="200" y="85" text-anchor="middle" font-size="26" fill="#5B6573" font-weight="700">駁回</text><text x="200" y="140" text-anchor="middle" font-size="14" fill="#8A93A0">黑盒</text></svg></div>'
             f'<div class="pan yes"><h4>✅ {s["yes"][0]}</h4><p>{s["yes"][1]}</p><svg viewBox="0 0 400 150"><g font-size="14" fill="#fff">{rows}<rect x="20" y="{y}" width="360" height="30" rx="6" fill="#D98E04"/><text x="32" y="{y+20}" fill="#16304F" font-weight="700">{s["act"]}</text></g></svg></div></div>')
    elif k == "wf":
        cls = {"人工": "man", "AI": "ai", "承辦人": "hu"}
        b = f'<div class="subtitle">{s["subtitle"]}</div><div class="wf"><div></div>' + "".join(f'<div class="h">{c}</div>' for c in s["cols"])
        for lab, cells in s["rows"]:
            b += f'<div class="rl">{lab}</div>' + "".join(f'<div class="cell {cls[c]}">{c}</div>' for c in cells)
        b += f'</div><div class="note">{s["foot"]}</div>'
    elif k == "flow":
        b = '<div class="flow5">' + "".join(f'<div class="c"><div class="ic"><svg viewBox="0 0 64 64" fill="none" stroke="#16304F" stroke-width="4">{ICONS[ic]}</svg></div><b>{a}</b><span>{c}</span></div>' for a, c, ic in s["steps"]) + f'</div><div class="note">{s["foot"]}</div>'
    elif k == "four":
        b = '<div class="four">' + "".join(f'<div class="it"><div class="ck">✓</div><div><b>{a}</b><span>{c}</span><em>{d}</em></div></div>' for a, c, d in s["items"]) + '</div>'
    elif k == "ba":
        b = f'<div class="ba"><div class="box mess">{"<br>".join(s["before"])}</div><div class="ar">→</div><div class="box neat">{"<br>".join(s["after"])}</div></div><div class="chips" style="margin-top:22px">' + "".join(f'<div class="chip">{a}<small>{c}</small></div>' for a, c in s["chips"]) + '</div>' + (f'<div class="note">{s["foot"]}</div>' if s.get("foot") else '')
    elif k == "pipe":
        b = '<div class="st7">' + "".join(f'<div class="c"><i>{j}</i><b>{a}</b><div class="o">{o}</div><div class="src">{src}</div></div>' for j, (a, o, src) in enumerate(s["steps"], 1)) + '</div>'
    elif k == "arch":
        b = f'<div style="margin-top:-8px;transform:scale(.95);transform-origin:top left">{arch_html()}</div>' + (f'<div style="position:absolute;right:72px;top:64px;font-size:16px;color:#8A93A0">{s["foot"]}</div>' if s.get("foot") else '')
    elif k == "gate":
        b = '<div class="gate">' + "".join(f'<div class="g"><div class="ic"><svg viewBox="0 0 48 48" fill="none" stroke="#fff" stroke-width="3">{GATE_ICONS[ic]}</svg></div><b>{a}</b><span>{c}</span></div>' for a, c, ic in s["items"]) + '</div>'
    elif k == "data":
        b = f'<div class="data">{donut_svg(s["donut"])}<div class="ins">{s["ins"]}<small>{s["sub"]}</small><div class="chips" style="margin-top:26px">' + "".join(f'<div class="chip" style="font-size:18px">{a}<small>{c}</small></div>' for a, c in s["chips"]) + '</div></div></div>'
    elif k == "eval":
        dz = "".join(f'<div class="d"><b>{a}</b><span>{c}</span></div>' for a, c in s["design"])
        tbl = "<table><tr>" + "".join(f"<th>{h}</th>" for h in s["head"]) + "</tr>" + "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in s["rows"]) + "</table>"
        hl = f'<div class="hl"><b>{s["hl_title"]}</b>' + "".join(f"<p>{x}</p>" for x in s["hl"]) + "</div>"
        b = f'<div class="ev"><div class="dz">{dz}</div><div>{tbl}</div>{hl}</div><div class="ev-foot">{s["foot"]}</div>'
    elif k == "cases":
        b = '<div class="cases">' + "".join(f'<div class="c"><div class="lab">{a}</div><h4>{c}</h4><div class="ans">{d}</div><p>{e}</p></div>' for a, c, d, e in s["cases"]) + f'</div><div class="note">{s["foot"]}</div>'
    elif k == "board":
        b = '<div class="board">' + "".join(f'<div class="it"><span class="d {st}"></span>{a}<small>{c}</small></div>' for a, c, st in s["items"]) + f'</div><div class="note">{s["foot"]}</div>'
    elif k == "pillars":
        b = '<div class="pil">' + "".join(f'<div class="c big"><i>{j}</i><div><b>{a}</b>{f"<small>{c}</small>" if c else ""}</div></div>' for j, (a, c) in enumerate(s["items"], 1)) + '</div>'
    elif k == "flywheel":
        n_ = len(s["loop"]); cx, cy, R = 370, 245, 140; nodes = ""
        for j, (a, c) in enumerate(s["loop"]):
            ang = -math.pi / 2 + 2 * math.pi * j / n_; x, y = cx + R * math.cos(ang), cy + R * math.sin(ang)
            nodes += f'<circle cx="{x:.0f}" cy="{y:.0f}" r="46" fill="#16304F"/><text x="{x:.0f}" y="{y+7:.0f}" text-anchor="middle" font-size="19" font-weight="700" fill="#fff">{a}</text>'
            lx, ly = cx + (R + 78) * math.cos(ang), cy + (R + 78) * math.sin(ang)
            anchor = "middle" if abs(math.cos(ang)) < .3 else ("start" if math.cos(ang) > 0 else "end")
            nodes += f'<text x="{lx:.0f}" y="{ly+5:.0f}" text-anchor="{anchor}" font-size="13.5" fill="#334">{c}</text>'
        ring = f'<circle cx="{cx}" cy="{cy}" r="{R}" fill="none" stroke="#D98E04" stroke-width="5" stroke-dasharray="14 10"/><path d="M{cx+R-8} {cy-22} l10 22 l-22 8" fill="none" stroke="#D98E04" stroke-width="5"/>'
        svg = f'<svg viewBox="0 0 740 470">{ring}{nodes}<text x="{cx}" y="{cy+8}" text-anchor="middle" font-size="22" font-weight="900" fill="#D98E04">越用越準</text></svg>'
        b = f'<div class="fw"><div><div class="why"><h4>{s.get("why_title","為什麼只能自己累積")}</h4>' + "".join(f"<p>・{w}</p>" for w in s["why"]) + f'</div><div class="note" style="position:static;margin-top:16px;font-size:17px">{s["update"]}</div></div>{svg}</div>'
    elif k == "revise":
        b = '<div class="rv">' + "".join(f'<div class="c{" hi" if j == 3 else ""}"><i>{j}</i><b>{a}</b><p>{c}</p></div>' for j, (a, c) in enumerate(s["steps"], 1)) + f'</div><div class="note">{s["helper"]}</div>'
    elif k == "done":
        b = '<div class="dn"><div>' + "".join(f'<div class="it"><span class="d {st}"></span>{a}</div>' for a, st in s["items"]) + '</div><div class="sc">' + "".join(f'<div class="c"><b>{p}</b><h4>{a}</h4><p>{c}</p></div>' for a, p, c in s["score"]) + f'</div></div><div class="note">{s["foot"]}</div>'
    elif k == "score":
        b = '<div class="score4">' + "".join(f'<div class="c"><b>{p}</b><h4>{a}</h4><p>{c}</p><div class="bar"><i style="width:{int(p[:-1])*2.5}%"></i></div></div>' for a, p, c in s["rows"]) + '</div>'
    return f'<div class="slide"><div class="sec">{s["sec"]}</div><h3>{s["title"]}</h3>{b}<div class="ft"><span>訴願智審臺 ｜ 2026 新北市 AI 智慧城市黑客松・法制局組</span><span>{i} / {n}</span></div></div>'

def _chrome(args, out_file):
    prof = tempfile.mkdtemp(prefix="cp-", dir=TMP)
    if os.path.exists(out_file): os.remove(out_file)
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run", "--disable-extensions", f"--user-data-dir={prof}", *args],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    t0, last, stable = time.time(), -1, 0
    while time.time() - t0 < 90:
        time.sleep(0.4)
        if p.poll() is not None and os.path.exists(out_file): break
        if os.path.exists(out_file):
            sz = os.path.getsize(out_file); stable = stable + 1 if sz == last and sz > 0 else 0; last = sz
            if stable >= 3: break
    try: os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError: pass
    if not os.path.exists(out_file): raise RuntimeError("chrome produced nothing")

def build_pdf():
    html = f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>{CSS}{ARCH_CSS}</style></head><body>' + "".join(h_slide(i + 1, s) for i, s in enumerate(S)) + "</body></html>"
    hp = f"{TMP}/deck.html"; open(hp, "w").write(html)
    _chrome(["--no-pdf-header-footer", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000", f"--print-to-pdf={OUT_PDF}", f"file://{hp}"], OUT_PDF)
    print("pdf", OUT_PDF)

def arch_png():
    hp = f"{TMP}/arch.html"
    open(hp, "w").write(f'<!doctype html><html><head><meta charset="utf-8"><style>body{{margin:0;background:#fff;zoom:2}}{ARCH_CSS}</style></head><body>{arch_html()}</body></html>')
    _chrome(["--hide-scrollbars", "--window-size=2300,1080", "--virtual-time-budget=4000", f"--screenshot={OUT_ARCH}", f"file://{hp}"], OUT_ARCH)
    print("arch", OUT_ARCH); return OUT_ARCH

# =====================================================================================
# PPTX
# =====================================================================================
FONT = "Microsoft JhengHei"
def rgb(h): return RGBColor.from_string(h)

def tb(sl, x, y, w, h, text="", size=18, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05); tf.margin_top = tf.margin_bottom = Inches(0.03)
    p = tf.paragraphs[0]; p.alignment = align
    r = p.add_run(); r.text = text; r.font.size = Pt(size); r.font.bold = bold; r.font.name = FONT; r.font.color.rgb = rgb(color)
    return box

def rect(sl, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE, lw=1, radius=0.08):
    s = sl.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
    if line: s.line.color.rgb = rgb(line); s.line.width = Pt(lw)
    else: s.line.fill.background()
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE: s.adjustments[0] = radius
    return s

def circle_txt(sl, x, y, d, text, fill=NAVY, size=13, color="FFFFFF"):
    c = rect(sl, x, y, d, d, fill, shape=MSO_SHAPE.OVAL)
    tf = c.text_frame; tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text; r.font.size = Pt(size); r.font.bold = True; r.font.name = FONT; r.font.color.rgb = rgb(color)

def frame(sl, i, n, s):
    rect(sl, 0, 0, 10.4, 0.08, NAVY); rect(sl, 10.4, 0, 2.933, 0.08, AMBER)
    tb(sl, 0.7, 0.42, 8, 0.3, s.get("sec", ""), 11, True, AMBER)
    tb(sl, 0.7, 0.66, 12, 0.8, s["title"], 28, True, NAVY)
    rect(sl, 0.7, 7.0, 11.93, 0.01, "E6EAF0")
    tb(sl, 0.7, 7.03, 8, 0.3, "訴願智審臺 ｜ 2026 新北市 AI 智慧城市黑客松・法制局組", 9.5, False, "8A93A0")
    tb(sl, 11.6, 7.03, 1.03, 0.3, f"{i} / {n}", 9.5, False, "8A93A0", PP_ALIGN.RIGHT)

def note(sl, text, y=6.15):
    rect(sl, 0.7, y, 11.93, 0.62, "FFF8EA"); rect(sl, 0.7, y, 0.07, 0.62, AMBER)
    tb(sl, 0.9, y + 0.02, 11.6, 0.6, text, 13.5, False, "334455", anchor=MSO_ANCHOR.MIDDLE)

def bullets(sl, x, y, w, h, items, size=16, color=INK, space=6):
    box = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)); tf = box.text_frame; tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph(); p.space_after = Pt(space)
        r0 = p.add_run(); r0.text = "●  "; r0.font.size = Pt(max(size - 5, 6)); r0.font.name = FONT; r0.font.color.rgb = rgb(AMBER)
        r = p.add_run(); r.text = it; r.font.size = Pt(size); r.font.name = FONT; r.font.color.rgb = rgb(color)
    return box

def table(sl, x, y, w, head, rows, col_w=None, size=11.5, row_h=0.42):
    nr, nc = len(rows) + 1, len(head)
    t = sl.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(row_h * nr)).table
    if col_w:
        for j, cw in enumerate(col_w): t.columns[j].width = Inches(cw)
    for j, h in enumerate(head):
        c = t.cell(0, j); c.text = h; c.fill.solid(); c.fill.fore_color.rgb = rgb(NAVY)
        for p in c.text_frame.paragraphs:
            p.alignment = PP_ALIGN.CENTER
            for r in p.runs: r.font.size = Pt(size); r.font.bold = True; r.font.name = FONT; r.font.color.rgb = rgb("FFFFFF")
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row):
            c = t.cell(i, j); c.text = v; c.fill.solid(); c.fill.fore_color.rgb = rgb("F7F9FB" if j == 0 else "FFFFFF")
            c.margin_top = c.margin_bottom = Inches(0.04)
            for p in c.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
                for r in p.runs:
                    r.font.size = Pt(size); r.font.name = FONT; r.font.color.rgb = rgb(NAVY if j == 0 else INK); r.font.bold = (j == 0)
                    if i == len(rows) and j > 0: r.font.color.rgb = rgb(GREEN); r.font.bold = True
    return t

def build_pptx(png):
    prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]; n = len(S)
    for i, s in enumerate(S, 1):
        sl = prs.slides.add_slide(blank); k = s["kind"]
        if k in ("cover", "end"):
            rect(sl, 0, 0, 13.333, 7.5, NAVY); rect(sl, 0, 0, 0.1, 7.5, AMBER); rect(sl, 10.2, -1.8, 5.6, 5.6, "1E3F68", shape=MSO_SHAPE.OVAL)
            top = 1.3 if k == "cover" else 2.3
            tb(sl, 1.0, top, 11, 0.4, s["tag"], 12, True, GOLD)
            tb(sl, 1.0, top + 0.45, 11.5, 1.4, s["title"], 66 if k == "cover" else 54, True, "FFFFFF")
            if s.get("sub"): tb(sl, 1.0, top + 1.85, 11.5, 0.6, s["sub"], 21, False, "C9D6E6")
            if s.get("claim"): rect(sl, 1.0, top + 2.6, 0.05, 0.75, AMBER); tb(sl, 1.15, top + 2.55, 10, 0.9, s["claim"], 17, False, "E6EDF5")
            if k == "cover":
                tb(sl, 1.0, 5.95, 10, 0.4, s["team"], 15, True, "E6EDF5"); tb(sl, 1.0, 6.5, 10, 0.4, s["url"], 12, False, "9FB0C8")
            continue
        frame(sl, i, n, s)
        if k == "pain":
            tb(sl, 0.7, 1.7, 4.2, 0.3, "困難（命題文件）", 10.5, True, "8A93A0"); tb(sl, 6.1, 1.7, 6.5, 0.3, "我們的設計", 10.5, True, "8A93A0")
            rect(sl, 0.7, 2.02, 4.2, 0.02, "E6EAF0"); rect(sl, 6.1, 2.02, 6.5, 0.02, "E6EAF0")
            for j, (a, c, d) in enumerate(s["rows"]):
                y = 2.25 + j * 1.5
                circle_txt(sl, 0.7, y + 0.3, 0.5, str(j + 1), size=15); tb(sl, 1.35, y + 0.25, 3.6, 0.7, a, 19, True, NAVY, anchor=MSO_ANCHOR.MIDDLE)
                tb(sl, 5.1, y + 0.2, 0.9, 0.7, "→", 30, True, AMBER, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
                rect(sl, 6.1, y, 6.5, 1.15, "FFF8EA", shape=MSO_SHAPE.ROUNDED_RECTANGLE); rect(sl, 6.1, y, 0.07, 1.15, AMBER)
                tb(sl, 6.3, y + 0.1, 6.2, 0.5, c, 18, True, INK); tb(sl, 6.3, y + 0.62, 6.2, 0.45, d, 12.5, False, "5B6573")
        elif k == "vs":
            rect(sl, 0.7, 1.65, 5.8, 4.9, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
            tb(sl, 1.0, 1.9, 5.3, 0.5, "✕  " + s["no"][0], 22, True, "5B6573"); tb(sl, 1.0, 2.45, 5.3, 0.9, s["no"][1], 14.5, False, "5B6573")
            rect(sl, 1.3, 4.3, 4.6, 1.2, "DDE3EA", shape=MSO_SHAPE.ROUNDED_RECTANGLE); tb(sl, 1.3, 4.3, 4.6, 1.2, "駁回", 22, True, "5B6573", PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
            tb(sl, 1.3, 5.55, 4.6, 0.4, "黑盒", 11, False, "8A93A0", PP_ALIGN.CENTER)
            rect(sl, 6.85, 1.65, 5.8, 4.9, NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
            tb(sl, 7.15, 1.9, 5.3, 0.5, "✓  " + s["yes"][0], 22, True, "FFFFFF"); tb(sl, 7.15, 2.45, 5.3, 1.0, s["yes"][1], 14.5, False, "E6EDF5")
            for j, r in enumerate(s["rows"]):
                rect(sl, 7.15, 3.85 + j * 0.62, 5.2, 0.5, "24466F", shape=MSO_SHAPE.ROUNDED_RECTANGLE); tb(sl, 7.25, 3.85 + j * 0.62, 5.0, 0.5, r, 12.5, False, "FFFFFF", anchor=MSO_ANCHOR.MIDDLE)
            y = 3.85 + len(s["rows"]) * 0.62
            rect(sl, 7.15, y, 5.2, 0.5, AMBER, shape=MSO_SHAPE.ROUNDED_RECTANGLE); tb(sl, 7.25, y, 5.0, 0.5, s["act"], 12.5, True, NAVY, anchor=MSO_ANCHOR.MIDDLE)
        elif k == "wf":
            tb(sl, 0.7, 1.32, 8, 0.4, s["subtitle"], 15, False, "8A5A00")
            colw, x0 = 2.05, 2.35
            for j, c in enumerate(s["cols"]):
                tb(sl, x0 + j * (colw + 0.12), 1.95, colw, 0.4, c, 12.5, True, "8A93A0", PP_ALIGN.CENTER); rect(sl, x0 + j * (colw + 0.12), 2.35, colw, 0.02, "E6EAF0")
            fills = {"人工": (LIGHT, "8A93A0"), "AI": (NAVY, "FFFFFF"), "承辦人": (AMBER, NAVY)}
            for r, (lab, cells) in enumerate(s["rows"]):
                y = 2.55 + r * 1.55
                tb(sl, 0.7, y, 1.6, 1.3, lab, 18, True, NAVY, anchor=MSO_ANCHOR.MIDDLE)
                for j, c in enumerate(cells):
                    f, col = fills[c]; x = x0 + j * (colw + 0.12)
                    rect(sl, x, y, colw, 1.3, f, shape=MSO_SHAPE.ROUNDED_RECTANGLE); tb(sl, x, y, colw, 1.3, c, 20, True, col, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
            note(sl, s["foot"], 6.0)
        elif k == "flow":
            for j, (a, c, _) in enumerate(s["steps"]):
                x = 0.7 + j * 2.42
                rect(sl, x + 0.55, 1.75, 1.2, 1.2, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.25)
                circle_txt(sl, x + 0.85, 2.05, 0.6, str(j + 1), size=18)
                tb(sl, x, 3.1, 2.3, 0.5, a, 20, True, NAVY, PP_ALIGN.CENTER); tb(sl, x, 3.65, 2.3, 1.2, c, 13, False, "5B6573", PP_ALIGN.CENTER)
            note(sl, s["foot"])
        elif k == "four":
            for j, (a, c, d) in enumerate(s["items"]):
                x, y = 0.7 + (j % 2) * 6.05, 1.7 + (j // 2) * 2.4
                rect(sl, x, y, 5.9, 2.15, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                circle_txt(sl, x + 0.25, y + 0.3, 0.6, "✓", GREEN, 20)
                tb(sl, x + 1.05, y + 0.22, 4.7, 0.5, a, 18, True, NAVY); tb(sl, x + 1.05, y + 0.75, 4.7, 0.5, c, 13.5, False, "334455"); tb(sl, x + 1.05, y + 1.3, 4.7, 0.5, d, 12, False, "8A5A00")
        elif k == "ba":
            rect(sl, 0.7, 1.65, 5.2, 3.25, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE); tb(sl, 0.95, 1.85, 4.8, 3.0, "\n".join(s["before"]), 14, False, "5B6573")
            tb(sl, 6.0, 2.9, 1.3, 0.9, "→", 40, True, AMBER, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
            rect(sl, 7.4, 1.65, 5.2, 3.25, "FFF8EA", AMBER, MSO_SHAPE.ROUNDED_RECTANGLE, 1.5); tb(sl, 7.65, 1.85, 4.8, 3.0, "\n".join(s["after"]), 14, False, INK)
            for j, (a, c) in enumerate(s["chips"]):
                x = 0.7 + j * 3.0
                rect(sl, x, 5.15, 2.85, 0.9, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE); tb(sl, x + 0.15, 5.17, 2.6, 0.5, a, 17, True, NAVY); tb(sl, x + 0.15, 5.62, 2.6, 0.4, c, 11, False, "5B6573")
            if s.get("foot"): note(sl, s["foot"], 6.2)
        elif k == "pipe":
            for j, (a, o, src) in enumerate(s["steps"]):
                x = 0.7 + j * 1.71
                rect(sl, x, 1.6, 1.62, 3.4, "FFFFFF", LINE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.5)
                circle_txt(sl, x + 0.12, 1.72, 0.32, str(j + 1), NAVY, 11)
                tb(sl, x + 0.08, 2.1, 1.48, 0.45, a, 13.5, True, NAVY)
                tb(sl, x + 0.08, 2.55, 1.48, 0.8, o, 11, False, INK)
                rect(sl, x + 0.12, 3.6, 1.38, 0.01, "E6EAF0")
                tb(sl, x + 0.08, 3.68, 1.48, 1.1, "依據 " + src, 10, False, "8A93A0")
        elif k == "arch":
            sl.shapes.add_picture(png, Inches(0.95), Inches(1.55), width=Inches(11.4))
            if s.get("foot"): tb(sl, 8.6, 0.42, 4.0, 0.3, s["foot"], 11, False, "8A93A0", PP_ALIGN.RIGHT)
        elif k == "gate":
            for j, (a, c, _) in enumerate(s["items"]):
                x = 0.7 + j * 3.02
                rect(sl, x, 1.7, 2.85, 4.2, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                circle_txt(sl, x + 0.95, 2.0, 0.95, str(j + 1), size=26)
                tb(sl, x + 0.15, 3.15, 2.55, 0.5, a, 18, True, NAVY, PP_ALIGN.CENTER); tb(sl, x + 0.2, 3.7, 2.45, 2.0, c, 13.5, False, "334455", PP_ALIGN.CENTER)
        elif k == "data":
            cx, cy, R = 0.9, 1.75, 3.9
            start = -90
            for name, pct, col in s["donut"]:
                arc = sl.shapes.add_shape(MSO_SHAPE.BLOCK_ARC, Inches(cx), Inches(cy), Inches(R), Inches(R))
                arc.fill.solid(); arc.fill.fore_color.rgb = rgb(col); arc.line.fill.background(); arc.shadow.inherit = False
                sweep = 360 * pct / 100
                arc.adjustments[0] = start; arc.adjustments[1] = start + sweep; arc.adjustments[2] = 0.2
                start += sweep
            tb(sl, cx, cy + 1.25, R, 0.9, f'{s["donut"][0][1]}%', 44, True, NAVY, PP_ALIGN.CENTER); tb(sl, cx, cy + 2.1, R, 0.4, s["donut"][0][0], 14, False, "5B6573", PP_ALIGN.CENTER)
            tb(sl, cx, cy + 2.45, R, 0.4, "・".join(f"{n_} {p}%" for n_, p, _ in s["donut"][1:]), 11, False, "8A93A0", PP_ALIGN.CENTER)
            tb(sl, 5.3, 1.9, 7.3, 1.2, s["ins"], 24, True, NAVY); tb(sl, 5.3, 3.15, 7.3, 0.9, s["sub"], 15, False, "5B6573")
            for j, (a, c) in enumerate(s["chips"]):
                x = 5.3 + j * 2.45
                rect(sl, x, 4.4, 2.3, 1.0, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE); tb(sl, x + 0.12, 4.43, 2.1, 0.5, a, 14, True, NAVY); tb(sl, x + 0.12, 4.9, 2.1, 0.4, c, 10.5, False, "5B6573")
        elif k == "eval":
            for j, (a, c) in enumerate(s["design"]):
                y = 1.6 + j * 1.05
                rect(sl, 0.7, y, 2.7, 0.95, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                tb(sl, 0.85, y + 0.05, 2.5, 0.35, a, 12.5, True, NAVY); tb(sl, 0.85, y + 0.38, 2.5, 0.55, c, 9.5, False, "334455")
            table(sl, 3.6, 1.6, 5.9, s["head"], [list(r) for r in s["rows"]], [0.9, 1.6, 1.8, 1.6], 9.5, 0.48)
            rect(sl, 9.75, 1.6, 2.9, 4.2, "FFF8EA", shape=MSO_SHAPE.ROUNDED_RECTANGLE); rect(sl, 9.75, 1.6, 0.07, 4.2, AMBER)
            tb(sl, 9.95, 1.7, 2.6, 0.6, s["hl_title"], 12.5, True, NAVY)
            bullets(sl, 9.95, 2.35, 2.6, 3.4, s["hl"], 10, "334455", 6)
            tb(sl, 0.7, 6.3, 11.9, 0.5, s["foot"], 9.5, False, "8A93A0")
        elif k == "cases":
            for j, (a, c, d, e) in enumerate(s["cases"]):
                x = 0.7 + j * 4.03
                rect(sl, x, 1.7, 3.85, 4.2, "FFFFFF", LINE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.5)
                tb(sl, x + 0.22, 1.85, 3.4, 0.35, a, 10.5, True, AMBER); tb(sl, x + 0.22, 2.2, 3.4, 0.55, c, 20, True, NAVY)
                rect(sl, x + 0.22, 2.85, 1.3, 0.45, NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE); tb(sl, x + 0.22, 2.85, 1.3, 0.45, d, 15, True, "FFFFFF", PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
                tb(sl, x + 0.22, 3.45, 3.4, 2.3, e, 13.5, False, "334455")
            note(sl, s["foot"])
        elif k == "board":
            for j, (a, c, st) in enumerate(s["items"]):
                x, y = 0.7 + (j % 2) * 6.1, 1.75 + (j // 2) * 0.95
                circle_txt(sl, x, y + 0.2, 0.28, "", {"on": GREEN, "half": AMBER, "off": "C5CDD8"}[st])
                tb(sl, x + 0.45, y, 4.0, 0.6, a, 18, False, NAVY, anchor=MSO_ANCHOR.MIDDLE); tb(sl, x + 4.2, y, 1.7, 0.6, c, 12, False, "5B6573", PP_ALIGN.RIGHT, MSO_ANCHOR.MIDDLE)
                rect(sl, x, y + 0.62, 5.85, 0.01, "E6EAF0")
            note(sl, s["foot"])
        elif k == "pillars":
            for j, (a, c) in enumerate(s["items"]):
                x, y = 0.7 + (j % 2) * 6.05, 1.65 + (j // 2) * 2.55
                rect(sl, x, y, 5.9, 2.35, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                circle_txt(sl, x + 0.35, y + 0.75, 0.85, str(j + 1), size=26)
                if c:
                    tb(sl, x + 1.45, y + 0.55, 4.3, 0.8, a, 26, True, NAVY, anchor=MSO_ANCHOR.MIDDLE); tb(sl, x + 1.45, y + 1.35, 4.3, 0.5, c, 14, False, "8A5A00")
                else:
                    tb(sl, x + 1.45, y + 0.4, 4.3, 1.55, a, 26, True, NAVY, anchor=MSO_ANCHOR.MIDDLE)
        elif k == "flywheel":
            rect(sl, 0.7, 1.65, 5.5, 2.9, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
            tb(sl, 0.95, 1.8, 5.0, 0.4, s.get("why_title","為什麼只能自己累積"), 15, True, NAVY)
            tb(sl, 0.95, 2.25, 5.0, 2.3, "\n".join("・" + w for w in s["why"]), 12, False, "334455")
            rect(sl, 0.7, 4.75, 5.5, 1.25, "FFF8EA"); rect(sl, 0.7, 4.75, 0.07, 1.25, AMBER); tb(sl, 0.9, 4.78, 5.2, 1.2, s["update"], 12, False, "334455", anchor=MSO_ANCHOR.MIDDLE)
            cx, cy, R = 9.6, 3.85, 1.55; n_ = len(s["loop"])
            ring = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - R), Inches(cy - R), Inches(2 * R), Inches(2 * R)); ring.fill.background(); ring.line.color.rgb = rgb(AMBER); ring.line.width = Pt(4); ring.line.dash_style = 4; ring.shadow.inherit = False
            tb(sl, cx - 1, cy - 0.3, 2, 0.6, "越用越準", 18, True, AMBER, PP_ALIGN.CENTER, MSO_ANCHOR.MIDDLE)
            for j, (a, c) in enumerate(s["loop"]):
                ang = -math.pi / 2 + 2 * math.pi * j / n_; x, y = cx + R * math.cos(ang), cy + R * math.sin(ang)
                circle_txt(sl, x - 0.45, y - 0.45, 0.9, a, size=14)
                lx, ly = cx + (R + 1.1) * math.cos(ang), cy + (R + 1.1) * math.sin(ang)
                al = PP_ALIGN.CENTER if abs(math.cos(ang)) < .3 else (PP_ALIGN.LEFT if math.cos(ang) > 0 else PP_ALIGN.RIGHT)
                tb(sl, lx - 1.1, ly - 0.25, 2.2, 0.5, c, 10.5, False, "334455", al, MSO_ANCHOR.MIDDLE)
        elif k == "revise":
            for j, (a, c) in enumerate(s["steps"]):
                x = 0.7 + j * 3.02
                rect(sl, x, 1.65, 2.85, 3.6, "FFF8EA" if j == 3 else "FFFFFF", AMBER if j == 3 else LINE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.5)
                circle_txt(sl, x + 0.2, 1.85, 0.45, str(j + 1), size=14)
                tb(sl, x + 0.2, 2.4, 2.5, 0.5, a, 16, True, NAVY); tb(sl, x + 0.2, 2.95, 2.5, 2.2, c, 12.5, False, "334455")
            note(sl, s["helper"], 5.6)
        elif k == "done":
            for j, (a, st) in enumerate(s["items"]):
                y = 1.7 + j * 0.55
                circle_txt(sl, 0.7, y + 0.15, 0.25, "", {"on": GREEN, "half": AMBER, "off": "C5CDD8"}[st])
                tb(sl, 1.1, y, 4.8, 0.55, a, 15, False, NAVY, anchor=MSO_ANCHOR.MIDDLE); rect(sl, 0.7, y + 0.52, 5.2, 0.01, "E6EAF0")
            for j, (a, p, c) in enumerate(s["score"]):
                x, y = 6.5 + (j % 2) * 3.1, 1.7 + (j // 2) * 2.0
                rect(sl, x, y, 2.95, 1.85, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                tb(sl, x + 0.18, y + 0.12, 2.6, 0.7, p, 30, True, NAVY); tb(sl, x + 0.18, y + 0.8, 2.6, 0.4, a, 14, True, NAVY); tb(sl, x + 0.18, y + 1.18, 2.6, 0.6, c, 10.5, False, "334455")
            note(sl, s["foot"])
        elif k == "score":
            for j, (a, p, c) in enumerate(s["rows"]):
                x = 0.7 + j * 3.02
                rect(sl, x, 1.7, 2.85, 4.2, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                tb(sl, x + 0.2, 1.85, 2.5, 0.9, p, 44, True, NAVY); tb(sl, x + 0.2, 2.8, 2.5, 0.5, a, 18, True, NAVY); tb(sl, x + 0.2, 3.35, 2.5, 1.8, c, 13.5, False, "334455")
                rect(sl, x + 0.2, 5.4, 2.45, 0.08, "E6EAF0"); rect(sl, x + 0.2, 5.4, 2.45 * int(p[:-1]) / 40, 0.08, AMBER)
    prs.save(OUT_PPT); print("pptx", OUT_PPT)

if __name__ == "__main__":
    build_pdf(); build_pptx(arch_png()); shutil.rmtree(TMP, ignore_errors=True)
