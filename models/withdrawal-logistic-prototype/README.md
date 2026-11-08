# 启动减药后2年发作复发风险模型（研究原型）

本项目用于验证“临床信息抽取—结构化变量—风险模型”的数据链路。当前代码使用 8 个变量和二分类 Logistic 模型，合成数据仅用于程序演示，不能代表临床风险，也不能给出停药建议。

主索引日是首次有证据支持的实际减低任一抗癫痫发作药物每日剂量日期。正式完全停药属于单独的条件性 landmark 队列，不能与主队列混合。

## 重要边界

- 当前原型不处理删失、竞争风险、时间变化协变量、校准更新或真实外部验证。
- `outcome_2y=0` 只适用于完成 730 天可靠随访且无确认复发者；随访不足者不能编码为 0。
- 新数据使用 `epilepsy_duration_before_remission_years`，表示达到缓解前的癫痫病程；旧字段 `epilepsy_duration_years` 仅作为兼容别名。
- 真实研究必须保留 `patient_id`、索引类型和日期、复发日期、最后可靠随访、死亡、删失和抽取器版本。
- LLM 只抽取变量、状态和证据；风险概率由锁定并校准的模型计算，不能自动生成停药指令。

## 运行

```powershell
$env:PYTHONPATH = (Get-Location).Path
python run_demo.py
python run_train.py --input real_model_schema.csv --model-output real_model.json
```

含 `patient_id` 时，原型优先进行患者级随机划分；没有该字段时会标记 `row_level_demo_only`，不能作为真实验证结果。

## 研究依据

- Lamberink 等，Lancet Neurology 2017，PMID 28483337，DOI 10.1016/S1474-4422(17)30114-X。
- Beaulieu-Jones 等，Lancet Digital Health 2023，PMID 38000873，DOI 10.1016/S2589-7500(23)00179-6。
- TRIPOD+AI，BMJ 2024，DOI 10.1136/bmj-2023-078378。
- AAN 抗癫痫发作药物停药实践建议，Neurology 2021，DOI 10.1212/WNL.0000000000012944。

详细流程、字段契约、删失规则和外部验证要求见 `USAGE.md`。

