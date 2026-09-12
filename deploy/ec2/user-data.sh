#!/bin/bash
# EC2 首次開機：裝 python3.11 → 跑 redeploy.sh。__BUCKET__ 由 create-infra.sh 代入。
set -euo pipefail
dnf install -y python3.11 python3.11-pip
aws s3 cp "s3://__BUCKET__/app.tar.gz" /tmp/app.tar.gz
mkdir -p /opt/app && tar -xzf /tmp/app.tar.gz -C /opt/app
bash /opt/app/deploy/ec2/redeploy.sh "__BUCKET__"
