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

cp /opt/app/deploy/node/app.service /etc/systemd/system/app-node.service
systemctl daemon-reload
systemctl enable app-node
systemctl restart app-node

sleep 4
echo "--- health ---"
curl -sf localhost/api/health | head -c 600 || { echo "health 失敗，最近日誌："; journalctl -u app-node -n 30 --no-pager; exit 1; }
echo
