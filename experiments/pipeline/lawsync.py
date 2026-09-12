"""同步全國法規資料庫（法務部官方開放資料）→ inputs/laws_synced.json，並回報與上次快照的差異。

來源（政府資料開放平臺「中文法規_法律資料檔下載」，政府資料開放授權條款第 1 版）：
  法律  https://sendlaw.moj.gov.tw/PublicData/GetFile.ashx?DType=XML&AuData=CF   （FalV.zip，約 6 MB）
  命令  https://sendlaw.moj.gov.tw/PublicData/GetFile.ashx?DType=XML&AuData=CM   （MingLing.zip，約 25 MB）
ZIP 內為單一 XML（<法規> 節點）＋ schema.csv；欄位：法規名稱、最新異動日期(YYYYMMDD)、生效日期、廢止註記、沿革內容、條文(條號/條文內容)。
平臺標示更新頻率「每 1 月」，實測檔案日期為當日 00:00（每日重產）。

用法：
  python -m pipeline.lawsync                # 只抓關注清單（WATCH），存 inputs/laws_synced.json，印差異
  python -m pipeline.lawsync --all          # 全量（法律 1,346 部＋命令 10,450 部，JSON 約數百 MB，不建議）
  python -m pipeline.lawsync --check        # 不下載，只比對快照與 資料集 PDF 版本
"""
import io, json, re, sys, zipfile
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "inputs" / "laws_synced.json"
SRC = {
    "法律": "https://sendlaw.moj.gov.tw/PublicData/GetFile.ashx?DType=XML&AuData=CF",
    "命令": "https://sendlaw.moj.gov.tw/PublicData/GetFile.ashx?DType=XML&AuData=CM",
}
# 本專案關注的法規（資料集 11 部 ＋ 決定書慣常援引之命令）
WATCH = {"訴願法", "行政程序法", "行政罰法", "行政執行法", "民法", "廢棄物清理法", "空氣污染防制法", "噪音管制法", "建築法",
         "洗錢防制法", "政府資訊公開法", "行政院及各級行政機關訴願審議委員會審議規則", "違反廢棄物清理法罰鍰額度裁罰準則",
         "違反空氣污染防制法罰鍰額度裁罰準則", "噪音管制法施行細則", "廢棄物清理法施行細則"}


def roc(ymd: str) -> str | None:
    ymd = (ymd or "").strip()
    if ymd == "99991231":  # 官方哨兵值：尚未定生效日
        return None
    return f"{int(ymd[:4]) - 1911}-{ymd[4:6]}-{ymd[6:]}" if len(ymd) == 8 and ymd.isdigit() else None


def _download(url: str) -> bytes:
    """優先 urllib；sendlaw.moj.gov.tw 憑證鏈缺 Subject Key Identifier，Python 3.12+ 之 OpenSSL 3 會拒絕，
    此時退回系統 curl（使用作業系統信任庫）。正式環境建議固定用 curl 或補齊 CA bundle。"""
    import ssl, subprocess
    req = Request(url, headers={"User-Agent": "ntpc-hackathon-lawsync/1.0"})
    try:
        with urlopen(req, timeout=300) as r:
            return r.read()
    except Exception as e:  # URLError(SSL) 等
        print(f"  urllib 失敗（{type(e).__name__}），改用 curl", file=sys.stderr)
        return subprocess.run(["curl", "-sSL", "--max-time", "300", url], check=True, capture_output=True).stdout


def fetch_xml(url: str) -> ET.Element:
    buf = io.BytesIO(_download(url))
    with zipfile.ZipFile(buf) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
        return ET.fromstring(z.read(name))


def parse(root: ET.Element, kind: str, watch: set | None) -> dict:
    out = {}
    for L in root.findall("法規"):
        name = (L.findtext("法規名稱") or "").strip()
        if watch and name not in watch:
            continue
        hist = (L.findtext("沿革內容") or "").strip()
        # 沿革中的「自…施行」句，供人工判讀施行日（官方生效日期欄多為空）
        effect_lines = [ln.strip() for ln in hist.splitlines() if "施行" in ln]
        arts = {}
        for c in L.findall(".//條文"):
            no = re.sub(r"\s+", "", (c.findtext("條號") or "")).replace("第", "").replace("條", "")
            arts[no] = (c.findtext("條文內容") or "").strip()
        out[name] = {
            "kind": kind, "url": (L.findtext("法規網址") or "").strip(),
            "amended": roc(L.findtext("最新異動日期")), "effective": roc(L.findtext("生效日期")),
            "repealed": bool((L.findtext("廢止註記") or "").strip()),
            "history_tail": hist.splitlines()[-1].strip() if hist else "", "effect_lines": effect_lines[-3:],
            "n_articles": len(arts), "articles": arts,
        }
    return out


def diff(old: dict, new: dict) -> list[dict]:
    rows = []
    for n, v in new.items():
        o = old.get(n)
        if not o:
            rows.append({"law": n, "change": "新增收錄", "amended": v["amended"], "effective": v["effective"]})
        elif o.get("amended") != v["amended"]:
            rows.append({"law": n, "change": "有新修正", "from": o.get("amended"), "amended": v["amended"], "effective": v["effective"], "note": v["history_tail"]})
        elif o.get("n_articles") != v["n_articles"]:
            rows.append({"law": n, "change": "條文數變動", "from": o.get("n_articles"), "to": v["n_articles"]})
    return rows


def main(argv):
    all_ = "--all" in argv
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"laws": {}, "synced_at": None}
    if "--check" in argv:
        pdf = json.loads((ROOT / "inputs" / "laws.json").read_text(encoding="utf-8"))
        for n, v in old["laws"].items():
            if n in pdf:
                p = pdf[n]["amended"]
                m = re.match(r"民國 (\d+) 年 (\d+) 月 (\d+) 日", p)
                p_iso = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else p
                flag = "一致" if p_iso == v["amended"] else f"資料集 PDF 落後（PDF {p_iso} → 官方 {v['amended']}{'，生效 ' + v['effective'] if v['effective'] else ''}）"
                print(f"{n:<28} {flag}")
        return
    new = {}
    for kind, url in SRC.items():
        print(f"下載 {kind} {url}", file=sys.stderr)
        new.update(parse(fetch_xml(url), kind, None if all_ else WATCH))
    rows = diff(old["laws"], new)
    snap = {"synced_at": date.today().isoformat(), "source": SRC, "license": "政府資料開放授權條款-第1版", "laws": new}
    OUT.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"同步完成 {snap['synced_at']}：{len(new)} 部（上次 {old.get('synced_at') or '無'}）；差異 {len(rows)} 筆 → {OUT.relative_to(ROOT)}")
    for r in rows:
        print("  •", json.dumps(r, ensure_ascii=False))
    missing = WATCH - set(new)
    if missing:
        print("  未在官方資料中找到：", "、".join(sorted(missing)))


if __name__ == "__main__":
    main(sys.argv[1:])
