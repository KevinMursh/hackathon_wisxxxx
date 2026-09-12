#!/bin/bash
# 首次從 FastAPI 切換到 Node 後端。只需跑一次，之後日常更新用 deploy/node/push.sh。
# 順序很重要：先把部署包放上去並解開，再裝工具（機器上原本沒有 node），最後才起服務。
set -euo pipefail
cd "$(dirname "$0")/../.."
source deploy/config.sh

IID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=${APP_NAME}" "Name=instance-state-name,Values=running" \
      --query 'Reservations[0].Instances[0].InstanceId' --output text)
[ "$IID" = "None" ] && { echo "找不到執行中的 ${APP_NAME}"; exit 1; }
echo "目標機器：$IID"

ssm() {   # $1=說明 $2=逾時秒 $3=指令
  local CMD
  CMD=$(aws ssm send-command --instance-ids "$IID" --document-name AWS-RunShellScript \
        --timeout-seconds "$2" --parameters "commands=[\"$3\"]" --query Command.CommandId --output text)
  echo "── $1（$CMD）"
  local n=$(( $2 / 5 + 20 ))
  for _ in $(seq 1 "$n"); do
    S=$(aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query Status --output text 2>/dev/null || echo Pending)
    case "$S" in
      Success) aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query StandardOutputContent --output text | tail -20; return 0;;
      Failed|Cancelled|TimedOut)
        echo "失敗（$S）："
        aws ssm get-command-invocation --command-id "$CMD" --instance-id "$IID" --query StandardErrorContent --output text | tail -30
        return 1;;
    esac
    sleep 5
  done
  echo "等太久，自己查：aws ssm get-command-invocation --command-id $CMD --instance-id $IID"; return 1
}

echo "1/4 打包並上傳"
tar --exclude='node_modules' --exclude='.cache' --exclude='env.production' \
    --exclude='.DS_Store' --exclude='__pycache__' \
    -czf /tmp/app-node.tar.gz server prototype deploy
aws s3 cp /tmp/app-node.tar.gz "s3://${BUCKET}/app-node.tar.gz"

echo "2/4 解開部署包到 /opt/app"
ssm "解壓" 120 "mkdir -p /opt/app && aws s3 cp s3://${BUCKET}/app-node.tar.gz /tmp/app-node.tar.gz && tar -xzf /tmp/app-node.tar.gz -C /opt/app && ls /opt/app/deploy/node/"

echo "3/4 安裝外部工具（LibreOffice 約 250MB，可能要 5–10 分鐘）"
ssm "setup-tools" 1800 "bash /opt/app/deploy/node/setup-tools.sh"

echo "4/4 停用舊 FastAPI、寫設定、起 Node 服務"
ssm "切換服務" 900 "systemctl disable --now app 2>/dev/null; \
[ -f /opt/app/server/env.production ] || printf 'AWS_REGION=us-west-2\\nMODEL=us.anthropic.claude-sonnet-4-5-20250929-v1:0\\nBEDROCK_MIN_INTERVAL=2.0\\nBEDROCK_CONCURRENCY=3\\nBOX_FILES=10\\nCLASSIFY_CACHE=0\\nS3_BUCKET=${BUCKET}\\nDDB_TABLE=appeal-cases\\n' > /opt/app/server/env.production; \
bash /opt/app/deploy/node/redeploy.sh ${BUCKET}"

IP=$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo
echo "✅ 切換完成：http://${IP}/"
echo "   健康檢查：curl http://${IP}/api/health"
echo "   回退舊版：aws ssm send-command --instance-ids $IID --document-name AWS-RunShellScript \\"
echo "             --parameters 'commands=[\"systemctl disable --now app-node && systemctl enable --now app\"]'"
