#!/bin/bash
# 安裝後端所需外部工具。支援 Amazon Linux 2023（dnf）與 Ubuntu（apt）。
# 必要：poppler-utils、file、Node 20 —— 缺了服務會 503
# 選配：LibreOffice（Office 檔）、ffmpeg（影片）、qpdf、unzip —— 裝不起來不中斷，
#       服務照跑，/api/health 的 degraded 欄位會標示該格式無法處理。
set -uo pipefail
log() { echo "[setup-tools] $*"; }

if command -v dnf >/dev/null; then
  dnf install -y --allowerasing poppler-utils file unzip qpdf tar gzip xz || true
  command -v node >/dev/null || dnf install -y nodejs20 npm || {
    curl -fsSL https://rpm.nodesource.com/setup_20.x | bash - && dnf install -y nodejs; }

  # AL2023 沒有 ffmpeg：先試 ffmpeg-free，再退靜態版
  if ! command -v ffmpeg >/dev/null; then
    dnf install -y ffmpeg-free 2>/dev/null || {
      log "改用 ffmpeg 靜態版"
      curl -fsSL https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o /tmp/ff.tar.xz \
        && tar -xJf /tmp/ff.tar.xz -C /tmp \
        && install -m755 /tmp/ffmpeg-*-static/ffmpeg /tmp/ffmpeg-*-static/ffprobe /usr/local/bin/ \
        || log "⚠️ ffmpeg 安裝失敗 → 影片將回 unsupported"
    }
  fi

  # AL2023 沒有 LibreOffice 套件：用官方 RPM 包
  if ! command -v soffice >/dev/null; then
    # 版本會下架（24.8.x 已不在 stable），從目錄取現有最新版；可用 LO_VER 覆寫
    LO_VER="${LO_VER:-$(curl -fsSL https://download.documentfoundation.org/libreoffice/stable/ 2>/dev/null \
      | grep -oE '[0-9]+\.[0-9]+\.[0-9]+/' | tr -d '/' | sort -V | tail -1)}"
    [ -z "$LO_VER" ] && LO_VER=25.8.7
    log "下載 LibreOffice ${LO_VER} RPM（約 250MB）…"
    curl -fsSL "https://download.documentfoundation.org/libreoffice/stable/${LO_VER}/rpm/x86_64/LibreOffice_${LO_VER}_Linux_x86-64_rpm.tar.gz" -o /tmp/lo.tgz \
      && tar -xzf /tmp/lo.tgz -C /tmp \
      && dnf install -y /tmp/LibreOffice_*/RPMS/*.rpm \
      || log "⚠️ LibreOffice 安裝失敗 → Office 檔將回 unsupported"
    command -v soffice >/dev/null || {
      SO=$(ls -d /opt/libreoffice*/program/soffice 2>/dev/null | head -1)
      [ -n "$SO" ] && ln -sf "$SO" /usr/local/bin/soffice
    }
  fi

  dnf install -y google-noto-sans-cjk-ttc-fonts 2>/dev/null \
    || dnf install -y google-noto-sans-cjk-fonts 2>/dev/null \
    || log "⚠️ 中文字型未裝 → Office 轉 PDF 可能缺字"

elif command -v apt-get >/dev/null; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends \
    poppler-utils file unzip qpdf ffmpeg curl ca-certificates \
    libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-core \
    fonts-noto-cjk libheif-examples
  command -v node >/dev/null || { curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && apt-get install -y nodejs; }
else
  log "❌ 不認得的套件管理器"; exit 1
fi

log "檢查結果："
MISSING=0
for t in node pdftotext pdftoppm pdfinfo file; do
  P=$(command -v "$t" || true); printf '  [必要] %-10s %s\n' "$t" "${P:-(缺)}"; [ -z "$P" ] && MISSING=1
done
for t in unzip qpdf ffmpeg ffprobe soffice; do
  P=$(command -v "$t" || true); printf '  [選配] %-10s %s\n' "$t" "${P:-(缺，該格式回 unsupported)}"
done
[ "$MISSING" = 1 ] && { log "❌ 有必要工具缺少，服務會回 503"; exit 1; }
log "✅ 必要工具齊全"
