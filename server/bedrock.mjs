/* =========================================================
   Bedrock 呼叫的唯一入口。競賽規範：全帳號 ≤ 1 RPS。
   規範限的是「每秒請求數」，不是同時在途數：起跑間隔 BEDROCK_MIN_INTERVAL 秒（預設 2.0 = 0.5 RPS），
   併發上限 BEDROCK_CONCURRENCY（預設 3）。設 CONCURRENCY=1 即回到完全序列。Throttling 退避重試。
   之後 pipeline 各步（欄位/爭點/法規/草稿）都走這裡，共用同一組閘門。
   ========================================================= */
import { BedrockRuntimeClient, ConverseCommand, ConverseStreamCommand } from "@aws-sdk/client-bedrock-runtime";

export const REGION = process.env.AWS_REGION || "us-west-2";
export const DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0";
export const MODEL = process.env.MODEL || process.env.BEDROCK_MODEL_ID || DEFAULT_MODEL;
// 起跑節流：每 START_INTERVAL 才准「發出」一個請求（規範是每秒請求數，非同時數）
// 併發上限：同時在途的請求數；設 1 等同完全序列（舊行為）
const START_INTERVAL = +(process.env.BEDROCK_MIN_INTERVAL || 2.0) * 1000;
const CONCURRENCY = +(process.env.BEDROCK_CONCURRENCY || 3);
const MAX_RETRY = 4;

const client = new BedrockRuntimeClient({ region: REGION, maxAttempts: 1 });

/* ---------- 起跑節流 + 併發閘 ---------- */
let startChain = Promise.resolve();
let lastStart = 0;
let inFlight = 0;
const waiters = [];

function acquireSlot() {
  // 1) 排隊等「起跑許可」：彼此至少隔 START_INTERVAL
  const gate = startChain.then(async () => {
    const wait = START_INTERVAL - (Date.now() - lastStart);
    if (wait > 0) await sleep(wait);
    lastStart = Date.now();
  });
  startChain = gate.catch(() => {});
  // 2) 再等併發名額
  return gate.then(() => (inFlight < CONCURRENCY ? void inFlight++ : new Promise((r) => waiters.push(r)).then(() => void inFlight++)));
}
function releaseSlot() { inFlight--; const w = waiters.shift(); if (w) w(); }

async function withLock(fn) {
  await acquireSlot();
  try { return await fn(); } finally { releaseSlot(); }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class BedrockError extends Error {
  constructor(code, message, cause) { super(message); this.code = code; this.cause = cause; this.retryable = code === "BEDROCK_THROTTLED"; }
}

function classify(e) {
  if (e.name === "ThrottlingException" || e.$metadata?.httpStatusCode === 429) return "BEDROCK_THROTTLED";
  if (/AccessDenied|UnrecognizedClient|ExpiredToken|CredentialsProviderError|ResourceNotFound|ValidationException.*model/i.test(`${e.name} ${e.message}`)) return "BEDROCK_UNAVAILABLE";
  return "BEDROCK_ERROR";
}

/**
 * converse({system, messages, toolConfig, maxTokens, temperature, model})
 *  → { output, usage, stopReason, ms }
 */
export async function converse({ system, messages, toolConfig, maxTokens = 4096, temperature = 0, model = MODEL }) {
  const cmd = new ConverseCommand({
    modelId: model,
    system: system ? [{ text: system }] : undefined,
    messages,
    toolConfig,
    inferenceConfig: { maxTokens, temperature },
  });
  let lastErr;
  for (let attempt = 0; attempt < MAX_RETRY; attempt++) {
    try {
      return await withLock(async () => {
        const t0 = Date.now();
        const res = await client.send(cmd);
        return { output: res.output, usage: res.usage, stopReason: res.stopReason, ms: Date.now() - t0 };
      });
    } catch (e) {
      lastErr = e;
      if (classify(e) !== "BEDROCK_THROTTLED" || attempt === MAX_RETRY - 1) break;
      await sleep(1500 * 2 ** attempt);
    }
  }
  throw new BedrockError(classify(lastErr), lastErr.message, lastErr);
}

/** 強制 tool-use 取 JSON：回 tool 的 input 物件 */
export async function converseJson({ tool, ...rest }) {
  const r = await converse({ ...rest, toolConfig: { tools: [tool], toolChoice: { tool: { name: tool.toolSpec.name } } } });
  const use = r.output?.message?.content?.find((c) => c.toolUse)?.toolUse;
  if (!use) throw new BedrockError("SCHEMA_INVALID", "model returned no tool use");
  return { input: use.input, usage: r.usage, ms: r.ms, stopReason: r.stopReason };
}

/** 串流：async generator 逐段 yield 文字；整段串流期間佔住一個併發名額 */
export async function* converseStream({ system, messages, maxTokens = 4096, temperature = 0, model = MODEL }) {
  const cmd = new ConverseStreamCommand({
    modelId: model, system: system ? [{ text: system }] : undefined, messages, inferenceConfig: { maxTokens, temperature },
  });
  await acquireSlot();
  try {
    const res = await client.send(cmd);
    for await (const ev of res.stream) {
      const t = ev.contentBlockDelta?.delta?.text;
      if (t) yield t;
    }
  } catch (e) {
    throw e instanceof BedrockError ? e : new BedrockError(classify(e), e.message, e);
  } finally { releaseSlot(); }
}

/** health 用：最便宜的一次真呼叫 */
export async function ping() {
  const t0 = Date.now();
  await converse({ messages: [{ role: "user", content: [{ text: "ping" }] }], maxTokens: 5 });
  return { model: MODEL, region: REGION, ms: Date.now() - t0 };
}
