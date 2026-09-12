#!/bin/bash
# 看 EC2 上後端 log（走 SSM，不開 port）。用法：
#   ./deploy/logs.sh                 # 兩個服務各最近 60 行
#   ./deploy/logs.sh analysis 200    # 分析服務最近 200 行
#   ./deploy/logs.sh app-node 100    # Node 歸戶服務
#   ./deploy/logs.sh analysis grep "\[s[0-9]\]|Error|Traceback"   # 只看 pipeline 步驟與錯誤
set -euo pipefail
cd "$(dirname "$0")/.."; source deploy/config.sh
UNIT="${1:-}"; N="${2:-60}"; PAT="${3:-}"
IID=$(aws ec2 describe-instances --filters "Name=tag:Name,Values=${APP_NAME}" "Name=instance-state-name,Values=running" --query 'Reservations[0].Instances[0].InstanceId' --output text)
# cloudwatch-setup.sh 之後 stdout 改寫到 /var/log/ntpc/{unit}.log（journald 不再有內容）
if [ -z "$UNIT" ]; then CMD="for u in app-node analysis; do echo \"===== \$u (\$(systemctl is-active \$u))\"; tail -n $N /var/log/ntpc/\$u.log | cut -c1-220; done"
elif [ "$N" = "grep" ]; then CMD="grep -aE '$PAT' /var/log/ntpc/$UNIT.log | tail -80 | cut -c1-240"
else CMD="echo \"===== $UNIT (\$(systemctl is-active $UNIT))\"; tail -n $N /var/log/ntpc/$UNIT.log | cut -c1-240"; fi
ID=$(aws ssm send-command --instance-ids "$IID" --document-name AWS-RunShellScript --parameters "commands=[$(printf '%s' "$CMD" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')]" --query Command.CommandId --output text)
for i in $(seq 1 20); do S=$(aws ssm get-command-invocation --command-id "$ID" --instance-id "$IID" --query Status --output text 2>/dev/null || echo Pending); case "$S" in Success|Failed) break;; esac; sleep 2; done
aws ssm get-command-invocation --command-id "$ID" --instance-id "$IID" --query StandardOutputContent --output text
