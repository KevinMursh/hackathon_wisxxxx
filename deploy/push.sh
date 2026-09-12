#!/bin/bash
# 本機執行：打包 src/ + deploy/ → 上傳 S3 → 透過 SSM 叫 EC2 重新部署（不需 SSH）
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh

tar --exclude='.venv' --exclude='__pycache__' --exclude='.DS_Store' -czf /tmp/app.tar.gz src deploy
aws s3 cp /tmp/app.tar.gz "s3://${BUCKET}/app.tar.gz"

IID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=${APP_NAME}" "Name=instance-state-name,Values=running" \
      --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ "$IID" = "None" ] && { echo "找不到執行中的 ${APP_NAME}，先跑 deploy/create-infra.sh"; exit 1; }

CMD=$(aws ssm send-command --instance-ids "$IID" --document-name AWS-RunShellScript \
      --parameters "commands=[\"bash /opt/app/deploy/ec2/redeploy.sh ${BUCKET}\"]" \
      --query Command.CommandId --output text)
echo "SSM command $CMD 已送出，等待完成…"
for i in $(seq 1 40); do
  S=$(aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query Status --output text 2>/dev/null || echo Pending)
  case "$S" in Success) aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query StandardOutputContent --output text | tail -3; break;;
    Failed|Cancelled|TimedOut) aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query StandardErrorContent --output text; exit 1;;
  esac
  sleep 3
done
IP=$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "http://${IP}/"
