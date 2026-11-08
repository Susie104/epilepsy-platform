# 卒中后癫痫知识图谱术语与关系 v0.6

实体与关系的完整定义以 `schema.json` 为准。`entity_catalog.json` 定义 187 个实体；`graph_seed.json` 定义 643 条关系；`synonym_map.json` 提供 500 个归一化检索项。跨来源相同名称不等于同一人群、结局或可合并队列。

- `Dataset`、`Population`、`Outcome` 分别标记数据交付、人群边界与结局定义。
- `Model`、`FeatureSet`、`ScoreComponent` 分别标记模型、输入集合与评分规则；D13 v0.3 的 S1 是主模型候选，S2 是探索性，S3 只用于泄漏敏感性分析。
- `Study`、`Source` 和证据定位记录研究与来源；来源核对状态不等于临床验证。
- `DataQualityIssue`、`NOT_MERGED_WITH`、`CANNOT_CALCULATE` 显示数据限制和不可作的推断。

D13 与温州、苏州/安徽、Winder 网络数据分别建模。D13 一年二分类标签与 SeLECT 的晚期无诱因发作时间终点不同；没有事件日期、死亡日期及可靠末次随访日期时，不计算 Cox 或 Fine–Gray。
