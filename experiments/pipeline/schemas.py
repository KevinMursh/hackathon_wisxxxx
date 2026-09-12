"""各步輸出 schema（v2）。形狀對齊 prototype/data.js；to_frontend.py 負責最後轉成前端 case 物件。"""
from pydantic import BaseModel, Field


class Quote(BaseModel):
    file: str = Field(description="出處檔名，須為卷宗區塊標頭 === FILE … === 中的檔名")
    quote: str = Field(description="該檔原文逐字片段 10–60 字，不可改寫；圖片類寫畫面中可見的具體文字或內容")


class Tri(BaseModel):
    value: str | None = Field(description="該方對此欄位的說法／記載，簡短；該方未提及則 null")
    quote: Quote | None = Field(description="出處；無則 null")


class CompareRow(BaseModel):
    k: str = Field(description="欄位名，例：訴願人／原處分／收受・送達日／提起訴願日／違規時地／違規行為／舉證／裁罰額度／陳述意見程序")
    appellant: Tri | None = Field(description="訴願人方（訴願書、陳述意見書）")
    agency: Tri | None = Field(description="原處分機關方（答辯書、裁處書、通知書）")
    evidence: Tri | None = Field(description="卷證方（送達證書、稽查紀錄、照片、影片、檢舉單、係數表、車籍等）")
    conflict: str | None = Field(description="三方不一致時一句說明並指出以何者為準；一致則 null")


class Procedural(BaseModel):
    is_penalized_party: bool | None = Field(description="訴願人是否為受處分人（77③ 當事人適格）")
    has_capacity: bool | None = Field(description="訴願人是否具訴願能力（成年自然人／法人）（77④）")
    has_agent: bool | None = Field(description="是否委任代理人；有則是否附委任書（77⑤）")
    disposition_exists: bool | None = Field(description="原處分是否仍存在、未經撤銷（77⑥）")
    prior_appeal: bool | None = Field(description="是否對同一處分重行提起訴願（77⑦）")
    is_admin_disposition: bool | None = Field(description="系爭文書是否為行政處分（77⑧）")
    note: str = Field(description="上述判斷的依據，一句")


class Fields(BaseModel):
    """步驟二：結構化欄位＋三方對照＋程序要件。日期一律民國 YYY-MM-DD。"""
    appellant_masked: str = Field(description="訴願人，第二字以○遮罩")
    agency: str = Field(description="原處分機關全名")
    disposition_no: str = Field(description="裁處書文號")
    disposition_date: str = Field(description="裁處書日期")
    disposition_served_date: str | None = Field(description="裁處書送達日，只能來自送達證書類文件；無則 null")
    served_source: Quote | None
    appellant_stated_received: str | None = Field(description="訴願書自述收受日；未述 null")
    appeal_received_date: str | None = Field(description="訴願書遞送／收文日")
    penalty_amount: int | None = Field(description="罰鍰（元）")
    violation_fact: str = Field(description="原處分認定之違規事實，一至兩句")
    violation_date: str | None
    law_basis: list[str] = Field(description="原處分引用條號，格式「○○法第○條第○項第○款」，只抄不補")
    appellant_claims: list[str] = Field(description="訴願意旨逐點，一點一句")
    agency_replies: list[str] = Field(description="答辯意旨逐點；無答辯書則空")
    compare: list[CompareRow] = Field(description="三方對照表，6–10 列")
    procedural: Procedural
    case_type: str = Field(description="案件類型，例「違反廢棄物清理法」")
    main_issue: str = Field(description="主要爭點一句")


class Issue(BaseModel):
    id: str = Field(description="I1、I2…")
    title: str = Field(description="爭點標題 ≤ 20 字")
    appellant_claim: str
    agency_reply: str
    evidence: list[Quote] = Field(description="卷證原文片段 ≥ 1 則；不得引訴願書／答辯書當證據")
    laws: list[str] = Field(description="此爭點相關條文或判準，格式「○○法第○條第○項」或判解／函釋名稱；不確定不列")
    finding: str = Field(description="採訴願人／採機關／待議")
    reason: str = Field(description="一句依據，須指向 evidence")


class Issues(BaseModel):
    """步驟三：訴願人主張 vs 機關答辯 vs 卷證。"""
    procedural_issue: bool = Field(description="是否有程序爭點（逾期、不適格、非處分…）")
    issues: list[Issue]


class LawRec(BaseModel):
    kind: str = Field(description="法規／函釋／判解")
    name: str = Field(description="法規名稱（須在可用法規清單）或函釋／判解全名（須在候選清單）")
    article: str | None = Field(description="法規條號數字，如 27 或 27之1；函釋／判解 null")
    paragraph: str | None = Field(description="項款，如「第1項第1款」；無 null")
    role: str = Field(description="機關權限／處分依據／裁罰額度／裁量／程序／救濟期間／判準／政策說明")
    why: str = Field(description="與哪個爭點或事實相關，一句")
    rel: int = Field(description="相關度 0–100")


class Laws(BaseModel):
    """步驟四：應引用或審酌之法條、函釋、判解。"""
    recommended: list[LawRec]
    missing_in_defense: list[str] = Field(description="答辯書應引未引的條文或函釋；無則空")
    alert: str | None = Field(description="法規時效性警示：行為時與裁處時法條版本不同、或引用已修正條文；無則 null")


class SimNote(BaseModel):
    id: str = Field(description="候選清單中的 id，不得增減")
    one_liner: str = Field(description="該案事實與結論一句")
    why_similar: str = Field(description="與本案相似或可對照之處一句")
    score: int = Field(description="相似度 0–100")
    chips: list[str] = Field(description="2–3 個標籤，每個 ≤ 6 字")


class Sims(BaseModel):
    """步驟五：相似案例說明。"""
    notes: list[SimNote]
