"""case03 卷宗包：訴願書 10 頁、答辯書 10 頁、卷證 10 頁。HTML → Chrome PDF → (掃描件) PIL 後製。
與 case01/02 同一套管線；案情、文號、日期、法條、專案小組決議全部取自真實決定書 1143051259（114.12.17，81 I 撤銷）。"""
import os, subprocess, random, shutil, glob
from PIL import Image, ImageFilter, ImageEnhance, ImageChops, ImageDraw, ImageFont

SP = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SP)
D1, D2, D3 = f"{ROOT}/01-訴願書", f"{ROOT}/02-答辯書", f"{ROOT}/03-卷證"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
for d in (f"{SP}/html", f"{SP}/pdf", f"{SP}/png", f"{SP}/chrome-profile", D1, D2, D3, f"{D3}/04-複查現場照片"):
    os.makedirs(d, exist_ok=True)
random.seed(1143051259)

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
WM = '<div class="wm">黑客松測試用模擬文件 ‧ 非真實公文</div><div class="wm2">2026 新北市 AI 智慧城市黑客松 ‧ 法制局組 ‧ 評測用模擬卷證（依真實決定書 1143051259 反推）</div>'


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


# ------------------------------------------------------------------ 事實常數（全部取自真實決定書 1143051259）
P = "劉○鑫即劉○鑫建築師事務所"
PS = "劉○鑫"
OFFICE = "新北市○○區○○路 ○○ 號 ○ 樓"
SITE = "新北市○○區○○○路 291 號 2 樓"
HOTEL = "三○旅社"
GOV = "新北市政府工務局"
GOV_ADDR = "新北市板橋區中山路 1 段 161 號"
PEN_NO = "新北工使字第 1141305688 號"
PEN_DATE = "114 年 7 月 4 日"
NOTICE_NO = "新北工使字第 1141098374 號"
DEF_NO = "新北工使字第 1141583906 號"
REPORT_NO = "111-K004423"
RESULT_NO = "111-K004423-01"
USE_LIC = "（○○）使字第 ○○○○ 號"
RULE = "新北市供公眾使用建築物公共安全檢查簽證申報案件簽證不實認定及懲處作業要點"
BASIS = "新北市政府處理違反建築法使用管理規定事件裁罰基準"
CASE_ID = "1143051259"
FINDING_OLD = "防火區劃－防火區劃之防火門窗：免檢討"
FINDING_NEW = "防火區劃－防火區劃之防火門窗：未設置防火門，現場防火門材質不符規定"


