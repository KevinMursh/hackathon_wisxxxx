#!/bin/bash
# 在 EC2 上執行：從 S3 拉部署包 → 解壓 /opt/app → npm ci → 重啟服務
# 用法：bash /opt/app/deploy/node/redeploy.sh <bucket>
set -euo pipefail
BUCKET="$1"

# 本腳本自己就位於 /opt/app/deploy/node/，先複製到 /tmp 再執行，避免解壓時把執行中的檔案抽掉
if [ "${0#/tmp/}" = "$0" ]; then
  cp "$0" /tmp/redeploy-self.sh && exec bash /tmp/redeploy-self.sh "$BUCKET"
fi

aws s3 cp "s3://${BUCKET}/app-node.tar.gz" /tmp/app-node.tar.gz
mkdir -p /opt/app
rm -rf /opt/app/server /opt/app/prototype /opt/app/deploy
tar -xzf /tmp/app-node.tar.gz -C /opt/app

cd /opt/app/server
npm ci --omit=dev

# 服務設定檔放 /etc（/opt/app/server 每次部署會被清空）。不含任何憑證：AWS 走 Instance Profile。
if [ ! -f /etc/app-node.conf ]; then
  cat > /etc/app-node.conf <<CONF
AWS_REGION=us-west-2
MODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0
BEDROCK_MIN_INTERVAL=2.0
BEDROCK_CONCURRENCY=3
BOX_FILES=10
CLASSIFY_CACHE=0
S3_BUCKET=${BUCKET}
DDB_TABLE=appeal-cases
CONF
  echo "已建立 /etc/app-node.conf"
fi

cp /opt/app/deploy/node/app.service /etc/systemd/system/app-node.service
# 保留 CloudWatch 落檔設定（deploy/cloudwatch-setup.sh 建的 drop-in），重佈不覆蓋
systemctl daemon-reload
systemctl enable app-node
systemctl restart app-node || {
  echo "啟動失敗，最近日誌："
  journalctl -u app-node -n 40 --no-pager
  exit 1
}

sleep 4
echo "--- health ---"
curl -sf localhost/api/health | head -c 600 || { echo "health 失敗，最近日誌："; journalctl -u app-node -n 30 --no-pager; exit 1; }
echo
