"""三個評測案（case01／02／03）的 Tab1–5 對照標準答案：
  python eval/compare_truth.py                  # 打線上 API（預設 http://100.20.156.38）
  API=http://localhost:8100 python eval/compare_truth.py
標準答案來源：資料集/評測用（勿用於RAG）/{case}/04-標準答案.md、03-卷宗清單.md（人工抄成下方 TRUTH）。
比對方式：Tab1 期間三日期＋inTime；Tab3 相關法條是否在推薦／引用查核；Tab4 相似案例不得含本案自身決定書；
Tab5 主文＋條款、以及標準答案各論證點的關鍵字是否出現在草稿（關鍵字比對，非語意）。"""
import json, os, sys, urllib.request

API = os.getenv("API", "http://100.20.156.38")
TRUTH = {
 "case01": dict(id=os.getenv("CASE01", "c260913-p7yk"), own="04.111年-違反建築法事件-77(2)", served="111-08-24", recv="111-09-30", deadline="111-09-23", inTime=False, verdict="訴願不受理", art="77",
   laws=["訴願法 第 14 條", "訴願法 第 77 條", "行政程序法 第 72 條", "行政程序法 第 73 條", "行政程序法 第 48 條", "行政程序法 第 74 條"],
   points={"§14+§77②逾期不受理": ["第14條", "第77條"], "§72送達住居所": ["第72條"], "本人簽收非寄存": ["簽收", "寄存"], "處分書已教示": ["教示"], "8/25起算→9/23屆滿": ["9月23日", "屆滿"], "9/30始提起→逾期": ["9月30日", "逾"]}),
 "case02": dict(id=os.getenv("CASE02", "c260913-492a"), own="17.114年-違反廢棄物清理法事件-79I", served="114-09-18", recv="114-09-22", deadline="114-10-18", inTime=True, verdict="訴願駁回", art="79",
   laws=["訴願法 第 79 條", "行政罰法 第 18 條", "廢棄物清理法 第 27 條", "廢棄物清理法 第 4 條", "廢棄物清理法 第 50 條"],
   points={"§4+本府公告權限": ["第4條", "公告"], "§27①§50③+裁罰準則§2": ["第27條", "第50條", "裁罰準則"], "環保署108年函": ["環保署"], "稽查照片+車籍→事證明確": ["車籍"], "附表1項次13係數A=3": ["A=3"], "照片不足/拿回車上→不可採": ["拿回", "放大"], "原處分維持": ["駁回"]}),
 "case03": dict(id=os.getenv("CASE03", "c260913-dj1q"), own="19.114年-違反建築法事件-81I", served="114-07-09", recv="114-08-01", deadline="114-08-08", inTime=True, verdict="原處分撤銷", art="81",
   laws=["訴願法 第 81 條", "行政罰法 第 27 條", "建築法 第 2 條", "建築法 第 77 條", "建築法 第 91 條"],
   points={"§2+本府公告權限": ["第2條", "公告"], "§77③④§91-1①處罰依據": ["第77條", "第91條"], "申報辦法§5附表1": ["申報辦法"], "作業要點§4④": ["作業要點"], "複查+照片→簽證不實固非無據": ["複查"], "§27①②時效3年": ["第27條", "3年"], "111/6/9→114/7/4逾3年": ["111年6月9日", "114年7月4日"], "單純撤銷不命另為處分": ["撤銷"]}),
}

fails = 0
for name, t in TRUTH.items():
    d = json.load(urllib.request.urlopen(f"{API}/api/cases/{t['id']}/analysis")); o = d["output"]
    latest = o["drafts"][list(o["drafts"])[-1]]; txt = "\n".join(p["text"] for p in latest["paras"]).replace(" ", "")
    p = o["period"]; print(f"===== {name} ({t['id']})")
    ok1 = (p["served"], p["recv"], p["deadline"], p["inTime"]) == (t["served"], t["recv"], t["deadline"], t["inTime"]); fails += not ok1
    print("Tab1 期間:", "✓" if ok1 else f"✗ got {p['served']},{p['recv']},{p['deadline']},{p['inTime']}", "| 8款:", [c[2] for c in o["checks"]])
    print("Tab2 爭點:", [(i["id"], i["title"][:18], i["finding"]) for i in o["issues"]])
    names = [l["n"].replace(" ", "") for l in o["laws"]] + [c["n"].replace(" ", "") for c in o.get("citations", [])]
    miss = [l for l in t["laws"] if not any(n.startswith(l.replace(" ", "")) for n in names)]
    print("Tab3 法規:", f"{len(t['laws'])-len(miss)}/{len(t['laws'])}", "缺:", miss)
    sims = [s["fn"] for s in o["sims"]]; leak = any(s.startswith(t["own"]) for s in sims); fails += leak
    print("Tab4 相似:", len(sims), "件 | 本案自身混入:", "✗ 有" if leak else "✓ 無")
    j = o["judge"]; ok5 = j["verdict"].startswith(t["verdict"]) and t["art"] in j["art"]; fails += not ok5
    print("Tab5 判定:", "✓" if ok5 else "✗", j["verdict"], j["art"], "| 教示:", "附" if "行政訴訟" in txt[-300:] and "不附" not in txt[-300:] else "不附／說明")
    hits = {k: all(kw in txt for kw in kws) for k, kws in t["points"].items()}
    print("Tab5 論證點:", f"{sum(hits.values())}/{len(hits)}", "缺:", [k for k, v in hits.items() if not v])
print("\n硬性項目（期間／自身混入／主文條款）失敗數:", fails)
sys.exit(1 if fails else 0)