# ------------------------------------------------------------------ 處分函＋處分書（正本／影本共用，2 頁）
def penalty_letter(copy=False):
    tag = "影　本" if copy else "正　本"
    seal_style = "opacity:.55;filter:grayscale(1)" if copy else ""
    seal = f'<div class="seal" style="right:24mm;bottom:36mm;{seal_style}">新北市政府<br>工務局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>'
    p1 = f"""
<div style="position:absolute;right:20mm;top:14mm" class="stamp">{tag}</div>
<h1 style="letter-spacing:.2em">{GOV}　函</h1>
<table class="meta">
<tr><td>受文者</td><td>：{P}</td></tr>
<tr><td>發文日期</td><td>：中華民國 {PEN_DATE}</td></tr>
<tr><td>發文字號</td><td>：{PEN_NO}</td></tr>
<tr><td>速別</td><td>：普通件</td></tr>
<tr><td>密等及解密條件或保密期限</td><td>：普通</td></tr>
<tr><td>附件</td><td>：處分書 1 份（同文號）</td></tr>
</table>
<p class="item" style="margin-top:5mm">主旨：台端受託辦理{SITE}建築物（{HOTEL}）111 年度建築物公共安全檢查簽證及申報作業，經本局複查認定檢查簽證內容不實，違反建築法第 77 條第 3 項規定，依同法第 91 條之 1 第 1 項第 1 款規定裁處如附件處分書，請查照。</p>
<p class="item">說明：</p>
<p class="sub">一、依建築法第 77 條第 3 項、第 91 條之 1 第 1 項第 1 款、{RULE}第 4 點第 4 款及{BASIS}第 3 點第 1 項附表 6 規定辦理。</p>
<p class="sub">二、台端於 111 年 6 月 9 日向本局掛號申報旨揭建築物 111 年度公共安全檢查簽證（申報案號 {REPORT_NO}），原簽證檢查內容「{FINDING_OLD}」，經本局 111 年 7 月 5 日 {RESULT_NO} 申報結果通知書查核合格予以備查。嗣本局於 112 年 7 月 4 日派員至現場複查，複查結果「{FINDING_NEW}」，與原簽證內容不符。</p>
<p class="sub">三、本局前以 114 年 5 月 20 日{NOTICE_NO}函請台端陳述意見，台端於 114 年 6 月 10 日提出陳述理由書。案經本局 114 年 6 月 30 日召開 114 年度第 2 次「{RULE.replace('作業要點','')}」專案小組會議決議：依使用執照竣工圖所示旅館內走廊連接室外安全梯設有乙種防火門，次依當年建築技術管理規則，乙種防火門規定鋁製並鑲嵌鐵絲網玻璃者，本案乙種防火門已變更形式並非鑲嵌鐵絲網玻璃，陳述理由不同意；本案缺失依作業要點第 4 點第 4 款「申報場所經簽證為合格，惟經複查為不合格，情節嚴重」罰鍰辦理。</p>
<p class="sub">四、台端辦理建築法第 77 條第 3 項之檢查簽證內容不實，爰依法裁處，並副知內政部。</p>
<p class="item" style="margin-top:3mm">正本：{P}</p>
<p class="item">副本：內政部、{HOTEL}、本局使用管理科</p>
<div style="margin-top:6mm;text-align:right;padding-right:10mm">局長　○○○</div>
{seal}
"""
    p2 = f"""
<div style="position:absolute;right:20mm;top:14mm" class="stamp">{tag}</div>
<h1 style="letter-spacing:.2em">{GOV}　處分書</h1>
<table class="meta">
<tr><td>發文日期</td><td>：中華民國 {PEN_DATE}</td></tr>
<tr><td>發文字號</td><td>：{PEN_NO}</td></tr>
<tr><td>受處分人</td><td>：{P}　（建築師證書字號：（略）　統一編號：（略））</td></tr>
<tr><td>事務所地址</td><td>：{OFFICE}</td></tr>
</table>
<table class="grid" style="margin-top:4mm">
<tr><th style="width:26mm">申報案件</th><td>{SITE}（{HOTEL}，{USE_LIC}使用執照，B-4 旅館類）111 年度建築物公共安全檢查簽證申報，申報案號 {REPORT_NO}，111 年 6 月 9 日掛號申報，111 年 7 月 5 日 {RESULT_NO} 申報結果通知書備查。</td></tr>
<tr><th>違反事實</th><td>受處分人為上開申報案之檢查簽證專業人員，原簽證檢查內容「{FINDING_OLD}」；經本局 112 年 7 月 4 日派員現場複查，結果為「{FINDING_NEW}」，與原簽證內容不符，經本局 114 年 6 月 30 日專案小組會議認定屬檢查簽證內容不實。</td></tr>
<tr><th>違反法條</th><td>建築法第 77 條第 3 項。</td></tr>
<tr><th>處罰依據</th><td>建築法第 91 條之 1 第 1 項第 1 款；{RULE}第 4 點第 4 款；{BASIS}第 3 點第 1 項附表 6（第一次處罰鍰 6 萬元）。</td></tr>
<tr><th>裁處內容</th><td>處罰鍰新臺幣 <b>60,000</b> 元整。</td></tr>
<tr><th>繳納方式</th><td>請於本處分書送達之次日起 30 日內，持繳款單至指定金融機構繳納；逾期未繳納者，依法移送強制執行。</td></tr>
<tr><th>注意事項</th><td>本處分副知內政部（中央主管建築機關）；受處分人再有檢查簽證內容不實者，依附表 6 累次遞增罰鍰。</td></tr>
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
<tr><td></td><td>　身分證明文件字號：A1****2046　　出生年月日：（略）</td></tr>
<tr><td></td><td>　住　址（事務所）：{OFFICE}</td></tr>
<tr><td></td><td>　聯絡電話：02-2***-*816</td></tr>
<tr><td>原處分機關</td><td>：{GOV}</td></tr>
<tr><td>處分書發文日期及字號</td><td>：民國 {PEN_DATE}{PEN_NO}函併附同文號處分書</td></tr>
<tr><td>收受或知悉行政處分日期</td><td>：中華民國 114 年 7 月 4 日</td></tr>
<tr><td>受理訴願機關</td><td>：新北市政府</td></tr>
</table>
<h2>訴願請求事項</h2>
<p class="indent">請求撤銷原處分機關 {PEN_DATE}{PEN_NO}函併附同文號處分書所為之處分。</p>
<h2>事　實</h2>
<p class="indent">緣訴願人受託辦理{SITE}建築物（{HOTEL}，下稱系爭建築物）之 111 年度建築物公共安全檢查簽證及申報作業，於 111 年 6 月 9 日向原處分機關掛號申報（申報案號 {REPORT_NO}），並經原處分機關於 111 年 7 月 5 日以 {RESULT_NO} 申報結果通知書略以：查核合格，予以備查在案。嗣原處分機關於 112 年 7 月 4 日派員至現場複查，認原簽證內容「{FINDING_OLD}」與複查結果「{FINDING_NEW}」不符，涉辦理建築法第 77 條第 3 項之檢查簽證內容不實，經 114 年 6 月 30 日專案小組會議決議後，依{RULE}第 4 點第 4 款、建築法第 91 條之 1 第 1 項第 1 款規定，以 {PEN_DATE}{PEN_NO}函併附同文號處分書（下稱原處分）裁處訴願人新臺幣 6 萬元罰鍰。訴願人不服，提起本訴願。</p>
"""
    p2 = f"""
<h2 style="margin-top:0">理　由</h2>
<p class="item">一、原處分已逾行政罰法第 27 條第 1 項之 3 年裁處權時效，於法有違。按行政罰法第 27 條第 1 項規定：「行政罰之裁處權，因三年期間之經過而消滅。」第 2 項規定：「前項期間，自違反行政法上義務之行為終了時起算。」原處分所指「檢查簽證內容不實」之行為，係訴願人於 111 年 6 月 9 日掛號申報簽證之時即已完成並終了，縱認該行為構成違規，裁處權時效亦應自 111 年 6 月 9 日起算，至 114 年 6 月 8 日屆滿。原處分機關遲至 114 年 6 月 30 日始召開專案小組會議認定，並於 114 年 7 月 4 日作成原處分，距申報日已逾 3 年，裁處權業已消滅，原處分自屬違法，應予撤銷（時效計算詳附件五）。</p>
<p class="item">二、訴願人之簽證責任止於簽證當時之現況，並無隨時且全面為該場所適法性負責之義務。系爭建築物為旅館，常有不特定人士使用及出入，經營者亦得隨時更換門窗設備。訴願人於 111 年 6 月檢查時，系爭走廊連接室外安全梯之防火門為鋁框鑲嵌鐵絲網玻璃之乙種防火門，與使用執照竣工圖相符，並無變更，故於檢查表該項目簽註「免檢討」（附件三檢查報告書）。原處分機關於 112 年 7 月 4 日複查，距訴願人簽證已逾 1 年，其間現場設備有無更換，非訴願人所能掌握，亦非訴願人依建築法第 77 條第 3 項所負之簽證義務範圍。</p>
<p class="item">三、原處分機關未提出該防火門係於 111 年申報完成後始被拆除更換之具體證據，逕以 112 年複查現況推論 111 年簽證不實，舉證顯有不足。依行政程序法第 36 條及第 43 條規定，行政機關應依職權調查證據並斟酌全部陳述與調查結果認定事實；原處分機關就「簽證當時現場防火門是否即非鐵絲網玻璃」此一構成要件事實，僅憑 1 年後之複查照片，未調閱旅館裝修紀錄、未詢問旅館負責人門窗更換時點，即認定訴願人簽證不實，其認定事實欠缺證據基礎。</p>
"""
    p3 = f"""
<p class="item">四、退步言之，縱認訴願人簽證有誤，本件僅涉單一檢查項目，旅館其餘防火避難設施均經複查合格，且原處分機關 111 年 7 月 5 日亦查核合格予以備查，難認屬{RULE}第 4 點第 4 款所稱「情節嚴重」。原處分機關就「情節嚴重」之認定未附具體理由，逕依該款裁處，有裁量怠惰之違法。</p>
<p class="item">五、訴願人已於 114 年 6 月 10 日陳述理由書中提出上開時效及舉證意見，惟原處分之說明欄僅載「陳述理由不同意」，對裁處權時效是否經過全未說明，違反行政程序法第 96 條第 1 項第 2 款處分應記明理由之規定。</p>
<p class="item">六、綜上，原處分逾越裁處權時效、認定事實無據且理由不備，懇請鈞府撤銷原處分，以維訴願人權益。</p>
<h2>附送證件</h2>
<table class="grid" style="width:92%;margin:0 auto">
<tr><th style="width:16mm">編號</th><th>名稱</th><th style="width:16mm">數量</th><th style="width:34mm">附註</th></tr>
<tr><td style="text-align:center">附件一</td><td>{PEN_NO}函併同文號處分書影本</td><td style="text-align:center">1 份</td><td>2 頁</td></tr>
<tr><td style="text-align:center">附件二</td><td>111 年 7 月 5 日 {RESULT_NO} 申報結果通知書影本</td><td style="text-align:center">1 份</td><td></td></tr>
<tr><td style="text-align:center">附件三</td><td>111 年度建築物公共安全檢查簽證申報資料（檢查報告書）影本</td><td style="text-align:center">1 份</td><td>摘錄 2 頁</td></tr>
<tr><td style="text-align:center">附件四</td><td>訴願人建築師開業證書及專業檢查人認可證影本</td><td style="text-align:center">1 份</td><td></td></tr>
<tr><td style="text-align:center">附件五</td><td>裁處權時效計算說明</td><td style="text-align:center">1 份</td><td>訴願人製</td></tr>
</table>
<p style="margin-top:6mm">此　致</p>
<p style="padding-left:2em">{GOV}（轉呈 新北市政府）</p>
<div class="sign" style="margin-top:6mm">
<p>訴願人：{P}　{hand("劉○鑫", "17pt")}{sq("劉○鑫<br>建築師<br>事務所", "16mm", "6.5pt")}{sq("劉<br>印")}</p>
<p style="margin-top:4mm">中華民國　114　年　8　月　1　日</p>
</div>
<div style="position:absolute;left:20mm;bottom:20mm" class="note">
<span class="stamp">{GOV}　114.08.01　收文</span>　<span class="mono note">收文號：1140801-0233</span><br>
<span class="mono" style="font-size:9pt;letter-spacing:.15em;display:inline-block;margin-top:1mm;border-left:.4mm solid #000;border-right:.4mm solid #000;padding:0 2mm">||| |||| || | ||| || |||| | ||| || ||||  1140801-0233  10:16</span>
</div>
"""
    pages += [page(p1, "第 1 頁，共 10 頁", tight=True), page(p2, "第 2 頁，共 10 頁", tight=True), page(p3, "第 3 頁，共 10 頁", tight=True)]

    a1, a2 = penalty_letter(copy=True)
    pages += [page('<div class="att">附件一</div>' + a1, "第 4 頁，共 10 頁", tight=True),
              page('<div class="att">附件一</div>' + a2, "第 5 頁，共 10 頁", tight=True)]

    # 附件二：申報結果通知書影本
    p6 = f"""
<div class="att">附件二</div>
<div style="position:absolute;right:20mm;top:22mm" class="stamp">影　本</div>
<h1 style="letter-spacing:.15em;font-size:18pt">{GOV}<br>建築物公共安全檢查簽證申報結果通知書</h1>
<table class="meta">
<tr><td>受文者</td><td>：{P}</td></tr>
<tr><td>副本收受者</td><td>：{HOTEL}（建築物使用人）</td></tr>
<tr><td>發文日期</td><td>：中華民國 111 年 7 月 5 日</td></tr>
<tr><td>發文字號</td><td>：{RESULT_NO}</td></tr>
</table>
<table class="grid" style="margin-top:4mm;font-size:12pt">
<tr><th style="width:30mm">申報案號</th><td>{REPORT_NO}</td><th style="width:26mm">申報年度</th><td>111 年度</td></tr>
<tr><th>建築物地址</th><td colspan="3">{SITE}</td></tr>
<tr><th>建築物名稱</th><td>{HOTEL}</td><th>使用類組</th><td>B-4 旅館類</td></tr>
<tr><th>使用執照</th><td>{USE_LIC}</td><th>申報期間</th><td>每一年一次；4 月 1 日至 6 月 30 日</td></tr>
<tr><th>掛號申報日</th><td>111 年 6 月 9 日</td><th>檢查人員</th><td>{PS} 建築師（認可專業檢查人）</td></tr>
<tr><th>申報項目</th><td colspan="3">防火避難設施類、設備安全類</td></tr>
<tr><th>查核結果</th><td colspan="3"><b>查核合格，予以備查。</b></td></tr>
<tr><th>說明</th><td colspan="3">一、台端申報之檢查簽證資料，經本局書面查核，符合建築物公共安全檢查簽證及申報辦法規定，予以備查。<br>二、依建築法第 77 條第 4 項規定，本局得隨時派員或定期會同各有關機關複查；複查結果與簽證內容不符者，依同法第 91 條之 1 規定辦理。<br>三、下年度申報期間為 112 年 4 月 1 日至 6 月 30 日，請依限辦理。</td></tr>
</table>
<div style="margin-top:10mm;text-align:right;padding-right:10mm">局長　○○○</div>
<div class="seal" style="right:26mm;bottom:40mm;opacity:.55;filter:grayscale(1)">新北市政府<br>工務局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    pages.append(page(p6, "第 6 頁，共 10 頁"))

    # 附件三：檢查報告書摘錄 2 頁
    p7 = f"""
