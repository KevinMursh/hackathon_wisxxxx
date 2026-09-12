"""提案簡報產生器：同一份內容 → HTML(16:9) → Chrome PDF，並用 python-pptx 產出可編輯 PPTX。
執行：<venv 含 python-pptx>/python build_deck.py
"""
import os, subprocess, shutil, tempfile, time, signal
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PPT = f"{HERE}/提案簡報-訴願智審臺.pptx"
OUT_PDF = f"{HERE}/提案簡報-訴願智審臺.pdf"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP = tempfile.mkdtemp(prefix="deck-")

NAVY, AMBER, GRAY, LIGHT, RED, GREEN = "1F3A5F", "D98E04", "555555", "F2F4F7", "B3261E", "2E7D32"

# =====================================================================================
# 內容（單一來源）
# =====================================================================================
S = []  # 每張：dict(kind=..., ...)

S.append(dict(kind="cover",
    title="訴願智審臺",
    sub="新北市訴願案件審理作業流程之 AI 輔助應用",
    lines=["2026 新北市 AI 智慧城市黑客松｜法制局組", "Live Demo：http://100.20.156.38/　（AWS us-west-2）",
           "AI 不替承辦人決定——把例行比對做完、把證據攤開，每個結論都能點回卷證原句與真實條號"]))

S.append(dict(kind="pain",
    title="破題：法制局的三個困難，我們用三個設計回答",
    intro="訴願案量 110 年 1,238 件 → 114 年 1,566 件（+26%），洗錢防制法・廢棄物清理法・空氣污染防制法為最大宗；辦理期限不變、人力不變。",
    rows=[
        ("① 同類型案件分散撰擬，效率低",
         "每案都要人工讀卷、比對、從頭寫決定書",
         "固定五步驟 pipeline：上傳卷宗 → 自動歸戶 → 欄位／期間 → 爭點 → 法規 → 相似案例 → 草稿。程序性判斷（30 日期間、八款不受理）用程式算，不靠模型猜；每步輸出可單獨重跑。"),
        ("② 法規與函釋更新仰賴人工檢索",
         "漏查最新函釋、誤引已修正條文 → 決定書被法院撤銷",
         "法規庫「三時點」版本比對（行為時／裁處時／決定時），每條引用標示版本狀態；一鍵同步全國法規資料庫；草稿內所有條號程式查核，查無者標「未收錄」不放行。"),
        ("③ 缺乏標準化輔助工具",
         "各承辦人各自為政，見解不一致，AI 給一個答案又難以採信",
         "承辦人工作台：五分頁固定結構＋卷宗瀏覽器並排；助手是唯一修改入口——自然語言 → 所見即所得提案卡（修改前→修改後＋六步影響範圍）→ 承辦人確認 → 局部重跑 → 逐項回覆採納與否。"),
    ]))

S.append(dict(kind="bullets",
    title="定位：輔助，不是取代——這是採用與否的門檻",
    bullets=[
        "AI 只給一個答案，法制局第一個反應會是「那承辦人幹嘛」。我們給的是「選項 ＋ 各自的法律後果與風險」，決定權留在承辦人。",
        "每個爭點的「AI 認定」都附一句依據＋卷證錨點：文字 PDF 反白到字元、掃描件開頁圖、影片跳到秒數。",
        "判定列明示「訴願駁回／不受理／撤銷」與適用條款、風險等級、未驗證引用清單；承辦人一眼看出 AI 為何這樣寫。",
        "問答助手「有據才答、查無就說查無」：7 個唯讀工具（查法條、查判解、查決定書、查本案卷證、算期間），查到的東西一鍵轉成修改提案。",
        "所有修改留稽核軌跡：誰改、改了什麼、AI 原判定是什麼、採納或不採納的理由。",
    ],
    note="這不是包裝——訴願法 §58 II 原處分機關自我審查、審議規則對委員會獨立判斷的要求，都需要人做最後決定。"))

S.append(dict(kind="flow",
    title="承辦人的操作流程（Live Demo 路徑）",
    steps=[
        ("1 上傳卷宗", "一個合併 PDF 或一批混雜檔案（掃描、手寫、照片、影片、zip）；亂檔名也行"),
        ("2 自動歸戶", "27 種文件類型・5 種來源；標準檔名「11-裁處書送達證書_114-09-18.jpg」；承辦人就地修正，寫稽核"),
        ("3 五分頁分析", "案件擷取（含期間八款檢核）→ 爭點 → 法規 → 相似案例 → 決定書草稿；SSE 逐步推進，每步完成即可看"),
        ("4 助手修改", "「爭點 2 改採訴願人，因為…」→ 提案卡 → 確認 → 只重跑受影響的步驟 → 逐項回覆"),
        ("5 補件與結案", "案件進行中補件只辨識新檔；已送審／已結案鎖定；草稿版本 v1／v2 可回溯"),
    ],
    foot="示範案件：case02 廢棄物清理法亂丟煙蒂（20 頁卷宗＋影片）— 上傳 90 秒歸戶、約 2 分鐘出五分頁。"))

