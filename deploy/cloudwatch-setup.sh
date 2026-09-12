#!/bin/bash
# 在 EC2 上執行（由 push 或 SSM）：兩個 service 的 stdout 落檔 → CloudWatch agent 送到 log group /ntpc-law3/{app-node,analysis}
set -euo pipefail
dnf install -y -q amazon-cloudwatch-agent >/dev/null
mkdir -p /var/log/ntpc
for u in app-node analysis; do
  mkdir -p /etc/systemd/system/$u.service.d
  printf '[Service]\nStandardOutput=append:/var/log/ntpc/%s.log\nStandardError=append:/var/log/ntpc/%s.log\n' $u $u > /etc/systemd/system/$u.service.d/log.conf
done
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'JSON'
{"logs":{"logs_collected":{"files":{"collect_list":[
 {"file_path":"/var/log/ntpc/app-node.log","log_group_name":"/ntpc-law3/app-node","log_stream_name":"{instance_id}","timezone":"UTC","retention_in_days":7},
 {"file_path":"/var/log/ntpc/analysis.log","log_group_name":"/ntpc-law3/analysis","log_stream_name":"{instance_id}","timezone":"UTC","retention_in_days":7}
]}}}}
JSON
systemctl daemon-reload
systemctl restart app-node analysis
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json >/dev/null
sleep 3; systemctl is-active amazon-cloudwatch-agent app-node analysis
curl -sf localhost/api/health >/dev/null && echo "node ok"; curl -sf localhost:8100/api/analysis/health >/dev/null && echo "analysis ok"
