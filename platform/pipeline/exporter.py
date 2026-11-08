"""导出（方案 §9.1）：院内受控目录 + 防公式注入 + 元数据留痕。

导出只写院内受控目录；元数据（版本三元组、用途、导出人、审计事件 ID）
随文件一起落盘，CSV 用 sidecar `.meta.json`，XLSX 用独立 sheet。
"""
from __future__ import annotations

import csv
import json
import os
import time
import uuid
from typing import Any

_INJECT_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
FORWARD_COLUMNS = ["line", "case_id", "status", "risk_730d", "risk_band",
                   "ci_low", "ci_high", "in_support", "reject_codes",
                   "reject_reason", "model_version", "schema_version",
                   "mapping_version", "research_only"]
REVERSE_COLUMNS = FORWARD_COLUMNS + ["target_risk", "feasible_reduction_pct_low",
                                     "feasible_reduction_pct_upper",
                                     "dose_mg_low", "dose_mg_high",
                                     "extrapolated", "support_note"]
BANNER = "RESEARCH_ONLY — 教学/研究联调，不用于临床决策"


def guard_cell(value: Any) -> Any:
    """防 CSV/Excel 公式注入：对 = + - @ 起始单元格加前缀转义。"""
    if isinstance(value, str) and value and value[0] in _INJECT_PREFIXES:
        return "'" + value
    return value


def flatten_row(row: dict[str, Any], scenario: str,
                schema_version: str, mapping_version: str) -> dict[str, Any]:
    rng = row.get("feasible_reduction_range") or {}
    dose = row.get("dose_range_mg") or {}
    out = {
        "line": row.get("__line__"),
        "case_id": row.get("case_id"),
        "status": row.get("status"),
        "risk_730d": row.get("risk_730d"),
        "risk_band": row.get("risk_band"),
        "ci_low": row.get("ci_low"),
        "ci_high": row.get("ci_high"),
        "in_support": row.get("in_support"),
        "reject_codes": ";".join(row.get("reject_codes") or []),
        "reject_reason": row.get("reject_reason", ""),
        "model_version": row.get("model_version"),
        "schema_version": schema_version,
        "mapping_version": mapping_version,
        "research_only": bool(row.get("research_only", True)),
    }
    if scenario == "reverse":
        out.update({
            "target_risk": row.get("target_risk"),
            "feasible_reduction_pct_low": rng.get("pct_low"),
            "feasible_reduction_pct_upper": rng.get("pct_upper"),
            "dose_mg_low": dose.get("mg_low"), "dose_mg_high": dose.get("mg_high"),
            "extrapolated": row.get("extrapolated"),
            "support_note": row.get("support_note", ""),
        })
    return out


def export(rows: list[dict[str, Any]], *, out_dir: str, run_id: str,
           scenario: str, fmt: str, purpose: str, actor: str,
           versions: dict[str, str], event_id: str = "") -> dict[str, Any]:
    columns = REVERSE_COLUMNS if scenario == "reverse" else FORWARD_COLUMNS
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = f"run-{run_id}-{scenario}-{stamp}-{uuid.uuid4().hex[:8]}"
    flat = [flatten_row(r, scenario, versions.get("schema_version", ""),
                        versions.get("mapping_version", "")) for r in rows]

    meta = {
        "banner": BANNER, "run_id": run_id, "scenario": scenario,
        "purpose": purpose, "exported_by": actor, "exported_at": time.time(),
        "exported_at_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "versions": versions, "row_count": len(flat), "audit_event_id": event_id,
        "ok_rows": sum(1 for r in flat if r["status"] == "OK"),
        "rejected_rows": sum(1 for r in flat if r["status"] != "OK"),
    }

    if fmt == "json":
        path = os.path.join(out_dir, base + ".json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"meta": meta, "columns": columns, "rows": flat}, fh,
                      ensure_ascii=False, indent=2)
    elif fmt == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "results"
        ws.append([BANNER])
        ws.append(columns)
        for r in flat:
            ws.append([guard_cell(r.get(c)) for c in columns])
        ms = wb.create_sheet("meta")
        ms.append(["key", "value"])
        for k, v in meta.items():
            ms.append([k, guard_cell(json.dumps(v, ensure_ascii=False)
                       if isinstance(v, (dict, list)) else v)])
        path = os.path.join(out_dir, base + ".xlsx")
        wb.save(path)
    else:
        path = os.path.join(out_dir, base + ".csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow([f"# {BANNER}"])
            w.writerow(columns)
            for r in flat:
                w.writerow([guard_cell(r.get(c)) for c in columns])
    with open(path + ".meta.json", "w", encoding="utf-8") as fh:
        json.dump(meta, fh, ensure_ascii=False, indent=2)

    return {"path": os.path.abspath(path), "file_name": os.path.basename(path),
            "bytes": os.path.getsize(os.path.abspath(path)), "meta": meta}