S.append(dict(kind="table",
    title="對應命題四大功能：每一項都有可點的證據",
    head=["命題要求", "我們做到", "怎麼證明它沒有幻覺"],
    rows=[
        ["(1) 案件資訊擷取與分類", "訴願人／原處分／請求／理由逐點；案件類型＋主要爭點＋預判走向；送達日／收文日／屆滿日／在途期間", "欄位附 refs 錨點；訴願書自述收受日與送達證書不一致時標衝突、以送達證書為準"],
        ["(2) 智能法規推薦（含最新修正狀態）", "Bedrock Knowledge Base 語意檢索法規／判解／函釋 → 模型挑選 → 程式查核條號存在", "citations.status：ok／gap／pending（未收錄）；laws[].version.warn：修正日晚於行為日 → 提示行政罰法 §5"],
        ["(3) 相似案例比對（3–5 件）", "101 份決定書依領域 filter、排除本案；每案「為何相似」＋可借用理由段 → 對應本案爭點", "sims[].borrow 指到具體理由段；simDist 顯示同類案結果分布（不受理／駁回／撤銷）"],
        ["(4) 決定書草稿生成", "主文／事實／理由／綜上論結／救濟教示；few-shot 用相似決定書理由段；不受理案不寫實體", "草稿每段附 refs；unverifiedQuotes 引句回查；不受理／駁回／撤銷三種模板由程式選，不由模型決定主文"],
    ]))

S.append(dict(kind="twocol",
    title="步驟一：文件歸戶——卷宗不是乾淨 PDF，系統得看內容不看檔名",
    left=("做了什麼", [
        "正規化：pdf-text／pdf-scan／image／video／office／zip；掃描頁出頁圖、影片每 5 秒抽幀、HEIC 解碼",
        "分類：Claude Sonnet 4.5 視覺＋文字，tool-use 強制 JSON；每箱 ≤10 檔，逐箱 SSE 推結果",
        "27 種 doc_type（訴願書／答辯書／裁處書／送達證書／稽查紀錄／採證影片…）× 5 種來源（訴願人／原處分機關／第三方／本局／未知）",
        "程式推導 nature（主張／紀錄／證物）與 timing（處分作成前／作成／爭訟後），供下游比對",
        "sha256 去重、zip 展開、合併卷宗分段不拆檔、evidence 回查失敗自動打折信心",
    ]),
    right=("實測", [
        "case02 亂檔名 20 檔（IMG_3985.jpg／scan_0001.pdf／文件(2).pdf）：90 秒、20/20 正確",
        "27 檔含 20 頁合併卷宗＋zip＋heic＋office：85 秒、3 箱",
        "承辦人 PATCH 修正類型／來源 → 標準檔名重算 → 稽核一筆",
        "Bedrock ≤ 1 RPS：單 worker 序列、2 秒起跑間隔、在途 ≤3",
    ])))

S.append(dict(kind="pipeline",
    title="步驟二～五：固定 pipeline，不是自由 agent——1 RPS 下呼叫次數必須可預測",
    steps=[
        ("s2 欄位擷取", "1 次 Converse", "訴願人／處分文號／日期／請求／理由；三時點"),
        ("期間・程序", "0 次（程式）", "訴願法 §14 次日起 30 日、在途期間、§77 八款逐款 pass／fail"),
        ("s3 爭點", "1 次", "訴願書 vs 答辯書 vs 卷證三方比對；每爭點附 quote；AI 認定＋一句依據"),
        ("s4 法規", "KB Retrieve＋1 次", "候選 → 挑選 → 條號字典查核；版本三時點比對"),
        ("s5 相似案例", "KB Retrieve＋1 次", "領域 filter、排除本案；為何相似；可借用理由段"),
        ("s6 草稿", "1 次串流", "模板由程式依判定選；few-shot 理由段；條號回查"),
        ("異議／提案", "1 次重論證", "採納→只重跑受影響步驟、草稿出 v2；不採納→附證據回覆"),
    ],
    foot="每步落地 S3＋DynamoDB，可單步重跑、可做 eval；case02 全程 6 次呼叫、約 2 分鐘。"))

