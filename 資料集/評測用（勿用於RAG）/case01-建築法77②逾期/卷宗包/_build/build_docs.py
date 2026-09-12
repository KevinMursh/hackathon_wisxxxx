"""case01 卷宗包：訴願書 10 頁、答辯書 10 頁、卷證 10 頁。HTML → Chrome PDF → (掃描件) PIL 後製。
與 case02 同一套管線；案情依真實決定書 1113031004（111.12.27，77② 逾期不受理）反推。
決定書未記載違規態樣，本包以「建築法 §73 II 擅自變更使用（住宅→小吃店）」模擬，不影響程序爭點。"""
import os, subprocess, random, shutil, glob
from PIL import Image, ImageFilter, ImageEnhance, ImageChops, ImageDraw, ImageFont

SP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SP)
D1, D2, D3 = f"{ROOT}/01-訴願書", f"{ROOT}/02-答辯書", f"{ROOT}/03-卷證"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for d in (f"{SP}/html", f"{SP}/pdf", f"{SP}/png", f"{SP}/chrome-profile", D1, D2, D3, f"{D3}/04-採證照片"):
    os.makedirs(d, exist_ok=True)
random.seed(1113031004)

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
.seal{position:absolute;width:30mm;height:30mm;border:1.1mm solid #c1272d;border-radius:50%;color:#c1272d;display:flex;align-items:center;justify-content:center;text-align:center;font-size:8.5pt;line-height:1.3;opacity:.82;transform:rotate(-7deg);padding:2mm}
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
.tight{font-size:12pt;line-height:1.62}.tight p{margin:0 0 1.6mm}.tight h1{font-size:18pt;margin-bottom:3mm}.tight h2{font-size:13.5pt;margin:3.5mm 0 1.5mm}.tight .meta{font-size:11.5pt;line-height:1.55}.tight table.grid{font-size:10.5pt}.tight table.grid th,.tight table.grid td{padding:1mm 2mm}
.att{position:absolute;right:20mm;top:12mm;font-size:11pt;border:.4mm solid #333;padding:0 2mm}
"""
WM = '<div class="wm">黑客松測試用模擬文件 ‧ 非真實公文</div><div class="wm2">2026 新北市 AI 智慧城市黑客松 ‧ 法制局組 ‧ 評測用模擬卷證（依真實決定書 1113031004 反推）</div>'


def page(inner, pn=None, tight=False, extra=""):
    cls = "page tight" if tight else "page"
    return f'<div class="{cls}">{WM}{inner}{f"<div class=pn>{pn}</div>" if pn else ""}{extra}</div>'


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


def sq(text, w="11mm", fs="7pt"):
    return f'<span class="seal sq" style="position:static;display:inline-flex;width:{w};height:{w};font-size:{fs};vertical-align:middle;transform:rotate({random.uniform(-6,6):.0f}deg)">{text}</span>'


def _chrome(args, out_file):
    """Chrome headless 在本機不會自行退出：等輸出檔寫完（大小穩定）後主動終止。"""
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


def pdf_to_png(pdf, name, dpi=170, first=None):
    args = ["pdftoppm", "-r", str(dpi), "-png"]
    if first:
        args += ["-f", str(first), "-l", str(first)]
    subprocess.run([*args, "-singlefile", pdf, f"{SP}/png/{name}"], check=True)
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
    shade = Image.new("L", (w, h), 255)
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


def scan_pdf(pdf, name, gray=True):
    """文字 PDF → 掃描 JPG，回傳 (jpg, 單頁 pdf)。"""
    png = pdf_to_png(pdf, name)
    j = scanify(png, f"{SP}/png/{name}.jpg", gray=gray)
    return j, jpg_to_pdf(j, f"{SP}/pdf/{name}-scan.pdf")


def stamp_photo(src, dst, ts, width=1280):
    """加上手機／相機時間戳並縮圖存 JPEG。"""
    im = Image.open(src).convert("RGB")
    im = im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 34)
    except OSError:
        f = ImageFont.load_default()
    x, y = im.width - 20, im.height - 20
    d.text((x + 2, y + 2), ts, font=f, fill=(0, 0, 0), anchor="rd")
    d.text((x, y), ts, font=f, fill=(255, 190, 40), anchor="rd")
    im.save(dst, "JPEG", quality=82)
    return dst


# ------------------------------------------------------------------ 事實常數
P = "陳○勳"
AG = "陳○璇"
HOME = "新北市○○區○○路○段 312 巷 4 號 2 樓"
SITE = "新北市○○區○○街 ○○ 號 1 樓"
SHOP = "阿婆小吃"
GOV = "新北市政府工務局"
GOV_ADDR = "新北市板橋區中山路 1 段 161 號"
PEN_NO = "新北工使字第 1111587002 號"
PEN_DATE = "111 年 8 月 22 日"
NOTICE_NO = "新北工使字第 1111285631 號"
DEF_NO = "新北工使字第 1111962880 號"
USE_LIC = "（○○）使字第 ○○○○ 號"
INSPECT = "111 年 6 月 28 日 10 時 20 分"
CASE_ID = "1113031004"


# ------------------------------------------------------------------ 處分函＋處分書（正本／影本共用，2 頁）
def penalty_letter(copy=False):
    tag = "影　本" if copy else "正　本"
    seal_style = "opacity:.55;filter:grayscale(1)" if copy else ""
    seal = f'<div class="seal" style="right:24mm;bottom:40mm;{seal_style}">新北市政府<br>工務局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>'
    p1 = f"""
<div style="position:absolute;right:20mm;top:14mm" class="stamp">{tag}</div>
<h1 style="letter-spacing:.2em">{GOV}　函</h1>
<table class="meta">
<tr><td>受文者</td><td>：{P}君</td></tr>
<tr><td>發文日期</td><td>：中華民國 {PEN_DATE}</td></tr>
<tr><td>發文字號</td><td>：{PEN_NO}</td></tr>
<tr><td>速別</td><td>：普通件</td></tr>
<tr><td>密等及解密條件或保密期限</td><td>：普通</td></tr>
<tr><td>附件</td><td>：處分書 1 份（同文號）</td></tr>
</table>
<p class="item" style="margin-top:5mm">主旨：台端所有{SITE}建築物，未經申請核准擅自變更為餐飲場所使用，違反建築法第 73 條第 2 項規定，依同法第 91 條第 1 項第 1 款規定裁處如附件處分書，請查照。</p>
<p class="item">說明：</p>
<p class="sub">一、依建築法第 73 條第 2 項、第 91 條第 1 項第 1 款及行政罰法第 18 條第 1 項規定辦理。</p>
<p class="sub">二、旨揭建築物領有{USE_LIC}使用執照，核准用途為 H-2 類（住宅）。本局於 {INSPECT}派員現場勘查，發現 1 樓設置「{SHOP}」招牌、餐車、爐具及供不特定人用餐之桌椅，並有販售餐食之情形，屬建築物使用類組及變更使用辦法之 B-3 類（餐飲場所），核與核准用途不符，且未申請變更使用執照。</p>
<p class="sub">三、本局前以 111 年 7 月 5 日{NOTICE_NO}函請台端陳述意見，台端於 111 年 7 月 15 日提出陳述意見書，主張僅供家人自用、偶有親友聚餐。惟本局現場採證照片顯示該址設有營業招牌、菜單價目表及對外營業設施，所辯不足採；違規事實明確，爰依法裁處。</p>
<p class="sub">四、請於處分書所定期限內改善（回復核准用途）或補辦變更使用執照手續，屆期仍未改善或補辦手續而繼續使用者，本局將依建築法第 91 條第 1 項規定連續處罰，並得限期停止使用，必要時停止供水供電、封閉或強制拆除。</p>
<p class="item" style="margin-top:3mm">正本：{P}君</p>
<p class="item">副本：本局使用管理科</p>
<div style="margin-top:8mm;text-align:right;padding-right:10mm">局長　○○○</div>
{seal}
"""
    p2 = f"""
<div style="position:absolute;right:20mm;top:14mm" class="stamp">{tag}</div>
<h1 style="letter-spacing:.2em">{GOV}　處分書</h1>
<table class="meta">
<tr><td>發文日期</td><td>：中華民國 {PEN_DATE}</td></tr>
<tr><td>發文字號</td><td>：{PEN_NO}</td></tr>
<tr><td>受處分人</td><td>：{P}　（身分證明文件字號：A1****7752）</td></tr>
<tr><td>住　　址</td><td>：{HOME}</td></tr>
</table>
<table class="grid" style="margin-top:4mm">
<tr><th style="width:26mm">違規地點</th><td>{SITE}（{USE_LIC}使用執照，核准用途 H-2 類住宅）</td></tr>
<tr><th>違反事實</th><td>受處分人為上開建築物所有權人，未經申請核准，擅自將該建築物 1 樓變更為 B-3 類餐飲場所（「{SHOP}」）使用，經本局於 {INSPECT}現場勘查屬實，有勘查紀錄及採證照片附卷。</td></tr>
<tr><th>違反法條</th><td>建築法第 73 條第 2 項。</td></tr>
<tr><th>處罰依據</th><td>建築法第 91 條第 1 項第 1 款；行政罰法第 18 條第 1 項。</td></tr>
<tr><th>裁處內容</th><td>一、處罰鍰新臺幣 <b>60,000</b> 元整。<br>二、限於本處分書送達之次日起 60 日內（至遲於 111 年 10 月 23 日前）改善回復核准用途，或補辦變更使用執照手續，並報本局查驗。</td></tr>
<tr><th>繳納方式</th><td>請於本處分書送達之次日起 30 日內，持繳款單至指定金融機構繳納；逾期未繳納者，依法移送強制執行。</td></tr>
<tr><th>注意事項</th><td>屆期仍未改善或補辦手續而繼續使用者，得連續處罰，並限期停止其使用；必要時，並停止供水供電、封閉或強制拆除。</td></tr>
</table>
<p class="note" style="margin-top:4mm"><b>救濟教示：</b>受處分人如不服本處分，得於本處分書送達之次日起 30 日內，繕具訴願書並檢附本處分書影本，經由本局向新北市政府提起訴願（新北市政府訴願審議委員會，地址：{GOV_ADDR}）。</p>
<div style="margin-top:8mm;text-align:right;padding-right:10mm">局長　○○○</div>
{seal}
"""
    return p1, p2


# ------------------------------------------------------------------ A. 訴願書（10 頁）
def doc_appeal():
    pages = []
    p1 = f"""
<h1>訴　願　書</h1>
<table class="meta">
<tr><td>訴願人</td><td>：{P}</td></tr>
<tr><td></td><td>　身分證明文件字號：A1****7752　　出生年月日：民國 39 年 ○ 月 ○ 日</td></tr>
<tr><td></td><td>　住　址：{HOME}</td></tr>
<tr><td></td><td>　聯絡電話：09**-***-336</td></tr>
<tr><td>代理人</td><td>：{AG}（訴願人之女）</td></tr>
<tr><td></td><td>　身分證明文件字號：A2****0198　　住　址：同上　　聯絡電話：09**-***-114</td></tr>
<tr><td>原處分機關</td><td>：{GOV}</td></tr>
<tr><td>處分書發文日期及字號</td><td>：民國 {PEN_DATE}{PEN_NO}函併附同文號處分書</td></tr>
<tr><td>收受或知悉行政處分日期</td><td>：中華民國 111 年 8 月 24 日</td></tr>
<tr><td>受理訴願機關</td><td>：新北市政府</td></tr>
</table>
<h2>訴願請求事項</h2>
<p class="indent">請求撤銷原處分機關民國 {PEN_DATE}{PEN_NO}函併附同文號處分書所為之處分。</p>
<h2>事　實</h2>
<p class="indent">緣訴願人所有{SITE}建築物（下稱系爭建築物），經原處分機關以民眾檢舉為由，於 111 年 6 月 28 日派員至現場勘查，認訴願人未經申請核准擅自將系爭建築物變更為餐飲場所使用，違反建築法第 73 條第 2 項規定，以 {PEN_DATE}{PEN_NO}函併附同文號處分書（下稱原處分）依同法第 91 條第 1 項第 1 款規定裁處訴願人罰鍰新臺幣 6 萬元，並限期改善。訴願人於 111 年 8 月 24 日收受原處分，認原處分認事用法有誤，特提起本訴願。</p>
"""
    p2 = f"""
<h2 style="margin-top:0">理　由</h2>
<p class="item">一、系爭建築物為訴願人與家人居住逾三十年之自用住宅，並無對外營業之事實。系爭建築物 1 樓平日為訴願人之起居空間，訴願人年逾七旬，子女及親友假日常返家聚餐，訴願人偶亦烹煮滷味、麵食供親友食用，此為一般家庭之日常生活，與建築法所稱「變更使用類組」為餐飲場所使用者有別。原處分機關僅憑一次現場勘查，未查明有無對外收費營業、有無稅籍登記、營業時間及頻率等事實，即逕認系爭建築物已變更為 B-3 類餐飲場所使用，其認定事實顯有違誤。</p>
<p class="item">二、勘查當日 1 樓所置餐車、桌椅及「{SHOP}」布幔，係訴願人之女於 111 年端午連假期間為家族聚會所臨時擺設，該布幔為親友餽贈之玩笑字樣，並非營業招牌；菜單價目板亦係家人為聚會趣味所書，未曾對外收費。上開物品均已於 111 年 7 月間全數移除，系爭建築物現況回復為一般住宅（附件四照片可稽），並經○○里里長出具證明（附件五）。</p>
<p class="item">三、退步言之，縱認系爭建築物於勘查當日之使用態樣有與核准用途不符之處，惟其規模甚小、未收費營利、未影響公共安全，且訴願人於接獲通知後即自行改善，情節顯屬輕微。原處分機關未先依行政程序法第 7 條比例原則審酌以勸導、限期改善等較輕微手段即可達成目的，逕予裁處罰鍰新臺幣 6 萬元，對年邁無固定收入之訴願人而言顯屬過苛，有違比例原則及行政罰法第 18 條第 1 項應審酌受處罰者資力之規定。</p>
"""
    p3 = f"""
<p class="item">四、原處分機關 111 年 7 月 5 日{NOTICE_NO}陳述意見通知係以寄存方式送達，訴願人年事已高，未即時前往郵局領取，嗣經家人告知始知悉，倉促間所提陳述意見未能充分說明，原處分機關亦未再行查證即予裁處，程序上難謂周延。</p>
<p class="item">五、訴願人收受原處分後即著手拆除相關設施並蒐集資料，惟因年事已高、不諳法令，資料蒐集費時，遲至今日始委由其女提出本訴願，懇請鈞府體察實情。</p>
<p class="item">六、綜上，原處分認事用法均有違誤，懇請鈞府撤銷原處分，另為適法之處分，以維訴願人權益。</p>
<h2>附送證件</h2>
<table class="grid" style="width:92%;margin:0 auto">
<tr><th style="width:16mm">編號</th><th>名稱</th><th style="width:16mm">數量</th><th style="width:34mm">附註</th></tr>
<tr><td style="text-align:center">附件一</td><td>{PEN_NO}函併同文號處分書影本</td><td style="text-align:center">1 份</td><td>2 頁</td></tr>
<tr><td style="text-align:center">附件二</td><td>訴願委任書</td><td style="text-align:center">1 份</td><td>正本</td></tr>
<tr><td style="text-align:center">附件三</td><td>系爭建築物建物登記第一類謄本</td><td style="text-align:center">1 份</td><td>111.09.20 申領</td></tr>
<tr><td style="text-align:center">附件四</td><td>系爭建築物現況照片</td><td style="text-align:center">1 份</td><td>111.09.20 拍攝</td></tr>
<tr><td style="text-align:center">附件五</td><td>○○里里長證明書</td><td style="text-align:center">1 份</td><td>正本</td></tr>
<tr><td style="text-align:center">附件六</td><td>訴願人切結書</td><td style="text-align:center">1 份</td><td>正本</td></tr>
</table>
<p style="margin-top:6mm">此　致</p>
<p style="padding-left:2em">{GOV}（轉呈 新北市政府）</p>
<div class="sign" style="margin-top:6mm">
<p>訴願人：{P}　{hand("陳○勳", "17pt")}{sq("陳<br>印")}</p>
<p>代理人：{AG}　{hand("陳○璇", "17pt")}{sq("陳<br>印")}</p>
<p style="margin-top:4mm">中華民國　111　年　9　月　30　日</p>
</div>
<div style="position:absolute;left:20mm;bottom:20mm" class="note">
<span class="stamp">{GOV}　111.09.30　收文</span>　<span class="mono note">收文號：1110930-0417</span><br>
<span class="mono" style="font-size:9pt;letter-spacing:.15em;display:inline-block;margin-top:1mm;border-left:.4mm solid #000;border-right:.4mm solid #000;padding:0 2mm">|||| || ||| | |||| || | ||| |||| || |||  1110930-0417  14:52</span>
</div>
"""
    pages += [page(p1, "第 1 頁，共 10 頁"), page(p2, "第 2 頁，共 10 頁"), page(p3, "第 3 頁，共 10 頁", tight=True)]

    # 附件一：處分函＋處分書影本（2 頁）
    a1, a2 = penalty_letter(copy=True)
    pages += [page('<div class="att">附件一</div>' + a1, "第 4 頁，共 10 頁", tight=True),
              page('<div class="att">附件一</div>' + a2, "第 5 頁，共 10 頁", tight=True)]

    # 附件二：委任書（依新北市政府官方格式）
    p6 = f"""
<div class="att">附件二</div>
<h1>訴　願　委　任　書</h1>
<p class="indent" style="margin-top:8mm">委任人因違反建築法事件提起訴願一案（案號：　　　　　），謹依訴願法第 32 條委任受任人為訴願代理人，有為一切訴願行為之權，並有同法第 35 條之特別代理權（撤回訴願除外）。依訴願法第 34 條，提出本件委任書。</p>
<p style="margin-top:6mm">此　致</p>
<p style="padding-left:2em">新北市政府訴願審議委員會</p>
<table class="grid" style="margin-top:8mm;font-size:12.5pt">
<tr><th rowspan="4" style="width:18mm">委任人</th><th style="width:26mm">姓　名</th><td>{P}</td><th style="width:22mm">簽　章</th><td rowspan="4" style="text-align:center;vertical-align:middle">{hand("陳○勳", "20pt")}{sq("陳<br>印")}</td></tr>
<tr><th>身分證字號</th><td colspan="2">A1****7752</td></tr>
<tr><th>住　址</th><td colspan="2">{HOME}</td></tr>
<tr><th>聯絡電話</th><td colspan="2">09**-***-336</td></tr>
<tr><th rowspan="4">受任人</th><th>姓　名</th><td>{AG}（委任人之女）</td><th>簽　章</th><td rowspan="4" style="text-align:center;vertical-align:middle">{hand("陳○璇", "20pt")}{sq("陳<br>印")}</td></tr>
<tr><th>身分證字號</th><td colspan="2">A2****0198</td></tr>
<tr><th>住　址</th><td colspan="2">{HOME}</td></tr>
<tr><th>聯絡電話</th><td colspan="2">09**-***-114</td></tr>
</table>
<p style="text-align:center;margin-top:16mm;font-size:14pt">中　華　民　國　111　年　9　月　28　日</p>
"""
    pages.append(page(p6, "第 6 頁，共 10 頁"))

    # 附件三：建物登記第一類謄本（系統列印）
    css = """body{margin:0;font-family:"PingFang TC",-apple-system,sans-serif;background:#fff;color:#222;padding:26px 40px}
h2{text-align:center;font-size:22px;letter-spacing:.3em;margin:0 0 4px}
.sub{text-align:center;font-size:13px;color:#555;margin-bottom:14px}
table{border-collapse:collapse;width:100%;font-size:14px;margin-bottom:10px}
td,th{border:1px solid #333;padding:6px 10px;text-align:left;vertical-align:top}
th{background:#f3f3f3;width:150px;font-weight:600}
.cap{font-weight:700;font-size:15px;margin:10px 0 4px;letter-spacing:.2em}
.foot{font-size:12px;color:#444;margin-top:10px;line-height:1.6}
.wm{position:fixed;left:0;right:0;top:44%;text-align:center;transform:rotate(-20deg);font-size:34px;color:rgba(0,0,0,.06);letter-spacing:.3em}"""
    body = f"""
<div class="wm">黑客松測試用模擬畫面</div>
<h2>建物登記第一類謄本</h2>
<div class="sub">新北市○○地政事務所　列印時間：111/09/20 11:08　謄本種類碼：EB11-0920-0316　頁次：1/1</div>
<div class="cap">建物標示部</div>
<table>
<tr><th>建號</th><td>○○區○○段 01234-000</td><th>登記日期</th><td>民國 76 年 03 月 12 日</td></tr>
<tr><th>建物門牌</th><td colspan="3">{SITE.replace(' 1 樓','')}</td></tr>
<tr><th>建物坐落地號</th><td>○○段 0567-0000</td><th>主要用途</th><td><b>住家用</b></td></tr>
<tr><th>主要建材</th><td>鋼筋混凝土造</td><th>層數</th><td>5 層</td></tr>
<tr><th>建築完成日期</th><td>民國 75 年 12 月 20 日</td><th>使用執照字號</th><td>{USE_LIC}</td></tr>
<tr><th>層次／面積</th><td colspan="3">1 層：82.36 平方公尺　　2 層：82.36 平方公尺　　合計 164.72 平方公尺</td></tr>
<tr><th>附屬建物</th><td colspan="3">陽台 8.12 平方公尺</td></tr>
</table>
<div class="cap">建物所有權部</div>
<table>
<tr><th>登記次序</th><td>0002</td><th>登記日期</th><td>民國 83 年 06 月 07 日</td></tr>
<tr><th>登記原因</th><td>買賣</td><th>權利範圍</th><td>全部 1/1</td></tr>
<tr><th>所有權人</th><td><b>{P}</b></td><th>統一編號</th><td>A1****7752</td></tr>
<tr><th>住址</th><td colspan="3">{HOME}</td></tr>
</table>
<div class="cap">建物他項權利部</div>
<table><tr><td style="text-align:center;color:#666">（本建號無他項權利登記）</td></tr></table>
<div class="foot">本謄本係依電子處理之地籍資料列印，與登記簿記載相符。依土地法第 79 條之 2 規定，第一類謄本僅限登記名義人或其代理人申請。申請人：{AG}（代理人）　　新北市○○地政事務所　主任 ○○○（電子章）</div>
"""
    png = chrome_shot("A7", body, css, (1240, 1100))
    p7 = f"""
<div class="att">附件三</div>
<img src="file://{png}" style="width:100%;border:.3mm solid #999;margin-top:6mm">
<p class="note" style="margin-top:4mm">附註：本謄本用以證明訴願人為系爭建築物所有權人，且登記主要用途為「住家用」。</p>
"""
    pages.append(page(p7, "第 7 頁，共 10 頁"))

    # 附件四：訴願人拍攝之現況照片
    ph3 = stamp_photo(f"{SP}/photos/raw3.png", f"{SP}/png/A8-photo.jpg", "2022/09/20 15:07")
    p8 = f"""
<div class="att">附件四</div>
<h2 style="margin-top:0;letter-spacing:.2em">系爭建築物現況照片</h2>
<p class="note" style="text-align:center">拍攝人：{AG}　拍攝日期：111 年 9 月 20 日 15 時 07 分　地點：{SITE}</p>
<div style="width:150mm;margin:4mm auto 0"><img src="file://{ph3}" style="width:100%;border:.3mm solid #666"></div>
<p class="note" style="text-align:center;margin-top:2mm">照片 1　系爭建築物 1 樓外觀：招牌、餐車、桌椅均已移除，回復住宅使用。</p>
<p class="indent" style="margin-top:6mm;font-size:12.5pt">說明：原處分機關勘查時所見之「{SHOP}」布幔、餐車、爐具及桌椅，訴願人已於 111 年 7 月間全數移除；門首僅餘布幔拆除後之痕跡。系爭建築物現況為訴願人自住使用，無任何營業設施或對外販售行為。</p>
"""
    pages.append(page(p8, "第 8 頁，共 10 頁"))

    # 附件五：里長證明書（掃描）
    p9 = f"""
<div class="att">附件五</div>
<h1 style="letter-spacing:.3em">證　明　書</h1>
<p class="note" style="text-align:right">○○里證字第 1110921 號</p>
<p class="indent" style="margin-top:8mm;line-height:2.4;font-size:14pt">茲證明{P}君（身分證明文件字號 A1****7752）所有坐落{SITE}之房屋，為其本人及家屬長期居住之住宅。據本里辦公處所悉，該址於 111 年 7 月以後並無設置招牌、擺設攤車或對外販售餐食之情形，現況為一般住家使用。</p>
<p class="indent" style="line-height:2.4;font-size:14pt">特此證明。</p>
<p style="margin-top:14mm;font-size:14pt">此　致</p>
<p style="padding-left:2em;font-size:14pt">新北市政府訴願審議委員會</p>
<div class="sign" style="margin-top:16mm">
<p style="font-size:14pt">新北市○○區○○里辦公處</p>
<p style="font-size:14pt">里長：{hand("王○雄", "20pt")}　{sq("○○里<br>里長<br>王○雄", "16mm", "7.5pt")}</p>
<p style="margin-top:6mm;font-size:14pt">中華民國　111　年　9　月　21　日</p>
</div>
<div class="seal" style="left:26mm;bottom:34mm;width:34mm;height:34mm;font-size:8pt">新北市○○區<br>○○里辦公處<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    pdf9 = chrome_pdf("A9", page(p9))
    _, s9 = scan_pdf(pdf9, "A9", gray=False)

    # 附件六：切結書（手寫掃描）
    text = ("本人陳○勳，為新北市○○區○○街○○號1樓房屋所有權人，茲切結如下：\n\n"
            "一、該房屋為本人自住，從未辦理任何營業登記，亦未對外收費販售餐食。\n\n"
            "二、111年6月28日貴局人員到場時所見之布幔、餐車與桌椅，係家人聚會臨時擺放，已於111年7月全部拆除搬離。\n\n"
            "三、本人保證日後不再有類似情形，如有不實願負法律責任。")
    p10 = f"""
<div class="att">附件六</div>
<h1 style="letter-spacing:.3em">切　結　書</h1>
<div style="border:.3mm solid #444;padding:6mm 7mm;min-height:150mm;line-height:2.3;background:repeating-linear-gradient(#fff 0 8.6mm,#e6e6e6 8.6mm 8.8mm)">
{hand(text, "14pt")}
</div>
<div class="sign" style="margin-top:6mm">
<p>切結人：{hand("陳○勳", "20pt")}　{sq("陳<br>印")}</p>
<p>身分證明文件字號：{hand("A1****7752")}　　住址：{hand("新北市○○區○○路○段312巷4號2樓", "12pt")}</p>
<p>中華民國 {hand("111 年 9 月 26 日", "14pt")}</p>
</div>
"""
    pdf10 = chrome_pdf("A10", page(p10))
    _, s10 = scan_pdf(pdf10, "A10")

    main = chrome_pdf("A-訴願書", "".join(pages))
    out = f"{SP}/pdf/A-full.pdf"
    subprocess.run(["qpdf", "--empty", "--pages", main, s9, s10, "--", out], check=True)
    shutil.copy(out, f"{D1}/訴願書_陳○勳_1110930.pdf")
    return out


# ------------------------------------------------------------------ B. 答辯書（10 頁：檢送函 1 ＋ 答辯書 4 ＋ 附件 5）
def doc_defense():
    pages = []
    cover = f"""
<h1 style="letter-spacing:.2em">{GOV}　函</h1>
<table class="meta">
<tr><td>受文者</td><td>：新北市政府（訴願審議委員會）</td></tr>
<tr><td>發文日期</td><td>：中華民國 111 年 10 月 14 日</td></tr>
<tr><td>發文字號</td><td>：{DEF_NO}</td></tr>
<tr><td>速別</td><td>：普通件</td></tr>
<tr><td>密等及解密條件或保密期限</td><td>：普通</td></tr>
<tr><td>附件</td><td>：如說明二</td></tr>
</table>
<p class="item" style="margin-top:5mm">主旨：檢送訴願人{P}因違反建築法事件不服本局 {PEN_DATE}{PEN_NO}函併附同文號處分書提起訴願案之訴願答辯書及原卷 1 宗，請查照。</p>
<p class="item">說明：</p>
<p class="sub">一、依訴願法第 58 條第 3 項規定辦理。本件訴願書經訴願人於 111 年 9 月 30 日送達本局（本局收文號 1110930-0417），本局重新審查後，認本件訴願已逾法定期間，且原處分並無違法或不當，爰檢卷答辯。</p>
<p class="sub">二、檢附文件：（一）訴願答辯書 1 份（含附件一至五）；（二）原卷 1 宗（卷證目錄如附，共 10 頁）。</p>
<p class="sub">三、本件答辯書副本已依訴願法第 58 條第 4 項規定逕送訴願人。</p>
<p class="item" style="margin-top:4mm">正本：新北市政府（訴願審議委員會）</p>
<p class="item">副本：{P}君（代理人 {AG}）、本局使用管理科</p>
<div style="margin-top:14mm;text-align:right;padding-right:10mm">局長　○○○</div>
<div class="seal" style="right:24mm;bottom:56mm">新北市政府<br>工務局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    pages.append(page(cover, "第 1 頁，共 10 頁"))

    d1 = f"""
<h1>{GOV}　訴願答辯書</h1>
<table class="meta">
<tr><td>訴 願 人</td><td>：{P}　　住：{HOME}</td></tr>
<tr><td>代 理 人</td><td>：{AG}　　住：同上</td></tr>
<tr><td>原處分機關</td><td>：{GOV}　　設：{GOV_ADDR}</td></tr>
<tr><td>代 表 人</td><td>：局長 ○○○</td></tr>
<tr><td>受理訴願機關</td><td>：新北市政府</td></tr>
</table>
<p class="indent" style="margin-top:3mm">訴願人因違反建築法事件，不服本局 {PEN_DATE}{PEN_NO}函併附同文號處分書（下稱原處分）所為之處分，提起訴願，本局依法答辯如下：</p>
<h2>答辯聲明</h2>
<p class="indent">一、本件訴願不受理。</p>
<p class="indent">二、如認應為實體審查，請求駁回訴願。</p>
<h2>事　實</h2>
<p class="indent">緣訴願人所有{SITE}建築物（下稱系爭建築物），領有{USE_LIC}使用執照，核准用途為 H-2 類（住宅）。本局接獲民眾 111 年 6 月 14 日 1999 檢舉（案件編號 111061400873），於 {INSPECT}派員現場勘查，發現系爭建築物 1 樓設置「{SHOP}」招牌、餐車、爐具、菜單價目板及供不特定人用餐之桌椅，並有販售滷味、麵食之情形，屬建築物使用類組及變更使用辦法之 B-3 類餐飲場所，核與核准用途不符，且未申請變更使用執照。本局以 111 年 7 月 5 日{NOTICE_NO}函通知訴願人陳述意見（111 年 7 月 8 日寄存送達），訴願人於 111 年 7 月 15 日提出陳述意見書，主張僅供家人自用。本局審酌後認違規事實明確，依建築法第 73 條第 2 項、第 91 條第 1 項第 1 款規定，以原處分裁處訴願人罰鍰新臺幣 6 萬元並限期改善。原處分於 111 年 8 月 24 日郵務送達訴願人戶籍地，由訴願人本人簽收。訴願人遲至 111 年 9 月 30 日始向本局提起訴願。</p>
"""
    d2 = f"""
<h2 style="margin-top:0">理　由</h2>
<p class="item">一、程序部分：本件訴願已逾法定不變期間，應依訴願法第 77 條第 2 款為不受理之決定。</p>
<p class="sub">（一）按訴願法第 14 條第 1 項規定：「訴願之提起，應自行政處分達到或公告期滿之次日起三十日內為之。」同條第 3 項規定：「訴願之提起，以原行政處分機關或受理訴願機關收受訴願書之日期為準。」第 77 條第 2 款規定，提起訴願逾法定期間者，應為不受理之決定。次按行政程序法第 72 條第 1 項前段規定：「送達，於應受送達人之住居所、事務所或營業所為之。」</p>
<p class="sub">（二）查原處分於 111 年 8 月 24 日經郵務機關送達至訴願人戶籍地「{HOME}」，並經訴願人本人於送達證書蓋章簽收，此有送達證書附卷可稽（原卷第 02 件）；原處分書內並已教示不服處分之救濟方法、期間及受理機關。訴願人於訴願書亦自承於 111 年 8 月 24 日收受原處分，兩者相符。本件送達係交付本人，非寄存送達，無寄存生效日之爭議。</p>
<p class="sub">（三）依上開規定，本件 30 日訴願期間應自 111 年 8 月 25 日起算。訴願人設籍於新北市，與受理訴願機關新北市政府同在一地（附件三戶籍查詢結果），依訴願法第 16 條第 1 項及訴願扣除在途期間辦法，無在途期間可資扣除，其訴願期間至 111 年 9 月 23 日（星期五，非例假日）屆滿。惟訴願人遲至 111 年 9 月 30 日始將訴願書送達本局，此有訴願書上本局收文戳、收文條碼及公文系統收文登錄資料可考（附件二），已逾法定期間 7 日（期間計算詳附件一）。</p>
<p class="sub">（四）訴願人於訴願理由五雖稱因年事已高、資料蒐集費時致遲誤，惟此係可歸責於訴願人之事由，非訴願法第 15 條第 1 項所定「天災或其他不應歸責於己之事由」，訴願人亦未依同條規定申請回復原狀。是原處分業已確定，本件訴願為程序不合，應予不受理。</p>
"""
    d3 = f"""
<p class="item">二、實體部分（備位答辯）：縱認本件應為實體審查，原處分亦無違法或不當。</p>
<p class="sub">（一）按建築法第 73 條第 2 項規定：「建築物應依核定之使用類組使用，其有變更使用類組或有第九條建造行為以外主要構造、防火區劃、防火避難設施、消防設備、停車空間及其他與室內裝修有關之項目者，應申請變更使用執照。」第 91 條第 1 項第 1 款規定：「有左列情形之一者，處建築物所有權人、使用人、機械遊樂設施之經營者新臺幣六萬元以上三十萬元以下罰鍰，並限期改善或補辦手續，屆期仍未改善或補辦手續而繼續使用者，得連續處罰，並限期停止其使用。必要時，並停止供水供電、封閉或強制拆除：一、違反第七十三條第二項規定，未經核准變更使用擅自使用建築物者。」次按建築物使用類組及變更使用辦法第 2 條及附表一，H-2 類為住宅，B-3 類為餐飲場所；住宅變更為餐飲場所使用，屬使用類組之變更，應申請變更使用執照。</p>
<p class="sub">（二）訴願理由略謂：系爭建築物為自住，勘查所見餐車、桌椅、布幔係家庭聚會臨時擺設，未對外營業；縱有違規亦情節輕微且已改善，原處分未先勸導即裁罰，違反比例原則；陳述意見通知寄存送達致未充分陳述云云。</p>
<p class="sub">（三）惟查，本局 {INSPECT}現場勘查時，系爭建築物 1 樓門首懸掛「{SHOP}　滷味｜麵｜湯　營業中」招牌，門口設置不鏽鋼餐車及爐具、騎樓擺設供客用餐之折疊桌與塑膠椅，室內設有四組餐桌、飲料冷藏櫃、收銀盒及標示品項與價格之菜單板（乾麵 45、滷肉飯 30、陽春麵 40…），並有店員於餐車後方備餐，此有勘查紀錄表及採證照片 2 幀附卷可稽（原卷第 03、04 件）。上開設施之配置與標價，顯係持續對不特定人販售餐食之營業型態，核非「家庭聚會臨時擺設」所能解釋；訴願人所稱布幔為玩笑字樣、價目板為聚會趣味云云，與現場設有「營業中」標示及爐具餐車之客觀事實不符，不足採信。</p>
"""
    d4 = f"""
<p class="sub">（四）建築法第 73 條第 2 項係以建築物「有變更使用類組」之事實為規範對象，不以辦理營業登記或稅籍登記為要件；建築物是否已變更使用，應依現場使用之客觀態樣認定。系爭建築物於勘查時之使用態樣已符合 B-3 類餐飲場所之定義，訴願人未申請變更使用執照，違規事實明確。至訴願人主張事後已拆除設施回復住宅使用，此為處分後之改善行為，僅影響本局是否依同條項連續處罰，不影響原處分作成時違規事實之成立。</p>
<p class="sub">（五）關於裁罰額度，建築法第 91 條第 1 項法定罰鍰為新臺幣 6 萬元以上 30 萬元以下，本局審酌行政罰法第 18 條第 1 項所定違反行政法上義務行為應受責難程度、所生影響及所得利益，並考量訴願人為初次違規、規模較小，已裁處法定最低額 6 萬元，並未逾越法定範圍，亦無裁量濫用之情事。訴願人請求先予勸導而不裁罰，於法無據。</p>
<p class="sub">（六）本局 111 年 7 月 5 日{NOTICE_NO}陳述意見通知書，經郵務機關於 111 年 7 月 8 日依行政程序法第 74 條規定寄存於○○郵局並製作送達通知書黏貼及置於信箱，送達程序合法（原卷第 06 件）；訴願人亦已於 111 年 7 月 15 日提出陳述意見書（原卷第 07 件），其陳述意見之權利並未受剝奪，所指程序不周延，並無可採。</p>
<p class="item">三、綜上所陳，本件訴願已逾法定期間，應予不受理；縱為實體審查，訴願亦無理由。爰依訴願法第 58 條第 3 項規定，檢附原卷 1 宗，敬請察核。</p>
<h2>證　物</h2>
<table class="grid" style="width:92%;margin:0 auto">
<tr><th style="width:16mm">編號</th><th>名稱</th><th style="width:34mm">備註</th></tr>
<tr><td style="text-align:center">附件一</td><td>訴願期間計算表</td><td>本局製作</td></tr>
<tr><td style="text-align:center">附件二</td><td>本局公文管理系統收文登錄畫面（訴願書收文）</td><td>系統列印</td></tr>
<tr><td style="text-align:center">附件三</td><td>戶役政資訊系統戶籍查詢結果（訴願人設籍本市）</td><td>系統列印</td></tr>
<tr><td style="text-align:center">附件四</td><td>系爭建築物使用執照存根查詢結果（核准用途 H-2）</td><td>系統列印</td></tr>
<tr><td style="text-align:center">附件五</td><td>相關法條摘錄</td><td></td></tr>
<tr><td style="text-align:center">原卷</td><td>卷證 00–08，共 10 頁（目錄見原卷第 00 件）</td><td>另冊</td></tr>
</table>
<p style="margin-top:3mm">此　致</p>
<p style="padding-left:2em">新北市政府（訴願審議委員會）</p>
<div class="sign" style="margin-top:2mm">
<p>原處分機關：{GOV}　　代表人：局長　○○○</p>
<p>中華民國　111　年　10　月　14　日</p>
</div>
<div class="seal" style="right:22mm;bottom:20mm">新北市政府<br>工務局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    pages += [page(d1, "第 2 頁，共 10 頁", tight=True), page(d2, "第 3 頁，共 10 頁", tight=True),
              page(d3, "第 4 頁，共 10 頁", tight=True), page(d4, "第 5 頁，共 10 頁", tight=True)]

    # 附件一：訴願期間計算表
    b6 = f"""
<div class="att">附件一</div>
<h1 style="letter-spacing:.2em;font-size:18pt">訴願期間計算表</h1>
<p class="note">依據：訴願法第 14 條第 1 項、第 3 項、第 16 條第 1 項；行政程序法第 48 條、第 72 條第 1 項；訴願扣除在途期間辦法。</p>
<table class="grid" style="margin-top:3mm;font-size:12pt">
<tr><th style="width:38mm">項目</th><th style="width:40mm">日期</th><th>依據／說明</th></tr>
<tr><td>處分書發文日</td><td>111 年 8 月 22 日</td><td>{PEN_NO}</td></tr>
<tr><td>送達日（達到日）</td><td><b>111 年 8 月 24 日</b></td><td>郵務送達至訴願人戶籍地，本人蓋章簽收（原卷第 02 件送達證書）；訴願書自承收受日相同</td></tr>
<tr><td>送達方式</td><td>交付本人</td><td>非寄存送達，無行政程序法第 74 條寄存生效問題</td></tr>
<tr><td>期間起算日</td><td>111 年 8 月 25 日</td><td>行政程序法第 48 條第 2 項：始日不計入，自達到之次日起算</td></tr>
<tr><td>在途期間</td><td>0 日</td><td>訴願人設籍新北市（附件三），與受理訴願機關新北市政府同在一地，依訴願扣除在途期間辦法無在途期間</td></tr>
<tr><td>期間屆滿日</td><td><b>111 年 9 月 23 日</b></td><td>8 月 25 日起算第 30 日；該日為星期五，非星期日、國定假日或其他休息日，無行政程序法第 48 條第 4 項順延問題</td></tr>
<tr><td>訴願書收受日</td><td><b>111 年 9 月 30 日</b></td><td>本局收文號 1110930-0417，14 時 52 分櫃台收件（附件二）；訴願法第 14 條第 3 項以收受日為準</td></tr>
<tr><td>逾期日數</td><td><b>7 日</b></td><td>9 月 30 日 － 9 月 23 日</td></tr>
<tr><td>結論</td><td colspan="2"><b>已逾 30 日法定不變期間，應依訴願法第 77 條第 2 款不受理。</b>訴願人未主張亦不符訴願法第 15 條回復原狀要件。</td></tr>
</table>
<div style="margin-top:6mm;display:flex;align-items:stretch;font-size:10.5pt;line-height:1.4;text-align:center">
<div style="flex:0 0 22mm;border:.3mm solid #222;padding:2mm 1mm;background:#f0f0f0"><b>8/24</b><br>送達<br>（本人簽收）</div>
<div style="flex:1;border:.3mm solid #222;border-left:0;padding:2mm 1mm">8/25 起算（第 1 日）<br>　　……　　<br>9/23 屆滿（第 30 日）<br><span class="note">在途期間 0 日</span></div>
<div style="flex:0 0 34mm;border:.3mm solid #c1272d;border-left:0;padding:2mm 1mm;color:#c1272d">9/24 ～ 9/30<br>逾期 7 日</div>
<div style="flex:0 0 22mm;border:.3mm solid #222;border-left:0;padding:2mm 1mm;background:#f0f0f0"><b>9/30</b><br>本局收文<br>14:52</div>
</div>
<table class="meta" style="margin-top:6mm"><tr><td>製表：使用管理科 林○翰</td><td style="padding-left:14mm">科長：○○○</td><td style="padding-left:14mm">日期：111 年 10 月 12 日</td></tr></table>
"""
    pages.append(page(b6, "第 6 頁，共 10 頁"))

    # 附件二：公文系統收文登錄畫面
    css_sys = """body{margin:0;font-family:"PingFang TC",-apple-system,sans-serif;background:#e9edf2;color:#222}
.bar{background:#2b2f36;color:#ddd;padding:8px 14px;font-size:13px;display:flex;gap:12px;align-items:center}
.url{background:#fff;color:#333;border-radius:14px;padding:4px 12px;flex:1;font-size:13px}
.hdr{color:#fff;padding:10px 24px;font-size:17px;display:flex;justify-content:space-between}
.wrap{padding:18px 24px}
.card{background:#fff;border:1px solid #cdd3db;padding:14px 18px;margin-bottom:12px}
.card h3{margin:0 0 8px;font-size:15px;border-bottom:2px solid;padding-bottom:6px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
td,th{border:1px solid #dfe3e8;padding:7px 10px;text-align:left}
th{background:#f3f5f8;width:140px;font-weight:600;color:#444}
.tag{display:inline-block;border-radius:3px;padding:1px 8px;font-size:12px;margin-right:6px}
.warn{background:#fff8e1;border:1px solid #f0d78c;padding:8px 12px;font-size:12.5px;color:#6b4e00}
.wm{position:fixed;left:0;right:0;top:44%;text-align:center;transform:rotate(-20deg);font-size:34px;color:rgba(0,0,0,.06);letter-spacing:.3em}"""
    body = f"""
<div class="wm">黑客松測試用模擬畫面</div>
<div class="bar"><span>◀ ▶ ⟳</span><div class="url">https://odm.ntpc.gov.tw/receive/detail?no=1110930-0417　（模擬網址）</div><span>林○翰 ▾</span></div>
<div class="hdr" style="background:#6b3a1e"><span>新北市政府工務局　公文管理系統　收文登錄</span><span style="font-size:13px">列印時間 2022-10-12 09:41　列印人：使用管理科 林○翰</span></div>
<div class="wrap">
<div class="card" style="border-color:#6b3a1e"><h3 style="color:#6b3a1e;border-color:#6b3a1e">收文資料</h3>
<table>
<tr><th>收文號</th><td><b>1110930-0417</b>　<span class="tag" style="background:#f3e6dc;color:#6b3a1e">櫃台收件</span><span class="tag" style="background:#f3e6dc;color:#6b3a1e">訴願案件</span></td><th>收文日期時間</th><td><b>111/09/30 14:52</b></td></tr>
<tr><th>來文者</th><td>{P}（代理人 {AG}）</td><th>來文字號</th><td>（無）</td></tr>
<tr><th>來文日期</th><td>111/09/30（訴願書所載）</td><th>收件方式</th><td>親送（櫃台）</td></tr>
<tr><th>主旨</th><td colspan="3">不服本局 111 年 8 月 22 日{PEN_NO}函併附處分書，提起訴願（訴願書 1 份，附件六件）</td></tr>
<tr><th>條碼</th><td colspan="3"><span style="font-family:Menlo;letter-spacing:.2em;font-size:15px;border-left:3px solid #000;border-right:3px solid #000;padding:0 6px">|||| || ||| | |||| || | ||| |||| || |||</span>　1110930-0417</td></tr>
<tr><th>分文</th><td>使用管理科</td><th>承辦人</th><td>林○翰（111/10/03 簽收）</td></tr>
</table></div>
<div class="card" style="border-color:#6b3a1e"><h3 style="color:#6b3a1e;border-color:#6b3a1e">關聯案件</h3>
<table>
<tr><th>原處分文號</th><td>{PEN_NO}（111/08/22 發文）</td><th>送達紀錄</th><td>111/08/24 掛號送達，本人簽收</td></tr>
<tr><th>期間檢核</th><td colspan="3"><span class="tag" style="background:#fde8e8;color:#a11">系統提示：距送達日已逾 30 日（37 日）</span></td></tr>
</table></div>
</div>"""
    png = chrome_shot("B7", body, css_sys, (1440, 760))
    b7 = f"""
<div class="att">附件二</div>
<h2 style="letter-spacing:.2em;margin-top:0">公文管理系統　收文登錄畫面列印</h2>
<p class="note" style="text-align:center">收文號 1110930-0417　列印時間 111/10/12 09:41　列印人：使用管理科 林○翰</p>
<img src="file://{png}" style="width:100%;border:.3mm solid #999;margin-top:3mm">
<p class="note" style="margin-top:4mm">附註：本頁為系統畫面列印，用以證明訴願書於 111 年 9 月 30 日 14 時 52 分送達本局。</p>
"""
    pages.append(page(b7, "第 7 頁，共 10 頁"))

    # 附件三：戶役政查詢
    body = f"""
<div class="wm">黑客松測試用模擬畫面</div>
<div class="bar"><span>◀ ▶ ▶</span><div class="url">https://ris-gov.example/query/household　（模擬網址；實務為戶役政資訊系統機關查詢介面）</div><span>林○翰 ▾</span></div>
<div class="hdr" style="background:#0d3b66"><span>戶役政資訊系統　機關查詢（戶籍資料）</span><span style="font-size:13px">查詢時間 2022-10-12 09:50　查詢帳號：NTPC-PWB-0871（使用管理科 林○翰）</span></div>
<div class="wrap">
<div class="warn">本查詢依個人資料保護法第 15 條及訴願法第 16 條在途期間認定之法定職掌辦理，查詢目的：訴願案件（本局收文 1110930-0417）訴願人設籍地確認。查詢紀錄已留存。</div>
<div class="card" style="margin-top:12px;border-color:#0d3b66"><h3 style="color:#0d3b66;border-color:#0d3b66">戶籍資料</h3>
<table>
<tr><th>姓名</th><td><b>{P}</b></td><th>統一編號</th><td>A1****7752</td></tr>
<tr><th>出生日期</th><td>民國 39 年 ○ 月 ○ 日</td><th>戶籍狀態</th><td>現戶（在籍）</td></tr>
<tr><th>戶籍地址</th><td colspan="3"><b>{HOME}</b></td></tr>
<tr><th>遷入本址日期</th><td>民國 83 年 07 月 15 日</td><th>戶長</th><td>{P}（本人）</td></tr>
<tr><th>同戶人口</th><td colspan="3">{AG}（女）等共 3 人</td></tr>
</table></div>
<div class="card" style="border-color:#0d3b66"><h3 style="color:#0d3b66;border-color:#0d3b66">查詢結論</h3>
<table>
<tr><th>設籍縣市</th><td><b>新北市</b></td><th>受理訴願機關所在地</th><td>新北市（新北市政府，板橋區）</td></tr>
<tr><th>在途期間</th><td colspan="3"><span class="tag" style="background:#e6f2ea;color:#1f5f3a">同一直轄市：依訴願扣除在途期間辦法，無在途期間</span></td></tr>
</table></div>
</div>"""
    png = chrome_shot("B8", body, css_sys, (1440, 760))
    b8 = f"""
<div class="att">附件三</div>
<h2 style="letter-spacing:.2em;margin-top:0">戶役政資訊系統　戶籍查詢結果</h2>
<p class="note" style="text-align:center">查詢時間 111/10/12 09:50　查詢人：使用管理科 林○翰　查詢目的：訴願人設籍地確認（在途期間認定）</p>
<img src="file://{png}" style="width:100%;border:.3mm solid #999;margin-top:3mm">
<p class="note" style="margin-top:4mm">附註：本頁為系統畫面列印，個資已部分遮蔽。訴願人設籍新北市，無在途期間。</p>
"""
    pages.append(page(b8, "第 8 頁，共 10 頁"))

    # 附件四：使用執照存根查詢
    body = f"""
<div class="wm">黑客松測試用模擬畫面</div>
<div class="bar"><span>◀ ▶ ⟳</span><div class="url">https://building.ntpc.gov.tw/license/query?no=...　（模擬網址）</div><span>林○翰 ▾</span></div>
<div class="hdr" style="background:#1f5f3a"><span>新北市政府工務局　建築執照管理系統　使用執照存根查詢</span><span style="font-size:13px">查詢時間 2022-06-27 16:20　查詢人：使用管理科 林○翰</span></div>
<div class="wrap">
<div class="card" style="border-color:#1f5f3a"><h3 style="color:#1f5f3a;border-color:#1f5f3a">使用執照基本資料</h3>
<table>
<tr><th>執照字號</th><td><b>{USE_LIC}</b></td><th>發照日期</th><td>民國 75 年 12 月 20 日</td></tr>
<tr><th>建築地點</th><td colspan="3">新北市○○區○○街 ○○ 號（○○段 0567-0000 地號）</td></tr>
<tr><th>構造／層數</th><td>鋼筋混凝土造　地上 5 層</td><th>起造人</th><td>○○建設股份有限公司</td></tr>
</table></div>
<div class="card" style="border-color:#1f5f3a"><h3 style="color:#1f5f3a;border-color:#1f5f3a">核准用途（各層）</h3>
<table>
<tr><th>樓層</th><th style="width:auto">核准用途</th><th>使用類組</th><th>面積（㎡）</th></tr>
<tr><td>1 層</td><td><b>住宅</b></td><td><b>H-2</b></td><td>82.36</td></tr>
<tr><td>2 層</td><td>住宅</td><td>H-2</td><td>82.36</td></tr>
<tr><td>3 ～ 5 層</td><td>住宅</td><td>H-2</td><td>各 82.36</td></tr>
</table></div>
<div class="card" style="border-color:#1f5f3a"><h3 style="color:#1f5f3a;border-color:#1f5f3a">變更使用執照申請紀錄</h3>
<table><tr><td style="text-align:center;color:#666">（查無本址 1 層之變更使用執照申請或核准紀錄）</td></tr></table></div>
</div>"""
    png = chrome_shot("B9", body, css_sys, (1440, 760))
    b9 = f"""
<div class="att">附件四</div>
<h2 style="letter-spacing:.2em;margin-top:0">建築執照管理系統　使用執照存根查詢結果</h2>
<p class="note" style="text-align:center">查詢時間 111/06/27 16:20　查詢人：使用管理科 林○翰　查詢目的：檢舉案件 111061400873 核准用途確認</p>
<img src="file://{png}" style="width:100%;border:.3mm solid #999;margin-top:3mm">
<p class="note" style="margin-top:4mm">附註：系爭建築物 1 層核准用途為 H-2 類住宅，查無變更使用執照紀錄。</p>
"""
    pages.append(page(b9, "第 9 頁，共 10 頁"))

    # 附件五：相關法條摘錄
    b10 = f"""
<div class="att">附件五</div>
<h1 style="letter-spacing:.2em;font-size:18pt">相關法條摘錄</h1>
<p class="item"><b>訴願法第 14 條第 1 項、第 3 項</b>：訴願之提起，應自行政處分達到或公告期滿之次日起三十日內為之。／訴願之提起，以原行政處分機關或受理訴願機關收受訴願書之日期為準。</p>
<p class="item"><b>訴願法第 15 條第 1 項</b>：訴願人因天災或其他不應歸責於己之事由，致遲誤前條之訴願期間者，於其原因消滅後十日內，得以書面敘明理由向受理訴願機關申請回復原狀。但遲誤訴願期間已逾一年者，不得為之。</p>
<p class="item"><b>訴願法第 16 條第 1 項</b>：訴願人不在受理訴願機關所在地住居者，計算法定期間，應扣除其在途期間。但有訴願代理人住居受理訴願機關所在地，得為期間內應為之訴願行為者，不在此限。</p>
<p class="item"><b>訴願法第 77 條第 2 款</b>：訴願事件有左列各款情形之一者，應為不受理之決定：……二、提起訴願逾法定期間或未於第五十七條但書所定期間內補送訴願書者。</p>
<p class="item"><b>行政程序法第 48 條第 2 項</b>：期間之計算，以日、星期、月或年計算者，其始日不計算在內。但法律規定即日起算者，不在此限。</p>
<p class="item"><b>行政程序法第 72 條第 1 項</b>：送達，於應受送達人之住居所、事務所或營業所為之。但在行政機關辦公處所或他處會晤應受送達人時，得於會晤處所為之。</p>
<p class="item"><b>行政程序法第 74 條第 1 項、第 2 項</b>：送達，不能依前二條規定為之者，得將文書寄存送達地之地方自治或警察機關，並作送達通知書兩份，一份黏貼於應受送達人住居所、事務所、營業所或其就業處所門首，另一份交由鄰居轉交或置於該送達處所信箱或其他適當位置，以為送達。／前項情形，由郵政機關為送達者，得將文書寄存於送達地之郵政機關。</p>
<p class="item"><b>建築法第 73 條第 2 項</b>：建築物應依核定之使用類組使用，其有變更使用類組或有第九條建造行為以外主要構造、防火區劃、防火避難設施、消防設備、停車空間及其他與室內裝修有關之項目者，應申請變更使用執照。但建築物在一定規模以下之使用變更，不在此限。</p>
<p class="item"><b>建築法第 91 條第 1 項第 1 款</b>：有左列情形之一者，處建築物所有權人、使用人、機械遊樂設施之經營者新臺幣六萬元以上三十萬元以下罰鍰，並限期改善或補辦手續，屆期仍未改善或補辦手續而繼續使用者，得連續處罰，並限期停止其使用。必要時，並停止供水供電、封閉或強制拆除：一、違反第七十三條第二項規定，未經核准變更使用擅自使用建築物者。</p>
<p class="item"><b>行政罰法第 18 條第 1 項</b>：裁處罰鍰，應審酌違反行政法上義務行為應受責難程度、所生影響及因違反行政法上義務所得之利益，並得考量受處罰者之資力。</p>
"""
    pages.append(page(b10, "第 10 頁，共 10 頁", tight=True))

    pdf = chrome_pdf("B-答辯書", "".join(pages))
    shutil.copy(pdf, f"{D2}/答辯書及檢送函_工務局_1111014.pdf")
    return pdf


# ------------------------------------------------------------------ C. 卷證 00–08（10 頁）
ITEMS = [
    ("00", "卷證目錄", "文字 PDF", "訴願法 58 III 檢卷答辯：機關送卷時必附目錄"),
    ("01", "處分函併附處分書正本（2 頁）", "文字 PDF", "原行政處分本體（訴願標的）；內載救濟教示"),
    ("02", "處分書送達證書", "掃描 JPG", "訴願法 14：訴願期間自送達次日起算之唯一證據（本人簽收、郵務送達）"),
    ("03", "現場勘查紀錄表", "掃描 JPG（手寫）", "111.6.28 勘查；決定書未及實體，備位答辯用"),
    ("04", "採證照片彙整頁（另附 2 幀 JPG）", "文字 PDF ＋ 照片 JPG", "勘查當日外觀與室內採證"),
    ("05", "陳述意見通知書", "文字 PDF", "行政程序法 102：裁罰前應給予陳述意見機會"),
    ("06", "陳述意見通知書送達證書", "掃描 JPG", "寄存送達（行政程序法 74）；與第 02 件送達方式不同"),
    ("07", "訴願人陳述意見書", "掃描 JPG（手寫）", "訴願人裁罰前之主張（與訴願理由一致）"),
    ("08", "裁處簽呈", "掃描 JPG（含核章）", "機關內部決策軌跡"),
]


def c00_index():
    rows = "".join(f"<tr><td style='text-align:center'>{n}</td><td>{t}</td><td>{f}</td><td class='note'>{w}</td></tr>" for n, t, f, w in ITEMS)
    inner = f"""
<h1 style="letter-spacing:.2em">卷　證　目　錄</h1>
<table class="meta">
<tr><td>案由</td><td>：訴願人{P}因違反建築法事件提起訴願</td></tr>
<tr><td>原處分</td><td>：{PEN_DATE}{PEN_NO}函併附同文號處分書</td></tr>
<tr><td>檢送機關</td><td>：{GOV}（使用管理科）</td></tr>
<tr><td>檢送文號</td><td>：111 年 10 月 14 日{DEF_NO}</td></tr>
<tr><td>受理機關案號</td><td>：新北市政府訴願審議委員會 {CASE_ID} 號</td></tr>
</table>
<table class="grid" style="margin-top:4mm">
<tr><th style="width:12mm">編號</th><th>文件名稱</th><th style="width:34mm">形式</th><th>在卷理由（法律依據／決定書對應）</th></tr>
{rows}
</table>
<p class="note" style="margin-top:4mm">＊本卷共 9 件 10 頁；採證照片原始檔 2 幀以電子檔另附。訴願書（含附件，10 頁）及答辯書（含檢送函與附件，10 頁）另冊裝訂，全卷合計 30 頁。</p>
"""
    return chrome_pdf("C00", page(inner))


def c01_penalty():
    a1, a2 = penalty_letter(copy=False)
    return chrome_pdf("C01", page(a1, tight=True) + page(a2, tight=True))


def delivery_cert(name, doc_title, doc_no, send_date, recv_date, recv_sig, deposit=None):
    """deposit=None：交付本人；deposit=(寄存日, 郵局)：寄存送達。"""
    if deposit:
        dep_date, office = deposit
        result = f"""
<div>☐ 已交付應受送達人本人</div>
<div>☐ 已交付有辨別事理能力之同居人、受雇人或接收郵件人員（行政程序法第 73 條）</div>
<div>☑ 寄存於 {hand(office, "13pt")}（行政程序法第 74 條），並作送達通知書兩份，一份黏貼於門首，一份置於信箱</div>
<div class="note">未獲會晤應受送達人，亦無有辨別事理能力之同居人或受雇人可代收。</div>"""
        date_row = f"中華民國 {hand(dep_date, '15pt')}（寄存日）"
        sig = f"{hand('（寄存，無收領人）', '13pt')}"
    else:
        result = """
<div>☑ 已交付應受送達人本人</div>
<div>☐ 已交付有辨別事理能力之同居人、受雇人或接收郵件人員（行政程序法第 73 條）</div>
<div>☐ 寄存於＿＿＿＿（行政程序法第 74 條）</div>"""
        date_row = f"中華民國 {hand(recv_date, '15pt')}"
        sig = f"{hand(recv_sig, '20pt')}　{sq('陳<br>印')}"
    stamp_date = (dep_date if deposit else recv_date).replace(' 年 ', '.').replace(' 月 ', '.').replace(' 日', '')
    inner = f"""
<h1 style="letter-spacing:.2em">送　達　證　書</h1>
<table class="grid" style="font-size:12.5pt">
<tr><th style="width:34mm">送達機關</th><td>{GOV}</td></tr>
<tr><th>送達文書</th><td>{doc_title}<br>{doc_no}</td></tr>
<tr><th>應受送達人</th><td>{P}</td></tr>
<tr><th>送達處所</th><td>{HOME}（戶籍地）</td></tr>
<tr><th>交寄日期</th><td>中華民國 {send_date}</td></tr>
<tr><th>送達方式</th><td>☑ 郵務送達（掛號）　☐ 自行送達　☐ 留置送達</td></tr>
<tr><th>送達結果</th><td>{result}</td></tr>
<tr><th>送達日期</th><td>{date_row}</td></tr>
<tr><th>收領人簽章</th><td style="height:22mm">{sig}</td></tr>
<tr><th>送達人</th><td>中華郵政 ○○郵局　郵務士 {hand("張○偉", "13pt")}　<span class="stamp" style="font-size:8.5pt">○○郵局 {stamp_date} 投遞</span></td></tr>
</table>
<p class="note" style="margin-top:4mm">附註：本證書由送達人填載後黏貼於文書送達紀錄，退回送達機關歸卷。</p>
<div style="position:absolute;left:22mm;bottom:30mm" class="note"><span class="stamp">{GOV}　收文歸卷</span></div>
"""
    pdf = chrome_pdf(name, page(inner))
    png = pdf_to_png(pdf, name)
    return scanify(png, f"{SP}/png/{name}.jpg")


def c02():
    j = delivery_cert("C02", "處分函併附處分書", PEN_NO, "111 年 8 月 22 日", "111 年 8 月 24 日", "陳○勳")
    shutil.copy(j, f"{D3}/02-裁處書送達證書.jpg")
    return j


def c03_inspection():
    inner = f"""
<h1 style="letter-spacing:.15em;font-size:18pt">{GOV}　建築物使用管理現場勘查紀錄表</h1>
<table class="grid" style="font-size:12pt">
<tr><th style="width:30mm">案件編號</th><td>{hand("111061400873（1999檢舉）")}</td><th style="width:26mm">勘查日期</th><td>{hand("111.06.28  10:20")}</td></tr>
<tr><th>勘查方式</th><td colspan="3">☑ 現場勘查　☐ 影像審視　☐ 陳情訪查　☐ 其他</td></tr>
<tr><th>勘查地點</th><td colspan="3">{hand("○○區○○街○○號1樓")}</td></tr>
<tr><th>使用執照／核准用途</th><td colspan="3">{hand("（○○）使字第○○○○號；1層 H-2 住宅（6/27 已查存根）")}</td></tr>
<tr><th>所有權人／使用人</th><td colspan="3">{hand("陳○勳（謄本所有權人）；現場稱「阿婆」不在，店員不願具名")}</td></tr>
<tr><th>現場情形</th><td colspan="3" style="height:40mm">{hand("門首懸掛「阿婆小吃 滷味｜麵｜湯 營業中」紅色布幔招牌；門口設不鏽鋼餐車一台（瓦斯爐、湯鍋、滷味櫃），騎樓擺折疊桌2張、塑膠椅6張，有2名客人用餐；室內餐桌4組、飲料冷藏櫃、收銀盒、牆面菜單板（乾麵45、滷肉飯30、陽春麵40…）；後方廚房設營業用瓦斯爐及排煙罩。詢店員稱每日中午、晚間營業。")}</td></tr>
<tr><th>採證方式</th><td colspan="3">{hand("拍攝外觀、室內照片各1幀（10:21、10:24）")}</td></tr>
<tr><th>初步認定</th><td colspan="3">{hand("H-2 住宅擅自變更為 B-3 餐飲場所使用，違反建築法§73Ⅱ；擬依§91Ⅰ①通知所有權人陳述意見後裁處並限期改善。")}</td></tr>
<tr><th>勘查人員</th><td>{hand("林○翰", "15pt")}　{sq("林", "10mm")}</td><th>科長核閱</th><td>{hand("已閱 6/30", "13pt")}　{sq("科長", "10mm")}</td></tr>
</table>
<p class="note" style="margin-top:3mm">＊本表依本局建築物使用管理稽查作業規定填製，一式一份歸卷。</p>
"""
    pdf = chrome_pdf("C03", page(inner))
    png = pdf_to_png(pdf, "C03")
    j = scanify(png, f"{SP}/png/C03.jpg")
    shutil.copy(j, f"{D3}/03-現場勘查紀錄表.jpg")
    return j


def c04_photos():
    p1 = stamp_photo(f"{SP}/photos/raw1.png", f"{D3}/04-採證照片/採證照片-01_20220628-102113.jpg", "2022/06/28 10:21")
    p2 = stamp_photo(f"{SP}/photos/raw2.png", f"{D3}/04-採證照片/採證照片-02_20220628-102447.jpg", "2022/06/28 10:24")
    caps = ["10:21　系爭建築物 1 樓外觀：門首懸掛「阿婆小吃」招牌、門口餐車與騎樓桌椅", "10:24　室內：餐桌 4 組、飲料冷藏櫃、收銀盒、菜單價目板，後方為廚房"]
    imgs = "".join(f'<div style="margin-bottom:3mm"><img src="file://{p}" style="width:100%;border:.3mm solid #666"><div class="note" style="text-align:center">採證照片 {i+1}　{c}</div></div>' for i, (p, c) in enumerate(zip([p1, p2], caps)))
    inner = f"""
<h2 style="margin-top:0;letter-spacing:.2em">採證照片彙整頁</h2>
<p class="note" style="text-align:center;margin-bottom:3mm">拍攝：使用管理科 林○翰　攝於 2022/06/28（民國 111 年 6 月 28 日）　地點：{SITE}　案件 111061400873</p>
<div style="width:132mm;margin:0 auto">{imgs}</div>
"""
    pdf = chrome_pdf("C04", page(inner))
    shutil.copy(pdf, f"{D3}/04-採證照片彙整頁.pdf")
    return pdf


def c05_notice():
    inner = f"""
<h1 style="letter-spacing:.2em">{GOV}　函</h1>
<table class="meta">
<tr><td>受文者</td><td>：{P}君</td></tr>
<tr><td>發文日期</td><td>：中華民國 111 年 7 月 5 日</td></tr>
<tr><td>發文字號</td><td>：{NOTICE_NO}</td></tr>
<tr><td>速別</td><td>：普通件</td></tr>
<tr><td>附件</td><td>：採證照片 2 幀（影本）</td></tr>
</table>
<p class="item" style="margin-top:5mm">主旨：台端所有{SITE}建築物涉未經核准擅自變更為餐飲場所使用，違反建築法第 73 條第 2 項規定，請於文到之次日起 10 日內以書面向本局陳述意見，請查照。</p>
<p class="item">說明：</p>
<p class="sub">一、依行政程序法第 102 條及第 104 條規定辦理。</p>
<p class="sub">二、本局接獲民眾檢舉（案件編號 111061400873），於 {INSPECT}派員現場勘查，發現旨揭建築物 1 樓設置「{SHOP}」招牌、餐車、爐具及供不特定人用餐之桌椅並販售餐食，屬 B-3 類餐飲場所使用，核與使用執照核准用途 H-2 類住宅不符，且未申請變更使用執照。</p>
<p class="sub">三、台端得於期限內以書面陳述意見並檢附相關證據；如該建築物係由他人使用，請一併提供使用人姓名及聯絡方式。逾期未陳述者，本局將逕依現有事證依法處理。</p>
<p class="sub">四、依建築法第 91 條第 1 項第 1 款規定，違反同法第 73 條第 2 項者，處建築物所有權人、使用人新臺幣 6 萬元以上 30 萬元以下罰鍰，並限期改善或補辦手續。請台端儘速停止違規使用或申請變更使用執照。</p>
<p class="item" style="margin-top:4mm">正本：{P}君</p>
<p class="item">副本：本局使用管理科</p>
<div style="margin-top:14mm;text-align:right;padding-right:10mm">局長　○○○</div>
<div class="seal" style="right:24mm;bottom:50mm">新北市政府<br>工務局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    pdf = chrome_pdf("C05", page(inner))
    shutil.copy(pdf, f"{D3}/05-陳述意見通知書.pdf")
    return pdf


def c06():
    j = delivery_cert("C06", "陳述意見通知書", NOTICE_NO, "111 年 7 月 5 日", "111 年 7 月 8 日", "", deposit=("111 年 7 月 8 日", "○○郵局"))
    shutil.copy(j, f"{D3}/06-陳述意見通知書送達證書.jpg")
    return j


def c07_statement():
    text = (
        "本人陳○勳，收到貴局 111 年 7 月 5 日通知，說我○○街○○號 1 樓房子改做餐飲使用。\n\n"
        "一、這間房子是我住了三十幾年的家，1 樓就是我平常住的地方，沒有開店做生意。\n\n"
        "二、6 月底那幾天是端午連假，兒女孫子都回來，女兒把桌椅搬到門口讓大家吃飯，那個布條是親戚開玩笑送的，我自己煮滷味麵給大家吃，沒有跟外人收錢。\n\n"
        "三、東西我已經在收了，請貴局不要罰我。"
    )
    inner = f"""
<h1 style="letter-spacing:.3em">陳　述　意　見　書</h1>
<p class="note" style="text-align:right">貴局來函字號：{NOTICE_NO}</p>
<div style="border:.3mm solid #444;padding:6mm 7mm;min-height:150mm;line-height:2.3;background:repeating-linear-gradient(#fff 0 8.6mm,#e6e6e6 8.6mm 8.8mm)">
{hand(text, "14pt")}
</div>
<div class="sign" style="margin-top:6mm">
<p>陳述人：{hand("陳○勳", "20pt")}　{sq("陳<br>印")}</p>
<p>聯絡電話：{hand("09**-***-336")}</p>
<p>中華民國 {hand("111 年 7 月 15 日", "14pt")}</p>
</div>
<div style="position:absolute;left:22mm;bottom:26mm" class="note"><span class="stamp">{GOV}　111.07.18　收文</span>　<span class="mono">收文號：1110718-0261</span></div>
"""
    pdf = chrome_pdf("C07", page(inner))
    png = pdf_to_png(pdf, "C07")
    j = scanify(png, f"{SP}/png/C07.jpg")
    shutil.copy(j, f"{D3}/07-陳述意見書.jpg")
    return j


def c08_memo():
    inner = f"""
<h1 style="letter-spacing:.2em">{GOV}　簽</h1>
<table class="meta">
<tr><td>於</td><td>：使用管理科</td></tr>
<tr><td>日期</td><td>：中華民國 111 年 8 月 10 日</td></tr>
<tr><td>案件編號</td><td>：111061400873</td></tr>
</table>
<p class="item" style="margin-top:4mm">主旨：{P}君所有{SITE}建築物（核准用途 H-2 住宅）未經核准擅自變更為 B-3 餐飲場所使用，違反建築法第 73 條第 2 項，擬依同法第 91 條第 1 項第 1 款裁處罰鍰新臺幣 6 萬元並限期改善，簽請核示。</p>
<p class="item">說明：</p>
<p class="sub">一、本案經民眾 111 年 6 月 14 日 1999 檢舉，本科 6 月 27 日查得使用執照存根核准用途為住宅，6 月 28 日現場勘查發現 1 樓設「{SHOP}」招牌、餐車、爐具、菜單價目板及供客用餐桌椅，並有客人用餐、店員備餐，違規事實明確（勘查紀錄表及照片如附）。</p>
<p class="sub">二、本科 7 月 5 日函請所有權人陳述意見（7 月 8 日寄存送達），所有權人 7 月 15 日陳述意見書稱係家庭聚會臨時擺設、未對外收費。惟現場設有「營業中」標示、標價菜單板及營業用爐具餐車，店員自承每日中午、晚間營業，所辯與客觀事證不符，不予採信。</p>
<p class="sub">三、裁罰額度：法定罰鍰 6 萬至 30 萬元。審酌行政罰法第 18 條第 1 項，所有權人為初次違規、規模較小、已表示願改善，擬裁處法定最低額 6 萬元，並限於處分書送達次日起 60 日內改善或補辦變更使用執照。</p>
<p class="item">擬辦：奉核後，以本局名義製發處分書送達受處分人，並副知檢舉人；屆期由本科複查，未改善者依法連續處罰。</p>
<div style="margin-top:8mm;display:flex;gap:6mm;align-items:flex-start;flex-wrap:wrap">
<div>承辦：{hand("林○翰 8/10", "13pt")} {sq("林", "14mm", "8pt")}</div>
<div>科長：{hand("如擬 8/12", "13pt")} {sq("科長<br>○○○", "14mm", "8pt")}</div>
<div>主任秘書：{hand("如擬 8/16", "13pt")} {sq("主秘<br>○○○", "14mm", "8pt")}</div>
<div>局長：{hand("可 8/18", "13pt")} {sq("局長<br>○○○", "14mm", "8pt")}</div>
</div>
<div style="position:absolute;right:22mm;top:16mm" class="stamp">使用管理科　第 111-1204 號簽</div>
"""
    pdf = chrome_pdf("C08", page(inner))
    png = pdf_to_png(pdf, "C08")
    j = scanify(png, f"{SP}/png/C08.jpg", gray=False)
    shutil.copy(j, f"{D3}/08-裁處簽呈.jpg")
    return j


def merge(pdfs, out):
    subprocess.run(["qpdf", "--empty", "--pages", *pdfs, "--", out], check=True)
    n = subprocess.run(["qpdf", "--show-npages", out], capture_output=True, text=True).stdout.strip()
    return out, n


if __name__ == "__main__":
    a = doc_appeal()
    b = doc_defense()
    c = [c00_index(), c01_penalty()]
    c.append(jpg_to_pdf(c02(), f"{SP}/pdf/C02.pdf"))
    c.append(jpg_to_pdf(c03_inspection(), f"{SP}/pdf/C03.pdf"))
    c.append(c04_photos())
    c.append(c05_notice())
    c.append(jpg_to_pdf(c06(), f"{SP}/pdf/C06.pdf"))
    c.append(jpg_to_pdf(c07_statement(), f"{SP}/pdf/C07.pdf"))
    c.append(jpg_to_pdf(c08_memo(), f"{SP}/pdf/C08.pdf"))
    shutil.copy(c[0], f"{D3}/00-卷證目錄.pdf")
    shutil.copy(c[1], f"{D3}/01-處分書正本.pdf")
    out, n = merge([a, b, *c], f"{ROOT}/卷宗全卷合併.pdf")
    for name, p in (("訴願書", a), ("答辯書", b)):
        print(name, subprocess.run(["qpdf", "--show-npages", p], capture_output=True, text=True).stdout.strip(), "頁")
    print("merged", out, "pages:", n)
