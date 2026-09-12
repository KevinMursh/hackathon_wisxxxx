"""提案簡報產生器：同一份內容 → HTML(16:9) → Chrome PDF；並用 python-pptx 產出可編輯 PPTX。
架構圖使用 AWS 官方 Architecture Icons（assets/aws-icons/，取自 npm aws-icons 3.3.0）。
執行：<venv 含 python-pptx>/python build_deck.py
"""
import os, subprocess, shutil, tempfile, time, signal, base64
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

HERE = os.path.dirname(os.path.abspath(__file__))
ICON = f"{HERE}/assets/aws-icons"
OUT_PPT = f"{HERE}/提案簡報-訴願智審臺.pptx"
OUT_PDF = f"{HERE}/提案簡報-訴願智審臺.pdf"
OUT_ARCH = f"{HERE}/assets/aws-architecture.png"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP = tempfile.mkdtemp(prefix="deck-")

NAVY, INK, AMBER, GOLD, GRAY, LIGHT, LINE, GREEN = "16304F", "0F2038", "D98E04", "F2B544", "5B6573", "F4F6F9", "DDE3EA", "2E7D32"

# =====================================================================================
# 內容（單一來源）
# =====================================================================================
S = []

S.append(dict(kind="cover",
    title="訴願智審臺",
    sub="新北市訴願案件審理作業流程之 AI 輔助應用",
    tag="2026 新北市 AI 智慧城市黑客松 ｜ 法制局組",
    claim="AI 不替承辦人決定——把例行比對做完、把證據攤開，每個結論都能點回卷證原句與真實條號。",
    stats=[("1,566", "件／年　114 年訴願案量"), ("101", "份決定書全量結構化"), ("3 × 30", "頁評測卷宗包，與 RAG 隔離"), ("≤ 1", "RPS 下固定 pipeline")],
    url="Live Demo　http://100.20.156.38/"))

S.append(dict(kind="pain", sec="01 ／ 破題",
    title="法制局的三個困難，我們用三個設計回答",
    intro="訴願案量 110 年 1,238 件 → 114 年 1,566 件（+26%），洗錢防制法・廢棄物清理法・空氣污染防制法為最大宗；辦理期限不變、人力不變。",
    rows=[
        ("同類型案件分散撰擬，效率低", "每案都要人工讀卷、比對、從頭寫決定書",
         "固定五步驟 pipeline：上傳卷宗 → 自動歸戶 → 欄位／期間 → 爭點 → 法規 → 相似案例 → 草稿。程序性判斷（30 日期間、八款不受理）用程式算，不靠模型猜；每步輸出可單獨重跑。"),
        ("法規與函釋更新仰賴人工檢索", "漏查最新函釋、誤引已修正條文 → 決定書被法院撤銷",
         "法規庫「三時點」版本比對（行為時／裁處時／決定時），每條引用標示版本狀態；一鍵同步全國法規資料庫；草稿內所有條號程式查核，查無者標「未收錄」不放行。"),
        ("缺乏標準化輔助工具", "各承辦人各自為政，見解不一致；AI 只給一個答案又難以採信",
         "承辦人工作台：五分頁固定結構＋卷宗瀏覽器並排；助手是唯一修改入口——自然語言 → 所見即所得提案卡（修改前→修改後＋影響範圍）→ 承辦人確認 → 局部重跑 → 逐項回覆採納與否。"),
    ]))

S.append(dict(kind="bullets", sec="02 ／ 定位",
    title="輔助，不是取代——這是採用與否的門檻",
    bullets=[
        "AI 只給一個答案，法制局第一個反應會是「那承辦人幹嘛」。我們給的是「選項 ＋ 各自的法律後果與風險」，決定權留在承辦人。",
        "每個爭點的「AI 認定」都附一句依據＋卷證錨點：文字 PDF 反白到字元、掃描件開頁圖、影片跳到秒數。",
        "判定列明示「訴願駁回／不受理／撤銷」與適用條款、風險等級、未驗證引用清單；承辦人一眼看出 AI 為何這樣寫。",
        "問答助手「有據才答、查無就說查無」：7 個唯讀工具（查法條、查判解、查決定書、查本案卷證、算期間），查到的東西一鍵轉成修改提案。",
        "所有修改留稽核軌跡：誰改、改了什麼、AI 原判定是什麼、採納或不採納的理由。",
    ],
    note="這不是包裝——訴願法 §58 II 原處分機關自我審查、審議規則對委員會獨立判斷的要求，都需要人做最後決定。"))

S.append(dict(kind="flow", sec="03 ／ 流程",
    title="承辦人的操作流程（Live Demo 路徑）",
    steps=[
        ("上傳卷宗", "一個合併 PDF 或一批混雜檔案（掃描、手寫、照片、影片、zip）；亂檔名也行"),
        ("自動歸戶", "27 種文件類型・5 種來源；標準檔名「11-裁處書送達證書_114-09-18.jpg」；承辦人就地修正，寫稽核"),
        ("五分頁分析", "案件擷取（含期間八款檢核）→ 爭點 → 法規 → 相似案例 → 決定書草稿；SSE 逐步推進，每步完成即可看"),
        ("助手修改", "「爭點 2 改採訴願人，因為…」→ 提案卡 → 確認 → 只重跑受影響的步驟 → 逐項回覆"),
        ("補件與結案", "案件進行中補件只辨識新檔；已送審／已結案鎖定；草稿版本 v1／v2 可回溯"),
    ],
    foot="示範案件：case02 廢棄物清理法亂丟煙蒂（20 頁卷宗＋影片）— 上傳 90 秒歸戶、約 2 分鐘出五分頁。"))