S.append(dict(kind="arch", title="AWS 雲端技術架構（全部在競賽允許清單內）"))

S.append(dict(kind="table",
    title="幻覺與時效控制：四道閘門",
    head=["風險", "閘門", "落地位置"],
    rows=[
        ["捏造條號／案號", "條號字典查核（11 部法規逐條）；草稿內所有引用回查；查無 → citations.status = pending，草稿標「未收錄」", "s4／s6 程式層，不靠 prompt"],
        ["引句與卷證不符", "每段 quote 回查原文；失敗列入 unverifiedQuotes；信心打 0.6 折", "歸戶 evidence_unverified；分析 refs"],
        ["引到已修正／廢止的法規", "法規庫三時點：行為時／裁處時／決定時；修正日晚於行為日 → ⚠ 提示行政罰法 §5；「同步全國法規資料庫」逐部比對官方修正日（實測 12 部：2 部新修正、10 部一致）", "lawlib／lawsync"],
        ["AI 誤判程序結論", "主文模板由程式依期間／八款檢核決定（不受理／駁回／撤銷），模型只寫理由；不受理案不寫實體", "judge → drafts.tmpl"],
    ]))

S.append(dict(kind="twocol",
    title="資料應用性：命題資料集怎麼用、缺什麼、怎麼補",
    left=("命題方提供（僅供競賽）", [
        "101 份歷史決定書（110–114 年）→ 檔名四段結構解析：領域 × 結果交叉統計；不受理 70／駁回 15／撤銷 3／撤銷另處 12／混合 1",
        "11 部法規 → 逐條切片建條號字典＋KB；19 則判解、10 則函釋 → KB metadata（kind／law／article）",
        "發現：不受理占 69%，每個領域都以不受理為主——所以期間計算必須是程式、不能是模型",
        "發現：空氣污染防制法是命題三大宗之一，但資料集零判解零函釋 → 上網補齊",
    ]),
    right=("自行蒐集補強（皆政府公開來源）", [
        "政府資訊公開法全文（判解有引、法規本體原缺）",
        "洗錢防制法「帳戶控制權」判準：臺北市 114 年決定書＋法務部 114 年書函",
        "空污法：臺北市 114 年決定書＋環保署 108／環境部 113 年函",
        "官方訴願書／答辯書／委任書／閱卷申請書範本（新北市法制局、行政院、彰化縣法制處）",
        "個資紅線：真實案件資料不送第三方服務；競賽環境只用去識別化資料，全部在 AWS 帳號內處理",
    ])))

S.append(dict(kind="twocol",
    title="評測集：決定書是「輸出」，答辯書和卷證才是「輸入」——而輸入是不公開的",
    left=("問題", [
        "訴願法 §58 III／IV：答辯書只存在於機關、受理機關卷內、訴願人手上，沒有公開機制",
        "訴願法 §49、§75 II：卷宗閱覽限訴願人、參加人、代理人，第三人拿不到",
        "只拿決定書測，系統靠相似案例檢索就能「認出」同一份文件，分數虛高",
    ]),
    right=("做法：反推重建 3 案 × 30 頁卷宗包，與 RAG 嚴格隔離", [
        "case01 建築法 §77② 逾期不受理：訴願書 10＋答辯書 10＋卷證 10；六點實體理由當干擾，正確結論仍是不受理",
        "case02 廢清法 §79 I 駁回：20 頁＋3 幀照片＋12 秒影片；訴願書收受日 9/16 vs 送達證書 9/18；三方主張衝突",
        "case03 建築法 §81 I 撤銷：行政罰法 §27 三年時效——起算日／處分日皆在卷內，答辯書迴避不答；機關實體事證強但「固非無據、惟時效消滅」→ 單純撤銷、不附教示",
        "掃描（手寫、彩色核章）、系統截圖、照片、影片混合；每頁浮水印「模擬文件」，個資遮蔽",
        "對應的 3 份真實決定書從 KB 排除；ingestion 腳本不掃評測資料夾",
    ])))

