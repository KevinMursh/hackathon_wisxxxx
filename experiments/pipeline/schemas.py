"""各步輸出 schema。欄位形狀對齊 prototype/data.js（fields / period / checks / issues / laws / citations / sims / drafts）。"""
from pydantic import BaseModel, Field


class Quote(BaseModel):
    file: str = Field(description="出處檔名，須為卷宗中存在的檔名")
    quote: str = Field(description="該檔原文逐字片段（10–60 字），不可改寫")


class Fields(BaseModel):
    """步驟二：從訴願書、裁處書、送達證書、答辯書擷取的結構化欄位。日期一律民國 YYY-MM-DD。"""
    appellant_masked: str = Field(description="訴願人，第二字以○遮罩")
    agency: str = Field(description="原處分機關全名")
    disposition_no: str = Field(description="原處分（裁處書）文號")
    disposition_date: str = Field(description="裁處書日期")
    disposition_served_date: str | None = Field(description="裁處書送達日，以送達證書為準；無送達證書則 null")
    served_source: Quote | None = Field(description="送達日的出處")
    appellant_stated_received: str | None = Field(description="訴願書自述收受處分日；未述則 null")
    appeal_received_date: str | None = Field(description="訴願書遞送／收文日")
    penalty_amount: int | None = Field(description="罰鍰金額（新臺幣元），無則 null")
    violation_fact: str = Field(description="原處分認定的違規事實，一至兩句")
    violation_date: str | None = Field(description="行為（違規）日期")
    law_basis: list[str] = Field(description="原處分引用的法條，格式「○○法第○條第○項第○款」")
    appellant_claims: list[str] = Field(description="訴願意旨，逐點，每點一句")
    agency_replies: list[str] = Field(description="答辯意旨，逐點，每點一句；無答辯書則空")
    conflicts: list[str] = Field(description="訴願人自述與卷證不一致之處，每點一句；無則空")


class Issue(BaseModel):
    title: str = Field(description="爭點標題，10 字內")
    appellant_claim: str
    agency_reply: str
    evidence: list[Quote] = Field(description="卷證中與此爭點有關的原文片段，至少一則")
    finding: str = Field(description="AI 認定：採訴願人 / 採機關 / 待議")
    reason: str = Field(description="一句依據，須指向 evidence")


class Issues(BaseModel):
    """步驟三：訴願人主張 vs 機關答辯 vs 卷證的逐點對照。"""
    case_type: str = Field(description="案件類型，例「違反○○法」")
    procedural_issue: bool = Field(description="是否存在程序爭點（逾期、當事人不適格、非行政處分等）")
    issues: list[Issue]


class LawRec(BaseModel):
    law: str = Field(description="法規名稱，須為提供清單中的名稱")
    article: str = Field(description="條號，僅數字，如 27 或 27之1")
    paragraph: str | None = Field(description="項款，如「第1項第1款」，無則 null")
    role: str = Field(description="處分依據 / 裁罰額度 / 程序 / 救濟期間 / 裁量 / 其他")
    why: str = Field(description="與本案哪個爭點或事實相關，一句")


class Laws(BaseModel):
    """步驟四：本案應引用或審酌的法條。"""
    recommended: list[LawRec]
    missing_in_defense: list[str] = Field(description="答辯書應引而未引的條文，格式「○○法第○條」；無則空")


class SimNote(BaseModel):
    id: str = Field(description="決定書 id，須為提供清單中的 id")
    one_liner: str = Field(description="該案案情與結論，一句")
    why_similar: str = Field(description="與本案相似之處，一句")


class Sims(BaseModel):
    """步驟五：相似案例說明。"""
    notes: list[SimNote]