<div class="att">附件三</div>
<div style="position:absolute;right:20mm;top:22mm" class="stamp">影　本</div>
<h1 style="letter-spacing:.15em;font-size:18pt">建築物公共安全檢查簽證申報書<br><span style="font-size:13pt">（111 年度）</span></h1>
<table class="grid" style="font-size:12pt">
<tr><th style="width:32mm">申報案號</th><td>{REPORT_NO}</td><th style="width:26mm">掛號日期</th><td>111 年 6 月 9 日</td></tr>
<tr><th>建築物名稱</th><td>{HOTEL}</td><th>使用類組</th><td>B-4 旅館類</td></tr>
<tr><th>建築物地址</th><td colspan="3">{SITE}</td></tr>
<tr><th>使用執照字號</th><td>{USE_LIC}</td><th>樓層／面積</th><td>2 層　412.8 ㎡</td></tr>
<tr><th>所有權人／使用人</th><td colspan="3">王○○（{HOTEL}負責人）　聯絡電話 02-2***-*903</td></tr>
<tr><th>申報項目</th><td colspan="3">☑ 防火避難設施類　☑ 設備安全類　☐ 昇降設備（另案）</td></tr>
<tr><th>檢查日期</th><td>111 年 5 月 26 日</td><th>檢查結果</th><td><b>合格</b></td></tr>
</table>
<h2 style="font-size:13.5pt;letter-spacing:.2em;margin-top:6mm">檢查專業人員簽證</h2>
<table class="grid" style="font-size:12pt">
<tr><th style="width:32mm">專業機構／人員</th><td>{P}</td></tr>
<tr><th>認可證字號</th><td>內政部（○○）台內營專檢字第 ○○○○ 號</td></tr>
<tr><th>建築師證書</th><td>建築師證書 ○○ 建證字第 ○○○○ 號；新北市建築師開業證書 ○○ 字第 ○○○ 號</td></tr>
<tr><th>簽證聲明</th><td>本人依建築物公共安全檢查簽證及申報辦法及建築物防火避難設施及設備安全標準檢查簽證項目表逐項檢查，簽證結果屬實。</td></tr>
<tr><th>簽章</th><td style="height:18mm">{hand("劉○鑫", "18pt")}　{sq("劉○鑫<br>建築師<br>事務所", "16mm", "6.5pt")}　{hand("111.6.7", "12pt")}</td></tr>
</table>
"""
    rows = [
        ("1", "防火區劃", "防火區劃之牆壁及樓地板", "符合", "依竣工圖檢視，無變更"),
        ("2", "防火區劃", "防火區劃之防火門窗", "<b>免檢討</b>", "依竣工圖及現況，無變更"),
        ("3", "防火區劃", "防火區劃之貫穿部位", "符合", ""),
        ("4", "內部裝修材料", "居室及通達地面之走廊、樓梯", "符合", "耐燃三級以上"),
        ("5", "避難層出入口", "出入口數量、寬度", "符合", ""),
        ("6", "走廊", "走廊寬度、淨高", "符合", "1.6 m"),
        ("7", "直通樓梯", "室內樓梯、室外安全梯", "符合", "室外安全梯 1 座，通達地面"),
        ("8", "安全梯", "安全梯構造及出入口防火門", "符合", "見項目 2"),
        ("9", "屋頂避難平臺", "—", "免檢討", "2 層建築，免設"),
        ("10", "緊急進口", "—", "免檢討", "面臨道路，免設"),
    ]
    tr = "".join(f"<tr><td style='text-align:center'>{a}</td><td>{b}</td><td>{c}</td><td style='text-align:center'>{d}</td><td class='note'>{e}</td></tr>" for a, b, c, d, e in rows)
    p8 = f"""
<div class="att">附件三</div>
<div style="position:absolute;right:20mm;top:22mm" class="stamp">影　本</div>
<h1 style="letter-spacing:.15em;font-size:17pt">建築物防火避難設施及設備安全標準檢查簽證項目表<br><span style="font-size:12pt">（摘錄：防火避難設施類）　申報案號 {REPORT_NO}</span></h1>
<table class="grid" style="font-size:11.5pt">
<tr><th style="width:10mm">項次</th><th style="width:28mm">檢查項目</th><th>檢查內容</th><th style="width:18mm">檢查結果</th><th style="width:44mm">改善或備註</th></tr>
{tr}
</table>
<p class="note" style="margin-top:3mm">檢查結果欄：符合／不符合／免檢討（該項目不適用或無變更者）。項目 2「防火區劃之防火門窗」簽註「免檢討」係指依使用執照竣工圖所示之乙種防火門現況無變更，未逐一檢討材質規格。</p>
<table class="meta" style="margin-top:8mm"><tr><td>檢查人員：{hand("劉○鑫", "15pt")} {sq("劉<br>印")}</td><td style="padding-left:14mm">檢查日期：111 年 5 月 26 日</td><td style="padding-left:14mm">第 3 頁，共 12 頁</td></tr></table>
"""
    pages += [page(p7, "第 7 頁，共 10 頁", tight=True), page(p8, "第 8 頁，共 10 頁", tight=True)]

    # 附件四：證書影本
    cert = lambda title, body, seal: f"""
<div style="border:1.2mm double #7a2b2b;padding:6mm 8mm;margin-bottom:6mm;position:relative;min-height:88mm">
<div style="text-align:center;font-size:17pt;letter-spacing:.4em;color:#7a2b2b">{title}</div>
{body}
<div class="seal" style="right:10mm;bottom:8mm;opacity:.5;filter:grayscale(1)">{seal}<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
</div>"""
    c1 = cert("建築師開業證書", f"""
<table class="meta" style="margin-top:4mm;font-size:12pt">
<tr><td>證書字號</td><td>：新北市建築師開業證書 ○○ 字第 ○○○ 號</td></tr>
<tr><td>建築師</td><td>：{PS}　　建築師證書：○○ 建證字第 ○○○○ 號</td></tr>
<tr><td>事務所名稱</td><td>：{P}</td></tr>
<tr><td>事務所地址</td><td>：{OFFICE}</td></tr>
<tr><td>發證日期</td><td>：中華民國 ○○ 年 ○ 月 ○ 日</td></tr>
<tr><td>有效期限</td><td>：至中華民國 116 年 ○ 月 ○ 日止</td></tr>
</table>
<p class="note" style="margin-top:3mm">依建築師法第 9 條規定核發。</p>""", "新北市政府")
    c2 = cert("建築物公共安全檢查專業檢查人認可證", f"""
<table class="meta" style="margin-top:4mm;font-size:12pt">
<tr><td>認可證字號</td><td>：內政部（○○）台內營專檢字第 ○○○○ 號</td></tr>
<tr><td>姓　名</td><td>：{PS}</td></tr>
<tr><td>資格</td><td>：開業建築師</td></tr>
<tr><td>檢查類別</td><td>：防火避難設施類、設備安全類</td></tr>
<tr><td>有效期限</td><td>：至中華民國 115 年 ○ 月 ○ 日止</td></tr>
</table>
<p class="note" style="margin-top:3mm">依建築物公共安全檢查簽證及申報辦法規定認可。</p>""", "內政部")
    p9 = f"""
<div class="att">附件四</div>
<div style="position:absolute;right:20mm;top:22mm" class="stamp">影　本</div>
<div style="margin-top:12mm">{c1}{c2}</div>
"""
    pages.append(page(p9, "第 9 頁，共 10 頁"))

    # 附件五：時效計算說明（訴願人製）
    p10 = f"""
<div class="att">附件五</div>
<h1 style="letter-spacing:.2em;font-size:18pt">裁處權時效計算說明</h1>
<p class="note">製作：{P}　依據：行政罰法第 27 條第 1 項、第 2 項</p>
<table class="grid" style="margin-top:3mm;font-size:12pt">
<tr><th style="width:44mm">項目</th><th style="width:38mm">日期</th><th>說明</th></tr>
<tr><td>簽證申報（行為完成）</td><td><b>111 年 6 月 9 日</b></td><td>訴願人掛號申報，簽證行為於申報時完成並終了（申報案號 {REPORT_NO}）</td></tr>
<tr><td>機關查核備查</td><td>111 年 7 月 5 日</td><td>{RESULT_NO} 申報結果通知書「查核合格，予以備查」</td></tr>
<tr><td>機關複查</td><td>112 年 7 月 4 日</td><td>距申報已 1 年餘；複查僅為機關「發現」，非行為終了時點，不影響起算</td></tr>
<tr><td>3 年時效屆滿</td><td><b>114 年 6 月 8 日</b></td><td>111 年 6 月 9 日起算 3 年（行政罰法第 27 條第 2 項自行為終了時起算）</td></tr>
<tr><td>專案小組會議</td><td>114 年 6 月 30 日</td><td>已逾時效 22 日</td></tr>
<tr><td>原處分作成</td><td><b>{PEN_DATE}</b></td><td>已逾時效 26 日</td></tr>
<tr><td>原處分送達</td><td>114 年 7 月 9 日</td><td>已逾時效 31 日</td></tr>
<tr><td>結論</td><td colspan="2"><b>原處分作成時裁處權已消滅，原處分違法，應予撤銷。</b></td></tr>
</table>
<div style="margin-top:6mm;display:flex;align-items:stretch;font-size:10.5pt;line-height:1.4;text-align:center">
<div style="flex:0 0 26mm;border:.3mm solid #222;padding:2mm 1mm;background:#f0f0f0"><b>111/6/9</b><br>申報簽證<br>（行為終了）</div>
<div style="flex:1;border:.3mm solid #222;border-left:0;padding:2mm 1mm">3 年裁處權時效<br>111/6/9 → 114/6/8<br><span class="note">（112/7/4 複查在時效內，機關尚有 11 個月可裁處）</span></div>
<div style="flex:0 0 26mm;border:.3mm solid #222;border-left:0;padding:2mm 1mm;background:#f0f0f0"><b>114/6/8</b><br>時效屆滿</div>
<div style="flex:0 0 40mm;border:.3mm solid #c1272d;border-left:0;padding:2mm 1mm;color:#c1272d">114/6/30 專案小組<br>114/7/4 處分<br><b>已逾時效</b></div>
</div>
<p class="indent" style="margin-top:6mm;font-size:12pt">附註：縱依最有利於原處分機關之見解，以 111 年 7 月 5 日備查日為起算日，時效亦於 114 年 7 月 4 日屆滿，原處分於同日作成、114 年 7 月 9 日始送達生效，仍已逾期。</p>
"""
    pages.append(page(p10, "第 10 頁，共 10 頁", tight=True))

    pdf = chrome_pdf("A-訴願書", "".join(pages))
    shutil.copy(pdf, f"{D1}/訴願書_劉○鑫建築師事務所_1140801.pdf")
    return pdf


# ------------------------------------------------------------------ B. 答辯書（10 頁：檢送函 1 ＋ 答辯書 4 ＋ 附件 5）
def doc_defense():
    pages = []
    cover = f"""