S.append(dict(kind="table",
    title="完成度：什麼已上線、什麼是 mock、什麼還沒做",
    head=["模組", "狀態", "說明"],
    rows=[
        ["文件歸戶 API（Node）", "✅ 上線", "7 支 endpoint、job 佇列、SSE 可重連、S3＋DynamoDB、稽核、demo 真跑"],
        ["分析 API（FastAPI，經 Node 反代）", "✅ 上線", "analyze／analysis／objection／reanalyze／lawlib／lawlib sync；case02、case03 樣本為真實跑出"],
        ["助手 API", "✅ 上線", "chat（唯讀）＋ propose_revision → proposals get／confirm／cancel；confirm 逐項走 objection；提案預覽只改寫受影響段落"],
        ["前端工作台（五分頁、卷宗瀏覽器、助手、補件、案件庫、法規庫）", "✅ 上線", "步驟一、步驟 2–5、助手、卷宗檢視均接真 API"],
        ["法規庫同步", "✅ 上線", "逐部抓全國法規資料庫修正日；約 1–2 分鐘"],
        ["補件辨識", "◐ 部分", "UI 完成；接真歸戶 API 為下一步"],
        ["登入／HTTPS", "✗ 未做", "SG IP 白名單代替；正式版加 Cognito＋CloudFront"],
        ["自動化測試", "✅", "pipeline／assistant／API 52 個測試＋ LIVE 測試"],
    ]))

S.append(dict(kind="table",
    title="評分項目對照",
    head=["評分項目", "配比", "我們的證據"],
    rows=[
        ["技術可行性", "20%", "全部使用允許清單服務；1 RPS 限制下固定 pipeline、序列 worker；掃描／手寫／影片皆可處理；已在 EC2 真跑，非 mock"],
        ["完成度", "25%", "前後端串接上線，Live Demo 可操作完整流程；歸戶→分析→修改→重跑→草稿 v2；52 個測試"],
        ["資料應用性", "30%", "101 份決定書全量結構化統計指導設計；法規／判解／函釋進 KB＋條號字典；三案卷宗包評測集與 RAG 隔離；自行補齊三個資料缺口"],
        ["主題契合度", "25%", "命題四大功能逐一對應；痛點 ①②③ 各有設計回答；輔助而非取代，決定權與稽核留在承辦人；可直接擴到洗錢／空污案型"],
    ]))

S.append(dict(kind="bullets",
    title="下一步與落地",
    bullets=[
        "補件接真歸戶 API；建議句加一次 Haiku 呼叫補充。",
        "法規同步排程化：lawsync → S3 → KB ingestion，前端顯示「資料最後同步時間」。",
        "洗錢防制法、空氣污染防制法案型：pipeline 不改，只補 KB 語料與領域 filter；資料集已完成領域統計與缺口補強。",
        "正式版：Cognito 登入、CloudFront HTTPS、決定書 ODT／PDF 匯出、與法制局公文系統對接。",
        "法制局可取回的資產：三案卷宗包評測集（可持續擴充）、法規三時點比對規則、27 種卷證分類定義。",
    ],
    note="Live Demo：http://100.20.156.38/　GitHub：含完整原始碼、部署腳本、評測集（無任何憑證）"))

S.append(dict(kind="cover",
    title="謝謝，請指教",
    sub="訴願智審臺——把例行比對做完、把證據攤開，決定留給承辦人",
    lines=["2026 新北市 AI 智慧城市黑客松｜法制局組"]))

