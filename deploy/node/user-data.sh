#!/bin/bash
# EC2 首次開機：拉部署包 → 裝工具 → 起服務。__BUCKET__ 由 create-infra 代入。
set -uo pipefail
exec > >(tee /var/log/user-data.log) 2>&1
BUCKET="__BUCKET__"

aws s3 cp "s3://${BUCKET}/app-node.tar.gz" /tmp/app-node.tar.gz
mkdir -p /opt/app && tar -xzf /tmp/app-node.tar.gz -C /opt/app

bash /opt/app/deploy/node/setup-tools.sh

# 服務設定檔（不含任何憑證：AWS 走 Instance Profile）
if [ ! -f /opt/app/server/env.production ]; then
  cat > /opt/app/server/env.production <<CONF
AWS_REGION=us-west-2
MODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0
BEDROCK_MIN_INTERVAL=2.0
BEDROCK_CONCURRENCY=3
BOX_FILES=10
CLASSIFY_CACHE=0
S3_BUCKET=${BUCKET}
DDB_TABLE=appeal-cases
CONF
fi

bash /opt/app/deploy/node/redeploy.sh "${BUCKET}"