<h1 style="letter-spacing:.2em">{GOV}　函</h1>
<table class="meta">
<tr><td>受文者</td><td>：新北市政府（訴願審議委員會）</td></tr>
<tr><td>發文日期</td><td>：中華民國 114 年 8 月 20 日</td></tr>
<tr><td>發文字號</td><td>：{DEF_NO}</td></tr>
<tr><td>速別</td><td>：普通件</td></tr>
<tr><td>密等及解密條件或保密期限</td><td>：普通</td></tr>
<tr><td>附件</td><td>：如說明二</td></tr>
</table>
<p class="item" style="margin-top:5mm">主旨：檢送訴願人{P}因違反建築法事件不服本局 {PEN_DATE}{PEN_NO}函併附同文號處分書提起訴願案之訴願答辯書及原卷 1 宗，請查照。</p>
<p class="item">說明：</p>
<p class="sub">一、依訴願法第 58 條第 3 項規定辦理。本件訴願書經訴願人於 114 年 8 月 1 日送達本局（本局收文號 1140801-0233），本局重新審查原處分後，認原處分並無違法或不當，爰檢卷答辯。</p>
<p class="sub">二、檢附文件：（一）訴願答辯書 1 份（含附件一至五）；（二）原卷 1 宗（卷證目錄如附，共 10 頁）；（三）複查現場照片電子檔 2 幀。</p>
<p class="sub">三、本件答辯書副本已依訴願法第 58 條第 4 項規定逕送訴願人。</p>
<p class="item" style="margin-top:4mm">正本：新北市政府（訴願審議委員會）</p>
<p class="item">副本：{P}、本局使用管理科</p>
<div style="margin-top:14mm;text-align:right;padding-right:10mm">局長　○○○</div>
<div class="seal" style="right:24mm;bottom:56mm">新北市政府<br>工務局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    pages.append(page(cover, "第 1 頁，共 10 頁"))

    d1 = f"""
<h1>{GOV}　訴願答辯書</h1>
<table class="meta">
<tr><td>訴 願 人</td><td>：{P}　　設：{OFFICE}</td></tr>
<tr><td>原處分機關</td><td>：{GOV}　　設：{GOV_ADDR}</td></tr>
<tr><td>代 表 人</td><td>：局長 ○○○</td></tr>
<tr><td>受理訴願機關</td><td>：新北市政府</td></tr>
</table>
<p class="indent" style="margin-top:3mm">訴願人因違反建築法事件，不服本局 {PEN_DATE}{PEN_NO}函併附同文號處分書（下稱原處分）所為之處分，提起訴願，本局依法答辯如下：</p>
<h2>答辯聲明</h2>
<p class="indent">本件訴願駁回。</p>
<h2>事　實</h2>
<p class="indent">緣訴願人受託辦理{SITE}建築物（{HOTEL}，下稱系爭建築物）之 111 年度建築物公共安全檢查簽證及申報作業，於 111 年 6 月 9 日向本局掛號申報（申報案號 {REPORT_NO}），並經本局於 111 年 7 月 5 日以 {RESULT_NO} 申報結果通知書略以：查核合格，予以備查在案。經本局於 112 年 7 月 4 日派員至現場複查，複查結果「{FINDING_NEW}」，惟原簽證檢查內容「{FINDING_OLD}」，涉及辦理建築法第 77 條第 3 項之檢查簽證內容不實。本局以 114 年 5 月 20 日{NOTICE_NO}函通知訴願人陳述意見，訴願人於 114 年 6 月 10 日提出陳述理由書。案經本局 114 年 6 月 30 日召開 114 年度第 2 次「{RULE.replace('作業要點','')}」專案小組會議決議，認定訴願人確有簽證不實之情事，本局爰依{RULE}第 4 點第 4 款規定，依建築法第 91 條之 1 第 1 項第 1 款及{BASIS}第 3 點第 1 項附表 6 規定，以原處分裁處訴願人 6 萬元罰鍰。原處分於 114 年 7 月 9 日送達，訴願人不服，於 114 年 8 月 1 日提起本件訴願。</p>
"""
    d2 = f"""
<h2 style="margin-top:0">理　由</h2>
<p class="item">一、程序部分：原處分於 114 年 7 月 9 日郵務送達訴願人事務所（原卷第 02 件送達證書），訴願人於 114 年 8 月 1 日提起訴願，未逾訴願法第 14 條第 1 項之 30 日期間；訴願人係就原處分之實體事項提出爭執，並非主張訴願法第 77 條所列各款不受理事由，程序上應予受理，進入實體審查。</p>
<p class="item">二、實體部分：</p>
<p class="sub">（一）按建築法第 2 條規定：「主管建築機關，在中央為內政部；在直轄市為直轄市政府；在縣（市）為縣（市）政府。」本府 104 年 10 月 5 日新北府工建字第 1041856028 號公告，建築法除違章建築處理事項外，所定主管機關權限劃分予本局執行。次按建築法第 77 條第 3 項及第 4 項規定：「供公眾使用之建築物，應由建築物所有權人、使用人定期委託中央主管建築機關認可之專業機構或人員檢查簽證，其檢查簽證結果應向當地主管建築機關申報。非供公眾使用之建築物，經內政部認有必要時亦同（第 3 項）。前項檢查簽證結果，主管建築機關得隨時派員或定期會同各有關機關複查（第 4 項）。」第 91 條之 1 第 1 款規定：「有左列情形之一者，處建築師、專業技師、專業機構或人員、專業技術人員、檢查員或實施機械遊樂設施安全檢查人員新臺幣 6 萬元以上 30 萬元以下罰鍰：一、辦理第 77 條第 3 項之檢查簽證內容不實者。」</p>
<p class="sub">（二）再按建築物公共安全檢查簽證及申報辦法第 5 條規定：「防火避難設施及設備安全標準檢查申報期間及施行日期，如附表一。」其附表一規定 B-4 旅館類每一年檢查申報一次，申報期間為 4 月 1 日至 6 月 30 日（附件三）。末按{RULE}第 4 點第 4 款規定：「受託機構人員，經查有下列情形者，本局應依建築法第 91 條之 1 第 1 款規定處以罰鍰，並副知中央主管建築機關：（四）申報場所經簽證為合格，惟經複查為不合格，情節嚴重。」{BASIS}第 3 點第 1 項規定：「違反本法使用管理規定事件之裁罰基準依附表 1 至附表 10 之規定。」其附表 6 就辦理檢查簽證內容不實者，第一次處罰鍰 6 萬元（附件二）。</p>
<p class="sub">（三）訴願理由略謂：原處分距申報掛號日已逾 3 年裁處權時效；該建物常有不特定人士使用及出入，訴願人並無隨時且全面負責之義務；本局未提出防火門於申報完成後被拆除更換之具體證據；本件非情節嚴重；原處分未說明時效云云。</p>
"""
    d3 = f"""
<p class="sub">（四）惟查，訴願人受託辦理系爭建築物 111 年度建築物公共安全檢查簽證及申報作業，原簽證檢查內容「{FINDING_OLD}」部分，前經本局 112 年 7 月 4 日派員至現場複查，結果為「{FINDING_NEW}」，此有 112 年 7 月 4 日建築物公共安全檢查簽證申報「防火避難設施類」複查情形紀錄表、現場照片 2 幀及系爭建築物 111 年檢查申報案之檢查報告書等影本附卷可稽（原卷第 03、04 件，訴願書附件三）。案經本局 114 年 6 月 30 日召開 114 年度第 2 次專案小組會議討論結果略以：「一、依使用執照竣工圖所示旅館內走廊連接室外安全梯設有乙種防火門，次依當年建築技術管理規則，乙種防火門規定鋁製並鑲嵌鐵絲網玻璃者，本案乙種防火門已變更形式並非鑲嵌鐵絲網玻璃，陳述理由不同意。二、本案缺失依『{RULE}』四（四）『申報場所經簽證為合格，惟經複查為不合格，情節嚴重。』罰鍰辦理。」（附件一會議紀錄）。</p>
<p class="sub">（五）系爭建築物使用執照竣工圖（附件四）明載 2 樓走廊連接室外安全梯處設有乙種防火門，該防火門為防火區劃及安全梯之必要構件，屬「防火區劃之防火門窗」檢查項目應逐項檢討之對象；訴願人身為認可之專業檢查人，於檢查時本應依竣工圖核對現場防火門之形式、材質是否符合規定，卻逕簽註「免檢討」，未為任何檢討，其簽證內容與應檢查之事實不符，即屬檢查簽證內容不實。訴願人主張簽證當時防火門為鐵絲網玻璃、嗣後遭旅館更換云云，並未提出檢查當時之照片或紀錄以實其說，其 111 年檢查報告書亦無任何關於該防火門材質之記載，所辯不足採。</p>
<p class="sub">（六）防火門為旅館住宿人員火災時之逃生關鍵設施，簽證專業人員就此項目未予檢討即簽證合格，致主管機關備查後 1 年餘始於複查發現不符，對公共安全影響重大，專案小組認定屬「情節嚴重」，並無裁量瑕疵；本局依附表 6 裁處第一次之法定最低額 6 萬元，亦無過苛。</p>
"""
    d4 = f"""
<p class="sub">（七）至訴願人主張裁處權時效及舉證責任等節，容有一併審酌之必要。惟本局係於 112 年 7 月 4 日複查時始發現簽證內容與現況不符，其後依作業要點通知訴願人陳述意見並提請專案小組審議認定，程序上並無延宕；且原處分作成時已審酌相關事證，裁處並無違誤。</p>
<p class="item">三、綜上所陳，本件訴願為無理由，爰依訴願法第 58 條第 3 項規定，檢附原卷 1 宗，敬請察核予以駁回。</p>
<h2>證　物</h2>
<table class="grid" style="width:92%;margin:0 auto">
<tr><th style="width:16mm">編號</th><th>名稱</th><th style="width:34mm">備註</th></tr>
<tr><td style="text-align:center">附件一</td><td>114 年 6 月 30 日 114 年度第 2 次專案小組會議紀錄</td><td></td></tr>
<tr><td style="text-align:center">附件二</td><td>{BASIS}附表 6（摘錄）</td><td>114.06.30 修正</td></tr>
<tr><td style="text-align:center">附件三</td><td>建築物公共安全檢查簽證及申報辦法附表一（摘錄）</td><td></td></tr>
<tr><td style="text-align:center">附件四</td><td>系爭建築物使用執照竣工圖（2 樓平面圖摘錄）</td><td>標示乙種防火門位置</td></tr>
<tr><td style="text-align:center">附件五</td><td>相關法條摘錄</td><td></td></tr>
<tr><td style="text-align:center">原卷</td><td>卷證 00–08，共 10 頁（含 112.07.04 複查紀錄表、現場照片、陳述理由書）</td><td>另冊</td></tr>
</table>
<p style="margin-top:4mm">此　致</p>
<p style="padding-left:2em">新北市政府（訴願審議委員會）</p>
<div class="sign" style="margin-top:3mm">
<p>原處分機關：{GOV}　　代表人：局長　○○○</p>
<p>中華民國　114　年　8　月　20　日</p>
</div>
<div class="seal" style="right:22mm;bottom:20mm">新北市政府<br>工務局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    pages += [page(d1, "第 2 頁，共 10 頁", tight=True), page(d2, "第 3 頁，共 10 頁", tight=True),
              page(d3, "第 4 頁，共 10 頁", tight=True), page(d4, "第 5 頁，共 10 頁", tight=True)]

    # 附件一：專案小組會議紀錄
    b6 = f"""
