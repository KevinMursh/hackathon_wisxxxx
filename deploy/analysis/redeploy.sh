#!/bin/bash
# 在 EC2 上執行：從 S3 拉 analysis.tar.gz → /opt/app/{experiments,資料集} → venv → 重啟 :8100
set -euo pipefail
BUCKET="$1"
aws s3 cp "s3://${BUCKET}/analysis.tar.gz" /tmp/analysis.tar.gz
mkdir -p /opt/app
rm -rf /opt/app/experiments /opt/app/資料集
tar -xzf /tmp/analysis.tar.gz -C /opt/app
[ -d /opt/venv-analysis ] || python3.11 -m venv /opt/venv-analysis
/opt/venv-analysis/bin/pip install -q -r /opt/app/experiments/requirements.txt
cp /opt/app/deploy/analysis/analysis.service /etc/systemd/system/analysis.service
systemctl daemon-reload
systemctl enable --now analysis
systemctl restart analysis
sleep 3
curl -sf localhost:8100/api/analysis/health && echo " <- analysis healthy"
