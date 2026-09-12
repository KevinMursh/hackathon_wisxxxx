#!/bin/bash
# 本機執行：打包 experiments（不含 .venv/runs）+ 資料集（不含評測用）+ deploy → S3 → SSM 重佈 :8100
set -euo pipefail
cd "$(dirname "$0")/../.."
source deploy/config.sh
COPYFILE_DISABLE=1 tar --no-xattrs --exclude='.venv' --exclude='__pycache__' --exclude='.DS_Store' --exclude='experiments/runs' \
    --exclude='資料集/評測用（勿用於RAG）' --exclude='experiments/inputs/decisions_text' \
    -czf /tmp/analysis.tar.gz experiments 資料集 deploy/analysis
aws s3 cp /tmp/analysis.tar.gz "s3://${BUCKET}/analysis.tar.gz"
IID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=${APP_NAME}" "Name=instance-state-name,Values=running" --query 'Reservations[0].Instances[0].InstanceId' --output text)
CMD=$(aws ssm send-command --instance-ids "$IID" --document-name AWS-RunShellScript --timeout-seconds 900 \
      --parameters "commands=[\"bash /opt/app/deploy/analysis/redeploy.sh ${BUCKET} || (mkdir -p /opt/app && aws s3 cp s3://${BUCKET}/analysis.tar.gz /tmp/a.tgz && tar -xzf /tmp/a.tgz -C /opt/app && bash /opt/app/deploy/analysis/redeploy.sh ${BUCKET})\"]" \
      --query Command.CommandId --output text)
echo "SSM ${CMD} 已送出，等待…"
for i in $(seq 1 60); do
  S=$(aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query Status --output text 2>/dev/null || echo Pending)
  case "$S" in Success) aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query StandardOutputContent --output text | tail -3; break;;
    Failed|Cancelled|TimedOut) aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query StandardErrorContent --output text | tail -20; exit 1;;
  esac
  sleep 5
done
