"""建 Bedrock Knowledge Base（S3 Vectors 向量庫、cohere multilingual v3）並啟動 ingestion。
冪等：已存在就沿用。結束後把 KB_ID 寫到 kb/kb.json。用法：python -m kb.create_kb"""
import json, time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from pipeline.common import REGION
from kb.build_corpus import BUCKET, PREFIX

NAME = "ntpc-law3-kb"
VBUCKET, INDEX = "ntpc-law3-vectors", "law3-index"
EMBED = f"arn:aws:bedrock:{REGION}::foundation-model/cohere.embed-multilingual-v3"
ROLE = "ntpc-law3-kb-role"
OUT = Path(__file__).resolve().parent / "kb.json"

sts, iam = boto3.client("sts"), boto3.client("iam")
s3v = boto3.client("s3vectors", region_name=REGION)
ba = boto3.client("bedrock-agent", region_name=REGION)
ACCT = sts.get_caller_identity()["Account"]


def ensure_role() -> str:
    try:
        return iam.get_role(RoleName=ROLE)["Role"]["Arn"]
    except ClientError:
        pass
    arn = iam.create_role(RoleName=ROLE, AssumeRolePolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "bedrock.amazonaws.com"},
        "Action": "sts:AssumeRole", "Condition": {"StringEquals": {"aws:SourceAccount": ACCT}}}]}))["Role"]["Arn"]
    iam.put_role_policy(RoleName=ROLE, PolicyName="kb", PolicyDocument=json.dumps({
        "Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Action": ["s3:GetObject", "s3:ListBucket"], "Resource": [f"arn:aws:s3:::{BUCKET}", f"arn:aws:s3:::{BUCKET}/*"]},
            {"Effect": "Allow", "Action": ["bedrock:InvokeModel"], "Resource": [EMBED]},
            {"Effect": "Allow", "Action": ["s3vectors:*"], "Resource": ["*"]},
        ]}))
    print("role 建好，等 15s 生效"); time.sleep(15)
    return arn


def ensure_index() -> str:
    try:
        s3v.create_vector_bucket(vectorBucketName=VBUCKET)
    except ClientError as e:
        if "Conflict" not in e.response["Error"]["Code"] and "AlreadyExists" not in str(e):
            raise
    try:
        s3v.create_index(vectorBucketName=VBUCKET, indexName=INDEX, dataType="float32", dimension=1024,
                         distanceMetric="cosine", metadataConfiguration={"nonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT"]})
    except ClientError as e:
        if "Conflict" not in e.response["Error"]["Code"] and "AlreadyExists" not in str(e):
            raise
    return s3v.get_index(vectorBucketName=VBUCKET, indexName=INDEX)["index"]["indexArn"]


def ensure_kb(role_arn: str, index_arn: str) -> str:
    for kb in ba.list_knowledge_bases()["knowledgeBaseSummaries"]:
        if kb["name"] == NAME:
            return kb["knowledgeBaseId"]
    kb = ba.create_knowledge_base(
        name=NAME, roleArn=role_arn,
        knowledgeBaseConfiguration={"type": "VECTOR", "vectorKnowledgeBaseConfiguration": {
            "embeddingModelArn": EMBED}},  # cohere v3 固定 1024 維，不可設 dimensions
        storageConfiguration={"type": "S3_VECTORS", "s3VectorsConfiguration": {"indexArn": index_arn}},
    )["knowledgeBase"]
    while ba.get_knowledge_base(knowledgeBaseId=kb["knowledgeBaseId"])["knowledgeBase"]["status"] == "CREATING":
        time.sleep(5)
    return kb["knowledgeBaseId"]


def ensure_ds(kb_id: str) -> str:
    for ds in ba.list_data_sources(knowledgeBaseId=kb_id)["dataSourceSummaries"]:
        if ds["name"] == "corpus":
            return ds["dataSourceId"]
    return ba.create_data_source(
        knowledgeBaseId=kb_id, name="corpus",
        dataSourceConfiguration={"type": "S3", "s3Configuration": {"bucketArn": f"arn:aws:s3:::{BUCKET}", "inclusionPrefixes": [PREFIX]}},
        vectorIngestionConfiguration={"chunkingConfiguration": {"chunkingStrategy": "FIXED_SIZE",
                                      "fixedSizeChunkingConfiguration": {"maxTokens": 400, "overlapPercentage": 20}}},
    )["dataSource"]["dataSourceId"]


if __name__ == "__main__":
    role = ensure_role(); print("role", role)
    idx = ensure_index(); print("index", idx)
    kb_id = ensure_kb(role, idx); print("kb", kb_id)
    ds_id = ensure_ds(kb_id); print("ds", ds_id)
    job = ba.start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)["ingestionJob"]
    OUT.write_text(json.dumps({"kbId": kb_id, "dsId": ds_id, "region": REGION, "jobId": job["ingestionJobId"]}, indent=2))
    print("ingestion", job["ingestionJobId"], job["status"])
    while True:
        j = ba.get_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id, ingestionJobId=job["ingestionJobId"])["ingestionJob"]
        print(" ", j["status"], j.get("statistics", {}))
        if j["status"] in ("COMPLETE", "FAILED", "STOPPED"):
            print(j.get("failureReasons", "")); break
        time.sleep(15)
