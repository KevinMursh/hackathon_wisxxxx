#!/bin/bash
# EC2 首次開機：拉部署包 → 裝工具 → 起服務。__BUCKET__ 由 create-infra 代入。
# 服務設定檔由 redeploy.sh 在 /etc/app-node.conf 產生（不含憑證，AWS 走 Instance Profile）。
set -uo pipefail
exec > >(tee /var/log/user-data.log) 2>&1
BUCKET="__BUCKET__"

aws s3 cp "s3://${BUCKET}/app-node.tar.gz" /tmp/app-node.tar.gz
mkdir -p /opt/app && tar -xzf /tmp/app-node.tar.gz -C /opt/app

bash /opt/app/deploy/node/setup-tools.sh
bash /opt/app/deploy/node/redeploy.sh "${BUCKET}"
