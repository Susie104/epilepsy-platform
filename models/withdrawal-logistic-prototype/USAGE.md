# 药物控制癫痫患者启动减药后复发风险模型：研究原型使用与审计说明

## 1. 文档定位

本项目是**研究原型**，用于验证“临床信息抽取—结构化变量—风险模型”的数据链路。当前代码使用 8 个变量和二分类 Logistic 模型，演示数据为合成数据，**不代表临床风险，也不能给出停药建议**。

本项目的主索引定义为：

> 首次有证据支持的实际减低任一抗癫痫发作药物每日剂量的日期。

医生仅提出减药计划但尚未实际降低剂量，不计入主索引。单纯换药、处方续配、自行漏服或不良反应导致的调整，必须单独标记，不能未经判定归入“启动减药”。

正式完全停药不是主索引的普通替代值。达到正式停药的人群属于条件性 landmark 队列：以正式停药日重新截断可用信息、重新规定纳入条件，并从该日开始计算后续结局。

## 2. 当前实现边界

- 当前实现只支持完整结局的二分类 Logistic 原型，不处理删失、竞争风险或时间变化协变量。
- `outcome_2y=1` 表示从主索引日开始 730 天内首次确认复发；`outcome_2y=0` 只允许用于完成 730 天可靠随访且未确认复发的患者。
- 随访不足 730 天、只有“本院未记录复发”、死亡或结局不确定的患者，不能直接编码为 0；应保留删失信息，进入离散时间生存模型或 Cox 模型。
- 真实研究必须进行患者级划分、时间外部验证、校准、决策曲线和预先规定的样本量论证。
- 生成式大语言模型只负责信息抽取、时间归一化和证据定位；风险概率由锁定并校准的风险模型计算。

## 3. 环境和目录

```powershell
python --version
$env:PYTHONPATH = (Get-Location).Path
```

```text
src/data.py       字段定义、LLM JSON 转换、CSV 导入和合成数据
src/model.py      Logistic 风险模型及 JSON 保存/加载
src/metrics.py    AUROC、AUPRC、Brier、Log-loss
run_demo.py       合成数据演示
run_train.py      真实或转换后 CSV 的原型训练
data_template.csv 字段模板
tests/            单元测试
```

## 4. 先运行合成数据演示

```powershell
$env:PYTHONPATH = (Get-Location).Path
python run_demo.py
```

演示使用 2,000 例合成患者。系数是研究流程演示用系数，不是 Lamberink 原始系数，也不是经过临床校准的模型。输出的 AUROC、AUPRC、Brier、Log-loss 和示例风险只用于检查程序链路。

## 5. 字段定义

当前 8 个模型字段为：

```text
epilepsy_duration_before_remission_years
seizure_free_months
age_at_onset
febrile_seizure_history
seizure_count_before_remission
self_limiting_syndrome
developmental_delay
eeg_epileptiform
```

其中 `epilepsy_duration_before_remission_years` 指**起病到达到缓解/无发作状态之间的病程**，不是起病到启动减药日的总时间。旧字段 `epilepsy_duration_years` 仍作为兼容别名读取，但新数据应使用上述明确字段名。

终生病史变量应读取索引日前所有可用记录；近期状态变量应记录预先规定的时间窗口以及距索引日的时间，例如索引日前最近一次 EEG 的检查日期和报告可用日期。

真实研究表还必须保留下列审计字段：

```text
patient_id
index_time
index_type
recurrence_date
last_reliable_followup_date
death_date
event_status
censor_days
split
extractor_version
```

这些字段不直接作为当前 8 变量模型的输入，但用于患者级划分、删失处理、时间外部验证、结局复核和版本追踪。

## 6. 真实数据的结局编码

当前二分类原型只接受以下规则：

- `outcome_2y=1`：主索引日后 730 天内首次由神经科医生确认的非诱发性癫痫发作。
- `outcome_2y=0`：有足够证据证明完成 730 天可靠随访且没有确认复发。
- 随访不足、失访、死亡、复发日期不确定或仅有“未见复发记录”：保留 `event_status`、`censor_days` 和最后可靠随访日期，不能编码为 0。
- 急性症状性发作、晕厥、心因性非癫痫发作和无法确认的描述，需要按结局判定手册处理，不能仅依据诊断编码或处方变化判定复发。

正式停药 landmark 队列必须单独保存 `index_type=formal_discontinuation`，不能与启动减药主队列混在同一个标签中。

## 7. 导入和训练

使用标准字段 CSV：

```powershell
python run_train.py `
  --input real_model_schema.csv `
  --model-output real_model.json
```

中文字段转换：

```powershell
python run_train.py `
  --input real_chinese.csv `
  --real-csv `
  --converted-output real_model_schema.csv `
  --model-output real_model.json
```

如果 CSV 含有 `patient_id`，原型会优先进行患者级随机划分；如果没有，输出会标记为 `row_level_demo_only`。真实研究不得把行级划分结果当作内部验证结果，应按患者划分并优先保留时间外部或独立机构数据。