S.append(dict(kind="table", sec="04 ／ 主題契合",
    title="對應命題四大功能：每一項都有可點的證據",
    head=["命題要求", "我們做到", "怎麼證明它沒有幻覺"],
    rows=[
        ["(1) 案件資訊擷取與分類", "訴願人／原處分／請求／理由逐點；案件類型＋主要爭點＋預判走向；送達日／收文日／屆滿日／在途期間", "欄位附 refs 錨點；訴願書自述收受日與送達證書不一致時標衝突、以送達證書為準"],
        ["(2) 智能法規推薦（含最新修正狀態）", "Bedrock Knowledge Base 語意檢索法規／判解／函釋 → 模型挑選 → 程式查核條號存在", "citations.status：ok／gap／pending（未收錄）；laws[].version.warn：修正日晚於行為日 → 提示行政罰法 §5"],
        ["(3) 相似案例比對（3–5 件）", "101 份決定書依領域 filter、排除本案；每案「為何相似」＋可借用理由段 → 對應本案爭點", "sims[].borrow 指到具體理由段；simDist 顯示同類案結果分布（不受理／駁回／撤銷）"],
        ["(4) 決定書草稿生成", "主文／事實／理由／綜上論結／救濟教示；few-shot 用相似決定書理由段；不受理案不寫實體", "草稿每段附 refs；unverifiedQuotes 引句回查；不受理／駁回／撤銷三種模板由程式選，不由模型決定主文"],
    ]))

S.append(dict(kind="twocol", sec="05 ／ 技術",
    title="步驟一：文件歸戶——卷宗不是乾淨 PDF，系統得看內容不看檔名",
    left=("做了什麼", [
        "正規化：pdf-text／pdf-scan／image／video／office／zip；掃描頁出頁圖、影片每 5 秒抽幀、HEIC 解碼",
        "分類：Claude Sonnet 4.5 視覺＋文字，tool-use 強制 JSON；每箱 ≤10 檔，逐箱 SSE 推結果",
        "27 種 doc_type × 5 種來源（訴願人／原處分機關／第三方／本局／未知）",
        "程式推導 nature（主張／紀錄／證物）與 timing（處分作成前／作成／爭訟後），供下游比對",
        "sha256 去重、zip 展開、合併卷宗分段不拆檔、evidence 回查失敗自動打折信心",
    ]),
    right=("實測", [
        "case02 亂檔名 20 檔（IMG_3985.jpg／scan_0001.pdf／文件(2).pdf）：90 秒、20/20 正確",
        "27 檔含 20 頁合併卷宗＋zip＋heic＋office：85 秒、3 箱",
        "承辦人 PATCH 修正類型／來源 → 標準檔名重算 → 稽核一筆",
        "Bedrock ≤ 1 RPS：單 worker 序列、2 秒起跑間隔、在途 ≤3",
    ])))

