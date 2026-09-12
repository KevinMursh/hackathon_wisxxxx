#!/bin/bash
# 在 EC2 上執行：從 S3 拉最新部署包 → 解壓到 /opt/app → 裝依賴 → 重啟服務
set -euo pipefail
BUCKET="$1"
mkdir -p /opt/app
aws s3 cp "s3://${BUCKET}/app.tar.gz" /tmp/app.tar.gz
rm -rf /opt/app/src && tar -xzf /tmp/app.tar.gz -C /opt/app
cd /opt/app/src/backend
[ -d /opt/venv ] || python3.11 -m venv /opt/venv
/opt/venv/bin/pip install -q -r requirements.txt
cp /opt/app/deploy/ec2/app.service /etc/systemd/system/app.service
systemctl daemon-reload
systemctl enable --now app
systemctl restart app
sleep 2
curl -sf localhost/api/health && echo " <- healthy"