# =====================================================================================
# 架構圖（SVG，HTML 直接用；PPTX 轉 PNG 嵌入）
# =====================================================================================
def arch_svg():
    def box(x, y, w, h, title, lines, fill="#fff", stroke=NAVY, tfill=NAVY, r=8, fs=14.5, gap=20):
        t = f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="#{stroke}" stroke-width="1.8"/>'
        t += f'<text x="{x+14}" y="{y+26}" font-size="{fs+2.5}" font-weight="700" fill="#{tfill}">{title}</text>'
        for i, l in enumerate(lines):
            t += f'<text x="{x+14}" y="{y+50+i*gap}" font-size="{fs}" fill="#333">{l}</text>'
        return t
    def arrow(x1, y1, x2, y2, label="", dash=False, lx=None, ly=None):
        d = ' stroke-dasharray="7 5"' if dash else ""
        s = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#{NAVY}" stroke-width="2" marker-end="url(#ah)"{d}/>'
        if label:
            s += f'<text x="{lx if lx is not None else (x1+x2)/2}" y="{ly if ly is not None else (y1+y2)/2-7}" font-size="12.5" fill="#{GRAY}" text-anchor="middle">{label}</text>'
        return s
    g = f'''<svg viewBox="0 0 1180 600" xmlns="http://www.w3.org/2000/svg" font-family="PingFang TC,Microsoft JhengHei,sans-serif">
<defs><marker id="ah" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#{NAVY}"/></marker></defs>
<rect x="0" y="0" width="1180" height="600" fill="#fff"/>
<rect x="244" y="14" width="928" height="574" rx="12" fill="#FAFBFD" stroke="#{AMBER}" stroke-width="2.2" stroke-dasharray="9 6"/>
<text x="262" y="40" font-size="15" font-weight="700" fill="#{AMBER}">AWS 競賽帳號 us-west-2 ｜ S3 Block Public Access ｜ SG 僅開 :80 給會場 IP ｜ 無 access key（Instance Profile）</text>
'''
    g += box(14, 230, 208, 140, "承辦人瀏覽器", ["五分頁工作台＋卷宗瀏覽器", "SSE／輪詢看進度", "presigned URL 讀卷證", "不需 AI 背景"], fill="#F2F4F7")
    g += arrow(222, 300, 258, 300, ":80", ly=290)
    g += f'<rect x="258" y="58" width="400" height="520" rx="10" fill="#fff" stroke="#{NAVY}" stroke-width="2.2"/>'
    g += f'<text x="274" y="84" font-size="17" font-weight="700" fill="#{NAVY}">Amazon EC2 t3.large（systemd・無狀態）</text>'
    g += box(274, 98, 368, 190, "Node 20 / Express :80", ["靜態前端 prototype/", "文件歸戶 API：上傳 → 正規化 → 裝箱", "　→ 分類 → SSE 逐箱推結果", "poppler・ffmpeg・LibreOffice", "單 worker 序列 → Bedrock ≤ 1 RPS", "/api/analysis・chat・lawlib → 反代"], fill="#F7F9FC")
    g += arrow(458, 288, 458, 318, "", dash=True)
    g += box(274, 320, 368, 240, "FastAPI :8100（Python）", ["分析 pipeline s2→s6：固定步驟、每步落地", "期間／八款檢核、條號字典查核（程式）", "異議重論證、提案預覽／確認、局部重跑", "助手 tool-use：7 個唯讀工具", "　＋ propose_revision（須承辦人確認）", "法規庫 lawlib／lawsync", "　（同步全國法規資料庫修正日）"], fill="#F7F9FC", gap=21)
    g += box(690, 58, 470, 150, "Amazon Bedrock", ["Converse — Claude Sonnet 4.5", "　文字＋圖片・tool-use 強制 JSON・串流・prompt cache", "Knowledge Base — 法規／判解／函釋／98 份決定書", "　S3 Vectors・cohere embed multilingual v3・metadata filter"], fill="#FFF8EC", stroke=AMBER, tfill=AMBER, gap=22)
    g += box(690, 224, 470, 92, "Amazon S3（private bucket）", ["cases/{id}/raw・normalized 頁圖與文字", "kb/ 語料＋metadata・部署包・presigned 15 分鐘"], fill="#F0F7F1", stroke=GREEN, tfill=GREEN)
    g += box(690, 326, 470, 92, "Amazon DynamoDB（單表 appeal-cases）", ["case／file／segment／job／event／audit 稽核", "每步分析結果・提案・分類 cache（sha256 × prompt）"], fill="#F0F7F1", stroke=GREEN, tfill=GREEN)
    g += box(690, 430, 470, 146, "身分與維運", ["IAM Instance Profile：bedrock／s3／dynamodb／ssm 最小權限", "SSM 免 SSH；push.sh 打包 → S3 → SSM 重佈（30 秒）", "CloudWatch Logs：兩個 service → /ntpc-law3/*（7 天）", "唯一外部來源：全國法規資料庫（法規同步）"], fill="#F2F4F7", stroke=GRAY, tfill=GRAY, gap=22)
    g += arrow(658, 130, 690, 130)
    g += arrow(658, 270, 690, 270)
    g += arrow(658, 372, 690, 372)
    g += '</svg>'
    return g