## 8. LLM JSON 契约

研究推荐保存带状态、证据和可用性标记的 JSON：

```json
{
  "epilepsy_duration_before_remission_years": {
    "value": 6,
    "status": "documented_positive",
    "evidence": [
      {
        "document_id": "DOC-001",
        "available_before_index": true,
        "quote": "2018年起病，2024年达到无发作状态"
      }
    ]
  },
  "seizure_free_months": {
    "value": 30,
    "status": "documented_positive",
    "evidence": []
  },
  "eeg_epileptiform": {
    "value": true,
    "status": "documented_positive",
    "evidence": []
  }
}
```

`unknown` 应转换为 `value: null` 并保留明确的缺失状态；“未明确记录”不是病历原文证据。当前原型在进入 Logistic 模型前会拒绝 `null`、`unknown` 和无法解析的值，避免把未知自动转换为“无”。正式研究应在训练管道内预先固定缺失处理，并在验证和部署阶段使用同一处理规则。

LLM 自报的 `confidence=0.95` 不等于 95% 正确率。是否自动采用字段，必须依据独立人工标注集校准，并分别报告自动抽取和人工修订后的性能。

## 9. 从病历到风险的推荐流程

1. 固定主索引为首次实际降低任一 ASM 日剂量的日期，并记录证据来源。
2. 仅输入索引时点以前已经可获得的文书；同日只有日期而没有时刻时，按预先规定的保守规则处理。
3. 终生病史和近期状态分开抽取，所有字段记录文书日期、可用日期和距索引日的时间。
4. LLM 输出固定 JSON、状态和证据片段；不得根据常识补写病历未出现的事实。
5. 运行格式、数值范围、时间关系、否定和证据语义校验。
6. 冲突字段同时保留“最近一次结果”和“既往是否出现过异常”；不能用最新正常 EEG 自动否定既往癫痫样放电。
7. 低置信度或语义不确定病例送癫痫专科医生复核，并记录修改前后值和耗时。
8. 生成患者级研究表，保留事件日期、最后可靠随访、死亡和删失信息。
9. 先完成队列盘点：可纳入人数、事件数、失访比例、核心变量可获得率和外部验证来源。
10. 样本量不足时优先使用简洁的惩罚化回归或离散时间生存模型，XGBoost和原始文本嵌入作为次要探索。

## 10. 预测单个患者

```python
from src.data import extract_features
from src.model import load_model_json

record = {
    "epilepsy_duration_before_remission_years": 6,
    "seizure_free_months": 30,
    "age_at_onset": 14,
    "febrile_seizure_history": True,
    "seizure_count_before_remission": 5,
    "self_limiting_syndrome": False,
    "developmental_delay": False,
    "eeg_epileptiform": True,
}
features, _ = extract_features(record)
model = load_model_json("real_model.json")
risk_2y = model.predict_one(features)
print(f"2年复发风险: {risk_2y:.3f}")
```

该数值仅表示模型在其训练人群、索引定义和校准状态下的风险估计，不能解释为停药阈值或治疗指令。

## 11. 评价和外部验证

主研究应预先指定：

- 主模型：能处理删失的离散时间生存模型，报告 730 天累计风险；二分类 Logistic 仅作次要分析。
- 区分度：时间依赖 AUROC 或 C 统计量；AUPRC 需说明删失处理。
- 校准度：校准截距、校准斜率、校准曲线和 Brier 分数。
- 临床效用：针对“强化随访/安排复核”等明确行动开展决策曲线，不把风险阈值解释成停药阈值。
- 外部验证：先在锁定模型上报告原始表现，再把重新校准作为单独的模型更新结果。
- 样本量：根据预期事件风险、模型复杂度和指标精度计算，不能只按固定比例或固定事件数套用。

## 12. 研究依据和已知限制

- Lamberink 等研究纳入 10 项研究、1,769 例患者，随访中复发 46%，中位随访 5.3 年；该比例不能直接当作本研究 2 年复发率。
- Beaulieu-Jones 等研究对象是 21 岁前首次癫痫样事件患者，不能据此承诺启动减药队列或中文病历达到相同性能。
- TRIPOD+AI 用于透明报告，PROBAST/PROBAST+AI 用于质量和偏倚评价；遵循规范本身不等于模型有效。
- AAN 2021 建议对无发作至少 2 年的成人开展个体化风险获益讨论，并不等于所有患者都适合停药。
- 当前源码没有实现删失、竞争风险、完整生存分析、校准更新或真实外部验证；这些属于正式研究开发工作。

## 13. 启动前检查

1. 抽查 30–50 例重建起病、缓解、启动减药、复发和失访时间。
2. 检查是否把未知值当成 0、普通 EEG 异常当成癫痫样放电、删失者当成阴性。
3. 检查训练和预测的特征顺序、索引类型、患者划分和抽取器版本。
4. 确认独立验证数据的机构、时间范围、授权、事件数和随访质量。
5. 只有在真实队列审计完成后，才确定模型复杂度、外部验证计划和 14 个月实施边界。

