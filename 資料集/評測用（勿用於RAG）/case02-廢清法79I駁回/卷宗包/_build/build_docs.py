"""case02 卷宗包：訴願書、答辯書、14 份卷證。HTML → Chrome PDF → (掃描件) PIL 後製。"""
import os, subprocess, random, shutil, glob
from PIL import Image, ImageFilter, ImageEnhance, ImageChops

SP = os.path.dirname(os.path.abspath(__file__))
ROOT = "/Users/caizhengyu/testtcowork/AI智慧城市黑客松/資料集/評測用（勿用於RAG）/case02-廢清法79I駁回/卷宗包"
D1, D2, D3 = f"{ROOT}/01-訴願書", f"{ROOT}/02-答辯書", f"{ROOT}/03-卷證"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for d in (f"{SP}/html", f"{SP}/pdf", f"{SP}/png", f"{SP}/chrome-profile", D1, D2, D3):
    os.makedirs(d, exist_ok=True)
random.seed(1141061379)

# ------------------------------------------------------------------ 共用樣式
CSS = """
@page{size:A4;margin:0}
*{box-sizing:border-box}
body{margin:0;font-family:"BiauKaiTC","標楷體","Kaiti TC",serif;font-size:13.5pt;line-height:1.85;color:#111}
.page{width:210mm;height:297mm;padding:20mm 20mm 18mm;position:relative;page-break-after:always;overflow:hidden;background:#fff}
.page:last-child{page-break-after:auto}
.wm{position:absolute;left:-20mm;top:120mm;width:250mm;text-align:center;transform:rotate(-28deg);font-size:26pt;letter-spacing:.3em;color:rgba(0,0,0,.075);pointer-events:none;white-space:nowrap}
.wm2{position:absolute;right:8mm;bottom:6mm;font-size:8pt;color:#999}
h1{text-align:center;font-size:20pt;letter-spacing:.35em;margin:0 0 6mm;font-weight:normal}
h2{text-align:center;font-size:15pt;letter-spacing:.5em;margin:6mm 0 3mm;font-weight:normal}
.meta{font-size:12pt;line-height:1.7}
.meta td{padding:0 4px;vertical-align:top}
p{margin:0 0 2.5mm;text-align:justify}
.indent{text-indent:2em}
.item{padding-left:2em;text-indent:-2em}
.sub{padding-left:4em;text-indent:-2em}
.sign{margin-top:8mm;text-align:right}
.pn{position:absolute;bottom:9mm;left:0;right:0;text-align:center;font-size:10pt;color:#555}
.seal{position:absolute;width:30mm;height:30mm;border:1.1mm solid #c1272d;border-radius:50%;color:#c1272d;display:flex;align-items:center;justify-content:center;text-align:center;font-size:8.5pt;line-height:1.3;opacity:.82;transform:rotate(-7deg);padding:2mm;background:rgba(255,255,255,.0)}
.seal.sq{border-radius:2mm;width:22mm;height:22mm;font-size:9pt;transform:rotate(3deg)}
.stamp{display:inline-block;border:.6mm solid #c1272d;color:#c1272d;padding:0 2mm;font-size:10pt;transform:rotate(-4deg);opacity:.85}
.ink{color:#1d3f8f}
.hand{font-family:"Kaiti TC","BiauKaiTC";color:#1d3f8f}
.hand span{display:inline-block}
table.grid{border-collapse:collapse;width:100%;font-size:11.5pt;line-height:1.5}
table.grid th,table.grid td{border:.3mm solid #222;padding:1.6mm 2mm;vertical-align:top}
table.grid th{background:#f0f0f0;font-weight:normal;text-align:center;white-space:nowrap}
.note{font-size:10.5pt;color:#333}
.box{border:.3mm solid #222;padding:3mm 4mm}
.mono{font-family:"Menlo","Courier New",monospace}
"""
WM = '<div class="wm">黑客松測試用模擬文件 ‧ 非真實公文</div><div class="wm2">2026 新北市 AI 智慧城市黑客松 ‧ 法制局組 ‧ 評測用模擬卷證（依真實決定書 1141061379 反推）</div>'


def page(inner, pn=None, extra=""):
    return f'<div class="page">{WM}{inner}{f"<div class=pn>{pn}</div>" if pn else ""}{extra}</div>'


def html(body, css=""):
    return f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>{CSS}{css}</style></head><body>{body}</body></html>'


def hand(text, size="13.5pt"):
    """模擬手寫：每個字微幅旋轉與位移。"""
    out = []
    for ch in text:
        if ch == "\n":
            out.append("<br>")
            continue
        r = random.uniform(-3, 3)
        y = random.uniform(-0.6, 0.6)
        out.append(f'<span style="transform:rotate({r:.1f}deg) translateY({y:.1f}px)">{ch}</span>')
    return f'<span class="hand" style="font-size:{size}">{"".join(out)}</span>'


def _chrome(args, out_file):
    """Chrome 152 headless 在本機不會自行退出：等輸出檔寫完（大小穩定）後主動終止。"""
    import tempfile, time, signal
    prof = tempfile.mkdtemp(prefix="cp-", dir=f"{SP}/chrome-profile")
    if os.path.exists(out_file):
        os.remove(out_file)
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
                          "--disable-extensions", "--disable-component-update", f"--user-data-dir={prof}", *args],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    t0, last, stable = time.time(), -1, 0
    while time.time() - t0 < 60:
        time.sleep(0.4)
        if p.poll() is not None and os.path.exists(out_file):
            break
        if os.path.exists(out_file):
            sz = os.path.getsize(out_file)
            stable = stable + 1 if sz == last and sz > 0 else 0
            last = sz
            if stable >= 3:
                break
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    shutil.rmtree(prof, ignore_errors=True)
    if not os.path.exists(out_file):
        raise RuntimeError(f"chrome produced nothing: {out_file}")


def chrome_pdf(name, body, css=""):
    hp = f"{SP}/html/{name}.html"
    pp = f"{SP}/pdf/{name}.pdf"
    open(hp, "w").write(html(body, css))
    _chrome(["--no-pdf-header-footer", "--run-all-compositor-stages-before-draw",
             "--virtual-time-budget=3000", f"--print-to-pdf={pp}", f"file://{hp}"], pp)
    print("  pdf", name, flush=True)
    return pp


