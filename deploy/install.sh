#!/usr/bin/env bash
# Linux 部署脚本：在目标服务器上以 root 运行一次即可
# 假定项目已经 clone/上传到 /opt/explorer
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/explorer}"
APP_USER="${APP_USER:-explorer}"

if [[ ! -d "$APP_DIR" ]]; then
  echo "项目目录不存在: $APP_DIR" >&2
  exit 1
fi

# 1. 创建运行用户（已存在则跳过）
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

# 2. 准备 venv 与依赖
cd "$APP_DIR"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 3. 目录权限
mkdir -p data logs
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# 4. 安装 systemd 单元
install -m 0644 deploy/systemd/explorer.service /etc/systemd/system/explorer.service
install -m 0644 deploy/systemd/explorer.timer   /etc/systemd/system/explorer.timer
systemctl daemon-reload
systemctl enable --now explorer.timer

echo "完成。查看下次触发时间：systemctl list-timers explorer.timer"
echo "立即手动跑一次：systemctl start explorer.service"