<div class="att">附件一</div>
<h1 style="letter-spacing:.1em;font-size:17pt">{GOV} 114 年度第 2 次<br>「{RULE.replace('作業要點','')}」專案小組會議紀錄</h1>
<table class="meta" style="font-size:11.5pt">
<tr><td>時間</td><td>：114 年 6 月 30 日（星期一）下午 2 時 30 分</td></tr>
<tr><td>地點</td><td>：本局 6 樓會議室</td></tr>
<tr><td>主席</td><td>：○副局長○○　　　　　　紀錄：使用管理科 黃○達</td></tr>
<tr><td>出席</td><td>：外聘委員 ○○○ 建築師、○○○ 技師、○○○ 教授；本局使用管理科科長 ○○○、建照科代表、法制人員</td></tr>
<tr><td>列席</td><td>：{P}（陳述人，14:45 到場陳述後離席）</td></tr>
</table>
<h2 style="font-size:13pt;letter-spacing:.2em;margin-top:4mm">壹、審議案件</h2>
<table class="grid" style="font-size:11pt">
<tr><th style="width:12mm">案號</th><th>申報案／場所</th><th>檢查人員</th><th>複查不符事項</th></tr>
<tr><td style="text-align:center">2-3</td><td>{REPORT_NO}　{HOTEL}（{SITE}）</td><td>{PS} 建築師</td><td>原簽證「{FINDING_OLD}」；112.07.04 複查「{FINDING_NEW}」</td></tr>
</table>
<h2 style="font-size:13pt;letter-spacing:.2em;margin-top:4mm">貳、陳述人陳述要旨（案 2-3）</h2>
<p class="indent" style="font-size:11.5pt">簽證當時防火門與竣工圖相符，故簽免檢討；旅館不特定人出入，事後設備更換非其所能控制；機關未證明門係申報後更換；自 111 年 6 月 9 日申報至今已逾 3 年，裁處權時效已消滅（書面陳述理由書已於 6 月 10 日送達本局）。</p>
<h2 style="font-size:13pt;letter-spacing:.2em;margin-top:4mm">參、討論結果（案 2-3）</h2>
<p class="item" style="font-size:11.5pt">一、依使用執照竣工圖所示旅館內走廊連接室外安全梯設有乙種防火門，次依當年建築技術管理規則，乙種防火門規定鋁製並鑲嵌鐵絲網玻璃者，本案乙種防火門已變更形式並非鑲嵌鐵絲網玻璃，陳述理由不同意。</p>
<p class="item" style="font-size:11.5pt">二、本案缺失依「{RULE}」四（四）「申報場所經簽證為合格，惟經複查為不合格，情節嚴重。」罰鍰辦理。</p>
<p class="item" style="font-size:11.5pt">三、決議：認定檢查簽證內容不實，請使用管理科依建築法第 91 條之 1 第 1 款及裁罰基準附表 6 簽辦裁處，並副知內政部。</p>
<h2 style="font-size:13pt;letter-spacing:.2em;margin-top:4mm">肆、散會</h2>
<p class="indent" style="font-size:11.5pt">下午 4 時 10 分。</p>
<div style="position:absolute;right:22mm;bottom:22mm">{sq("主席<br>○○○", "14mm", "8pt")}　{sq("紀錄<br>黃○達", "14mm", "8pt")}</div>
"""
    pages.append(page(b6, "第 6 頁，共 10 頁", tight=True))

    # 附件二：裁罰基準附表六（摘錄，依 114.06.30 修正版）
    b7 = f"""
<div class="att">附件二</div>
<h1 style="letter-spacing:.15em;font-size:17pt">{BASIS}<br><span style="font-size:13pt">附表六（摘錄）　建築法第 91 條之 1</span></h1>
<table class="grid" style="font-size:11.5pt">
<tr><th style="width:26mm"></th><th>第 1 款</th><th>第 2 款</th><th>第 3 款</th><th>第 4 款</th></tr>
<tr><th>違反規定</th>
<td>建築法第 77 條第 3 項。<br>建築法第 91 條之 1 第 1 項第 1 款。<br>【辦理檢查簽證內容不實者】【備註一】</td>
<td>建築法第 77 條第 3 項。<br>建築法第 91 條之 1 第 1 項第 2 款。<br>【允許他人假借其名義辦理檢查簽證業務或假借他人名義辦理該檢查簽證業務者】【備註一】</td>
<td>建築法第 77 條之 4 第 6 項第 1 款或第 77 條之 4 第 8 項第 1 款。<br>建築法第 91 條之 1 第 1 項第 3 款。<br>【將登記證或檢查員證提供他人使用或使用他人之登記證或檢查員證執業者】【備註二】</td>
<td>建築法第 77 條之 3 第 2 項第 3 款。<br>建築法第 91 條之 1 第 1 項第 4 款。<br>【安全檢查報告內容不實者】【備註二】</td></tr>
<tr><th>裁處罰鍰基準【新臺幣】</th><td colspan="4">一、第一次處罰鍰六萬元。<br>二、第二次起依罰鍰次數，累次遞增六萬元罰鍰。</td></tr>
<tr><th>裁罰對象</th><td>專業機構或人員。</td><td>檢查機構或人員。</td><td>昇降設備及機械停車設備之專業技術人員或檢查員。</td><td>建築師、專業技師或實施機械遊樂設施安全檢查人員。</td></tr>
<tr><th>備註</th><td colspan="4">一、同時違反建築法第九十一條之一第一款、第二款規定者，分別處罰之。<br>二、同時違反建築法第九十一條之一第三款、第四款規定者，分別處罰之。</td></tr>
</table>
<p class="note" style="margin-top:4mm">本案適用第 1 款，訴願人為第一次違反，處罰鍰 6 萬元。</p>
"""
    pages.append(page(b7, "第 7 頁，共 10 頁", tight=True))

    # 附件三：申報辦法附表一（摘錄，依全國法規資料庫）
    b8 = f"""
<div class="att">附件三</div>
<h1 style="letter-spacing:.15em;font-size:17pt">建築物公共安全檢查簽證及申報辦法<br><span style="font-size:13pt">第 5 條及附表一（摘錄）</span></h1>
<p class="item"><b>第 5 條</b>：防火避難設施及設備安全標準檢查申報期間及施行日期，如附表一。</p>
<p style="text-align:center;margin-top:4mm"><b>附表一、建築物防火避難設施及設備安全標準檢查申報期間及施行日期（摘錄）</b></p>
<table class="grid" style="font-size:11.5pt">
<tr><th rowspan="2" style="width:18mm">類別</th><th rowspan="2" style="width:14mm">組別</th><th colspan="2">規模</th><th colspan="2">檢查及申報期間</th><th rowspan="2" style="width:26mm">施行日期</th></tr>
<tr><th>樓地板面積</th><th>樓層、建築物高度</th><th style="width:22mm">頻率</th><th style="width:40mm">期間</th></tr>
<tr><td rowspan="4" style="text-align:center">B 類<br>商業類</td><td style="text-align:center">B-1</td><td>—</td><td>—</td><td>每一年一次</td><td>四月一日至六月三十日止（第二季）</td><td>八十六年一月一日起</td></tr>
<tr><td style="text-align:center">B-2</td><td>五百平方公尺以上</td><td>—</td><td>每一年一次</td><td>四月一日至六月三十日止（第二季）</td><td>八十六年一月一日起</td></tr>
<tr><td style="text-align:center">B-3</td><td>三百平方公尺以上</td><td>—</td><td>每一年一次</td><td>四月一日至六月三十日止（第二季）</td><td>八十六年一月一日起</td></tr>
<tr style="background:#fff3e0"><td style="text-align:center"><b>B-4</b></td><td>—</td><td>—</td><td><b>每一年一次</b></td><td><b>四月一日至六月三十日止（第二季）</b></td><td>八十六年一月一日起</td></tr>
</table>
<p class="note" style="margin-top:4mm">系爭建築物為 B-4 旅館類，每年應於第二季申報；訴願人 111 年 6 月 9 日申報，在申報期間內。（資料來源：全國法規資料庫，附表一）</p>
"""
    pages.append(page(b8, "第 8 頁，共 10 頁", tight=True))

    # 附件四：竣工圖 2 樓平面圖（SVG）
    svg = f"""
