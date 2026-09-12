# 所有部署腳本共用的設定
export AWS_PROFILE="${AWS_PROFILE:-ntpc-hackathon}"
export AWS_REGION="${AWS_REGION:-us-west-2}"
export APP_NAME="ntpc-law3"
export BUCKET="${APP_NAME}-deploy-229004791954"     # 私有 bucket，只放部署包
export INSTANCE_TYPE="t3.large"
# 主辦公布的四組會場對外 IP（9/12 現場公告）——SG 只開這四組，不開 0.0.0.0/0
export ALLOWED_IPS="60.250.71.45 61.222.117.53 59.125.121.41 60.250.71.43"
