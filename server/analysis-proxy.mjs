/* 分析階段（步驟 2–5／異議／法規庫）反代到同機 Python 服務 :8100。零依賴、串流直通（SSE 不緩衝）。
   在 server.mjs 的 express.static 之前加兩行：
     import { mountAnalysisProxy } from "./analysis-proxy.mjs";
     mountAnalysisProxy(app);
   契約：docs/API-分析階段.md */
import http from "node:http";

const TARGET = process.env.ANALYSIS_URL || "http://127.0.0.1:8100";
const PATHS = [
  /^\/api\/cases\/[^/]+\/(analyze|reanalyze|analysis|objection|chat)$/,
  /^\/api\/cases\/[^/]+\/proposals\/[^/]+(\/(confirm|cancel))?$/,   // 助手提案：GET／confirm／cancel
  /^\/api\/jobs\/an_[^/]+(\/events)?$/,   // 分析 job 以 an_ 開頭，不會撞到歸戶 job_
  /^\/api\/lawlib(\/sync)?$/,
  /^\/api\/analysis\/health$/,
];

export function mountAnalysisProxy(app) {
  app.use((req, res, next) => {
    if (!PATHS.some((p) => p.test(req.path))) return next();
    const u = new URL(req.originalUrl, TARGET);
    // express.json 已把 body 讀掉（readableEnded=true）：要自己重送序列化後的 body，並重算 content-length——
    // 否則只轉發原 content-length 卻不送 body，上游會等到逾時（POST objection／chat 全部卡住）
    const parsed = req.body && typeof req.body === "object" && !Buffer.isBuffer(req.body) && req.readableEnded ? Buffer.from(JSON.stringify(req.body)) : null;
    const headers = { ...req.headers, host: u.host };
    if (parsed) { headers["content-type"] = "application/json"; headers["content-length"] = String(parsed.length); delete headers["transfer-encoding"]; }
    const up = http.request({ host: u.hostname, port: u.port, path: u.pathname + u.search, method: req.method, headers }, (r) => {
      res.writeHead(r.statusCode, r.headers);
      r.pipe(res);
    });
    up.on("error", (e) => { if (!res.headersSent) res.status(502).json({ code: "ANALYSIS_UNAVAILABLE", message: e.message, retryable: true }); else res.end(); });
    // 只有「客戶端中途離開」才中止上游；Node ≥16 的 req 'close' 在 body 讀完就會觸發，不能拿來判斷
    res.on("close", () => { if (!res.writableFinished) up.destroy(); });
    if (parsed) up.end(parsed);
    else if (req.readableEnded || req.method === "GET") up.end();
    else req.pipe(up);
  });
}