# =====================================================================================
# HTML → PDF
# =====================================================================================
CSS = """
@page{size:1280px 720px;margin:0}*{box-sizing:border-box}
body{margin:0;font-family:"PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;color:#222}
.s{width:1280px;height:720px;position:relative;page-break-after:always;overflow:hidden;background:#fff;padding:48px 64px}
.s:last-child{page-break-after:auto}
.bar{position:absolute;left:0;top:0;width:100%;height:10px;background:#1F3A5F}
.bar:after{content:"";position:absolute;right:0;top:0;width:180px;height:10px;background:#D98E04}
h1{font-size:34px;margin:6px 0 18px;color:#1F3A5F;letter-spacing:.02em;line-height:1.25}
.pn{position:absolute;right:40px;bottom:22px;font-size:13px;color:#999}
.brand{position:absolute;left:64px;bottom:22px;font-size:13px;color:#999}
ul{margin:0;padding-left:26px}li{font-size:21px;line-height:1.5;margin-bottom:12px}
.note{position:absolute;left:64px;right:64px;bottom:56px;font-size:16px;color:#555;border-left:4px solid #D98E04;padding-left:12px}
.intro{font-size:19px;color:#444;margin-bottom:16px;line-height:1.45}
table{border-collapse:collapse;width:100%;font-size:16.5px;line-height:1.4}
th{background:#1F3A5F;color:#fff;padding:9px 11px;text-align:left;font-weight:600}
td{border-bottom:1px solid #d8dce3;padding:9px 11px;vertical-align:top}
td:first-child{font-weight:600;color:#1F3A5F;white-space:nowrap}
.pain{display:grid;grid-template-columns:1fr 1fr 1.7fr;gap:0 18px}
.pain .h{background:#1F3A5F;color:#fff;font-size:16px;padding:6px 12px;margin-bottom:8px}
.pain .c{font-size:16.5px;line-height:1.45;padding:10px 12px;border-bottom:1px solid #d8dce3;min-height:96px}
.pain .c.sol{background:#FFF8EC;border-left:4px solid #D98E04}
.pain .c.pp{font-weight:600;color:#1F3A5F}
.two{display:grid;grid-template-columns:1fr 1fr;gap:34px}
.two h3{font-size:20px;color:#D98E04;margin:0 0 10px;border-bottom:2px solid #D98E04;padding-bottom:4px}
.two li{font-size:17.5px;margin-bottom:9px}
.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-top:10px}
.flow div{background:#F2F4F7;border-top:6px solid #1F3A5F;padding:14px;min-height:300px}
.flow b{display:block;font-size:20px;color:#1F3A5F;margin-bottom:10px}.flow p{font-size:16.5px;line-height:1.5;margin:0}
.pipe{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-top:8px}
.pipe div{border:1.5px solid #1F3A5F;border-radius:8px;padding:10px 9px;min-height:330px;background:#fff}
.pipe b{display:block;font-size:17px;color:#1F3A5F}.pipe i{display:block;font-style:normal;color:#D98E04;font-size:14px;margin:4px 0 8px;font-weight:600}.pipe p{font-size:14.5px;line-height:1.45;margin:0}
.cover{background:#1F3A5F;color:#fff}.cover h1{color:#fff;font-size:64px;margin-top:150px;margin-bottom:8px}
.cover .sub{font-size:28px;color:#FFD27A;margin-bottom:40px}.cover p{font-size:19px;margin:6px 0;color:#dfe6f0}
.cover .bar{display:none}
"""

def h_slide(i, s):
    n = len(S)
    body = ""
    if s["kind"] == "cover":
        return f'<div class="s cover"><h1>{s["title"]}</h1><div class="sub">{s["sub"]}</div>{"".join(f"<p>{l}</p>" for l in s["lines"])}<div class="pn" style="color:#9fb0c8">{i}/{n}</div></div>'
    if s["kind"] == "bullets":
        body = "<ul>" + "".join(f"<li>{b}</li>" for b in s["bullets"]) + "</ul>"
        if s.get("note"): body += f'<div class="note">{s["note"]}</div>'
    elif s["kind"] == "pain":
        body = f'<div class="intro">{s["intro"]}</div><div class="pain"><div class="h">痛點（命題文件）</div><div class="h">現況</div><div class="h">我們的設計</div>'
        for a, b, c in s["rows"]:
            body += f'<div class="c pp">{a}</div><div class="c">{b}</div><div class="c sol">{c}</div>'
        body += "</div>"
    elif s["kind"] == "table":
        body = "<table><tr>" + "".join(f"<th>{h}</th>" for h in s["head"]) + "</tr>"
        for r in s["rows"]:
            body += "<tr>" + "".join(f"<td{chr(32)}style=\"white-space:nowrap\">{c}</td>" if len(c) <= 5 else f"<td>{c}</td>" for c in r) + "</tr>"
        body += "</table>"
    elif s["kind"] == "twocol":
        (lt, ll), (rt, rl) = s["left"], s["right"]
        body = f'<div class="two"><div><h3>{lt}</h3><ul>{"".join(f"<li>{x}</li>" for x in ll)}</ul></div><div><h3>{rt}</h3><ul>{"".join(f"<li>{x}</li>" for x in rl)}</ul></div></div>'
    elif s["kind"] == "flow":
        body = '<div class="flow">' + "".join(f"<div><b>{a}</b><p>{b}</p></div>" for a, b in s["steps"]) + "</div>"
        body += f'<div class="note">{s["foot"]}</div>'
    elif s["kind"] == "pipeline":
        body = '<div class="pipe">' + "".join(f"<div><b>{a}</b><i>{b}</i><p>{c}</p></div>" for a, b, c in s["steps"]) + "</div>"
        body += f'<div class="note">{s["foot"]}</div>'
    elif s["kind"] == "arch":
        body = f'<div style="margin-top:-6px">{arch_svg()}</div>'
    return f'<div class="s"><div class="bar"></div><h1>{s["title"]}</h1>{body}<div class="brand">訴願智審臺｜法制局組</div><div class="pn">{i}/{n}</div></div>'

