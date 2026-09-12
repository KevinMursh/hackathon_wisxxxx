/* 分析階段（步驟 2–5／異議／法規庫）反代到同機 Python 服務 :8100。零依賴、串流直通（SSE 不緩衝）。
   在 server.mjs 的 express.static 之前加兩行：
     import { mountAnalysisProxy } from "./analysis-proxy.mjs";
     mountAnalysisProxy(app);
   契約：docs/API-分析階段.md */
import http from "node:http";

const TARGET = process.env.ANALYSIS_URL || "http://127.0.0.1:8100";
const PATHS = [
  /^\/api\/cases\/[^/]+\/(analyze|reanalyze|analysis|objection)$/,
  /^\/api\/jobs\/an_[^/]+(\/events)?$/,   // 分析 job 以 an_ 開頭，不會撞到歸戶 job_
  /^\/api\/lawlib(\/sync)?$/,
  /^\/api\/analysis\/health$/,
];

export function mountAnalysisProxy(app) {
  app.use((req, res, next) => {
    if (!PATHS.some((p) => p.test(req.path))) return next();
    const u = new URL(req.originalUrl, TARGET);
    const up = http.request({ host: u.hostname, port: u.port, path: u.pathname + u.search, method: req.method,
      headers: { ...req.headers, host: u.host } }, (r) => {
      res.writeHead(r.statusCode, r.headers);
      r.pipe(res);
    });
    up.on("error", (e) => res.status(502).json({ code: "ANALYSIS_UNAVAILABLE", message: e.message, retryable: true }));
    req.on("close", () => up.destroy());
    if (req.readableEnded || req.method === "GET") up.end();
    else if (req.body && Object.keys(req.body).length) up.end(JSON.stringify(req.body));  // express.json 已吃掉 body
    else req.pipe(up);
  });
}