<svg viewBox="0 0 560 330" width="100%" xmlns="http://www.w3.org/2000/svg" font-family="BiauKaiTC,Kaiti TC" font-size="11">
<rect x="1" y="1" width="558" height="328" fill="#fff" stroke="#999" stroke-dasharray="4 3"/>
<!-- 外牆 -->
<rect x="40" y="40" width="440" height="250" fill="none" stroke="#222" stroke-width="4"/>
<!-- 走廊 -->
<rect x="40" y="140" width="440" height="50" fill="#f4f4f4" stroke="none"/>
<text x="230" y="170" font-size="13">走　廊（淨寬 1.6 m）</text>
<!-- 客房 上排 -->
{"".join(f'<rect x="{40+i*88}" y="40" width="88" height="100" fill="none" stroke="#222" stroke-width="2"/><text x="{60+i*88}" y="95" font-size="12">{201+i}</text>' for i in range(5))}
<!-- 客房 下排 -->
{"".join(f'<rect x="{40+i*88}" y="190" width="88" height="100" fill="none" stroke="#222" stroke-width="2"/><text x="{60+i*88}" y="245" font-size="12">{206+i}</text>' for i in range(3))}
<rect x="304" y="190" width="88" height="100" fill="none" stroke="#222" stroke-width="2"/><text x="318" y="245" font-size="12">室內樓梯</text>
<line x1="312" y1="200" x2="384" y2="200" stroke="#222"/><line x1="312" y1="212" x2="384" y2="212" stroke="#222"/><line x1="312" y1="224" x2="384" y2="224" stroke="#222"/><line x1="312" y1="236" x2="384" y2="236" stroke="#222"/>
<rect x="392" y="190" width="88" height="100" fill="none" stroke="#222" stroke-width="2"/><text x="410" y="245" font-size="12">辦公／備品</text>
<!-- 室外安全梯 -->
<rect x="480" y="120" width="60" height="90" fill="none" stroke="#222" stroke-width="2" stroke-dasharray="6 3"/>
<text x="484" y="112" font-size="11">室外安全梯</text>
{"".join(f'<line x1="484" y1="{130+i*10}" x2="536" y2="{130+i*10}" stroke="#222"/>' for i in range(8))}
<!-- 乙種防火門 -->
<line x1="480" y1="150" x2="480" y2="182" stroke="#fff" stroke-width="6"/>
<path d="M480 150 A32 32 0 0 1 512 182" fill="none" stroke="#c1272d" stroke-width="2"/>
<line x1="480" y1="150" x2="512" y2="182" stroke="#c1272d" stroke-width="3"/>
<circle cx="480" cy="166" r="14" fill="none" stroke="#c1272d" stroke-width="1.5"/>
<text x="330" y="128" font-size="12" fill="#c1272d">乙種防火門（鋁製鑲嵌鐵絲網玻璃）</text>
<line x1="470" y1="132" x2="482" y2="152" stroke="#c1272d" stroke-width="1"/>
<!-- 圖框 -->
<text x="50" y="318" font-size="10">{USE_LIC}使用執照竣工圖　2 樓平面圖　S=1/200（摘錄，模擬）　{HOTEL}　{SITE}</text>
</svg>"""
    b9 = f"""
<div class="att">附件四</div>
<h1 style="letter-spacing:.15em;font-size:17pt">系爭建築物使用執照竣工圖<br><span style="font-size:13pt">2 樓平面圖（摘錄）</span></h1>
<div style="border:.3mm solid #666;padding:3mm">{svg}</div>
<p class="note" style="margin-top:3mm">圖說：2 樓走廊東端連接室外安全梯，竣工圖標示該出入口設「乙種防火門」。依當年建築技術規則建築設計施工編第 76 條，乙種防火門為鋁製並鑲嵌鐵絲網玻璃者。112 年 7 月 4 日複查該門為鋁框透明玻璃（非鐵絲網玻璃），與竣工圖不符（原卷第 04 件照片）。</p>
<p class="note">資料來源：本局建築執照管理系統竣工圖電子檔（{USE_LIC}）；本頁為摘錄重繪，模擬用。</p>
"""
    pages.append(page(b9, "第 9 頁，共 10 頁"))

    # 附件五：法條摘錄
    b10 = f"""
<div class="att">附件五</div>
<h1 style="letter-spacing:.2em;font-size:18pt">相關法條摘錄</h1>
<p class="item"><b>建築法第 2 條第 1 項</b>：主管建築機關，在中央為內政部；在直轄市為直轄市政府；在縣（市）為縣（市）政府。</p>
<p class="item"><b>建築法第 77 條第 3 項、第 4 項</b>：供公眾使用之建築物，應由建築物所有權人、使用人定期委託中央主管建築機關認可之專業機構或人員檢查簽證，其檢查簽證結果應向當地主管建築機關申報。非供公眾使用之建築物，經內政部認有必要時亦同。／前項檢查簽證結果，主管建築機關得隨時派員或定期會同各有關機關複查。</p>
<p class="item"><b>建築法第 91 條之 1 第 1 款</b>：有左列情形之一者，處建築師、專業技師、專業機構或人員、專業技術人員、檢查員或實施機械遊樂設施安全檢查人員新臺幣六萬元以上三十萬元以下罰鍰：一、辦理第七十七條第三項之檢查簽證內容不實者。</p>
<p class="item"><b>建築物公共安全檢查簽證及申報辦法第 5 條</b>：防火避難設施及設備安全標準檢查申報期間及施行日期，如附表一。</p>
<p class="item"><b>{RULE}第 4 點第 4 款</b>：受託機構人員，經查有下列情形者，本局應依建築法第 91 條之 1 第 1 款規定處以罰鍰，並副知中央主管建築機關：（四）申報場所經簽證為合格，惟經複查為不合格，情節嚴重。</p>
<p class="item"><b>{BASIS}第 3 點第 1 項</b>：違反本法使用管理規定事件之裁罰基準依附表 1 至附表 10 之規定。</p>
<p class="item"><b>行政罰法第 27 條第 1 項、第 2 項</b>：行政罰之裁處權，因三年期間之經過而消滅。／前項期間，自違反行政法上義務之行為終了時起算。但行為之結果發生在後者，自該結果發生時起算。</p>
<p class="item"><b>行政罰法第 18 條第 1 項</b>：裁處罰鍰，應審酌違反行政法上義務行為應受責難程度、所生影響及因違反行政法上義務所得之利益，並得考量受處罰者之資力。</p>
<p class="item"><b>行政程序法第 36 條</b>：行政機關應依職權調查證據，不受當事人主張之拘束，對當事人有利及不利事項一律注意。</p>
<p class="item"><b>訴願法第 14 條第 1 項</b>：訴願之提起，應自行政處分達到或公告期滿之次日起三十日內為之。</p>
"""
    pages.append(page(b10, "第 10 頁，共 10 頁", tight=True))

    pdf = chrome_pdf("B-答辯書", "".join(pages))
    shutil.copy(pdf, f"{D2}/答辯書及檢送函_工務局_1140820.pdf")
    return pdf


# ------------------------------------------------------------------ C. 卷證 00–08（10 頁）
ITEMS = [
    ("00", "卷證目錄", "文字 PDF", "訴願法 58 III 檢卷答辯：機關送卷時必附目錄"),
    ("01", "處分函併附處分書正本（2 頁）", "文字 PDF", "原行政處分本體（訴願標的）；內載救濟教示"),
    ("02", "處分書送達證書", "掃描 JPG", "訴願法 14：114.7.9 郵務送達事務所，受雇人代收（行政程序法 73）"),
    ("03", "112.7.4 複查情形紀錄表", "掃描 JPG（手寫）", "決定書理由五：「複查情形紀錄表」"),
    ("04", "複查現場照片彙整頁（另附 2 幀 JPG）", "文字 PDF ＋ 照片 JPG", "決定書理由五：「現場照片」"),
    ("05", "陳述意見通知書", "文字 PDF", "行政程序法 102；作業要點陳述程序"),
    ("06", "訴願人陳述理由書", "文字 PDF", "決定書答辯意旨：「陳述理由不同意」之所指"),
    ("07", "公安申報管理系統案件歷程", "系統列印 PDF", "111.6.9 申報 → 111.7.5 備查 → 112.7.4 複查 → 114.7.4 裁處"),
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
<tr><td>檢送文號</td><td>：114 年 8 月 20 日{DEF_NO}</td></tr>
<tr><td>受理機關案號</td><td>：新北市政府訴願審議委員會 {CASE_ID} 號</td></tr>
</table>
<table class="grid" style="margin-top:4mm">
<tr><th style="width:12mm">編號</th><th>文件名稱</th><th style="width:34mm">形式</th><th>在卷理由（法律依據／決定書對應）</th></tr>
{rows}
</table>
<p class="note" style="margin-top:4mm">＊本卷共 9 件 10 頁；複查現場照片原始檔 2 幀以電子檔另附。訴願書（含附件，10 頁）及答辯書（含檢送函與附件，10 頁）另冊裝訂，全卷合計 30 頁。111 年檢查報告書全本（12 頁）已由訴願人於訴願書附件三提出摘錄，本局留存正本備查。</p>
"""
    return chrome_pdf("C00", page(inner))


def c01_penalty():
    a1, a2 = penalty_letter(copy=False)
    return chrome_pdf("C01", page(a1, tight=True) + page(a2, tight=True))


def c02():
    inner = f"""
<h1 style="letter-spacing:.2em">送　達　證　書</h1>
<table class="grid" style="font-size:12.5pt">
<tr><th style="width:34mm">送達機關</th><td>{GOV}</td></tr>
<tr><th>送達文書</th><td>處分函併附處分書<br>{PEN_NO}</td></tr>
<tr><th>應受送達人</th><td>{P}</td></tr>
<tr><th>送達處所</th><td>{OFFICE}（事務所）</td></tr>
<tr><th>交寄日期</th><td>中華民國 114 年 7 月 4 日</td></tr>
<tr><th>送達方式</th><td>☑ 郵務送達（掛號）　☐ 自行送達　☐ 留置送達</td></tr>
<tr><th>送達結果</th><td>
<div>☐ 已交付應受送達人本人</div>
<div>☑ 已交付有辨別事理能力之同居人、受雇人或接收郵件人員（行政程序法第 73 條）：{hand("事務所行政人員 林○如", "13pt")}</div>
<div>☐ 寄存於＿＿＿＿（行政程序法第 74 條）</div>
</td></tr>
<tr><th>送達日期</th><td>中華民國 {hand("114 年 7 月 9 日", "15pt")}</td></tr>
<tr><th>收領人簽章</th><td style="height:22mm">{hand("林○如", "20pt")}　{sq("劉○鑫<br>建築師<br>事務所", "16mm", "6.5pt")}</td></tr>
<tr><th>送達人</th><td>中華郵政 ○○郵局　郵務士 {hand("周○明", "13pt")}　<span class="stamp" style="font-size:8.5pt">○○郵局 114.7.9 投遞</span></td></tr>
</table>
<p class="note" style="margin-top:4mm">附註：本證書由送達人填載後黏貼於文書送達紀錄，退回送達機關歸卷。</p>
<div style="position:absolute;left:22mm;bottom:30mm" class="note"><span class="stamp">{GOV}　收文歸卷</span></div>
"""
    pdf = chrome_pdf("C02", page(inner))
    png = pdf_to_png(pdf, "C02")
    j = scanify(png, f"{SP}/png/C02.jpg")
    shutil.copy(j, f"{D3}/02-裁處書送達證書.jpg")
    return j