def _chrome(args, out_file):
    prof = tempfile.mkdtemp(prefix="cp-", dir=TMP)
    if os.path.exists(out_file): os.remove(out_file)
    p = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run", "--disable-extensions",
                          f"--user-data-dir={prof}", *args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
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
    html = f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>{CSS}</style></head><body>' + \
           "".join(h_slide(i + 1, s) for i, s in enumerate(S)) + "</body></html>"
    hp = f"{TMP}/deck.html"; open(hp, "w").write(html)
    _chrome(["--no-pdf-header-footer", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=4000", f"--print-to-pdf={OUT_PDF}", f"file://{hp}"], OUT_PDF)
    print("pdf", OUT_PDF)

def arch_png():
    hp = f"{TMP}/arch.html"; pg = f"{TMP}/arch.png"
    svg = arch_svg().replace("viewBox", 'width="2360" height="1120" viewBox')
    open(hp, "w").write('<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;background:#fff}</style></head><body>' + svg + '</body></html>')
    _chrome(["--hide-scrollbars", "--window-size=2360,1120", "--virtual-time-budget=3000", f"--screenshot={pg}", f"file://{hp}"], pg)
    return pg

# =====================================================================================
# PPTX
# =====================================================================================
FONT = "Microsoft JhengHei"
def rgb(h): return RGBColor.from_string(h)

def tb(slide, x, y, w, h, text="", size=18, bold=False, color="222222", align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05); tf.margin_top = tf.margin_bottom = Inches(0.03)
    p = tf.paragraphs[0]; p.alignment = align
    r = p.add_run(); r.text = text; r.font.size = Pt(size); r.font.bold = bold; r.font.name = FONT; r.font.color.rgb = rgb(color)
    return box

def bullets(slide, x, y, w, h, items, size=16, color="222222", space=6):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame; tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(space)
        r = p.add_run(); r.text = "•  " + it; r.font.size = Pt(size); r.font.name = FONT; r.font.color.rgb = rgb(color)
    return box

def rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
    if line: s.line.color.rgb = rgb(line); s.line.width = Pt(1)
    else: s.line.fill.background()
    s.shadow.inherit = False
    return s

def chrome_frame(slide, i, n, title):
    rect(slide, 0, 0, 13.333, 0.11, NAVY); rect(slide, 11.4, 0, 1.933, 0.11, AMBER)
    tb(slide, 0.6, 0.35, 12.1, 0.8, title, 26, True, NAVY)
    tb(slide, 0.6, 7.05, 6, 0.3, "訴願智審臺｜法制局組", 10, False, "999999")
    tb(slide, 11.8, 7.05, 1, 0.3, f"{i}/{n}", 10, False, "999999", PP_ALIGN.RIGHT)

def table(slide, x, y, w, head, rows, col_w=None, size=11.5, row_h=0.42):
    nr, nc = len(rows) + 1, len(head)
    t = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(row_h * nr)).table
    if col_w:
        for j, cw in enumerate(col_w): t.columns[j].width = Inches(cw)
    for j, h in enumerate(head):
        c = t.cell(0, j); c.text = h; c.fill.solid(); c.fill.fore_color.rgb = rgb(NAVY)
        for p in c.text_frame.paragraphs:
            for r in p.runs: r.font.size = Pt(size + 0.5); r.font.bold = True; r.font.name = FONT; r.font.color.rgb = rgb("FFFFFF")
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row):
            c = t.cell(i, j); c.text = v; c.fill.solid(); c.fill.fore_color.rgb = rgb("FFFFFF" if i % 2 else LIGHT)
            c.margin_top = c.margin_bottom = Inches(0.04)
            for p in c.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(size); r.font.name = FONT
                    if j == 0: r.font.bold = True; r.font.color.rgb = rgb(NAVY)
    return t