def chrome_shot(name, body, css="", size=(1440, 960)):
    hp = f"{SP}/html/{name}.html"
    pg = f"{SP}/png/{name}.png"
    open(hp, "w").write(f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head><body>{body}</body></html>')
    _chrome(["--hide-scrollbars", f"--window-size={size[0]},{size[1]}", "--virtual-time-budget=3000",
             f"--screenshot={pg}", f"file://{hp}"], pg)
    print("  shot", name, flush=True)
    return pg


def pdf_to_png(pdf, name, dpi=170):
    subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-singlefile", pdf, f"{SP}/png/{name}"], check=True)
    return f"{SP}/png/{name}.png"


def scanify(png, jpg_out, gray=True):
    im = Image.open(png).convert("RGB")
    w, h = im.size
    im = im.rotate(random.uniform(-0.8, 0.8), resample=Image.BICUBIC, fillcolor=(255, 255, 255))
    if gray:
        im = im.convert("L").convert("RGB")
    noise = Image.effect_noise((w, h), 22).convert("RGB")
    noise = noise.point(lambda p: 255 - abs(p - 128) // 3)
    im = ImageChops.multiply(im, noise)
    # 邊緣漸層陰影（掃描器壓不平）
    shade = Image.new("L", (w, h), 255)
    from PIL import ImageDraw
    sd = ImageDraw.Draw(shade)
    for i in range(60):
        sd.line((i, 0, i, h), fill=205 + i * 50 // 60)
    im = ImageChops.multiply(im, shade.convert("RGB"))
    im = im.filter(ImageFilter.GaussianBlur(0.55))
    im = ImageEnhance.Contrast(im).enhance(1.12)
    im = ImageEnhance.Brightness(im).enhance(0.985)
    im.save(jpg_out, "JPEG", quality=68)
    return jpg_out


def jpg_to_pdf(jpg, pdf):
    Image.open(jpg).convert("RGB").save(pdf, "PDF", resolution=170.0)
    return pdf


# ------------------------------------------------------------------ 事實常數
P = "鄭○芳"
CAR = "000-0000"
WHEN = "114 年 6 月 27 日 12 時 40 分許"
WHERE = "本市○○區○○○路○○號旁"
PEN_NO = "新北環稽字第 41-114-090351 號"
PEN_DATE = "114 年 9 月 16 日"
EPB = "新北市政府環境保護局"

# ------------------------------------------------------------------ A. 訴願書（3 頁）
def doc_appeal():
    p1 = f"""
<h1>訴　願　書</h1>
<table class="meta">
<tr><td>訴願人</td><td>：{P}</td></tr>
<tr><td></td><td>　身分證明文件字號：A2****3421　　出生年月日：（略）</td></tr>
<tr><td></td><td>　住　址：新北市○○區○○路○○巷○○號○樓</td></tr>
<tr><td></td><td>　聯絡電話：09**-***-521</td></tr>
<tr><td>原處分機關</td><td>：{EPB}</td></tr>
<tr><td>處分書發文日期及字號</td><td>：民國 {PEN_DATE}{PEN_NO}裁處書</td></tr>
<tr><td>收受或知悉行政處分之日期</td><td>：中華民國 114 年 9 月 16 日</td></tr>
<tr><td>受理訴願機關</td><td>：新北市政府</td></tr>
</table>
<h2>訴願請求事項</h2>
<p class="indent">請求撤銷原處分機關 {PEN_DATE}{PEN_NO}裁處書所為之處分。</p>
<h2>事　實</h2>
<p class="indent">緣訴願人所有車號 {CAR} 號汽車，於 {WHEN}，經原處分機關指稱訴願人於{WHERE}隨地拋棄煙蒂，致污染環境，依廢棄物清理法第 27 條第 1 款、第 50 條第 3 款及違反廢棄物清理法罰鍰額度裁罰準則第 2 條第 1 項第 1 款規定，裁處訴願人新臺幣 3,600 元罰鍰。訴願人不服，爰依法提起本件訴願。</p>
<h2>理　由</h2>
<p class="item">一、原處分機關所提出之照片未能清楚呈現所謂「煙蒂」存在之證據，僅能辨識車輛或人員位置，並未拍攝到煙蒂落地或丟棄之具體情況。原處分機關僅憑模糊照片即認定亂丟煙蒂，恐有舉證不足之情形。</p>
<p class="item">二、訴願人當時亦未有丟棄煙蒂之行為，並將煙蒂拿回車上垃圾桶丟棄，原處分機關所指違規事實與現場情況不符。</p>
"""
    p2 = f"""
<p class="item">三、訴願人於陳述意見期間業已向原處分機關說明上情，惟原處分機關未予採納，逕予裁罰，訴願人實難甘服。</p>
<p class="item">四、懇請鈞府明察，撤銷原處分，以維權益。</p>
<h2>附送證件</h2>
<table class="grid" style="width:80%;margin:0 auto">
<tr><th>名稱</th><th>數量</th><th>附註</th></tr>
<tr><td>{PEN_NO}裁處書影本</td><td style="text-align:center">1 份</td><td>如附件</td></tr>
</table>
<p style="margin-top:8mm">此　致</p>
<p style="padding-left:2em">新北市政府（經由 {EPB} 轉呈）</p>
<div class="sign" style="margin-top:14mm">
<p>訴願人：{P}　{hand("鄭○芳", "17pt")}<span class="seal sq" style="position:static;display:inline-flex;width:11mm;height:11mm;font-size:7pt;margin-left:3mm;vertical-align:middle">鄭<br>印</span></p>
<p style="margin-top:8mm">中華民國　114　年　9　月　22　日</p>
</div>
<div style="position:absolute;left:20mm;bottom:22mm" class="note">
<span class="stamp">{EPB}　114.09.22　收文</span>　<span class="mono note">收文號：1140922-0176</span>
</div>
"""
    p3 = penalty_notice(copy=True)
    body = page(p1, "第 1 頁，共 3 頁") + page(p2, "第 2 頁，共 3 頁") + page(p3, "第 3 頁，共 3 頁（附件：原處分書影本）")
    pdf = chrome_pdf("A-訴願書", body)
    shutil.copy(pdf, f"{D1}/訴願書_鄭○芳_1140922.pdf")
    return pdf


# ------------------------------------------------------------------ 裁處書（正本／影本共用）
def penalty_notice(copy=False):
    tag = '<div style="position:absolute;right:20mm;top:14mm" class="stamp">影　本</div>' if copy else '<div style="position:absolute;right:20mm;top:14mm" class="stamp">正　本</div>'
    seal = '' if copy else '<div class="seal" style="right:26mm;bottom:52mm">新北市政府<br>環境保護局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>'
    if copy:
        seal = '<div class="seal" style="right:26mm;bottom:52mm;opacity:.55;filter:grayscale(1)">新北市政府<br>環境保護局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>'
    return f"""
{tag}
<h1 style="letter-spacing:.2em">{EPB}　裁處書</h1>
<table class="meta">
<tr><td>發文日期</td><td>：中華民國 {PEN_DATE}</td></tr>
<tr><td>發文字號</td><td>：{PEN_NO}</td></tr>
<tr><td>受處分人</td><td>：{P}　（身分證明文件字號：A2****3421）</td></tr>
<tr><td>住　　址</td><td>：新北市○○區○○路○○巷○○號○樓</td></tr>
</table>
<table class="grid" style="margin-top:4mm">
<tr><th style="width:26mm">違反事實</th><td>受處分人於 {WHEN}，駕駛車號 {CAR} 號自用小客車，在{WHERE}隨地拋棄煙蒂，致污染環境，經民眾檢舉並檢附行車紀錄器影像，本局查證屬實。</td></tr>
<tr><th>違反法條</th><td>廢棄物清理法第 27 條第 1 款。</td></tr>
<tr><th>處罰依據</th><td>廢棄物清理法第 50 條第 3 款；違反廢棄物清理法罰鍰額度裁罰準則第 2 條第 1 項第 1 款及附表 1 項次 13；本局違反廢棄物清理法罰鍰額度裁罰準則（一般廢棄物）係數說明。</td></tr>
<tr><th>裁處內容</th><td>處罰鍰新臺幣 <b>3,600</b> 元整。</td></tr>
<tr><th>繳納方式</th><td>請於本裁處書送達之次日起 30 日內，持繳款單至指定金融機構或超商繳納；逾期未繳納者，依法移送強制執行。</td></tr>
<tr><th>注意事項</th><td>一、受處分人於陳述意見期間所提意見，經本局審酌後仍認違規事證明確（見說明）。<br>二、依行政罰法第 18 條第 1 項規定，審酌違反義務行為應受責難程度、所生影響，於裁罰準則係數範圍內認定污染程度係數 A＝3。</td></tr>
</table>
<p class="note" style="margin-top:4mm"><b>救濟教示：</b>受處分人如不服本處分，得於本處分書送達之次日起 30 日內，繕具訴願書並檢附本處分書影本，經由本局向新北市政府提起訴願。</p>
<div style="margin-top:12mm;text-align:right;padding-right:10mm">局長　○○○</div>
{seal}
"""


# ------------------------------------------------------------------ B. 答辯書（3 頁：檢送函 1 + 答辯書 2）
def doc_defense():
    cover = f"""
<h1 style="letter-spacing:.2em">{EPB}　函</h1>
<table class="meta">
<tr><td>受文者</td><td>：新北市政府（訴願審議委員會）</td></tr>
<tr><td>發文日期</td><td>：中華民國 114 年 10 月 6 日</td></tr>
<tr><td>發文字號</td><td>：新北環稽字第 1143520188 號</td></tr>
<tr><td>速別</td><td>：普通件</td></tr>
<tr><td>密等及解密條件或保密期限</td><td>：普通</td></tr>
<tr><td>附件</td><td>：如說明二</td></tr>
</table>
<p class="item" style="margin-top:5mm">主旨：檢送訴願人{P}因違反廢棄物清理法事件不服本局 {PEN_DATE}{PEN_NO}裁處書提起訴願案之訴願答辯書及原卷 1 宗，請查照。</p>
<p class="item">說明：</p>
<p class="sub">一、依訴願法第 58 條第 3 項規定辦理。本件訴願書經訴願人於 114 年 9 月 22 日送達本局（本局收文號 1140922-0176），本局重新審查原處分後，認原處分並無違法或不當，爰檢卷答辯。</p>
<p class="sub">二、檢附文件：（一）訴願答辯書 1 份；（二）原卷 1 宗（卷證目錄如附）；（三）採證影片電子檔 1 段（另以光碟檢送）。</p>
<p class="sub">三、本件答辯書副本已依訴願法第 58 條第 4 項規定逕送訴願人。</p>
<p class="item" style="margin-top:4mm">正本：新北市政府（訴願審議委員會）</p>
<p class="item">副本：{P}君、本局稽查科</p>
<div style="margin-top:14mm;text-align:right;padding-right:10mm">局長　○○○</div>
<div class="seal" style="right:24mm;bottom:56mm">新北市政府<br>環境保護局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    d1 = f"""
<h1>{EPB}　訴願答辯書</h1>
<table class="meta">
<tr><td>訴 願 人</td><td>：{P}　　住：新北市○○區○○路○○巷○○號○樓</td></tr>
<tr><td>原處分機關</td><td>：{EPB}　　設：新北市板橋區民族路 57 號</td></tr>
<tr><td>代 表 人</td><td>：局長 ○○○</td></tr>
<tr><td>受理訴願機關</td><td>：新北市政府</td></tr>
</table>
<p class="indent" style="margin-top:3mm">訴願人因違反廢棄物清理法事件，不服本局 {PEN_DATE}{PEN_NO}裁處書所為之處分，提起訴願，本局依法答辯如下：</p>
<h2>答辯聲明</h2>
<p class="indent">本件訴願駁回。</p>
<h2>事　實</h2>
<p class="indent">緣駕駛車號 {CAR} 號汽車（下稱系爭車輛）之駕駛人於 {WHEN}，在{WHERE}隨地拋棄煙蒂，致污染環境，經民眾於 114 年 6 月 28 日檢附行車紀錄器影像向本局檢舉（案件編號 114EPB0628-01937）。本局於 114 年 7 月 8 日審視影像、114 年 7 月 9 日查得系爭車輛車主為訴願人，並於 114 年 7 月 15 日以新北環稽字第 1143451762 號函通知訴願人陳述意見，該函於 114 年 7 月 21 日送達。訴願人於 114 年 7 月 30 日提出陳述意見書，主張並未丟棄煙蒂。本局複審影像放大照片及採證影片後，認違規事證明確，依廢棄物清理法第 27 條第 1 款、第 50 條第 3 款及違反廢棄物清理法罰鍰額度裁罰準則第 2 條第 1 項第 1 款規定，以 {PEN_DATE}{PEN_NO}裁處書裁處訴願人新臺幣 3,600 元罰鍰。裁處書於 114 年 9 月 18 日送達，訴願人不服，於 114 年 9 月 22 日提起本件訴願。</p>
<h2>理　由</h2>
<p class="item">一、程序部分：本件訴願人係就原處分之實體事項提出爭執，訴願書於法定期間內提起且程式尚無不合，程序上應予受理，進入實體審查。</p>
<p class="item">二、實體部分：</p>
<p class="sub">（一）按廢棄物清理法第 27 條第 1 款規定：「在指定清除地區內嚴禁有下列行為：一、隨地吐痰、檳榔汁、檳榔渣，拋棄紙屑、煙蒂、口香糖、瓜果或其皮、核、汁、渣或其他一般廢棄物。」、第 50 條第 3 款規定：「有下列情形之一者，處新臺幣 1 千 2 百元以上 6 千元以下罰鍰……三、為第 27 條各款行為之一。」次按違反廢棄物清理法罰鍰額度裁罰準則第 2 條第 1 項第 1 款規定，行為人違反本法義務規定之行為涉及一般廢棄物者，適用附表 1。</p>
"""
    d2 = f"""
<p class="sub">（二）訴願理由略謂：照片未能清楚呈現煙蒂存在之證據，僅能辨識車輛或人員位置，恐有舉證不足；訴願人並未丟棄煙蒂，已將煙蒂拿回車上垃圾桶丟棄云云。</p>
<p class="sub">（三）惟查，本局於事實欄所述時間、地點之採證，此有民眾檢舉之行車紀錄器影片（長度 12 秒）、擷取之稽查照片 3 幀及車籍查詢資料附卷可稽（證 1、證 2）。經審視卷附影像放大照片（證 1-2），訴願人於現場抽煙，移動至路邊水溝蓋上，並將手中煙蒂拋棄至水溝，其拋擲動作與煙蒂落點清晰可辨；復經審視採證影片第 14 秒至第 19 秒畫面，訴願人拋棄煙蒂後即轉身返回系爭車輛，煙蒂仍留置於水溝蓋上，並未見訴願人所稱將煙蒂拿回車上垃圾桶丟棄之情事。訴願人所辯，核與卷證不符，不足採信。</p>
<p class="sub">（四）本局依裁罰準則第 2 條第 1 項規定，審酌訴願人違規情節、應受責難程度及所生影響，認煙蒂係香煙濾嘴，成分為塑膠，內含重金屬、致癌物質等，容易經由下水道進入河川及海洋，造成鳥類和海洋生物誤食，甚至經由食物鏈危害人體健康，污染程度大（改制前行政院環境保護署 108 年 9 月 12 日環署毒字第 1080067666 號函參照），於不牴觸係數範圍內認定污染程度係數 A＝3，裁處 3,600 元罰鍰（計算式見證 3），於法並無不合。</p>
<p class="item">三、綜上所陳，本件訴願為無理由，爰依訴願法第 58 條第 3 項規定，檢附原卷 1 宗，敬請察核予以駁回。</p>
<h2>證　物</h2>
<table class="grid" style="width:92%;margin:0 auto">
<tr><th style="width:14mm">編號</th><th>名稱</th><th style="width:38mm">備註</th></tr>
<tr><td style="text-align:center">證 1</td><td>民眾檢舉行車紀錄器影片 1 段、擷取稽查照片 3 幀（證 1-1）及影像放大標註版（證 1-2）</td><td>影片另附電子檔</td></tr>
<tr><td style="text-align:center">證 2</td><td>公路監理資訊系統車籍查詢結果</td><td>114.07.09 查詢</td></tr>
<tr><td style="text-align:center">證 3</td><td>裁罰準則附表 1 項次 13 係數計算表</td><td></td></tr>
<tr><td style="text-align:center">證 4</td><td>陳述意見通知書、送達證書及訴願人陳述意見書</td><td></td></tr>
<tr><td style="text-align:center">證 5</td><td>裁處書、送達證書及本局裁處簽呈</td><td></td></tr>
</table>
<p style="margin-top:5mm">此　致</p>
<p style="padding-left:2em">新北市政府（訴願審議委員會）</p>
<div class="sign">
<p>原處分機關：{EPB}</p>
<p>代表人：局長　○○○</p>
<p style="margin-top:4mm">中華民國　114　年　10　月　6　日</p>
</div>
<div class="seal" style="right:22mm;bottom:22mm">新北市政府<br>環境保護局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    tight = ".tight{font-size:12pt;line-height:1.62}.tight p{margin:0 0 1.6mm}.tight h1{font-size:18pt;margin-bottom:3mm}.tight h2{font-size:13.5pt;margin:3.5mm 0 1.5mm}.tight .meta{font-size:11.5pt;line-height:1.55}.tight table.grid{font-size:10.5pt}.tight table.grid th,.tight table.grid td{padding:1mm 2mm}"
    body = page(cover, "第 1 頁，共 3 頁") + page(d1, "第 2 頁，共 3 頁").replace('class="page"','class="page tight"',1) + page(d2, "第 3 頁，共 3 頁").replace('class="page"','class="page tight"',1)
    pdf = chrome_pdf("B-答辯書", body, tight)
    shutil.copy(pdf, f"{D2}/答辯書及檢送函_環保局_1141006.pdf")
    return pdf


# ------------------------------------------------------------------ C. 卷證 00–13
ITEMS = [
    ("00", "卷證目錄", "文字 PDF", "訴願法 58 III 檢卷答辯：機關送卷時必附目錄"),
    ("01", "裁處書正本", "文字 PDF", "原行政處分本體（訴願標的）"),
    ("02", "裁處書送達證書", "掃描 JPG", "訴願法 14：訴願期間自送達次日起算之唯一證據"),
    ("03", "民眾檢舉案件受理單", "系統列印 PDF", "案件來源；記載檢舉時間、附件與承辦流程"),
    ("04", "稽查工作紀錄表", "掃描 JPG（手寫）", "稽查員審視影像之查證紀錄"),
    ("05", "採證照片彙整頁（另附 3 幀 JPG）", "文字 PDF ＋ 照片 JPG", "決定書理由四：「稽查照片…附卷可稽」"),
    ("06", "影像放大標註", "照片 JPG", "決定書理由六：「影像放大照片」"),
    ("07", "車籍查詢結果", "系統列印 PDF", "決定書理由四：「車籍查詢資料」；鎖定駕駛人＝訴願人"),
    ("08", "陳述意見通知書", "文字 PDF", "行政程序法 102：裁罰前應給予陳述意見機會"),
    ("09", "陳述意見通知書送達證書", "掃描 JPG", "證明已合法通知"),
    ("10", "訴願人陳述意見書", "掃描 JPG（手寫）", "訴願人裁罰前之主張（與訴願理由一致）"),
    ("11", "裁罰係數計算表", "文字 PDF", "決定書理由四、五：附表 1 項次 13、A＝3、3,600 元"),
    ("12", "裁處簽呈", "掃描 JPG（含核章）", "機關內部決策軌跡"),
    ("13", "採證影片截圖頁（另附 MP4）", "文字 PDF ＋ 影片 MP4", "決定書理由六：「違規影片」"),
]


def c00_index():
    rows = "".join(f"<tr><td style='text-align:center'>{n}</td><td>{t}</td><td>{f}</td><td class='note'>{w}</td></tr>" for n, t, f, w in ITEMS)
    inner = f"""
<h1 style="letter-spacing:.2em">卷　證　目　錄</h1>
<table class="meta">
<tr><td>案由</td><td>：訴願人{P}因違反廢棄物清理法事件提起訴願</td></tr>
<tr><td>原處分</td><td>：{PEN_DATE}{PEN_NO}裁處書</td></tr>
<tr><td>檢送機關</td><td>：{EPB}（稽查科）</td></tr>
<tr><td>檢送文號</td><td>：114 年 10 月 6 日新北環稽字第 1143520188 號</td></tr>
<tr><td>受理機關案號</td><td>：新北市政府訴願審議委員會 1141061379 號</td></tr>
</table>
<table class="grid" style="margin-top:4mm">
<tr><th style="width:12mm">編號</th><th>文件名稱</th><th style="width:34mm">形式</th><th>在卷理由（法律依據／決定書對應）</th></tr>
{rows}
</table>
<p class="note" style="margin-top:4mm">＊本卷共 14 件；採證影片（MP4，12 秒）與原始採證照片 3 幀以電子檔另附。訴願書（含附件裁處書影本，3 頁）及答辯書（含檢送函，3 頁）另冊裝訂，全卷合計 20 頁。</p>
"""
    return chrome_pdf("C00", page(inner))


def c01_penalty():
    return chrome_pdf("C01", page(penalty_notice(copy=False)))


def delivery_cert(name, doc_title, doc_no, send_date, recv_date, recv_sig):
    inner = f"""
<h1 style="letter-spacing:.2em">送　達　證　書</h1>
<table class="grid" style="font-size:12.5pt">
<tr><th style="width:34mm">送達機關</th><td>{EPB}</td></tr>
<tr><th>送達文書</th><td>{doc_title}<br>{doc_no}</td></tr>
<tr><th>應受送達人</th><td>{P}</td></tr>
<tr><th>送達處所</th><td>新北市○○區○○路○○巷○○號○樓</td></tr>
<tr><th>交寄日期</th><td>中華民國 {send_date}</td></tr>
<tr><th>送達方式</th><td>☑ 郵務送達（掛號）　☐ 自行送達　☐ 寄存送達　☐ 留置送達</td></tr>
<tr><th>送達結果</th><td>
<div>☑ 已交付應受送達人本人</div>
<div>☐ 已交付有辨別事理能力之同居人、受雇人或接收郵件人員（行政程序法第 73 條）</div>
<div>☐ 寄存於＿＿＿＿（行政程序法第 74 條）</div>
</td></tr>
<tr><th>送達日期</th><td>中華民國 {hand(recv_date, "15pt")}</td></tr>
<tr><th>收領人簽章</th><td style="height:22mm">{hand(recv_sig, "20pt")}　<span class="seal sq" style="position:static;display:inline-flex;width:11mm;height:11mm;font-size:7pt;vertical-align:middle">鄭<br>印</span></td></tr>
<tr><th>送達人</th><td>中華郵政 ○○郵局　郵務士 {hand("林○成", "13pt")}　<span class="stamp" style="font-size:8.5pt">○○郵局 {recv_date.replace(' 年 ', '.').replace(' 月 ', '.').replace(' 日', '')} 投遞</span></td></tr>
</table>
<p class="note" style="margin-top:4mm">附註：本證書由送達人填載後黏貼於文書送達紀錄，退回送達機關歸卷。</p>
<div style="position:absolute;left:22mm;bottom:30mm" class="note"><span class="stamp">{EPB}　收文歸卷</span></div>
"""
    pdf = chrome_pdf(name, page(inner))
    png = pdf_to_png(pdf, name)
    return scanify(png, f"{SP}/png/{name}.jpg")


def c02():
    j = delivery_cert("C02", "裁處書", PEN_NO, "114 年 9 月 16 日", "114 年 9 月 18 日", "鄭○芳")
    shutil.copy(j, f"{D3}/02-裁處書送達證書.jpg")
    return j


def c03_complaint():
    css = """body{margin:0;font-family:"PingFang TC",-apple-system,sans-serif;background:#eef1f5;color:#222}
.bar{background:#2b2f36;color:#ddd;padding:8px 14px;font-size:13px;display:flex;gap:12px;align-items:center}
.url{background:#fff;color:#333;border-radius:14px;padding:4px 12px;flex:1;font-size:13px}
.hdr{background:#1f5f3a;color:#fff;padding:10px 24px;font-size:17px;display:flex;justify-content:space-between}
.wrap{padding:18px 24px}
.card{background:#fff;border:1px solid #d5d9e0;border-radius:6px;padding:14px 18px;margin-bottom:12px}
.card h3{margin:0 0 8px;font-size:15px;color:#1f5f3a;border-bottom:2px solid #1f5f3a;padding-bottom:6px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
td,th{border:1px solid #dfe3e8;padding:7px 10px;text-align:left}
th{background:#f5f7f9;width:150px;font-weight:600;color:#444}
.tag{display:inline-block;background:#e6f2ea;color:#1f5f3a;border-radius:3px;padding:1px 8px;font-size:12px;margin-right:6px}
.flow{display:flex;gap:6px;font-size:12.5px;align-items:center}
.flow span{background:#e6f2ea;color:#1f5f3a;padding:4px 10px;border-radius:12px}
.flow i{color:#999;font-style:normal}
.wm{position:fixed;left:0;right:0;top:44%;text-align:center;transform:rotate(-20deg);font-size:34px;color:rgba(0,0,0,.06);letter-spacing:.3em}"""
    body = f"""
<div class="wm">黑客松測試用模擬畫面</div>
<div class="bar"><span>◀ ▶ ⟳</span><div class="url">https://epb-report.ntpc.gov.tw/case/view?id=114EPB0628-01937　（模擬網址）</div><span>陳○宏 ▾</span></div>
<div class="hdr"><span>新北市政府環境保護局　公害檢舉案件管理系統</span><span style="font-size:13px">列印時間 2025-07-08 10:32　列印人：稽查科 陳○宏</span></div>
<div class="wrap">
<div class="card"><h3>案件基本資料</h3>
<table>
<tr><th>案件編號</th><td><b>114EPB0628-01937</b>　<span class="tag">網路檢舉</span><span class="tag">附影片</span></td><th>受理時間</th><td>2025-06-28 09:12</td></tr>
<tr><th>檢舉類別</th><td>隨地拋棄煙蒂（廢棄物清理法第 27 條第 1 款）</td><th>案件狀態</th><td><span class="tag" style="background:#fff3e0;color:#8a4b00">查證中</span></td></tr>
<tr><th>違規時間</th><td>2025-06-27 12:40（依行車紀錄器時間戳）</td><th>違規車號</th><td><b>{CAR}</b>（自用小客車，銀色）</td></tr>
<tr><th>違規地點</th><td colspan="3">新北市○○區○○○路○○號旁（路邊停車格旁水溝蓋）</td></tr>
<tr><th>檢舉人</th><td>李○○（依公害糾紛處理法及檢舉獎勵辦法保密）</td><th>聯絡方式</th><td>09**-***-887（保密）</td></tr>
</table></div>
<div class="card"><h3>檢舉內容</h3>
<div style="font-size:13.5px;line-height:1.7">6/27 中午在○○○路等紅燈時，前方銀色轎車駕駛下車抽菸，抽完直接把菸蒂丟進路邊水溝，然後就上車走了。行車紀錄器有拍到整個過程，影片附上，截圖 3 張也附上。車牌 {CAR}。</div></div>
<div class="card"><h3>附件</h3>
<table>
<tr><th>附件 1</th><td>行車紀錄器影片　DASHCAM_20250627_124000.mp4　（12 秒，1280×720，780 KB）</td></tr>
<tr><th>附件 2</th><td>截圖 3 張　IMG_124009.jpg / IMG_124014.jpg / IMG_124019.jpg</td></tr>
</table></div>
<div class="card"><h3>處理流程</h3>
<div class="flow"><span>06-28 受理</span><i>→</i><span>07-01 分派稽查科</span><i>→</i><span>07-08 影像審視</span><i>→</i><span style="background:#eee;color:#888">車籍查詢</span><i>→</i><span style="background:#eee;color:#888">通知陳述意見</span><i>→</i><span style="background:#eee;color:#888">裁處</span></div>
</div>
</div>"""
    png = chrome_shot("C03", body, css, (1440, 900))
    inner = f"""
<h2 style="letter-spacing:.2em;margin-top:0">公害檢舉案件管理系統　畫面列印</h2>
<p class="note" style="text-align:center">案件編號 114EPB0628-01937　列印時間 2025-07-08 10:32　列印人：稽查科 陳○宏</p>
<img src="file://{png}" style="width:100%;border:.3mm solid #999;margin-top:3mm">
<p class="note" style="margin-top:4mm">附註：本頁為系統畫面列印，檢舉人個資已依規定遮蔽；影片與截圖電子檔隨卷附送。</p>
<div style="position:absolute;left:22mm;bottom:28mm" class="note"><span class="stamp">證 1　來源文件</span></div>
"""
    pdf = chrome_pdf("C03p", page(inner))
    shutil.copy(pdf, f"{D3}/03-民眾檢舉案件受理單.pdf")
    return pdf


def c04_inspection():
    inner = f"""
<h1 style="letter-spacing:.15em;font-size:18pt">{EPB}　稽查工作紀錄表</h1>
<table class="grid" style="font-size:12pt">
<tr><th style="width:30mm">案件編號</th><td>{hand("114EPB0628-01937")}</td><th style="width:26mm">稽查日期</th><td>{hand("114.07.08")}</td></tr>
<tr><th>稽查方式</th><td colspan="3">☐ 現場稽查　☑ 影像審視（民眾檢舉）　☐ 陳情訪查　☐ 其他</td></tr>
<tr><th>違規時間</th><td>{hand("114.06.27  12:40")}</td><th>違規地點</th><td>{hand("○○區○○○路○○號旁")}</td></tr>
<tr><th>行為人／車號</th><td colspan="3">{hand("車號 000-0000 銀色小客車駕駛（車籍待查）")}</td></tr>
<tr><th>違規事實</th><td colspan="3" style="height:34mm">{hand("審視檢舉人行車紀錄器影片（12秒）：12:40:09 駕駛立於車旁抽菸；12:40:14 移步至路邊水溝蓋上，右手向下拋擲煙蒂，煙蒂落於水溝蓋；12:40:19 駕駛返回駕駛座，煙蒂仍留置水溝蓋上。畫面連續、未見中斷或剪接。")}</td></tr>
<tr><th>採證方式</th><td colspan="3">{hand("擷取影片 3 幀（09s/14s/19s），另製作 14s 放大標註版")}</td></tr>
<tr><th>違反法條</th><td colspan="3">{hand("廢清法 §27①；處罰依據 §50③、裁罰準則附表1 項次13")}</td></tr>
<tr><th>初步認定</th><td colspan="3">{hand("違規事實明確，建議：查車籍→通知陳述意見→依法裁處。污染程度係數擬 A=3（煙蒂入水溝）。")}</td></tr>
<tr><th>稽查人員</th><td>{hand("陳○宏", "15pt")}　<span class="seal sq" style="position:static;display:inline-flex;width:10mm;height:10mm;font-size:7pt;vertical-align:middle">陳</span></td><th>科長核閱</th><td>{hand("已閱  7/10", "13pt")}　<span class="seal sq" style="position:static;display:inline-flex;width:10mm;height:10mm;font-size:7pt;vertical-align:middle">科長</span></td></tr>
</table>
<p class="note" style="margin-top:3mm">＊本表依本局稽查作業要點填製，一式一份歸卷。</p>
"""
    pdf = chrome_pdf("C04", page(inner))
    png = pdf_to_png(pdf, "C04")
    j = scanify(png, f"{SP}/png/C04.jpg")
    shutil.copy(j, f"{D3}/04-稽查工作紀錄表.jpg")
    return j


def c05_photos():
    ph = sorted(glob.glob(f"{D3}/05-採證照片/*.jpg"))
    caps = ["12:40:09　駕駛立於系爭車輛旁，右手持物", "12:40:14　移步至水溝蓋上，右手向下拋擲，煙蒂離手", "12:40:19　返回駕駛座，煙蒂留置於水溝蓋上"]
    imgs = "".join(f'<div style="margin-bottom:2mm"><img src="file://{p}" style="width:100%;border:.3mm solid #666"><div class="note" style="text-align:center">證 1-1-{i+1}　{c}</div></div>' for i, (p, c) in enumerate(zip(ph, caps)))
    inner = f"""
<h2 style="margin-top:0;letter-spacing:.2em">採證照片彙整頁（證 1-1）</h2>
<p class="note" style="text-align:center;margin-bottom:3mm">來源：民眾檢舉行車紀錄器影片擷取　攝於 2025/06/27（民國 114 年 6 月 27 日）　地點：{WHERE}　車號 {CAR}</p>
<div style="width:118mm;margin:0 auto">{imgs}</div>
"""
    pdf = chrome_pdf("C05", page(inner))
    shutil.copy(pdf, f"{D3}/05-採證照片彙整頁.pdf")
    return pdf


def c06_zoom_pdf():
    return jpg_to_pdf(f"{D3}/06-影像放大標註.jpg", f"{SP}/pdf/C06.pdf")


def c07_vehicle():
    css = """body{margin:0;font-family:"PingFang TC",-apple-system,sans-serif;background:#e9edf2;color:#222}
.bar{background:#2b2f36;color:#ddd;padding:8px 14px;font-size:13px;display:flex;gap:12px;align-items:center}
.url{background:#fff;color:#333;border-radius:14px;padding:4px 12px;flex:1;font-size:13px}
.hdr{background:#0d3b66;color:#fff;padding:10px 24px;font-size:17px;display:flex;justify-content:space-between}
.wrap{padding:18px 24px}
.card{background:#fff;border:1px solid #cdd3db;padding:14px 18px;margin-bottom:12px}
.card h3{margin:0 0 8px;font-size:15px;color:#0d3b66;border-bottom:2px solid #0d3b66;padding-bottom:6px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
td,th{border:1px solid #dfe3e8;padding:7px 10px;text-align:left}
th{background:#f3f5f8;width:140px;font-weight:600;color:#444}
.warn{background:#fff8e1;border:1px solid #f0d78c;padding:8px 12px;font-size:12.5px;color:#6b4e00}
.wm{position:fixed;left:0;right:0;top:44%;text-align:center;transform:rotate(-20deg);font-size:34px;color:rgba(0,0,0,.06);letter-spacing:.3em}"""
    body = f"""
<div class="wm">黑客松測試用模擬畫面</div>
<div class="bar"><span>◀ ▶ ⟳</span><div class="url">https://mvdis-gov.example/vehicle/query　（模擬網址；實務為公路監理資訊系統機關查詢介面）</div><span>陳○宏 ▾</span></div>
<div class="hdr"><span>公路監理資訊系統　機關車籍查詢</span><span style="font-size:13px">查詢時間 2025-07-09 14:07　查詢帳號：NTPC-EPB-0412（稽查科 陳○宏）</span></div>
<div class="wrap">
<div class="warn">本查詢依個人資料保護法第 15 條及公害稽查法定職掌辦理，查詢目的：公害檢舉案件（114EPB0628-01937）行為人身分確認。查詢紀錄已留存。</div>
<div class="card" style="margin-top:12px"><h3>車籍資料</h3>
<table>
<tr><th>車牌號碼</th><td><b>{CAR}</b></td><th>車種</th><td>自用小客車</td></tr>
<tr><th>廠牌／車型</th><td>NISSAN／TIIDA 1.6</td><th>顏色</th><td>銀</td></tr>
<tr><th>出廠年月</th><td>2013-05</td><th>車籍狀態</th><td>正常（未報停、未註銷）</td></tr>
<tr><th>發照日期</th><td>2013-06-14</td><th>行照有效期</th><td>—</td></tr>
</table></div>
<div class="card"><h3>車主資料</h3>
<table>
<tr><th>車主姓名</th><td><b>{P}</b></td><th>身分證字號</th><td>A2****3421</td></tr>
<tr><th>戶籍地址</th><td colspan="3">新北市○○區○○路○○巷○○號○樓</td></tr>
<tr><th>備註</th><td colspan="3">車主與檢舉影像中駕駛之關聯：影像未能辨識面貌，依行政罰法第 7 條及實務見解，以車主為推定行為人，並通知陳述意見。</td></tr>
</table></div>
</div>"""
    png = chrome_shot("C07", body, css, (1440, 800))
    inner = f"""
<h2 style="letter-spacing:.2em;margin-top:0">公路監理資訊系統　車籍查詢結果（證 2）</h2>
<p class="note" style="text-align:center">查詢時間 2025-07-09 14:07　查詢人：稽查科 陳○宏　查詢目的：案件 114EPB0628-01937 行為人身分確認</p>
<img src="file://{png}" style="width:100%;border:.3mm solid #999;margin-top:3mm">
<p class="note" style="margin-top:4mm">附註：本頁為系統畫面列印，個資已部分遮蔽。</p>
"""
    pdf = chrome_pdf("C07p", page(inner))
    shutil.copy(pdf, f"{D3}/07-車籍查詢結果.pdf")
    return pdf


def c08_notice():
    inner = f"""
<h1 style="letter-spacing:.2em">{EPB}　函</h1>
<table class="meta">
<tr><td>受文者</td><td>：{P}君</td></tr>
<tr><td>發文日期</td><td>：中華民國 114 年 7 月 15 日</td></tr>
<tr><td>發文字號</td><td>：新北環稽字第 1143451762 號</td></tr>
<tr><td>速別</td><td>：普通件</td></tr>
<tr><td>附件</td><td>：採證照片 3 幀（影本）</td></tr>
</table>
<p class="item" style="margin-top:5mm">主旨：台端所有車號 {CAR} 號自用小客車之駕駛人涉於 {WHEN}在{WHERE}隨地拋棄煙蒂，違反廢棄物清理法第 27 條第 1 款規定，請於文到之次日起 10 日內以書面向本局陳述意見，請查照。</p>
<p class="item">說明：</p>
<p class="sub">一、依行政程序法第 102 條及第 104 條規定辦理。</p>
<p class="sub">二、本局接獲民眾檢舉並檢附行車紀錄器影像（案件編號 114EPB0628-01937），經審視影像，車號 {CAR} 號自用小客車駕駛人於旨揭時間、地點有拋棄煙蒂之行為。經查該車車主為台端，爰依法通知陳述意見。</p>
<p class="sub">三、台端得於期限內以書面陳述意見，並得檢附相關證據；如台端非實際駕駛人，請一併提供實際駕駛人姓名及聯絡方式，以利查證。逾期未陳述者，本局將逕依現有事證依法處理。</p>
<p class="sub">四、依廢棄物清理法第 50 條第 3 款規定，違反同法第 27 條各款規定者，處新臺幣 1 千 2 百元以上 6 千元以下罰鍰。</p>
<p class="item" style="margin-top:4mm">正本：{P}君</p>
<p class="item">副本：本局稽查科</p>
<div style="margin-top:14mm;text-align:right;padding-right:10mm">局長　○○○</div>
<div class="seal" style="right:24mm;bottom:50mm">新北市政府<br>環境保護局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    pdf = chrome_pdf("C08", page(inner))
    shutil.copy(pdf, f"{D3}/08-陳述意見通知書.pdf")
    return pdf


def c09():
    j = delivery_cert("C09", "陳述意見通知書", "新北環稽字第 1143451762 號", "114 年 7 月 15 日", "114 年 7 月 21 日", "鄭○芳")
    shutil.copy(j, f"{D3}/09-陳述意見通知書送達證書.jpg")
    return j


def c10_statement():
    text = (
        "本人鄭○芳，收到貴局 114 年 7 月 15 日通知，說我 6 月 27 日在○○○路旁亂丟煙蒂。\n\n"
        "一、當天中午我確實有在車旁抽菸，但抽完後我有把煙蒂捏熄，並拿回車上放在門邊的小垃圾桶，並沒有丟在地上或水溝。\n\n"
        "二、貴局附的照片很模糊，只看得到我站在車旁和路邊的水溝蓋，根本看不到煙蒂，也看不出有丟東西的動作，這樣就要罰我，我覺得不公平。\n\n"
        "三、請貴局重新查明，不要開罰。\n\n"
        "以上陳述屬實。"
    )
    inner = f"""
<h1 style="letter-spacing:.3em">陳　述　意　見　書</h1>
<p class="note" style="text-align:right">貴局來函字號：新北環稽字第 1143451762 號</p>
<div style="border:.3mm solid #444;padding:6mm 7mm;min-height:150mm;line-height:2.3;background:repeating-linear-gradient(#fff 0 8.6mm,#e6e6e6 8.6mm 8.8mm)">
{hand(text, "14pt")}
</div>
<div class="sign" style="margin-top:6mm">
<p>陳述人：{hand("鄭○芳", "20pt")}　<span class="seal sq" style="position:static;display:inline-flex;width:11mm;height:11mm;font-size:7pt;vertical-align:middle">鄭<br>印</span></p>
<p>聯絡電話：{hand("09**-***-521")}</p>
<p>中華民國 {hand("114 年 7 月 30 日", "14pt")}</p>
</div>
<div style="position:absolute;left:22mm;bottom:26mm" class="note"><span class="stamp">{EPB}　114.07.31　收文</span>　<span class="mono">收文號：1140731-0092</span></div>
"""
    pdf = chrome_pdf("C10", page(inner))
    png = pdf_to_png(pdf, "C10")
    j = scanify(png, f"{SP}/png/C10.jpg")
    shutil.copy(j, f"{D3}/10-陳述意見書.jpg")
    return j


def c11_coef():
    inner = f"""
<h1 style="letter-spacing:.15em;font-size:18pt">裁罰係數計算表（證 3）</h1>
<p class="note">依據：違反廢棄物清理法罰鍰額度裁罰準則第 2 條第 1 項第 1 款及附表 1；{EPB}違反廢棄物清理法罰鍰額度裁罰準則（一般廢棄物）係數說明。</p>
<table class="grid" style="margin-top:3mm">
<tr><th style="width:30mm">案件</th><td colspan="3">{P}　車號 {CAR}　{WHEN}　{WHERE}　隨地拋棄煙蒂</td></tr>
<tr><th>違反條文</th><td colspan="3">廢棄物清理法第 27 條第 1 款</td></tr>
<tr><th>處罰條文</th><td colspan="3">廢棄物清理法第 50 條第 3 款（法定罰鍰範圍：新臺幣 1,200 元 ～ 6,000 元）</td></tr>
<tr><th>附表 1 項次</th><td colspan="3">項次 13：第 27 條第 1 款（隨地吐痰、檳榔汁、檳榔渣，拋棄紙屑、煙蒂、口香糖、瓜果或其皮、核、汁、渣或其他一般廢棄物）</td></tr>
</table>
<h2 style="font-size:13.5pt;letter-spacing:.2em;margin-top:6mm">係數審酌</h2>
<table class="grid">
<tr><th style="width:30mm">項目</th><th style="width:22mm">係數範圍</th><th style="width:20mm">認定值</th><th>審酌理由</th></tr>
<tr><td>基準額 B</td><td style="text-align:center">1,200</td><td style="text-align:center">1,200</td><td>法定罰鍰下限</td></tr>
<tr><td>污染程度係數 A<br><span class="note">（應受責難程度及所生影響）</span></td><td style="text-align:center">1 ～ 5</td><td style="text-align:center"><b>3</b></td><td>煙蒂係香煙濾嘴，成分為塑膠，內含重金屬、致癌物質等；本件煙蒂拋擲於路邊水溝，容易經由下水道進入河川及海洋，造成鳥類和海洋生物誤食，甚至經由食物鏈危害人體健康（改制前環保署 108 年 9 月 12 日環署毒字第 1080067666 號函），污染程度大於一般拋棄於路面之情形，惟非累犯，爰於係數範圍內認定 A＝3。</td></tr>
<tr><td>所得利益</td><td style="text-align:center">—</td><td style="text-align:center">0</td><td>無因違反義務所得之利益</td></tr>
<tr><td>資力考量</td><td style="text-align:center">—</td><td style="text-align:center">未調整</td><td>受處分人未主張亦無資料顯示資力不足</td></tr>
</table>
<h2 style="font-size:13.5pt;letter-spacing:.2em;margin-top:6mm">計算式</h2>
<div class="box" style="font-size:14pt;text-align:center">罰鍰額度 ＝ B × A ＝ 1,200 × 3 ＝ <b>新臺幣 3,600 元</b>　（落於法定範圍 1,200～6,000 元內）</div>
<table class="meta" style="margin-top:10mm"><tr><td>承辦：稽查科 陳○宏</td><td style="padding-left:14mm">科長：○○○</td><td style="padding-left:14mm">日期：114 年 8 月 20 日</td></tr></table>
"""
    pdf = chrome_pdf("C11", page(inner))
    shutil.copy(pdf, f"{D3}/11-裁罰係數計算表.pdf")
    return pdf


def c12_memo():
    st = lambda t: f'<span class="seal sq" style="position:static;display:inline-flex;width:14mm;height:14mm;font-size:8pt;vertical-align:middle;transform:rotate({random.uniform(-6,6):.0f}deg)">{t}</span>'
    inner = f"""
<h1 style="letter-spacing:.2em">{EPB}　簽</h1>
<table class="meta">
<tr><td>於</td><td>：稽查科</td></tr>
<tr><td>日期</td><td>：中華民國 114 年 8 月 20 日</td></tr>
<tr><td>案件編號</td><td>：114EPB0628-01937</td></tr>
</table>
<p class="item" style="margin-top:4mm">主旨：民眾檢舉車號 {CAR} 號自用小客車駕駛人（車主 {P}）於 {WHEN}在{WHERE}隨地拋棄煙蒂，違反廢棄物清理法第 27 條第 1 款，擬依同法第 50 條第 3 款裁處罰鍰新臺幣 3,600 元，簽請核示。</p>
<p class="item">說明：</p>
<p class="sub">一、本案經民眾於 114 年 6 月 28 日檢舉並檢附行車紀錄器影片，本科於 7 月 8 日審視影像、7 月 9 日查得車主，並於 7 月 15 日通知車主陳述意見（7 月 21 日送達）。</p>
<p class="sub">二、車主於 7 月 30 日提出陳述意見書，主張未丟棄煙蒂、已拿回車上，並稱照片模糊。經本科製作影像放大標註版（14 秒幀）並逐幀複審影片：14 秒幀可見拋擲動作及煙蒂離手；19 秒幀可見車主返回駕駛座而煙蒂仍留置水溝蓋上。車主所稱與影像不符，不予採信。</p>
<p class="sub">三、裁罰額度依裁罰準則附表 1 項次 13，審酌煙蒂入水溝污染程度，認定 A＝3，計 3,600 元（計算表如附）。</p>
<p class="item">擬辦：奉核後，以本局名義製發裁處書，送達受處分人，並副知檢舉人結案。</p>
<div style="margin-top:8mm;display:flex;gap:6mm;align-items:flex-start;flex-wrap:wrap">
<div>承辦：{hand("陳○宏 8/20", "13pt")} {st("陳")}</div>
<div>科長：{hand("如擬 8/22", "13pt")} {st("科長<br>○○○")}</div>
<div>主任秘書：{hand("如擬 8/26", "13pt")} {st("主秘<br>○○○")}</div>
<div>局長：{hand("可 9/10", "13pt")} {st("局長<br>○○○")}</div>
</div>
<div style="position:absolute;right:22mm;top:16mm" class="stamp">稽查科　第 114-0879 號簽</div>
"""
    pdf = chrome_pdf("C12", page(inner))
    png = pdf_to_png(pdf, "C12")
    j = scanify(png, f"{SP}/png/C12.jpg", gray=False)
    shutil.copy(j, f"{D3}/12-裁處簽呈.jpg")
    return j


def c13_video():
    shots = sorted(glob.glob(f"{SP}/png/vshot*.jpg"))
    caps = ["00:09　駕駛立於車旁", "00:12　移步至水溝蓋", "00:14　拋擲煙蒂（放大見證 1-2）", "00:17　返回駕駛座，煙蒂留置"]
    grid = "".join(f'<div><img src="file://{s}" style="width:100%;border:.3mm solid #666"><div class="note" style="text-align:center">{c}</div></div>' for s, c in zip(shots, caps))
    inner = f"""
<h2 style="margin-top:0;letter-spacing:.2em">採證影片截圖頁（證 1）</h2>
<table class="grid" style="font-size:11.5pt">
<tr><th style="width:30mm">檔名</th><td>違規採證影片_20250627-1240.mp4（原檔 DASHCAM_20250627_124000.mp4）</td></tr>
<tr><th>規格</th><td>12 秒　1280×720　15 fps　H.264　約 780 KB</td></tr>
<tr><th>來源</th><td>檢舉人行車紀錄器；時間戳 2025/06/27 12:40:08–12:40:19</td></tr>
<tr><th>審視結論</th><td>畫面連續無剪接；14 秒幀可見拋擲動作與煙蒂離手，19 秒幀可見煙蒂留置水溝蓋，駕駛已返回車內。</td></tr>
</table>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:3mm;margin-top:4mm">{grid}</div>
<p class="note" style="margin-top:4mm">附註：影片電子檔隨卷以光碟／電子檔檢送；本頁截圖供紙本卷宗閱覽。</p>
"""
    pdf = chrome_pdf("C13", page(inner))
    shutil.copy(pdf, f"{D3}/13-採證影片截圖頁.pdf")
    return pdf


def merge(pdfs, out):
    subprocess.run(["qpdf", "--empty", "--pages", *pdfs, "--", out], check=True)
    n = subprocess.run(["qpdf", "--show-npages", out], capture_output=True, text=True).stdout.strip()
    return out, n


if __name__ == "__main__":
    a = doc_appeal()
    b = doc_defense()
    c = [c00_index(), c01_penalty()]
    c.append(jpg_to_pdf(c02(), f"{SP}/pdf/C02.pdf"))
    c.append(c03_complaint())
    c.append(jpg_to_pdf(c04_inspection(), f"{SP}/pdf/C04.pdf"))
    c.append(c05_photos())
    c.append(c06_zoom_pdf())
    c.append(c07_vehicle())
    c.append(c08_notice())
    c.append(jpg_to_pdf(c09(), f"{SP}/pdf/C09.pdf"))
    c.append(jpg_to_pdf(c10_statement(), f"{SP}/pdf/C10.pdf"))
    c.append(c11_coef())
    c.append(jpg_to_pdf(c12_memo(), f"{SP}/pdf/C12.pdf"))
    c.append(c13_video())
    shutil.copy(c[0], f"{D3}/00-卷證目錄.pdf")
    shutil.copy(c[1], f"{D3}/01-裁處書正本.pdf")
    out, n = merge([a, b, *c], f"{ROOT}/卷宗全卷合併.pdf")
    print("merged", out, "pages:", n)
