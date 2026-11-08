"""Add the supplied five-study result book to the platform graph, idempotently.

This records package claims and provenance; it does not re-run the studies.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS_ID = "SRC_FIVE_ARCH_RESULTS_20261107"
CODE_ID = "SRC_FIVE_ARCH_CODE_20261107"
RESULTS_FILE = "assets/sources/五套算法架构_跑数结果汇编.pdf"
CODE_FILE = "assets/sources/五套算法架构_代码汇编.pdf"

STUDIES = [
    ("A", "入院特征基准", "Admission feature benchmark", "D13 公开队列 21,459 例；36 项入院特征；比较 LR、LightGBM、TabPFN。固定划分的内部基准研究，非外部验证。", "dataset_d13", "outcome_second_epilepsy", "公开真实队列", "入院基线预测", 36),
    ("B", "实验室特征增量", "Laboratory feature increment", "D13 公开队列 21,459 例；在 36 项入院特征上增加 34 项实验室特征，共 70 项。与 A 共用固定测试集。", "dataset_d13", "outcome_second_epilepsy", "公开真实队列", "实验室增量研究", 70),
    ("C", "卒中后并发症边界检验", "Post-stroke complication boundary test", "D13 公开队列 21,459 例；在 B 的 70 项上增加 4 项卒中后并发症。后发生变量有时间泄漏风险，不能作为入院时预测字段直接部署。", "dataset_d13", "outcome_second_epilepsy", "公开真实队列", "时间泄漏敏感性", 74),
    ("D", "卒中后首次早期发作时点预测", "Prediction after early post-stroke seizure", "温州 167 例去标识单中心队列，均为卒中后 7 天内早期发作；研究后续 PSE，核心 8 项和扩展 24 项特征，重复分层交叉验证，非外部验证。", "network_dataset_wenzhou_167", "network_outcome_wenzhou_pse", "单中心真实队列", "卒中后早期发作预测", 8),
    ("E", "抗发作药物与晚期 PSE 关联", "ASM and later PSE association", "温州同一 167 例去标识队列；比较接受与未接受 ASM 者的后续 PSE。属于观察性关联分析，不是独立预测模型，也不能推断用药因果效果。", "network_dataset_wenzhou_167", "network_outcome_wenzhou_pse", "单中心真实队列", "观察性关联分析", None),
]


def read_json(name: str):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def write_json(name: str, value):
    (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def upsert(items: list[dict], key: str, value: dict):
    for index, item in enumerate(items):
        if item[key] == value[key]:
            items[index] = value
            return
    items.append(value)


def source(source_id: str, title: str, file: str, kind: str):
    return {
        "source_id": source_id, "source_type": kind, "title": title,
        "origin": "三合医研发团队 · 河南大学 · 2026-11-07 交付包",
        "identifier": hashlib.sha256((ROOT / file).read_bytes()).hexdigest(),
        "url": "/knowledge-graph/" + file,
        "verification": "已核对交付包页面、队列和任务定义；未独立复跑，非外部临床验证",
    }


def main():
    graph = read_json("graph_seed.json")
    catalog = read_json("entity_catalog.json")
    claims = read_json("evidence_claims.json")
    sources = read_json("sources.json")
    html_path = ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")
    prefix = '<script id="app-data" type="application/json">'
    head, tail = html.split(prefix, 1)
    payload, rest = tail.split("</script>", 1)
    app_data = json.loads(payload)

    upsert(sources, "source_id", source(RESULTS_ID, "卒中后癫痫五套算法架构 · 跑数结果汇编", RESULTS_FILE, "项目结果汇编"))
    upsert(sources, "source_id", source(CODE_ID, "卒中后癫痫五套算法架构 · 代码汇编", CODE_FILE, "项目代码汇编"))
    for letter, title_zh, title_en, definition, dataset_id, outcome_id, provenance, analysis_type, feature_count in STUDIES:
        node_id = f"study_five_arch_{letter.lower()}_20261107"
        claim_id = f"FIVE-ARCH-{letter}-001"
        node = {
            "entity_id": node_id, "entity_type": "Study", "canonical_name_zh": f"架构 {letter}：{title_zh}",
            "canonical_name_en": f"Architecture {letter}: {title_en}", "definition": definition,
            "aliases_zh": [f"算法架构{letter}"], "aliases_en": [f"study {letter}"],
            "abbreviations": [], "non_synonyms": ["减药后复发模型", "外部临床验证"],
            "status": "provisional",
            "properties": {
                "source_ids": [RESULTS_ID, CODE_ID], "dataset_id": dataset_id,
                "outcome_id": outcome_id, "data_provenance": provenance,
                "analysis_type": analysis_type, "feature_count": feature_count,
                "validation_status": "交付包核对；非独立复跑或外部验证",
            },
        }
        upsert(graph["nodes"], "entity_id", node)
        upsert(catalog, "entity_id", node.copy())
        upsert(claims, "claim_id", {
            "claim_id": claim_id, "claim_group": "五套算法架构交付包", "subject": node_id,
            "predicate": "studies", "object": outcome_id, "statement": f"算法架构{letter}：{definition}",
            "direction": "项目研究记录", "population": provenance,
            "time_context": "卒中后癫痫研究；具体时点见结果汇编",
            "source_id": RESULTS_ID,
            "source_locator": "结果汇编第 0–1 节；A/B/C 第 2–7 节，D 第 8 节，E 第 9 节",
            "status": "交付包核对",
        })
        for suffix, relation, target in [("DATA", "DERIVED_FROM", dataset_id), ("OUTCOME", "HAS_OUTCOME", outcome_id)]:
            upsert(graph["edges"], "edge_id", {
                "edge_id": f"R-FIVE-{letter}-{suffix}", "relation_type": relation,
                "from": node_id, "to": target,
                "attributes": {"source_ids": [RESULTS_ID, CODE_ID], "status": "provisional",
                               "evidence_claim_ids": [claim_id], "evidence_locators": ["结果汇编第 0–1 节"]},
            })

    # Keep both prediction paths tied to their corresponding evidence nodes.
    for collection in (graph["nodes"], catalog):
        for node in collection:
            if node["entity_id"] == "model_d13_s1_lr_platt_v0_3":
                node.setdefault("properties", {})["research_demo_url"] = "/workspace?view=single&scenario=stroke"
            if node["entity_id"] == "study_five_arch_d_20261107":
                node.setdefault("properties", {})["research_demo_url"] = "/workspace?view=single&scenario=first"

    app_data["graph"] = graph
    app_data["sources"] = sources
    app_data["claims"] = claims
    app_data.setdefault("local_sources", {})[RESULTS_ID] = RESULTS_FILE
    app_data["local_sources"][CODE_ID] = CODE_FILE
    write_json("graph_seed.json", graph)
    write_json("entity_catalog.json", catalog)
    write_json("evidence_claims.json", claims)
    write_json("sources.json", sources)
    html_path.write_text(head + prefix + json.dumps(app_data, ensure_ascii=False, separators=(",", ":")) + "</script>" + rest, encoding="utf-8")
    write_json("FIVE_STUDIES_INTEGRATION.json", {
        "source_status": "交付包核对；D 核心 LR 已按原始队列复算", "model_demo": "/workspace?view=single&scenario=stroke",
        "study_d_prediction": "/workspace?view=single&scenario=first",
        "results_pdf_sha256": hashlib.sha256((ROOT / RESULTS_FILE).read_bytes()).hexdigest(),
        "code_pdf_sha256": hashlib.sha256((ROOT / CODE_FILE).read_bytes()).hexdigest(),
        "nodes": len(graph["nodes"]), "edges": len(graph["edges"]),
        "claims": len(claims), "sources": len(sources),
    })
    print(f"nodes={len(graph['nodes'])} edges={len(graph['edges'])} claims={len(claims)} sources={len(sources)}")


if __name__ == "__main__":
    main()