def build_pptx(png):
    prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]; n = len(S)
    for i, s in enumerate(S, 1):
        sl = prs.slides.add_slide(blank)
        k = s["kind"]
        if k == "cover":
            rect(sl, 0, 0, 13.333, 7.5, NAVY)
            tb(sl, 0.9, 2.0, 11.5, 1.3, s["title"], 54, True, "FFFFFF")
            tb(sl, 0.9, 3.3, 11.5, 0.7, s["sub"], 24, False, "FFD27A")
            bullets(sl, 0.9, 4.3, 11.5, 2, s["lines"], 15, "DFE6F0", 4)
            tb(sl, 11.8, 7.05, 1, 0.3, f"{i}/{n}", 10, False, "9FB0C8", PP_ALIGN.RIGHT)
            continue
        chrome_frame(sl, i, n, s["title"])
        if k == "bullets":
            bullets(sl, 0.7, 1.35, 11.9, 4.8, s["bullets"], 17, space=10)
            if s.get("note"):
                rect(sl, 0.7, 6.25, 0.06, 0.6, AMBER); tb(sl, 0.85, 6.22, 11.7, 0.7, s["note"], 12.5, False, "555555")
        elif k == "pain":
            tb(sl, 0.7, 1.25, 11.9, 0.7, s["intro"], 13.5, False, "444444")
            xs, ws = [0.7, 3.5, 6.3], [2.7, 2.7, 6.3]
            for j, h in enumerate(["痛點（命題文件）", "現況", "我們的設計"]):
                rect(sl, xs[j], 2.0, ws[j], 0.38, NAVY); tb(sl, xs[j], 2.0, ws[j], 0.38, h, 12.5, True, "FFFFFF", anchor=MSO_ANCHOR.MIDDLE)
            for r, (a, b, c) in enumerate(s["rows"]):
                y = 2.45 + r * 1.5
                tb(sl, xs[0], y, ws[0], 1.4, a, 13, True, NAVY)
                tb(sl, xs[1], y, ws[1], 1.4, b, 12.5, False, "333333")
                rect(sl, xs[2], y, ws[2], 1.4, "FFF8EC"); rect(sl, xs[2], y, 0.06, 1.4, AMBER)
                tb(sl, xs[2] + 0.12, y + 0.02, ws[2] - 0.2, 1.36, c, 12, False, "222222")
        elif k == "table":
            ncol = len(s["head"]); col_w = {3: [2.6, 4.7, 4.6], 2: [4, 7.9]}.get(ncol)
            if s["title"].startswith("完成度"): col_w = [4.3, 1.1, 6.5]
            if s["title"].startswith("評分"): col_w = [1.8, 0.9, 9.2]
            size = 11 if len(s["rows"]) >= 6 else 11.5
            table(sl, 0.7, 1.35, 11.9, s["head"], s["rows"], col_w, size)
        elif k == "twocol":
            for j, (t, items) in enumerate([s["left"], s["right"]]):
                x = 0.7 + j * 6.1
                tb(sl, x, 1.3, 5.8, 0.45, t, 16, True, AMBER); rect(sl, x, 1.75, 5.8, 0.03, AMBER)
                bullets(sl, x, 1.9, 5.8, 5, items, 13.5, space=7)
        elif k == "flow":
            for j, (a, b) in enumerate(s["steps"]):
                x = 0.7 + j * 2.42
                rect(sl, x, 1.5, 2.3, 4.2, LIGHT); rect(sl, x, 1.5, 2.3, 0.08, NAVY)
                tb(sl, x + 0.1, 1.7, 2.1, 0.5, a, 16, True, NAVY)
                tb(sl, x + 0.1, 2.25, 2.1, 3.3, b, 12.5, False, "333333")
            rect(sl, 0.7, 6.1, 0.06, 0.6, AMBER); tb(sl, 0.85, 6.07, 11.7, 0.7, s["foot"], 12.5, False, "555555")
        elif k == "pipeline":
            for j, (a, b, c) in enumerate(s["steps"]):
                x = 0.7 + j * 1.71
                rect(sl, x, 1.45, 1.62, 4.4, "FFFFFF", NAVY, MSO_SHAPE.ROUNDED_RECTANGLE)
                tb(sl, x + 0.08, 1.55, 1.48, 0.45, a, 13, True, NAVY)
                tb(sl, x + 0.08, 1.98, 1.48, 0.4, b, 11, True, AMBER)
                tb(sl, x + 0.08, 2.4, 1.48, 3.4, c, 11, False, "333333")
            rect(sl, 0.7, 6.15, 0.06, 0.6, AMBER); tb(sl, 0.85, 6.12, 11.7, 0.7, s["foot"], 12.5, False, "555555")
        elif k == "arch":
            sl.shapes.add_picture(png, Inches(0.55), Inches(1.2), width=Inches(12.2))
    prs.save(OUT_PPT); print("pptx", OUT_PPT)

if __name__ == "__main__":
    build_pdf()
    build_pptx(arch_png())
    shutil.rmtree(TMP, ignore_errors=True)
