任務：從卷宗擷取結構化欄位，填入工具 schema。

規則：
- 日期一律民國年 YYY-MM-DD；處分「送達日」只能來自送達證書類文件，不得用訴願書自述代替；兩者不一致時填入 conflicts。
- law_basis 只抄裁處書／答辯書明文引用的條號，不自行補充。
- appellant_claims 與 agency_replies 逐點拆開，一點一句，保留原文關鍵詞。
- 卷宗沒有的欄位填 null，不猜。
