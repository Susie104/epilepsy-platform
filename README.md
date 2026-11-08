# 癫痫研究平台

在线入口：[平台](https://epilepsy-platform--susie.uua2a.com/) · [路演](https://epilepsy-roadshow--susie.uua2a.com/)

| 目录 | 内容 |
| --- | --- |
| `platform/` | Flask 演示平台、前端、API 与测试 |
| `roadshow/` | 路演静态页和媒体素材 |
| `models/stroke-five-studies/` | 卒中后癫痫 A–E 五套算法脚本、D13 数据 |
| `models/withdrawal-730d/` | 减药后 730 天复发预测与逆向搜索，合成数据 |
| `models/withdrawal-logistic-prototype/` | 减药后复发逻辑回归原型 |
| `docs/` | 代码汇编、跑数结果、五篇方案和复现说明 |

## 本地运行

平台：Python 3.12，在 `platform/` 安装 `requirements.lock.txt`，运行 `python serve_local.py`，打开 `http://127.0.0.1:3000/`。

路演：在 `roadshow/` 运行 `python -m http.server 3001 --bind 127.0.0.1`，打开 `http://127.0.0.1:3001/?intro=0`。

UUMit 链接分别转发本机 3000 和 3001 端口。GitHub 提交不会自动更新这两个服务。

## 数据与复现

- D13 公共队列：21,459 行，75 列；[Dryad DOI 10.5061/dryad.w0vt4b92c](https://doi.org/10.5061/dryad.w0vt4b92c)；SHA-256 `be84a00921702c45e5c9d250176602b2c62ed96ac41716dca8893b0c5be49d4b`。
- `models/withdrawal-730d/synthetic_input/` 是 260 例教学合成数据，不代表真实临床模型性能。
- 温州 167 例真实队列、首次发作 167 例原始病例和第三方模型权重未收录；详见 [数据清单](DATA_MANIFEST.md)。
- 五套算法的 23 个脚本与代码汇编中的 SHA-256 逐一一致；[校验清单](models/stroke-five-studies/code/SHA256_MANIFEST.json)。复跑环境与命令见 `docs/配置要求与复现说明.docx`。
