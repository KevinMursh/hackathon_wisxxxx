"""「同步全國法規資料庫」（v6 法規庫按鈕的真實後端）：
逐部法規抓 law.moj.gov.tw 官方頁面 → 最新修正日期、生效狀態、全文條文
→ 與資料集版本比對 → runs/lawsync.json（前端 syncLog 用）
→ 有新修正者：全文寫進 KB 語料 laws/{法規}（現行）.txt 並重新 ingestion（--ingest）
用法：python -m kb.sync_laws [--ingest]"""
import html, json, re, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

import boto3

from kb.build_corpus import BUCKET, PREFIX, OUT as CORPUS
from pipeline import lawdb
from pipeline.common import REGION, RUNS
from pipeline.lawlib import roc

PCODE = {
    "訴願法": "A0030020", "廢棄物清理法": "O0050001", "洗錢防制法": "G0380131", "空氣污染防制法": "O0020001",
    "噪音管制法": "O0030001", "建築法": "D0070109", "行政罰法": "A0030210", "行政程序法": "A0030055",
    "行政執行法": "A0030023", "民法": "B0000001", "政府資訊公開法": "I0020026",
    # 決定書慣常援引、但資料集沒給的子法
    "違反廢棄物清理法罰鍰額度裁罰準則": "O0050090",
}
UA = {"User-Agent": "Mozilla/5.0 (hackathon law sync)"}


def fetch(pcode: str) -> str:
    """用 curl（urllib 在部分機器缺憑證鏈）；官方站偶爾很慢，重試 3 次。"""
    import subprocess
    for i in range(3):
        r = subprocess.run(["curl", "-s", "-m", "90", "-A", UA["User-Agent"],
                            f"https://law.moj.gov.tw/LawClass/LawAll.aspx?pcode={pcode}"], capture_output=True)
        if r.returncode == 0 and len(r.stdout) > 20000:
            return r.stdout.decode("utf-8", "ignore")
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"fetch failed pcode={pcode} rc={r.returncode} bytes={len(r.stdout)}")


