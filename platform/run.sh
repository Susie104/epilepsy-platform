#!/usr/bin/env bash
# 院内启动脚本（方案 §4.2 / 附录 D.3）
# 用法：
#   bash run.sh                 方案A（两道边界 + 进程内推理）
#   CHANNEL2=1 bash run.sh      方案B（边界二启用信封加密；需先 keygen）
#   REVERSE=0 bash run.sh       关闭逆向设计（未验证前）
# 环境变量：BIND_HOST(默认 127.0.0.1)、PORT(默认 3000)、CHANNEL2、REVERSE
set -euo pipefail
cd "$(dirname "$0")"

BIND_HOST="${BIND_HOST:-127.0.0.1}"
PORT="${PORT:-3000}"
mkdir -p var/{imports,runs,results,mappings,exports,staging,audit,keys}

if [ "${CHANNEL2:-0}" = "1" ] && [ ! -f var/keys/model.private.json ]; then
  echo "[!] 通道2 已启用但院内密钥缺失：请先执行"
  echo "      python -m gateway.keygen --dir var/keys"
  exit 1
fi

echo "[i] 教学/研究联调 · 不用于临床决策 · 数据不出院"
BIND_HOST="$BIND_HOST" PORT="$PORT" exec python3 server.py
