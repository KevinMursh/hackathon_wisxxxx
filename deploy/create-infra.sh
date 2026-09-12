#!/bin/bash
# 本機執行一次：IAM role + instance profile、私有 S3 bucket、Security Group、EC2
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/config.sh
ROLE="${APP_NAME}-ec2-role"

# 1. S3（新 bucket 預設 Block Public Access 全開，符合規範第 1 條）
aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null || \
  aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint="$AWS_REGION"
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# 2. IAM role：Bedrock + 這個 bucket + SSM（取代 SSH）
if ! aws iam get-role --role-name "$ROLE" >/dev/null 2>&1; then
  aws iam create-role --role-name "$ROLE" --assume-role-policy-document '{
    "Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ec2.amazonaws.com"},"Action":"sts:AssumeRole"}]}' >/dev/null
  aws iam attach-role-policy --role-name "$ROLE" --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
  aws iam put-role-policy --role-name "$ROLE" --policy-name app --policy-document "{
    \"Version\":\"2012-10-17\",\"Statement\":[
      {\"Effect\":\"Allow\",\"Action\":[\"bedrock:InvokeModel\",\"bedrock:InvokeModelWithResponseStream\",\"bedrock:Retrieve\",\"bedrock:RetrieveAndGenerate\",\"bedrock:Rerank\"],\"Resource\":\"*\"},
      {\"Effect\":\"Allow\",\"Action\":[\"s3:GetObject\",\"s3:PutObject\",\"s3:ListBucket\"],\"Resource\":[\"arn:aws:s3:::${BUCKET}\",\"arn:aws:s3:::${BUCKET}/*\"]}
    ]}"
  aws iam create-instance-profile --instance-profile-name "$ROLE" >/dev/null
  aws iam add-role-to-instance-profile --instance-profile-name "$ROLE" --role-name "$ROLE"
  echo "等待 instance profile 生效…"; sleep 12
fi

# 3. Security Group：只開 80 給會場四組 IP（規範第 3 條：不可全開）
VPC=$(aws ec2 describe-vpcs --filters Name=is-default,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=${APP_NAME}-sg" "Name=vpc-id,Values=$VPC" \
     --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
if [ "$SG" = "None" ] || [ -z "$SG" ]; then
  SG=$(aws ec2 create-security-group --group-name "${APP_NAME}-sg" --description "ntpc law3 web" --vpc-id "$VPC" --query GroupId --output text)
  for ip in $ALLOWED_IPS; do
    aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 80 --cidr "${ip}/32" >/dev/null
  done
fi
echo "SG=$SG"

# 4. 先上傳部署包，EC2 開機時要拉
tar --exclude='.venv' --exclude='__pycache__' --exclude='.DS_Store' -czf /tmp/app.tar.gz src deploy
aws s3 cp /tmp/app.tar.gz "s3://${BUCKET}/app.tar.gz"

# 5. EC2
AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 --query Parameter.Value --output text)
SUBNET=$(aws ec2 describe-subnets --filters Name=default-for-az,Values=true Name=vpc-id,Values=$VPC --query 'Subnets[0].SubnetId' --output text)
sed "s/__BUCKET__/${BUCKET}/g" deploy/ec2/user-data.sh > /tmp/user-data.sh
IID=$(aws ec2 run-instances --image-id "$AMI" --instance-type "$INSTANCE_TYPE" --subnet-id "$SUBNET" \
      --security-group-ids "$SG" --iam-instance-profile Name="$ROLE" --associate-public-ip-address \
      --user-data file:///tmp/user-data.sh \
      --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]' \
      --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${APP_NAME}}]" \
      --query 'Instances[0].InstanceId' --output text)
echo "EC2 $IID 啟動中…"
aws ec2 wait instance-running --instance-ids "$IID"
IP=$(aws ec2 describe-instances --instance-ids "$IID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "Public IP: $IP  （user-data 約需 1–2 分鐘裝完，之後開 http://${IP}/ ）"
for i in $(seq 1 40); do
  curl -sf --max-time 3 "http://${IP}/api/health" && { echo; echo "✅ http://${IP}/"; exit 0; }
  sleep 5
done
echo "還沒 healthy，可用 SSM 查：aws ssm start-session --target $IID"
