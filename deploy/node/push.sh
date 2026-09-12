#!/bin/bash
# 本機執行：打包 server/ + prototype/ + deploy/ → S3 → SSM 叫 EC2 重新部署（免 SSH）
set -euo pipefail
cd "$(dirname "$0")/../.."
source deploy/config.sh

COPYFILE_DISABLE=1 tar --no-xattrs --exclude='node_modules' --exclude='.cache' \
    --exclude='.DS_Store' --exclude='__pycache__' \
    -czf /tmp/app-node.tar.gz server prototype deploy
SIZE=$(du -h /tmp/app-node.tar.gz | cut -f1)
aws s3 cp /tmp/app-node.tar.gz "s3://${BUCKET}/app-node.tar.gz"
echo "部署包 ${SIZE} 已上傳"

IID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=${APP_NAME}" "Name=instance-state-name,Values=running" \
      --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ "$IID" = "None" ] && { echo "找不到執行中的 ${APP_NAME}，先跑 deploy/create-infra.sh"; exit 1; }

CMD=$(aws ssm send-command --instance-ids "$IID" --document-name AWS-RunShellScript \
      --timeout-seconds 900 \
      --parameters "commands=[\"bash /opt/app/deploy/node/redeploy.sh ${BUCKET}\"]" \
      --query Command.CommandId --output text)
echo "SSM $CMD 已送出，等待…"
for i in $(seq 1 100); do
  S=$(aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query Status --output text 2>/dev/null || echo Pending)
  case "$S" in
    Success) aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query StandardOutputContent --output text | tail -8; break;;
    Failed|Cancelled|TimedOut)
      echo "部署失敗（${S}）："
      aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query StandardErrorContent --output text
      exit 1;;
  esac
  sleep 3
done
IP=$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "http://${IP}/"
