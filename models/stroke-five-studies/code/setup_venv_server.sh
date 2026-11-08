#!/bin/bash
# 服务器端：清华镜像引导 pip 到 venv，并安装 D13 依赖（不依赖 ensurepip/系统 pip）
set -euo pipefail
cd ~/D13_20261107
MIRROR=https://pypi.tuna.tsinghua.edu.cn

PIPURL=$(curl -s --max-time 60 "$MIRROR/simple/pip/" \
  | grep -o 'href="[^"]*pip-[0-9][0-9.]*-py3-none-any\.whl[^"]*"' \
  | tail -1 | sed 's/^href="//; s/"$//')
case "$PIPURL" in
  http*) ;;
  *) PIPURL="$MIRROR$PIPURL" ;;
esac
echo "pip wheel: $PIPURL"

curl -s --max-time 120 -O "$PIPURL"
WHEEL=$(basename "$PIPURL")
unzip -q -o "$WHEEL" -d venv/lib/python3.12/site-packages/
rm -f "$WHEEL"

./venv/bin/python -m pip --version
./venv/bin/pip install -q -r requirements.txt
./venv/bin/python -c 'import numpy,pandas,sklearn,lightgbm,matplotlib,joblib; print("deps ok", numpy.__version__, pandas.__version__, sklearn.__version__, lightgbm.__version__)'
echo "VENV_READY"
