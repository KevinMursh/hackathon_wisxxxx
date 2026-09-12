# 部署（EC2 + FastAPI，前後端同源）

```
瀏覽器 ──HTTP:80──► EC2 t3.large（us-west-2）
                      └─ uvicorn：/ 靜態前端（src/frontend）＋ /api/*（src/backend）
                           └─ Instance Profile → Bedrock Claude Sonnet 4.5（全域鎖 ≤ 1 RPS）
```

| 項目 | 值 |
|---|---|
| Live URL | http://100.20.156.38/ |
| Instance | `i-0317e2f9af300f2bf`（Name=`ntpc-law3`） |
| SG | `sg-0009d15c615ede2a9`，只開 80 給會場四組 IP（見 `config.sh`） |
| 部署包 bucket | `s3://ntpc-law3-deploy-229004791954/app.tar.gz`（私有） |
| IAM role | `ntpc-law3-ec2-role`：Bedrock Invoke/Retrieve/Rerank、該 bucket、SSM |

## 日常更新（改完 src/ 之後）

```bash
./deploy/push.sh        # 打包 src+deploy → S3 → SSM 叫 EC2 重裝並重啟，約 30 秒
```

## 第一次建環境（已做過，重建才需要）

```bash
./deploy/create-infra.sh
```

## 除錯

```bash
source deploy/config.sh
aws ssm start-session --target i-0317e2f9af300f2bf     # 免 SSH 進機器
sudo journalctl -u app -f                                # 看服務 log
```

## 不在會場（IP 不在四組內）時

自己的 IP 加進 SG：
```bash
aws ec2 authorize-security-group-ingress --group-id sg-0009d15c615ede2a9 --protocol tcp --port 80 --cidr $(curl -s https://checkip.amazonaws.com)/32
```

## 後續可加

- CloudFront（HTTPS、`xxx.cloudfront.net` 網址）：origin 指 EC2 public DNS，SG 另開 80 給 prefix list `com.amazonaws.global.cloudfront.origin-facing`
- Bedrock Knowledge Base：role 已含 `bedrock:Retrieve`，建好 KB 後在 `bedrock.py` 加 `retrieve()` 即可