def c03_recheck():
    inner = f"""
<h1 style="letter-spacing:.1em;font-size:17pt">{GOV}<br>建築物公共安全檢查簽證申報「防火避難設施類」複查情形紀錄表</h1>
<table class="grid" style="font-size:12pt">
<tr><th style="width:30mm">申報案號</th><td>{hand(REPORT_NO)}</td><th style="width:26mm">複查日期</th><td>{hand("112.07.04  14:10")}</td></tr>
<tr><th>建築物</th><td colspan="3">{hand("三○旅社  ○○區○○○路291號2樓  B-4")}</td></tr>
<tr><th>檢查人員（簽證）</th><td colspan="3">{hand("劉○鑫 建築師（劉○鑫建築師事務所）")}</td></tr>
<tr><th>複查依據</th><td colspan="3">☑ 建築法 §77 IV 定期複查（112 年度抽查名單）　☐ 檢舉　☐ 其他</td></tr>
<tr><th>複查項目</th><th>原簽證結果</th><th colspan="2">複查結果</th></tr>
<tr><td>防火區劃之牆壁及樓地板</td><td>{hand("符合")}</td><td colspan="2">{hand("符合")}</td></tr>
<tr><td>防火區劃之防火門窗</td><td>{hand("免檢討")}</td><td colspan="2" style="height:30mm">{hand("不符合。2F走廊東端通室外安全梯之門，竣工圖為乙種防火門；現場為鋁框透明強化玻璃門（無鐵絲網、無防火標示、無防火門認證標籤），未設置防火門，材質不符規定。拍照2幀。旅館櫃台人員稱「一直都是這扇門」，無法提供更換紀錄。")}</td></tr>
<tr><td>走廊、直通樓梯、安全梯</td><td>{hand("符合")}</td><td colspan="2">{hand("符合")}</td></tr>
<tr><td>避難層出入口、內部裝修</td><td>{hand("符合")}</td><td colspan="2">{hand("符合")}</td></tr>
<tr><th>複查結論</th><td colspan="3">{hand("原簽證「免檢討」項目經複查為不合格，涉簽證內容不實，擬提專案小組認定；另通知使用人限期改善。")}</td></tr>
<tr><th>複查人員</th><td>{hand("黃○達", "15pt")}　{sq("黃", "10mm")}</td><th>科長核閱</th><td>{hand("已閱 7/6", "13pt")}　{sq("科長", "10mm")}</td></tr>
</table>
"""
    pdf = chrome_pdf("C03", page(inner, tight=True))
    png = pdf_to_png(pdf, "C03")
    j = scanify(png, f"{SP}/png/C03.jpg")
    shutil.copy(j, f"{D3}/03-複查情形紀錄表.jpg")
    return j


def c04_photos():
    p1 = stamp_photo(f"{SP}/photos/raw1.png", f"{D3}/04-複查現場照片/複查照片-01_20230704-141232.jpg", "2023/07/04 14:12")
    p2 = stamp_photo(f"{SP}/photos/raw2.png", f"{D3}/04-複查現場照片/複查照片-02_20230704-141505.jpg", "2023/07/04 14:15")
    caps = ["14:12　2 樓走廊東端通室外安全梯之出入口：鋁框透明玻璃門，上方為緊急出口標示", "14:15　門扇近拍：透明強化玻璃，無鐵絲網、無防火門認證標籤"]
    imgs = "".join(f'<div style="margin-bottom:3mm"><img src="file://{p}" style="width:100%;border:.3mm solid #666"><div class="note" style="text-align:center">複查照片 {i+1}　{c}</div></div>' for i, (p, c) in enumerate(zip([p1, p2], caps)))
    inner = f"""
<h2 style="margin-top:0;letter-spacing:.2em">複查現場照片彙整頁</h2>
<p class="note" style="text-align:center;margin-bottom:3mm">拍攝：使用管理科 黃○達　攝於 2023/07/04（民國 112 年 7 月 4 日）　地點：{SITE}（{HOTEL}）　申報案號 {REPORT_NO}</p>
<div style="width:132mm;margin:0 auto">{imgs}</div>
"""
    pdf = chrome_pdf("C04", page(inner))
    shutil.copy(pdf, f"{D3}/04-複查現場照片彙整頁.pdf")
    return pdf


def c05_notice():
    inner = f"""
<h1 style="letter-spacing:.2em">{GOV}　函</h1>
<table class="meta">
<tr><td>受文者</td><td>：{P}</td></tr>
<tr><td>發文日期</td><td>：中華民國 114 年 5 月 20 日</td></tr>
<tr><td>發文字號</td><td>：{NOTICE_NO}</td></tr>
<tr><td>速別</td><td>：普通件</td></tr>
<tr><td>附件</td><td>：112 年 7 月 4 日複查情形紀錄表及現場照片影本</td></tr>
</table>
<p class="item" style="margin-top:5mm">主旨：台端受託辦理{SITE}建築物（{HOTEL}）111 年度公共安全檢查簽證申報案（{REPORT_NO}），經本局複查結果與原簽證內容不符，涉檢查簽證內容不實，請於 114 年 6 月 10 日前以書面向本局陳述意見，並得於本局專案小組會議列席陳述，請查照。</p>
<p class="item">說明：</p>
<p class="sub">一、依行政程序法第 102 條、第 104 條及{RULE}規定辦理。</p>
<p class="sub">二、台端 111 年 6 月 9 日申報之檢查簽證，原簽證內容「{FINDING_OLD}」；本局 112 年 7 月 4 日派員複查，結果「{FINDING_NEW}」。依使用執照竣工圖，2 樓走廊連接室外安全梯處設有乙種防火門，該項目應予檢討。</p>
<p class="sub">三、本局將於 114 年 6 月 30 日下午 2 時 30 分召開 114 年度第 2 次「{RULE.replace('作業要點','')}」專案小組會議審議本案，台端得列席陳述意見。</p>
<p class="sub">四、依建築法第 91 條之 1 第 1 款規定，辦理第 77 條第 3 項之檢查簽證內容不實者，處新臺幣 6 萬元以上 30 萬元以下罰鍰。逾期未陳述者，本局將逕依現有事證提會審議。</p>
<p class="item" style="margin-top:4mm">正本：{P}</p>
<p class="item">副本：本局使用管理科</p>
<div style="margin-top:12mm;text-align:right;padding-right:10mm">局長　○○○</div>
<div class="seal" style="right:24mm;bottom:46mm">新北市政府<br>工務局<br>印<br><span style="font-size:6.5pt">（模擬）</span></div>
"""
    pdf = chrome_pdf("C05", page(inner))
    shutil.copy(pdf, f"{D3}/05-陳述意見通知書.pdf")
    return pdf


def c06_statement():
    inner = f"""
<div style="border-bottom:.5mm solid #333;padding-bottom:2mm;margin-bottom:4mm;display:flex;justify-content:space-between;align-items:flex-end">
<div style="font-size:16pt;letter-spacing:.2em">{P}</div>
<div class="note">{OFFICE}　TEL 02-2***-*816</div>
</div>
<h1 style="letter-spacing:.3em">陳　述　理　由　書</h1>
<table class="meta">
<tr><td>受文者</td><td>：{GOV}</td></tr>
<tr><td>日期</td><td>：中華民國 114 年 6 月 10 日</td></tr>
<tr><td>貴局來函</td><td>：114 年 5 月 20 日{NOTICE_NO}</td></tr>
<tr><td>案由</td><td>：{HOTEL} 111 年度公共安全檢查簽證申報案（{REPORT_NO}）複查不符陳述</td></tr>
</table>
<p class="item" style="margin-top:4mm">一、本人於 111 年 5 月 26 日至系爭建築物檢查時，2 樓走廊東端通室外安全梯之門扇為鋁框鑲嵌鐵絲網玻璃之乙種防火門，與竣工圖相符、無變更，故於「防火區劃之防火門窗」項目簽註「免檢討」，並非未檢查。</p>
<p class="item">二、貴局 112 年 7 月 4 日複查距本人檢查已逾 13 個月。旅館為不特定人出入之營業場所，經營者得隨時更換門扇；本人依建築法第 77 條第 3 項所負者為簽證當時之檢查義務，並無隨時且全面為該場所適法性負責之義務。</p>
<p class="item">三、貴局未提出該防火門係於 111 年申報後始被拆除更換之具體證據，逕以 112 年現況推論 111 年簽證不實，舉證不足。請貴局向旅館負責人查證門扇更換時點。</p>
<p class="item">四、退步言之，縱認本人簽證有誤，自 111 年 6 月 9 日申報迄今已逾 3 年，依行政罰法第 27 條第 1 項規定，裁處權因 3 年期間之經過而消滅，貴局已不得裁處。</p>
<p class="item">五、本人將於 6 月 30 日專案小組會議列席說明，懇請貴局審酌上情，不予裁罰。</p>
<div class="sign" style="margin-top:8mm">
<p>陳述人：{P}　{hand("劉○鑫", "18pt")}{sq("劉○鑫<br>建築師<br>事務所", "16mm", "6.5pt")}</p>
</div>
<div style="position:absolute;left:22mm;bottom:22mm" class="note"><span class="stamp">{GOV}　114.06.10　收文</span>　<span class="mono">收文號：1140610-0158</span></div>
"""
    pdf = chrome_pdf("C06", page(inner, tight=True))
    shutil.copy(pdf, f"{D3}/06-陳述理由書.pdf")
    return pdf