def _txt(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse(page: str) -> dict:
    name = re.search(r"法規名稱：.*?<a[^>]*>([^<]+)</a>", page, re.S)
    name = _txt(name.group(1)) if name else (re.search(r"法規名稱：\s*([^<\s]+)", _txt(page[:5000])) or [None, None])[1]
    amended = roc(_txt(page[page.find("修正日期"):][:200])) if "修正日期" in page else roc(_txt(page[page.find("公布日期"):][:200]))
    eff = re.search(r"最後生效日期：\s*(民國\s*\d+\s*年\s*\d+\s*月\s*\d+\s*日)", _txt(page))
    pending = bool(re.search(r"尚未生效", page))
    arts = {}
    for m in re.finditer(r'name="(\d+(?:-\d+)?)">第\s*[\d\-]+\s*條</a></div><div class="col-data"><div class="law-article">(.*?)</div>\s*</div></div>', page, re.S):
        no = m.group(1).replace("-", "之")
        lines = [_txt(x) for x in re.findall(r'<div class="line-\d+[^"]*">(.*?)</div>', m.group(2), re.S)]
        arts[no] = "\n".join(l for l in lines if l)
    return {"name": name, "amended": amended, "effective": roc(eff.group(1)) if eff else None, "pending": pending, "articles": arts}


def to_text(name: str, info: dict) -> str:
    head = f"法規名稱：{name}\n修正日期：民國 {info['amended']}（全國法規資料庫同步）\n"
    return head + "\n".join(f"第 {k} 條\n{v}" for k, v in info["articles"].items())


def run(ingest: bool = False) -> dict:
    db = lawdb.load()
    dataset = {k: roc(v["amended"]) for k, v in db.items()}
    dataset["政府資訊公開法"] = "94-12-28"
    report = {"checkedAt": datetime.now().strftime("%Y-%m-%d %H:%M"), "source": "law.moj.gov.tw LawAll.aspx", "results": []}
    changed = []
    for name, pcode in PCODE.items():
        try:
            info = parse(fetch(pcode))
            if info["name"] and info["name"] != name:
                raise RuntimeError(f"pcode {pcode} 對應到「{info['name']}」，非「{name}」")
        except Exception as e:  # 單部失敗不中斷
            report["results"].append({"n": name, "error": str(e)[:80]}); continue
        ds = dataset.get(name)
        status = "not_in_dataset" if ds is None else ("changed" if info["amended"] and info["amended"] > ds else "same")
        row = {"n": name, "datasetDate": ds, "officialDate": info["amended"], "effective": info["effective"], "pendingArticles": info["pending"],
               "arts": len(info["articles"]), "status": status}
        report["results"].append(row)
        print(f"  {status:<15} {name:<22} 資料集 {ds or '—':<10} 官方 {info['amended']}{'（部分條文尚未生效，' + str(info['effective']) + '）' if info['pending'] else ''}  {len(info['articles'])} 條", file=sys.stderr)
        if status in ("changed", "not_in_dataset") and info["articles"]:
            changed.append((name, info))
        time.sleep(0.5)
    report["summary"] = {"checked": len(PCODE), "changed": sum(r.get("status") == "changed" for r in report["results"]),
                         "same": sum(r.get("status") == "same" for r in report["results"]),
                         "added": sum(r.get("status") == "not_in_dataset" for r in report["results"])}
    RUNS.mkdir(exist_ok=True)
    (RUNS / "lawsync.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 有新修正／新增 → 現行版寫進語料（資料集版本保留，檔名加「現行」）；本機先落地，S3 失敗不中斷
    (CORPUS / "laws").mkdir(parents=True, exist_ok=True)
    uploads = []
    for name, info in changed:
        key = f"laws/{name}（現行 {info['amended']}）.txt"
        text = to_text(name, info)
        meta = {"metadataAttributes": {"kind": "laws", "law": name, "title": f"{name}（現行 {info['amended']}）", "version": "current", "amended": info["amended"]}}
        (CORPUS / key).write_text(text, encoding="utf-8")
        (CORPUS / (key + ".metadata.json")).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        uploads.append((key, text, meta))
    print(f"本機寫入 {len(uploads)} 部現行版 → {CORPUS}/laws/", file=sys.stderr)
    try:
        s3 = boto3.client("s3", region_name=REGION)
        for key, text, meta in uploads:
            s3.put_object(Bucket=BUCKET, Key=PREFIX + key, Body=text.encode("utf-8"), ContentType="text/plain; charset=utf-8")
            s3.put_object(Bucket=BUCKET, Key=PREFIX + key + ".metadata.json", Body=json.dumps(meta, ensure_ascii=False).encode("utf-8"))
        print(f"上傳 {len(uploads)} 部 → s3://{BUCKET}/{PREFIX}laws/", file=sys.stderr)
    except Exception as e:
        print(f"S3 上傳失敗（{str(e)[:60]}）；本機語料已更新，憑證恢復後重跑即可", file=sys.stderr); ingest = False
    if ingest and changed:
        cfg = json.loads((Path(__file__).resolve().parent / "kb.json").read_text())
        ba = boto3.client("bedrock-agent", region_name=cfg["region"])
        j = ba.start_ingestion_job(knowledgeBaseId=cfg["kbId"], dataSourceId=cfg["dsId"])["ingestionJob"]
        while j["status"] not in ("COMPLETE", "FAILED"):
            time.sleep(10)
            j = ba.get_ingestion_job(knowledgeBaseId=cfg["kbId"], dataSourceId=cfg["dsId"], ingestionJobId=j["ingestionJobId"])["ingestionJob"]
        print("KB ingestion", j["status"], j["statistics"].get("numberOfNewDocumentsIndexed"), "new", file=sys.stderr)
    return report


if __name__ == "__main__":
    run(ingest="--ingest" in sys.argv)
