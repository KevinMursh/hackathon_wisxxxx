/* DynamoDB 單表：
   PK CASE#{caseId}   SK FILE#{fileId} | AUDIT#{iso}#{seq}
   PK JOB#{jobId}     SK META | EVT#{seq:06}
   PK CACHE#{sha}     SK {model}#{promptHash}
   S3_PREFIX 有值時（本機 dev），PK 前面再加 "{prefix}#" 與正式資料隔開 */
import { DynamoDBClient, DescribeTableCommand } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, PutCommand, GetCommand, QueryCommand, UpdateCommand } from "@aws-sdk/lib-dynamodb";

const REGION = process.env.AWS_REGION || "us-west-2";
export const TABLE = process.env.DDB_TABLE;
const NS = (process.env.S3_PREFIX || "").replace(/\/+$/g, "");
if (!TABLE) { console.error("DDB_TABLE 未設定"); process.exit(1); }

const raw = new DynamoDBClient({ region: REGION });
const db = DynamoDBDocumentClient.from(raw, { marshallOptions: { removeUndefinedValues: true } });
const pk = (s) => (NS ? `${NS}#${s}` : s);
const pad = (n) => String(n).padStart(6, "0");

/* ---------- File ---------- */
export async function putFile(f) { await db.send(new PutCommand({ TableName: TABLE, Item: { PK: pk(`CASE#${f.caseId}`), SK: `FILE#${f.fileId}`, ...f } })); return f; }
export async function getFile(caseId, fileId) { const r = await db.send(new GetCommand({ TableName: TABLE, Key: { PK: pk(`CASE#${caseId}`), SK: `FILE#${fileId}` } })); return r.Item ? strip(r.Item) : null; }
export async function listFiles(caseId) {
  const r = await db.send(new QueryCommand({ TableName: TABLE, KeyConditionExpression: "PK = :p AND begins_with(SK, :s)", ExpressionAttributeValues: { ":p": pk(`CASE#${caseId}`), ":s": "FILE#" } }));
  return (r.Items ?? []).map(strip);
}
export async function updateFile(caseId, fileId, patch) {
  const names = {}, values = {}, sets = [];
  for (const [k, v] of Object.entries(patch)) { names[`#${k}`] = k; values[`:${k}`] = v; sets.push(`#${k} = :${k}`); }
  names["#updatedAt"] = "updatedAt"; values[":updatedAt"] = new Date().toISOString(); sets.push("#updatedAt = :updatedAt");
  const r = await db.send(new UpdateCommand({ TableName: TABLE, Key: { PK: pk(`CASE#${caseId}`), SK: `FILE#${fileId}` }, UpdateExpression: "SET " + sets.join(", "), ExpressionAttributeNames: names, ExpressionAttributeValues: values, ReturnValues: "ALL_NEW" }));
  return strip(r.Attributes);
}

/* ---------- Job ---------- */
export async function putJob(j) { await db.send(new PutCommand({ TableName: TABLE, Item: { PK: pk(`JOB#${j.jobId}`), SK: "META", ...j } })); return j; }
export async function getJob(jobId) { const r = await db.send(new GetCommand({ TableName: TABLE, Key: { PK: pk(`JOB#${jobId}`), SK: "META" } })); return r.Item ? strip(r.Item) : null; }
export async function updateJob(jobId, patch) {
  const names = {}, values = {}, sets = [];
  for (const [k, v] of Object.entries(patch)) { names[`#${k}`] = k; values[`:${k}`] = v; sets.push(`#${k} = :${k}`); }
  await db.send(new UpdateCommand({ TableName: TABLE, Key: { PK: pk(`JOB#${jobId}`), SK: "META" }, UpdateExpression: "SET " + sets.join(", "), ExpressionAttributeNames: names, ExpressionAttributeValues: values }));
}
export async function appendEvent(jobId, seq, event, data) {
  await db.send(new PutCommand({ TableName: TABLE, Item: { PK: pk(`JOB#${jobId}`), SK: `EVT#${pad(seq)}`, seq, event, data, at: new Date().toISOString() } }));
}
export async function listEvents(jobId, afterSeq = 0) {
  const r = await db.send(new QueryCommand({ TableName: TABLE, KeyConditionExpression: "PK = :p AND SK > :s", ExpressionAttributeValues: { ":p": pk(`JOB#${jobId}`), ":s": `EVT#${pad(afterSeq)}` } }));
  return (r.Items ?? []).map(strip);
}

/* ---------- Audit ---------- */
let auditSeq = 0;
export async function appendAudit(caseId, entry) {
  const at = new Date().toISOString();
  const item = { PK: pk(`CASE#${caseId}`), SK: `AUDIT#${at}#${pad(auditSeq++)}`, at, ...entry };
  await db.send(new PutCommand({ TableName: TABLE, Item: item }));
  return strip(item);
}
export async function listAudit(caseId) {
  const r = await db.send(new QueryCommand({ TableName: TABLE, KeyConditionExpression: "PK = :p AND begins_with(SK, :s)", ExpressionAttributeValues: { ":p": pk(`CASE#${caseId}`), ":s": "AUDIT#" } }));
  return (r.Items ?? []).map(strip);
}

/* ---------- 分類 cache ---------- */
export async function cacheGet(sha, variant) { const r = await db.send(new GetCommand({ TableName: TABLE, Key: { PK: pk(`CACHE#${sha}`), SK: variant } })); return r.Item?.value ?? null; }
export async function cachePut(sha, variant, value) { await db.send(new PutCommand({ TableName: TABLE, Item: { PK: pk(`CACHE#${sha}`), SK: variant, value, at: new Date().toISOString() } })); }

export async function health() {
  try { const r = await raw.send(new DescribeTableCommand({ TableName: TABLE })); return r.Table?.TableStatus === "ACTIVE"; } catch { return false; }
}

function strip(item) { const { PK, SK, ...rest } = item; return rest; }