def c07_system():
    css = """body{margin:0;font-family:"PingFang TC",-apple-system,sans-serif;background:#e9edf2;color:#222}
.bar{background:#2b2f36;color:#ddd;padding:8px 14px;font-size:13px;display:flex;gap:12px;align-items:center}
.url{background:#fff;color:#333;border-radius:14px;padding:4px 12px;flex:1;font-size:13px}
.hdr{background:#1f5f3a;color:#fff;padding:10px 24px;font-size:17px;display:flex;justify-content:space-between}
.wrap{padding:18px 24px}
.card{background:#fff;border:1px solid #cdd3db;padding:14px 18px;margin-bottom:12px}
.card h3{margin:0 0 8px;font-size:15px;color:#1f5f3a;border-bottom:2px solid #1f5f3a;padding-bottom:6px}
table{border-collapse:collapse;width:100%;font-size:13.5px}
td,th{border:1px solid #dfe3e8;padding:7px 10px;text-align:left}
th{background:#f3f5f8;width:140px;font-weight:600;color:#444}
.tag{display:inline-block;border-radius:3px;padding:1px 8px;font-size:12px;margin-right:6px}
.ok{background:#e6f2ea;color:#1f5f3a}.ng{background:#fde8e8;color:#a11}.wa{background:#fff3e0;color:#8a4b00}
.wm{position:fixed;left:0;right:0;top:44%;text-align:center;transform:rotate(-20deg);font-size:34px;color:rgba(0,0,0,.06);letter-spacing:.3em}"""
    body = f"""
<div class="wm">黑客松測試用模擬畫面</div>
<div class="bar"><span>◀ ▶ ⟳</span><div class="url">https://bpsr.ntpc.gov.tw/case/history?no={REPORT_NO}　（模擬網址）</div><span>黃○達 ▾</span></div>
<div class="hdr"><span>新北市政府工務局　建築物公共安全檢查申報管理系統　案件歷程</span><span style="font-size:13px">列印時間 2025-08-18 11:03　列印人：使用管理科 黃○達</span></div>
<div class="wrap">
<div class="card"><h3>申報案基本資料</h3>
<table>
<tr><th>申報案號</th><td><b>{REPORT_NO}</b>　<span class="tag ok">111 年度</span><span class="tag ok">B-4 旅館類</span></td><th>建築物</th><td>{HOTEL}　{SITE}</td></tr>
<tr><th>檢查人員</th><td>{PS} 建築師（認可證 台內營專檢字第 ○○○○ 號）</td><th>申報人</th><td>王○○（使用人）</td></tr>
<tr><th>申報項目</th><td colspan="3">防火避難設施類、設備安全類　　簽證結果：合格</td></tr>
</table></div>
<div class="card"><h3>案件歷程</h3>
<table>
<tr><th style="width:120px">日期</th><th style="width:150px">階段</th><th style="width:auto">內容</th><th style="width:110px">狀態</th></tr>
<tr><td>2022-06-09</td><td>掛號申報</td><td>檢查人員線上申報並掛號，紙本報告書 12 頁送件</td><td><span class="tag ok">已受理</span></td></tr>
<tr><td>2022-07-05</td><td>書面查核</td><td>發 {RESULT_NO} 申報結果通知書：查核合格，予以備查</td><td><span class="tag ok">備查</span></td></tr>
<tr><td>2023-07-04</td><td>現場複查</td><td>112 年度定期抽查。複查結果：防火區劃之防火門窗 不合格（原簽證免檢討）</td><td><span class="tag ng">不符</span></td></tr>
<tr><td>2023-07-06</td><td>複查歸檔</td><td>複查情形紀錄表核閱歸卷；另案通知使用人限期改善</td><td><span class="tag wa">待提會</span></td></tr>
<tr><td>2025-05-20</td><td>陳述意見通知</td><td>{NOTICE_NO} 函通知檢查人員陳述意見</td><td><span class="tag wa">通知</span></td></tr>
<tr><td>2025-06-10</td><td>陳述意見</td><td>檢查人員陳述理由書收文（1140610-0158）</td><td><span class="tag wa">已收</span></td></tr>
<tr><td>2025-06-30</td><td>專案小組</td><td>114 年度第 2 次會議：認定簽證不實，依作業要點四（四）罰鍰辦理</td><td><span class="tag ng">認定</span></td></tr>
<tr><td>2025-07-04</td><td>裁處</td><td>{PEN_NO} 處分書：罰鍰 60,000 元（附表 6 第一次）</td><td><span class="tag ng">已裁處</span></td></tr>
<tr><td>2025-07-09</td><td>送達</td><td>掛號送達事務所，受雇人代收</td><td><span class="tag ok">已送達</span></td></tr>
<tr><td>2025-08-01</td><td>訴願</td><td>訴願書收文 1140801-0233</td><td><span class="tag wa">訴願中</span></td></tr>
</table></div>
</div>"""
    png = chrome_shot("C07", body, css, (1440, 900))
    inner = f"""
<h2 style="letter-spacing:.2em;margin-top:0">建築物公共安全檢查申報管理系統　案件歷程列印</h2>
<p class="note" style="text-align:center">申報案號 {REPORT_NO}　列印時間 114/08/18 11:03　列印人：使用管理科 黃○達</p>
<img src="file://{png}" style="width:100%;border:.3mm solid #999;margin-top:3mm">
<p class="note" style="margin-top:4mm">附註：本頁為系統畫面列印，用以呈現自 111 年申報至 114 年裁處之完整時間軸。</p>
"""
    pdf = chrome_pdf("C07p", page(inner))
    shutil.copy(pdf, f"{D3}/07-公安申報系統案件歷程.pdf")
    return pdf


def c08_memo():
    inner = f"""
<h1 style="letter-spacing:.2em">{GOV}　簽</h1>
<table class="meta">
<tr><td>於</td><td>：使用管理科</td></tr>
<tr><td>日期</td><td>：中華民國 114 年 7 月 1 日</td></tr>
<tr><td>申報案號</td><td>：{REPORT_NO}</td></tr>
</table>
<p class="item" style="margin-top:4mm">主旨：{P}辦理{HOTEL}（{SITE}）111 年度建築物公共安全檢查簽證內容不實，經 114 年 6 月 30 日專案小組會議認定，擬依建築法第 91 條之 1 第 1 款及裁罰基準附表 6 裁處罰鍰新臺幣 6 萬元，簽請核示。</p>
<p class="item">說明：</p>
<p class="sub">一、本案 111 年 6 月 9 日申報、111 年 7 月 5 日備查；本科 112 年 7 月 4 日複查發現「防火區劃之防火門窗」原簽證免檢討，現場為鋁框透明玻璃門，非竣工圖所示乙種防火門（複查紀錄表及照片如附）。</p>
<p class="sub">二、本科 114 年 5 月 20 日函請檢查人員陳述意見，其 6 月 10 日陳述理由書主張簽證當時門扇相符、事後更換非其所能控制、本局舉證不足，並主張已逾 3 年裁處權時效。</p>
<p class="sub">三、114 年 6 月 30 日專案小組會議決議：依竣工圖及當年建築技術規則，乙種防火門應為鋁製鑲嵌鐵絲網玻璃，本案已變更形式，陳述理由不同意；依作業要點四（四）「情節嚴重」罰鍰辦理。</p>
<p class="sub">四、裁罰額度：依裁罰基準附表 6，第一次處罰鍰 6 萬元；檢查人員無前案紀錄。</p>
<p class="item">擬辦：奉核後，以本局名義製發處分書送達受處分人，副知內政部及旅館使用人；本案自申報日起已逾 3 年，請法制人員併予審視。</p>
<div style="margin-top:8mm;display:flex;gap:6mm;align-items:flex-start;flex-wrap:wrap">
<div>承辦：{hand("黃○達 7/1", "13pt")} {sq("黃", "14mm", "8pt")}</div>
<div>科長：{hand("如擬 7/2", "13pt")} {sq("科長<br>○○○", "14mm", "8pt")}</div>
<div>法制：{hand("時效請併審酌 7/2", "12pt")} {sq("法制", "14mm", "8pt")}</div>
<div>主任秘書：{hand("如擬 7/3", "13pt")} {sq("主秘<br>○○○", "14mm", "8pt")}</div>
<div>局長：{hand("可 7/3", "13pt")} {sq("局長<br>○○○", "14mm", "8pt")}</div>
</div>
<div style="position:absolute;right:22mm;top:16mm" class="stamp">使用管理科　第 114-0977 號簽</div>
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
    os.makedirs(f"{D3}/04-複查現場照片", exist_ok=True)
    a = doc_appeal()
    b = doc_defense()
    c = [c00_index(), c01_penalty()]
    c.append(jpg_to_pdf(c02(), f"{SP}/pdf/C02.pdf"))
    c.append(jpg_to_pdf(c03_recheck(), f"{SP}/pdf/C03.pdf"))
    c.append(c04_photos())
    c.append(c05_notice())
    c.append(c06_statement())
    c.append(c07_system())
    c.append(jpg_to_pdf(c08_memo(), f"{SP}/pdf/C08.pdf"))
    shutil.copy(c[0], f"{D3}/00-卷證目錄.pdf")
    shutil.copy(c[1], f"{D3}/01-處分書正本.pdf")
    out, n = merge([a, b, *c], f"{ROOT}/卷宗全卷合併.pdf")
    for name, p in (("訴願書", a), ("答辯書", b)):
        print(name, subprocess.run(["qpdf", "--show-npages", p], capture_output=True, text=True).stdout.strip(), "頁")
    print("merged", out, "pages:", n)