S.append(dict(kind="pipeline", sec="05 ／ 技術",
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

S.append(dict(kind="arch", sec="06 ／ AWS 架構", title="AWS 雲端技術架構（全部在競賽允許清單內）"))

S.append(dict(kind="table", sec="07 ／ 可信度",
    title="幻覺與時效控制：四道閘門",
    head=["風險", "閘門", "落地位置"],
    rows=[
        ["捏造條號／案號", "條號字典查核（11 部法規逐條）；草稿內所有引用回查；查無 → citations.status = pending，草稿標「未收錄」", "s4／s6 程式層，不靠 prompt"],
        ["引句與卷證不符", "每段 quote 回查原文；失敗列入 unverifiedQuotes；信心打 0.6 折", "歸戶 evidence_unverified；分析 refs"],
        ["引到已修正／廢止的法規", "法規庫三時點：行為時／裁處時／決定時；修正日晚於行為日 → ⚠ 提示行政罰法 §5；「同步全國法規資料庫」逐部比對官方修正日（實測 12 部：2 部新修正、10 部一致）", "lawlib／lawsync"],
        ["AI 誤判程序結論", "主文模板由程式依期間／八款檢核決定（不受理／駁回／撤銷），模型只寫理由；不受理案不寫實體", "judge → drafts.tmpl"],
    ]))

S.append(dict(kind="twocol", sec="08 ／ 資料應用",
    title="命題資料集怎麼用、缺什麼、怎麼補",
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

S.append(dict(kind="twocol", sec="08 ／ 資料應用",
    title="評測集：決定書是「輸出」，答辯書和卷證才是「輸入」——而輸入是不公開的",
    left=("問題", [
        "訴願法 §58 III／IV：答辯書只存在於機關、受理機關卷內、訴願人手上，沒有公開機制",
        "訴願法 §49、§75 II：卷宗閱覽限訴願人、參加人、代理人，第三人拿不到",
        "只拿決定書測，系統靠相似案例檢索就能「認出」同一份文件，分數虛高",
    ]),
    right=("做法：反推重建 3 案 × 30 頁卷宗包，與 RAG 嚴格隔離", [
        "case01 建築法 §77② 逾期不受理：六點實體理由當干擾，正確結論仍是不受理",
        "case02 廢清法 §79 I 駁回：20 頁＋3 幀照片＋12 秒影片；收受日 9/16 vs 送達證書 9/18；三方主張衝突",
        "case03 建築法 §81 I 撤銷：行政罰法 §27 三年時效——起算日／處分日皆在卷內，答辯書迴避不答；「固非無據、惟時效消滅」→ 單純撤銷、不附教示",
        "掃描（手寫、彩色核章）、系統截圖、照片、影片混合；每頁浮水印「模擬文件」，個資遮蔽",
        "對應的 3 份真實決定書從 KB 排除；ingestion 腳本不掃評測資料夾",
    ])))

S.append(dict(kind="table", sec="09 ／ 完成度",
    title="什麼已上線、什麼是部分、什麼還沒做",
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

S.append(dict(kind="score", sec="10 ／ 評分對照",
    title="評分項目對照",
    rows=[
        ("技術可行性", "20%", "全部使用允許清單服務；1 RPS 限制下固定 pipeline、序列 worker；掃描／手寫／影片皆可處理；已在 EC2 真跑，非 mock"),
        ("完成度", "25%", "前後端串接上線，Live Demo 可操作完整流程；歸戶 → 分析 → 修改 → 重跑 → 草稿 v2；52 個測試"),
        ("資料應用性", "30%", "101 份決定書全量結構化統計指導設計；法規／判解／函釋進 KB＋條號字典；三案卷宗包評測集與 RAG 隔離；自行補齊三個資料缺口"),
        ("主題契合度", "25%", "命題四大功能逐一對應；痛點 ①②③ 各有設計回答；輔助而非取代，決定權與稽核留在承辦人；可直接擴到洗錢／空污案型"),
    ]))

S.append(dict(kind="bullets", sec="11 ／ 落地",
    title="下一步與落地",
    bullets=[
        "補件接真歸戶 API；建議句加一次 Haiku 呼叫補充。",
        "法規同步排程化：lawsync → S3 → KB ingestion，前端顯示「資料最後同步時間」。",
        "洗錢防制法、空氣污染防制法案型：pipeline 不改，只補 KB 語料與領域 filter；資料集已完成領域統計與缺口補強。",
        "正式版：Cognito 登入、CloudFront HTTPS、決定書 ODT／PDF 匯出、與法制局公文系統對接。",
        "法制局可取回的資產：三案卷宗包評測集（可持續擴充）、法規三時點比對規則、27 種卷證分類定義。",
    ],
    note="Live Demo：http://100.20.156.38/　GitHub：含完整原始碼、部署腳本、評測集（無任何憑證）"))

S.append(dict(kind="end", title="謝謝，請指教", sub="訴願智審臺——把例行比對做完、把證據攤開，決定留給承辦人", tag="2026 新北市 AI 智慧城市黑客松 ｜ 法制局組"))

# =====================================================================================
# AWS 架構圖（HTML，官方圖示）—— 同時用於 PDF 頁面與 PPTX 嵌圖
# =====================================================================================
def icon_uri(name):
    return "data:image/svg+xml;base64," + base64.b64encode(open(f"{ICON}/{name}.svg", "rb").read()).decode()

ARCH_CSS = """
.aw{position:relative;width:1150px;height:560px;font-family:"PingFang TC","Microsoft JhengHei",sans-serif;color:#0F2038;font-size:13px;line-height:1.35}
.aw .cloud{position:absolute;left:236px;top:0;width:914px;height:560px;border:2px solid #232F3E;border-radius:6px;background:#fff}
.aw .cloud .lab{position:absolute;left:0;top:0;display:flex;align-items:center;gap:8px;padding:6px 12px 6px 8px;font-weight:700;font-size:13.5px;color:#232F3E}
.aw .cloud .lab img{width:30px;height:30px}
.aw .region{position:absolute;left:252px;top:44px;width:882px;height:500px;border:1.5px dashed #00A4A6;border-radius:6px;background:#FAFEFE}
.aw .region .lab{position:absolute;left:10px;top:8px;display:flex;align-items:center;gap:6px;font-size:12.5px;color:#00A4A6;font-weight:700}
.aw .region .lab img{width:22px;height:22px}
.aw .svc{position:absolute;background:#fff;border:1.5px solid #DDE3EA;border-radius:8px;padding:10px 12px;box-shadow:0 2px 6px rgba(15,32,56,.06)}
.aw .svc .h{display:flex;align-items:center;gap:10px;margin-bottom:6px}
.aw .svc .h img{width:40px;height:40px;flex:none}
.aw .svc .h b{font-size:14.5px;color:#0F2038;line-height:1.2}
.aw .svc .h small{display:block;font-weight:400;color:#5B6573;font-size:11.5px}
.aw .svc p{margin:0 0 2px;font-size:12.5px;color:#334}
.aw .grp{position:absolute;border:1.5px solid #ED7100;border-radius:8px;background:#FFF9F3}
.aw .grp .gl{position:absolute;left:10px;top:-13px;background:#FFF9F3;padding:0 6px;font-size:12.5px;font-weight:700;color:#ED7100;display:flex;align-items:center;gap:6px}
.aw .grp .gl img{width:24px;height:24px}
.aw .client{position:absolute;left:0;top:200px;width:214px;text-align:center}
.aw .client img{width:64px;height:64px}
.aw .client b{display:block;font-size:14.5px;margin-top:4px}
.aw .client p{margin:4px 0 0;font-size:12px;color:#334;text-align:left;padding-left:14px}
.aw svg.ar{position:absolute;left:0;top:0;width:1150px;height:560px;pointer-events:none}
.aw .ops{position:absolute;left:266px;top:472px;width:854px;height:60px;display:flex;gap:14px;align-items:center}
.aw .ops .o{display:flex;align-items:center;gap:8px;flex:1;background:#fff;border:1.5px solid #DDE3EA;border-radius:8px;padding:6px 10px;font-size:11.5px;color:#334;height:56px}
.aw .ops .o img{width:34px;height:34px;flex:none}
.aw .ops .o b{display:block;font-size:12.5px;color:#0F2038}
"""

def arch_html():
    I = icon_uri
    def arrow(x1, y1, x2, y2, label="", dash=False, ly=None):
        d = ' stroke-dasharray="6 4"' if dash else ""
        s = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#16304F" stroke-width="1.8" marker-end="url(#ah)"{d}/>'
        if label:
            s += f'<text x="{(x1+x2)/2}" y="{ly if ly is not None else (y1+y2)/2-6}" font-size="11" fill="#5B6573" text-anchor="middle">{label}</text>'
        return s
    arrows = ('<svg class="ar" viewBox="0 0 1150 560"><defs><marker id="ah" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><path d="M0,0 L9,3.5 L0,7 z" fill="#16304F"/></marker></defs>'
              + arrow(214, 262, 268, 262, "HTTP :80", ly=252)
              + arrow(459, 242, 459, 256, dash=True)
              + arrow(650, 148, 700, 148, "Converse・Retrieve", ly=140)
              + arrow(650, 290, 700, 290)
              + arrow(650, 402, 700, 402)
              + '</svg>')
    return f'''<div class="aw">
<div class="cloud"><div class="lab"><img src="{I('AWSCloudlogo')}">AWS 競賽帳號</div></div>
<div class="region"><div class="lab"><img src="{I('Region')}">Region us-west-2　｜　S3 Block Public Access　｜　Security Group 僅開 :80 給會場 IP　｜　無 access key</div></div>

<div class="client"><img src="{I('Client')}"><b>承辦人瀏覽器</b>
<p>・五分頁工作台＋卷宗瀏覽器</p><p>・SSE／輪詢看進度</p><p>・presigned URL 讀卷證</p><p>・不需 AI 背景</p></div>

<div class="grp" style="left:268px;top:94px;width:382px;height:366px">
  <div class="gl"><img src="{I('AmazonEC2')}">Amazon EC2　t3.large（systemd・無狀態）</div>
  <div class="svc" style="left:12px;top:18px;width:356px;height:128px">
    <div class="h"><b>Node 20 / Express :80<small>靜態前端 prototype/　＋　文件歸戶 API</small></b></div>
    <p>上傳 → 正規化（poppler・ffmpeg・LibreOffice）→ 裝箱 → 分類 → SSE 逐箱推結果</p>
    <p>單 worker 序列 → Bedrock ≤ 1 RPS；/api/analysis・chat・lawlib → 反代 :8100</p>
  </div>
  <div class="svc" style="left:12px;top:164px;width:356px;height:190px">
    <div class="h"><b>FastAPI :8100（Python）<small>分析・助手・法規庫</small></b></div>
    <p>分析 pipeline s2 → s6：固定步驟、每步落地、可單步重跑</p>
    <p>期間／八款檢核、條號字典查核（程式，不靠模型）</p>
    <p>異議重論證、提案預覽／確認、局部重跑</p>
    <p>助手 tool-use：7 個唯讀工具 ＋ propose_revision（須承辦人確認）</p>
    <p>法規庫 lawlib／lawsync（同步全國法規資料庫修正日）</p>
  </div>
</div>

<div class="svc" style="left:700px;top:84px;width:420px;height:128px">
  <div class="h"><img src="{I('AmazonBedrock')}"><b>Amazon Bedrock<small>Converse API・Knowledge Base</small></b></div>
  <p><b>Claude Sonnet 4.5</b>：文字＋圖片・tool-use JSON・串流・cache</p>
  <p><b>Knowledge Base</b>：法規／判解／函釋／98 決定書（評測 3 案排除）</p>
  <p>S3 Vectors・cohere embed multilingual v3・metadata filter</p>
</div>
<div class="svc" style="left:700px;top:240px;width:420px;height:100px">
  <div class="h"><img src="{I('AmazonSimpleStorageService')}"><b>Amazon S3<small>private bucket・Block Public Access</small></b></div>
  <p>cases/{{id}}/raw・normalized（頁圖與逐頁文字）</p>
  <p>kb/ 語料＋metadata・部署包・presigned URL 15 分鐘</p>
</div>
<div class="svc" style="left:700px;top:352px;width:420px;height:100px">
  <div class="h"><img src="{I('AmazonDynamoDB')}"><b>Amazon DynamoDB<small>單表 appeal-cases（PAY_PER_REQUEST）</small></b></div>
  <p>case／file／segment／job／event／audit 稽核</p>
  <p>每步分析結果・提案・分類 cache（sha256 × prompt）</p>
</div>

<div class="ops">
  <div class="o"><img src="{I('AWSIdentityandAccessManagement')}"><span><b>IAM Instance Profile</b>bedrock／s3／dynamodb／ssm 最小權限</span></div>
  <div class="o"><img src="{I('AWSSystemsManager')}"><span><b>Systems Manager</b>免 SSH；push.sh → S3 → SSM 重佈 30 秒</span></div>
  <div class="o"><img src="{I('AmazonCloudWatch')}"><span><b>CloudWatch Logs</b>兩個 service → /ntpc-law3/*（7 天）</span></div>
  <div class="o" style="border-style:dashed;opacity:.8"><img src="{I('AmazonCognito')}"><img src="{I('AmazonCloudFront')}"><span><b>正式版</b>Cognito 登入・CloudFront HTTPS</span></div>
</div>
{arrows}
</div>'''

# =====================================================================================
# HTML → PDF
# =====================================================================================
CSS = """
@page{size:1280px 720px;margin:0}*{box-sizing:border-box}
body{margin:0;font-family:"PingFang TC","Microsoft JhengHei","Noto Sans TC",sans-serif;color:#0F2038;-webkit-print-color-adjust:exact}
.s{width:1280px;height:720px;position:relative;page-break-after:always;overflow:hidden;background:#fff;padding:44px 64px 0}
.s:last-child{page-break-after:auto}
.s:before{content:"";position:absolute;left:0;top:0;width:100%;height:6px;background:linear-gradient(90deg,#16304F 0 78%,#D98E04 78% 100%)}
.sec{font-size:13px;letter-spacing:.18em;color:#D98E04;font-weight:700;margin-bottom:6px}
h1{font-size:31px;margin:0 0 6px;color:#16304F;letter-spacing:.01em;line-height:1.3;font-weight:700}
.rule{width:56px;height:4px;background:#D98E04;border-radius:2px;margin:10px 0 20px}
.foot{position:absolute;left:64px;right:64px;bottom:20px;display:flex;justify-content:space-between;font-size:12px;color:#8A93A0;border-top:1px solid #E6EAF0;padding-top:8px}
ul{margin:0;padding-left:0;list-style:none}
li{font-size:20px;line-height:1.5;margin-bottom:14px;padding-left:26px;position:relative}
li:before{content:"";position:absolute;left:4px;top:.62em;width:9px;height:9px;border-radius:50%;background:#D98E04}
.note{position:absolute;left:64px;right:64px;bottom:60px;font-size:15.5px;color:#334;background:#FFF8EA;border-left:4px solid #D98E04;padding:10px 14px;border-radius:0 6px 6px 0}
.intro{font-size:18px;color:#334;line-height:1.5;margin-bottom:16px}
table{border-collapse:separate;border-spacing:0;width:100%;font-size:16px;line-height:1.42;border-radius:8px;overflow:hidden}
th{background:#16304F;color:#fff;padding:10px 12px;text-align:left;font-weight:600}
td{border-bottom:1px solid #E6EAF0;padding:9px 12px;vertical-align:top}
tr:nth-child(even) td{background:#F7F9FB}
td:first-child{font-weight:700;color:#16304F}
.pain{display:grid;grid-template-columns:2.1fr 2fr 4.4fr;gap:14px 16px}
.pain .hd{font-size:13px;letter-spacing:.12em;color:#8A93A0;font-weight:700;padding-bottom:4px;border-bottom:2px solid #E6EAF0}
.pain .pp{display:flex;gap:12px;align-items:flex-start;font-size:17.5px;font-weight:700;color:#16304F;line-height:1.4;padding-top:4px}
.pain .pp i{flex:none;width:30px;height:30px;border-radius:50%;background:#16304F;color:#fff;font-style:normal;font-size:15px;display:flex;align-items:center;justify-content:center}
.pain .cur{font-size:15.5px;color:#334;line-height:1.45;padding-top:6px}
.pain .sol{font-size:15.5px;line-height:1.5;background:#FFF8EA;border-left:4px solid #D98E04;border-radius:0 8px 8px 0;padding:10px 14px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:36px}
.two h3{font-size:19px;color:#16304F;margin:0 0 12px;display:flex;align-items:center;gap:10px}
.two h3:before{content:"";width:8px;height:22px;background:#D98E04;border-radius:2px}
.two li{font-size:16.5px;margin-bottom:10px;padding-left:20px}.two li:before{width:7px;height:7px;top:.65em}
.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-top:6px}
.flow .c{background:#F4F6F9;border-radius:12px;padding:18px 16px;min-height:300px;position:relative}
.flow .c i{display:flex;width:36px;height:36px;border-radius:50%;background:#16304F;color:#fff;font-style:normal;font-weight:700;font-size:17px;align-items:center;justify-content:center;margin-bottom:12px}
.flow .c b{display:block;font-size:19px;color:#16304F;margin-bottom:10px}.flow .c p{font-size:15.5px;line-height:1.5;margin:0;color:#334}
.flow .c:after{content:"›";position:absolute;right:-15px;top:120px;font-size:34px;color:#C5CDD8}
.flow .c:last-child:after{content:""}
.pipe{display:grid;grid-template-columns:repeat(7,1fr);gap:10px;margin-top:6px}
.pipe .c{border:1.5px solid #DDE3EA;border-radius:10px;padding:14px 12px;min-height:320px;background:#fff;position:relative}
.pipe .c b{display:block;font-size:16.5px;color:#16304F}.pipe .c i{display:inline-block;font-style:normal;color:#B36F00;background:#FFF2D6;border-radius:4px;padding:1px 7px;font-size:12.5px;margin:8px 0 10px;font-weight:700}.pipe .c p{font-size:14px;line-height:1.5;margin:0;color:#334}
.pipe .c:after{content:"";position:absolute;right:-8px;top:24px;width:0;height:0;border-left:8px solid #C5CDD8;border-top:6px solid transparent;border-bottom:6px solid transparent}
.pipe .c:last-child:after{content:""}
.score{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:4px}
.score .c{background:#F4F6F9;border-radius:12px;padding:20px 22px;display:grid;grid-template-columns:auto 1fr;gap:6px 18px;align-items:start}
.score .pct{font-size:44px;font-weight:800;color:#16304F;line-height:1;grid-row:span 2}
.score .k{font-size:19px;font-weight:700;color:#16304F}.score .v{font-size:15.5px;line-height:1.5;color:#334}
.score .bar{grid-column:1/3;height:6px;background:#E6EAF0;border-radius:3px;overflow:hidden}.score .bar i{display:block;height:100%;background:#D98E04}
.cover{background:#16304F;color:#fff;padding:0}
.cover:before{display:none}
.cover .band{position:absolute;left:0;top:0;width:8px;height:100%;background:#D98E04}
.cover .blob{position:absolute;right:-140px;top:-160px;width:520px;height:520px;border-radius:50%;background:#1E3F68;opacity:.7}
.cover .blob2{position:absolute;right:120px;bottom:-220px;width:420px;height:420px;border-radius:50%;background:#D98E04;opacity:.12}
.cover .in{position:absolute;left:84px;top:118px;right:84px}
.cover .tag{font-size:15px;letter-spacing:.2em;color:#F2B544;font-weight:700;margin-bottom:26px}
.cover h1{color:#fff;font-size:72px;margin:0 0 6px;letter-spacing:.04em}
.cover .sub{font-size:26px;color:#C9D6E6;margin-bottom:26px}
.cover .claim{font-size:18.5px;color:#E6EDF5;line-height:1.55;max-width:820px;border-left:3px solid #D98E04;padding-left:16px}
.cover .stats{position:absolute;left:84px;right:84px;bottom:76px;display:grid;grid-template-columns:repeat(4,1fr);gap:18px}
.cover .st{background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:14px 18px}
.cover .st b{display:block;font-size:34px;color:#F2B544;line-height:1.1}.cover .st span{font-size:13.5px;color:#C9D6E6}
.cover .url{position:absolute;left:84px;bottom:36px;font-size:14px;color:#9FB0C8}
.end .in{top:250px}.end h1{font-size:60px}
"""

def h_slide(i, s):
    n = len(S); k = s["kind"]
    if k in ("cover", "end"):
        inner = f'<div class="band"></div><div class="blob"></div><div class="blob2"></div><div class="in"><div class="tag">{s["tag"]}</div><h1>{s["title"]}</h1><div class="sub">{s["sub"]}</div>'
        if k == "cover":
            inner += f'<div class="claim">{s["claim"]}</div></div><div class="stats">' + "".join(f'<div class="st"><b>{a}</b><span>{b}</span></div>' for a, b in s["stats"]) + f'</div><div class="url">{s["url"]}</div>'
        else:
            inner += "</div>"
        return f'<div class="s cover {k}">{inner}</div>'
    body = ""
    if k == "bullets":
        body = "<ul>" + "".join(f"<li>{b}</li>" for b in s["bullets"]) + "</ul>"
        if s.get("note"): body += f'<div class="note">{s["note"]}</div>'
    elif k == "pain":
        body = f'<div class="intro">{s["intro"]}</div><div class="pain"><div class="hd">痛點（命題文件）</div><div class="hd">現況</div><div class="hd">我們的設計</div>'
        for j, (a, b, c) in enumerate(s["rows"], 1):
            body += f'<div class="pp"><i>{j}</i><span>{a}</span></div><div class="cur">{b}</div><div class="sol">{c}</div>'
        body += "</div>"
    elif k == "table":
        body = "<table><tr>" + "".join(f"<th>{h}</th>" for h in s["head"]) + "</tr>"
        for r in s["rows"]:
            body += "<tr>" + "".join((f'<td style="white-space:nowrap">{c}</td>' if len(c) <= 5 else f"<td>{c}</td>") for c in r) + "</tr>"
        body += "</table>"
    elif k == "twocol":
        (lt, ll), (rt, rl) = s["left"], s["right"]
        body = f'<div class="two"><div><h3>{lt}</h3><ul>{"".join(f"<li>{x}</li>" for x in ll)}</ul></div><div><h3>{rt}</h3><ul>{"".join(f"<li>{x}</li>" for x in rl)}</ul></div></div>'
    elif k == "flow":
        body = '<div class="flow">' + "".join(f'<div class="c"><i>{j}</i><b>{a}</b><p>{b}</p></div>' for j, (a, b) in enumerate(s["steps"], 1)) + "</div>"
        body += f'<div class="note">{s["foot"]}</div>'
    elif k == "pipeline":
        body = '<div class="pipe">' + "".join(f'<div class="c"><b>{a}</b><i>{b}</i><p>{c}</p></div>' for a, b, c in s["steps"]) + "</div>"
        body += f'<div class="note">{s["foot"]}</div>'
    elif k == "score":
        body = '<div class="score">' + "".join(f'<div class="c"><div class="pct">{p}</div><div class="k">{a}</div><div class="v">{c}</div><div class="bar"><i style="width:{int(p[:-1])*2.5}%"></i></div></div>' for a, p, c in s["rows"]) + "</div>"
    elif k == "arch":
        body = f'<div style="margin-top:-10px;transform:scale(.93);transform-origin:top left">{arch_html()}</div>'
    return f'<div class="s"><div class="sec">{s["sec"]}</div><h1>{s["title"]}</h1><div class="rule"></div>{body}<div class="foot"><span>訴願智審臺 ｜ 2026 新北市 AI 智慧城市黑客松・法制局組</span><span>{i} / {n}</span></div></div>'

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
    html = f'<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><style>{CSS}{ARCH_CSS}</style></head><body>' + \
           "".join(h_slide(i + 1, s) for i, s in enumerate(S)) + "</body></html>"
    hp = f"{TMP}/deck.html"; open(hp, "w").write(html)
    _chrome(["--no-pdf-header-footer", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=5000", f"--print-to-pdf={OUT_PDF}", f"file://{hp}"], OUT_PDF)
    print("pdf", OUT_PDF)

def arch_png():
    hp = f"{TMP}/arch.html"
    open(hp, "w").write(f'<!doctype html><html><head><meta charset="utf-8"><style>body{{margin:0;background:#fff;zoom:2}}{ARCH_CSS}</style></head><body>{arch_html()}</body></html>')
    _chrome(["--hide-scrollbars", "--window-size=2300,1120", "--virtual-time-budget=4000", f"--screenshot={OUT_ARCH}", f"file://{hp}"], OUT_ARCH)
    print("arch", OUT_ARCH)
    return OUT_ARCH

# =====================================================================================
# PPTX
# =====================================================================================
FONT = "Microsoft JhengHei"
def rgb(h): return RGBColor.from_string(h)

def tb(slide, x, y, w, h, text="", size=18, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05); tf.margin_top = tf.margin_bottom = Inches(0.03)
    p = tf.paragraphs[0]; p.alignment = align
    r = p.add_run(); r.text = text; r.font.size = Pt(size); r.font.bold = bold; r.font.name = FONT; r.font.color.rgb = rgb(color)
    return box

def bullets(slide, x, y, w, h, items, size=16, color=INK, space=6):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame; tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph(); p.space_after = Pt(space)
        r0 = p.add_run(); r0.text = "●  "; r0.font.size = Pt(size - 6); r0.font.name = FONT; r0.font.color.rgb = rgb(AMBER)
        r = p.add_run(); r.text = it; r.font.size = Pt(size); r.font.name = FONT; r.font.color.rgb = rgb(color)
    return box

def rect(slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE, lw=1):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
    if line: s.line.color.rgb = rgb(line); s.line.width = Pt(lw)
    else: s.line.fill.background()
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE: s.adjustments[0] = 0.08
    return s

def circle_num(slide, x, y, d, n, size=13):
    c = rect(slide, x, y, d, d, NAVY, shape=MSO_SHAPE.OVAL)
    tf = c.text_frame; tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0; tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = str(n); r.font.size = Pt(size); r.font.bold = True; r.font.name = FONT; r.font.color.rgb = rgb("FFFFFF")

def frame(slide, i, n, s):
    rect(slide, 0, 0, 10.4, 0.06, NAVY); rect(slide, 10.4, 0, 2.933, 0.06, AMBER)
    tb(slide, 0.6, 0.32, 8, 0.3, s.get("sec", ""), 10.5, True, AMBER)
    tb(slide, 0.6, 0.55, 12.1, 0.75, s["title"], 24, True, NAVY)
    rect(slide, 0.65, 1.28, 0.55, 0.05, AMBER)
    rect(slide, 0.6, 7.0, 12.13, 0.01, "E6EAF0")
    tb(slide, 0.6, 7.03, 8, 0.3, "訴願智審臺 ｜ 2026 新北市 AI 智慧城市黑客松・法制局組", 9.5, False, "8A93A0")
    tb(slide, 11.7, 7.03, 1.03, 0.3, f"{i} / {n}", 9.5, False, "8A93A0", PP_ALIGN.RIGHT)

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
            c = t.cell(i, j); c.text = v; c.fill.solid(); c.fill.fore_color.rgb = rgb("FFFFFF" if i % 2 else "F7F9FB")
            c.margin_top = c.margin_bottom = Inches(0.04)
            for p in c.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(size); r.font.name = FONT; r.font.color.rgb = rgb(INK)
                    if j == 0: r.font.bold = True; r.font.color.rgb = rgb(NAVY)
    return t

def note(slide, text, y=6.2):
    rect(slide, 0.7, y, 11.9, 0.62, "FFF8EA"); rect(slide, 0.7, y, 0.06, 0.62, AMBER)
    tb(slide, 0.85, y + 0.02, 11.7, 0.6, text, 12, False, "334455", anchor=MSO_ANCHOR.MIDDLE)

def build_pptx(png):
    prs = Presentation(); prs.slide_width = Inches(13.333); prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]; n = len(S)
    for i, s in enumerate(S, 1):
        sl = prs.slides.add_slide(blank); k = s["kind"]
        if k in ("cover", "end"):
            rect(sl, 0, 0, 13.333, 7.5, NAVY); rect(sl, 0, 0, 0.09, 7.5, AMBER)
            rect(sl, 10.2, -1.8, 5.4, 5.4, "1E3F68", shape=MSO_SHAPE.OVAL)
            top = 1.05 if k == "cover" else 2.5
            tb(sl, 0.9, top, 11.5, 0.4, s["tag"], 12, True, GOLD)
            tb(sl, 0.9, top + 0.45, 11.5, 1.3, s["title"], 60 if k == "cover" else 50, True, "FFFFFF")
            tb(sl, 0.9, top + 1.75, 11.5, 0.6, s["sub"], 22, False, "C9D6E6")
            if k == "cover":
                rect(sl, 0.9, 3.6, 0.04, 0.85, AMBER)
                tb(sl, 1.05, 3.55, 8.6, 1.0, s["claim"], 14.5, False, "E6EDF5")
                for j, (a, bb) in enumerate(s["stats"]):
                    x = 0.9 + j * 2.95
                    rect(sl, x, 5.15, 2.75, 1.15, "24466F", shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                    tb(sl, x + 0.15, 5.2, 2.5, 0.6, a, 26, True, GOLD)
                    tb(sl, x + 0.15, 5.78, 2.5, 0.45, bb, 10.5, False, "C9D6E6")
                tb(sl, 0.9, 6.75, 8, 0.3, s["url"], 11, False, "9FB0C8")
            continue
        frame(sl, i, n, s)
        if k == "bullets":
            bullets(sl, 0.7, 1.55, 11.9, 4.5, s["bullets"], 16.5, space=11)
            if s.get("note"): note(sl, s["note"])
        elif k == "pain":
            tb(sl, 0.7, 1.45, 11.9, 0.6, s["intro"], 13, False, "334455")
            xs, ws = [0.7, 3.65, 6.35], [2.8, 2.55, 6.25]
            for j, h in enumerate(["痛點（命題文件）", "現況", "我們的設計"]):
                tb(sl, xs[j], 2.1, ws[j], 0.3, h, 10, True, "8A93A0"); rect(sl, xs[j], 2.42, ws[j], 0.02, "E6EAF0")
            for r, (a, b, c) in enumerate(s["rows"]):
                y = 2.55 + r * 1.45
                circle_num(sl, xs[0], y + 0.05, 0.36, r + 1)
                tb(sl, xs[0] + 0.45, y, ws[0] - 0.45, 1.3, a, 13.5, True, NAVY)
                tb(sl, xs[1], y, ws[1], 1.3, b, 12, False, "334455")
                rect(sl, xs[2], y, ws[2], 1.32, "FFF8EA", shape=MSO_SHAPE.ROUNDED_RECTANGLE); rect(sl, xs[2], y, 0.06, 1.32, AMBER)
                tb(sl, xs[2] + 0.14, y + 0.04, ws[2] - 0.24, 1.26, c, 11.5, False, INK)
        elif k == "table":
            ncol = len(s["head"]); col_w = {3: [2.6, 4.7, 4.6]}.get(ncol)
            if s["title"].startswith("什麼已上線"): col_w = [4.3, 1.1, 6.5]
            size = 11 if len(s["rows"]) >= 6 else 11.5
            table(sl, 0.7, 1.55, 11.9, s["head"], s["rows"], col_w, size)
        elif k == "twocol":
            for j, (t, items) in enumerate([s["left"], s["right"]]):
                x = 0.7 + j * 6.1
                rect(sl, x, 1.6, 0.08, 0.32, AMBER); tb(sl, x + 0.18, 1.52, 5.6, 0.45, t, 15.5, True, NAVY)
                bullets(sl, x, 2.05, 5.8, 4.8, items, 12.8, space=7)
        elif k == "flow":
            for j, (a, b) in enumerate(s["steps"]):
                x = 0.7 + j * 2.42
                rect(sl, x, 1.6, 2.3, 4.25, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                circle_num(sl, x + 0.18, 1.78, 0.42, j + 1, 14)
                tb(sl, x + 0.18, 2.32, 2.0, 0.5, a, 15.5, True, NAVY)
                tb(sl, x + 0.18, 2.85, 1.95, 2.9, b, 12, False, "334455")
            note(sl, s["foot"], 6.15)
        elif k == "pipeline":
            for j, (a, b, c) in enumerate(s["steps"]):
                x = 0.7 + j * 1.71
                rect(sl, x, 1.6, 1.62, 4.35, "FFFFFF", LINE, MSO_SHAPE.ROUNDED_RECTANGLE)
                tb(sl, x + 0.08, 1.7, 1.48, 0.45, a, 12.5, True, NAVY)
                rect(sl, x + 0.1, 2.16, 1.42, 0.3, "FFF2D6"); tb(sl, x + 0.1, 2.15, 1.42, 0.32, b, 9.5, True, "B36F00", anchor=MSO_ANCHOR.MIDDLE)
                tb(sl, x + 0.08, 2.55, 1.48, 3.3, c, 10.5, False, "334455")
            note(sl, s["foot"], 6.2)
        elif k == "score":
            for j, (a, p, c) in enumerate(s["rows"]):
                x, y = 0.7 + (j % 2) * 6.05, 1.55 + (j // 2) * 2.6
                rect(sl, x, y, 5.85, 2.4, LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                tb(sl, x + 0.2, y + 0.15, 1.6, 0.9, p, 34, True, NAVY)
                tb(sl, x + 1.8, y + 0.22, 3.9, 0.45, a, 16, True, NAVY)
                tb(sl, x + 1.8, y + 0.68, 3.9, 1.5, c, 11.5, False, "334455")
                rect(sl, x + 0.2, y + 2.1, 5.45, 0.07, "E6EAF0"); rect(sl, x + 0.2, y + 2.1, 5.45 * int(p[:-1]) / 40, 0.07, AMBER)
        elif k == "arch":
            sl.shapes.add_picture(png, Inches(0.95), Inches(1.4), width=Inches(11.4))
    prs.save(OUT_PPT); print("pptx", OUT_PPT)

if __name__ == "__main__":
    build_pdf()
    build_pptx(arch_png())
    shutil.rmtree(TMP, ignore_errors=True)
