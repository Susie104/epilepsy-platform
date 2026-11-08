"""CSV 契约与预检规则（schema_version 1.0.0）。

对应方案 §6：字段口径 = 2 个管理字段 + 8 个模型字段；
§6.2 逆向设计追加 B1-B7；§6.3 减药强度候选列为"先采集、后建模"；
§7.3 拒绝码表。

红线：不得把空值自动改为 0；不得把"未提及"当作"阴性"。
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import io
import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Any

SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------- 拒绝码表
REJECT_CODES: dict[str, str] = {
    "E101": "必填列缺失（管理字段）",
    "E102": "列名无法映射且无映射版本",
    "E103": "case_id 重复或含直接标识符",
    "E104": "index_date 格式非法或晚于当前日期",
    "E201": "模型字段取值越界（负数或超上限）",
    "E202": "模型字段类型非法（文本写入数值列）",
    "E203": "三值字段出现非法枚举",
    "E204": "模型字段为空且契约不允许缺失",
    "E301": "映射版本未确认或已被覆盖",
    "E302": "未经 confirm 直接运行",
    "E303": "用途不匹配（预测文件被用于重训）",
    "E401": "超出训练支持范围",
    "E402": "模型文件 SHA-256 校验失败",
    "E403": "逆向设计外推超出可行域",
    "E501": "文件超限（大小/行数/列数/字段长度）",
    "E502": "编码不可识别",
    "E503": "链接来源不在白名单或疑似 SSRF",
    "E601": "越权访问（对象级权限不足）",
}

SECURITY_CODES = {"E503", "E601", "E103"}

# ---------------------------------------------------------------- 字段规格
# kind: int | float | tri（1/0/空） | enum | date | str
Field = dict[str, Any]

MANAGEMENT_FIELDS: list[Field] = [
    {"name": "case_id", "label": "院内病例代号", "kind": "str", "required": True,
     "max_len": 64, "note": "HMAC 生成的不可逆代号，禁止姓名/身份证/手机号"},
    {"name": "index_date", "label": "首次实际减药日期", "kind": "date", "required": True,
     "note": "YYYY-MM-DD，由病历与审核人确定"},
]

MODEL_FIELDS: list[Field] = [
    {"name": "epilepsy_duration_before_remission_years", "label": "缓解前病程（年）",
     "kind": "float", "min": 0.0, "max": 100.0, "required": True},
    {"name": "seizure_free_months", "label": "减药前无发作月数",
     "kind": "float", "min": 0.0, "max": 600.0, "required": True},
    {"name": "age_at_onset", "label": "起病年龄（年）",
     "kind": "float", "min": 0.0, "max": 120.0, "required": True},
    {"name": "febrile_seizure_history", "label": "患者本人热性惊厥史",
     "kind": "tri", "required": True,
     "note": "家族史不计入；未提及不得填 0"},
    {"name": "seizure_count_before_remission", "label": "缓解前发作次数",
     "kind": "int", "min": 0, "max": 10000, "required": True},
    {"name": "self_limiting_syndrome", "label": "自限性癫痫综合征", "kind": "tri",
     "required": True},
    {"name": "developmental_delay", "label": "发育迟缓", "kind": "tri", "required": True},
    {"name": "eeg_epileptiform", "label": "EEG 癫痫样异常", "kind": "tri",
     "required": True, "note": "普通非特异性异常不得自动等同为 1"},
]

# §6.3 决策点 D2：先采集、不进模型（是否入模由算法负责人确认）
EXTENSION_FIELDS: list[Field] = [
    {"name": "relative_dose_reduction_pct", "label": "实际减药幅度（%）",
     "kind": "float", "min": 0.0, "max": 100.0, "required": False, "collected": True},
    {"name": "reduction_strategy", "label": "减量方式", "kind": "enum",
     "values": ["single_step", "stepwise"], "required": False, "collected": True},
    {"name": "asm_count", "label": "减药时用药种数", "kind": "int",
     "min": 1, "max": 10, "required": False, "collected": True},
    {"name": "previous_asm_failure_count", "label": "既往发作药物失败次数",
     "kind": "int", "min": 0, "max": 50, "required": False, "collected": True},
]

# §6.2 逆向设计（scenario=reverse 时必填 B1-B4）
REVERSE_FIELDS: list[Field] = [
    {"name": "asm_name", "label": "抗发作药物名称", "kind": "str", "required": True,
     "max_len": 64, "sensitive": True},
    {"name": "current_daily_dose_mg", "label": "减药前日剂量（mg）", "kind": "float",
     "min": 0.0, "max": 20000.0, "required": True, "sensitive": True},
    {"name": "planned_reduction_pct", "label": "计划减药幅度（%）", "kind": "float",
     "min": 0.0, "max": 100.0, "required": True},
    {"name": "reduction_schedule", "label": "减量方式", "kind": "enum",
     "values": ["single_step", "stepwise"], "required": True},
    {"name": "reduction_steps", "label": "分次减量步数", "kind": "int",
     "min": 1, "max": 24, "required": False,
     "required_if": ("reduction_schedule", "stepwise")},
    {"name": "asm_polytherapy", "label": "是否联合用药", "kind": "tri", "required": False},
    {"name": "previous_reduction_failure", "label": "既往减药失败/复发史", "kind": "tri",
     "required": False},
]

# §6.4 验证/重训模板必备列（用途 = validation / retrain）
VALIDATION_FIELDS: list[Field] = [
    {"name": "follow_up_days", "label": "随访天数", "kind": "int", "min": 0,
     "max": 3650, "required": True},
    {"name": "outcome_event", "label": "结局（1=复发/0=未复发）", "kind": "tri",
     "required": True},
    {"name": "censoring_status", "label": "删失状态", "kind": "enum",
     "values": ["none", "lost", "death", "study_end"], "required": True},
    {"name": "patient_level_group_id", "label": "患者级分组标识", "kind": "str",
     "required": True, "max_len": 64},
]
RETRAIN_EXTRA_FIELDS: list[Field] = [
    {"name": "site_id", "label": "中心标识（多中心预留）", "kind": "str",
     "required": False, "max_len": 32},
]

PURPOSES = ("prediction", "reverse", "validation", "retrain")

# 直接标识符黑名单（§9.1）——预检阶段扫描列名与抽样单元格
FORBIDDEN_COLUMN_PATTERNS = [
    r"(?i)(patient_)?name", r"姓名", r"id_?card", r"身份证", r"phone", r"mobile",
    r"手机", r"电话", r"address", r"住址", r"地址", r"bed_?no", r"床号",
    r"card_?no", r"就诊卡", r"住院号", r"mrn", r"病案号", r"email", r"邮箱",
]
FORBIDDEN_VALUE_PATTERNS = [
    re.compile(r"\b1[3-9]\d{9}\b"),                                   # 手机号
    re.compile(r"\b\d{17}[\dXx]\b"),                                  # 身份证
    re.compile(r"[\u4e00-\u9fa5]{2,4}(?=患者|病人)"),                  # 姓名式文本
]

DEFAULT_LIMITS = {
    "max_bytes": 50 * 1024 * 1024,
    "max_rows": 100_000,
    "max_cols": 200,
    "max_field_len": 4096,
    "retention_days": 180,
}


def required_columns(scenario: str) -> list[str]:
    cols = [f["name"] for f in MANAGEMENT_FIELDS]
    cols += [f["name"] for f in MODEL_FIELDS]
    if scenario == "reverse":
        cols += [f["name"] for f in REVERSE_FIELDS if f.get("required")]
    return cols


def optional_columns(scenario: str) -> list[str]:
    cols = [f["name"] for f in EXTENSION_FIELDS]
    if scenario == "reverse":
        cols += [f["name"] for f in REVERSE_FIELDS if not f.get("required")]
    return cols


def spec_by_name(scenario: str) -> dict[str, Field]:
    specs: dict[str, Field] = {}
    for group in (MANAGEMENT_FIELDS, MODEL_FIELDS, EXTENSION_FIELDS):
        for f in group:
            specs[f["name"]] = f
    if scenario == "reverse":
        for f in REVERSE_FIELDS:
            specs[f["name"]] = f
    for f in VALIDATION_FIELDS + RETRAIN_EXTRA_FIELDS:
        specs.setdefault(f["name"], f)
    return specs


def make_case_id(mrn: str, salt: bytes) -> str:
    """§9.1：case_id = HMAC-SHA256(院内病案号, 院内盐) 前 16 位十六进制。

    医院侧自行生成；平台只校验格式，从不接收病案号明文。
    """
    return hmac.new(salt, mrn.encode("utf-8"), hashlib.sha256).hexdigest()[:16]


def file_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def detect_encoding(raw: bytes) -> str:
    """只识别 UTF-8(含 BOM)；其他编码必须由院内配置显式声明（§6.5）。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    for enc in ("utf-8",):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return ""


@dataclass
class RowError:
    line: int
    field: str
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {"line": self.line, "field": self.field, "code": self.code,
                "message": self.message}


@dataclass
class ValidationResult:
    ok: bool
    scenario: str
    encoding: str
    columns: list[str] = field(default_factory=list)
    total_rows: int = 0
    runnable_rows: int = 0
    rejected_rows: int = 0
    needs_review_rows: int = 0
    errors: list[RowError] = field(default_factory=list)
    batch_errors: list[RowError] = field(default_factory=list)
    unmapped_required: list[str] = field(default_factory=list)
    forbidden_hits: list[str] = field(default_factory=list)
    column_stats: dict[str, Any] = field(default_factory=dict)
    codes_seen: dict[str, int] = field(default_factory=dict)

    def to_dict(self, truncated: int = 200) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        for e in self.batch_errors:
            rows.append({**e.to_dict(), "line": 0})
        rows += [e.to_dict() for e in self.errors[:truncated]]
        return {
            "ok": self.ok,
            "scenario": self.scenario,
            "encoding": self.encoding,
            "columns": self.columns,
            "total_rows": self.total_rows,
            "runnable_rows": self.runnable_rows,
            "rejected_rows": self.rejected_rows,
            "needs_review_rows": self.needs_review_rows,
            "errors": rows,
            "batch_errors": [e.to_dict() for e in self.batch_errors],
            "errors_truncated": len(self.errors) > truncated,
            "unmapped_required": self.unmapped_required,
            "forbidden_hits": self.forbidden_hits,
            "column_stats": self.column_stats,
            "codes_seen": self.codes_seen,
        }


# ------------------------------------------------------------- 文件解析
_FORBIDDEN_COL = [re.compile(p) for p in FORBIDDEN_COLUMN_PATTERNS]
_DATE_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")
_CASE_ID_RE = re.compile(r"^[0-9a-zA-Z_-]{6,64}$")
_TRI_OK = {"0", "1", "0.0", "1.0"}


def _is_forbidden_column(name: str) -> bool:
    if name == "asm_name":  # Contract field: medication name, not patient name.
        return False
    return any(p.search(name) for p in _FORBIDDEN_COL)


def parse_raw(raw: bytes, declared_encoding: str | None = None,
              limits: dict[str, int] | None = None):
    try:
        return _parse_raw(raw, declared_encoding, limits)
    except UnicodeDecodeError:
        return [], [], "", [RowError(0, "*", "E502", REJECT_CODES["E502"])]
    except csv.Error:
        return [], [], "", [RowError(0, "*", "E501", "CSV 格式非法或字段超过解析上限")]


def _parse_raw(raw: bytes, declared_encoding: str | None = None,
              limits: dict[str, int] | None = None):
    """解析 CSV 为原始字符串行；不做类型转换、不做静默编码猜测。

    返回 (columns, rows, encoding, batch_errors)。rows 中每个元素是
    {列名: 原始字符串}，行号从 2 起（1 为表头）。
    """
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    batch: list[RowError] = []
    if len(raw) > limits["max_bytes"]:
        batch.append(RowError(0, "*", "E501",
                              f"文件超过大小上限 {limits['max_bytes']} 字节"))
        return [], [], "", batch

    enc = detect_encoding(raw)
    if not enc:
        if declared_encoding in ("gbk", "gb18030"):
            enc = declared_encoding  # 院内配置显式声明后才允许转码
        else:
            batch.append(RowError(0, "*", "E502",
                                  "编码不可识别；仅支持 UTF-8(含 BOM)，其他编码须在院内配置显式声明"))
            return [], [], "", batch

    text = raw.decode(enc)
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
    except StopIteration:
        batch.append(RowError(0, "*", "E501", "空文件"))
        return [], [], enc, batch

    columns = [c.strip() for c in header]
    if len(set(columns)) != len(columns):
        return columns, [], enc, [RowError(0, "*", "E103", "CSV 包含重复列名，须人工消歧后重新导入")]
    if len(columns) > limits["max_cols"]:
        batch.append(RowError(0, "*", "E501",
                              f"列数 {len(columns)} 超过上限 {limits['max_cols']}"))
        return columns, [], enc, batch

    rows: list[dict[str, str]] = []
    overlong = 0
    for idx, rec in enumerate(reader, start=2):
        if not rec or (len(rec) == 1 and not rec[0].strip()):
            continue
        if len(rec) != len(columns):
            # 行宽与表头不一致：整行拒绝，不猜测补位
            batch.append(RowError(idx, "*", "E501",
                                  f"列数与表头不一致（表头 {len(columns)} 列，该行 {len(rec)} 列）"))
            continue
        row = {}
        for name, val in zip(columns, rec):
            if val is None:
                val = ""
            if len(val) > limits["max_field_len"]:
                val = val[: limits["max_field_len"]]
                overlong += 1
            row[name] = val.strip()
        rows.append({"__line__": idx, **row})

    if len(rows) > limits["max_rows"]:
        batch.append(RowError(0, "*", "E501",
                              f"数据行数 {len(rows)} 超过上限 {limits['max_rows']}"))
        return columns, [], enc, batch
    if overlong:
        batch.append(RowError(0, "*", "E501",
                              f"{overlong} 个单元格超过字段长度上限 {limits['max_field_len']}"))
    return columns, rows, enc, batch


# ------------------------------------------------------------- 字段映射
def propose_mapping(columns: list[str], scenario: str,
                    saved: dict[str, str] | None = None) -> dict[str, Any]:
    """医院列名 → 标准字段。

    仅做精确名匹配与规范化（小写、去空格/下划线）匹配；**不做模糊猜测**，
    避免把"住院天数"错配成"无发作月数"这类静默语义错误。
    """
    specs = spec_by_name(scenario)
    std = set(specs)
    saved = saved or {}
    mapping: dict[str, str] = {}
    ambiguous: list[str] = []

    def norm(s: str) -> str:
        return re.sub(r"[\s\-]+", "", s.lower())

    index: dict[str, list[str]] = {}
    for c in columns:
        if c in saved:
            mapping[c] = saved[c]
            continue
        if c in std:
            mapping[c] = c
            continue
        index.setdefault(norm(c), []).append(c)
    for c in columns:
        if c in mapping:
            continue
        hit = index.get(norm(c))
        if hit and len(hit) == 1 and hit[0] in std:
            mapping[c] = hit[0]
        elif hit and len(hit) > 1:
            ambiguous.append(c)

    mapped_std = set(mapping.values())
    req = [n for n in required_columns(scenario) if n not in mapped_std]
    unknown_cols = [c for c in columns
                    if c not in mapping and not _is_forbidden_column(c)]
    return {
        "mapping": mapping,
        "unmapped_required": req,
        "ambiguous": ambiguous,
        "unknown_columns": unknown_cols,
        "status": "COMPLETE" if not req else "INCOMPLETE",
    }


# ------------------------------------------------------------- 单元格校验
def _coerce(spec: Field, raw_val: str, today: _date) -> tuple[Any, str | None]:
    """返回 (值, 错误码)。空值语义严格按 D5：required 且为空 → E204。"""
    kind = spec["kind"]
    val = (raw_val or "").strip()
    if val == "" or val.lower() in ("na", "n/a", "null", "none", "nan"):
        if spec.get("required"):
            return None, "E204"
        return None, None

    if kind == "str":
        if len(val) > spec.get("max_len", DEFAULT_LIMITS["max_field_len"]):
            return None, "E501"
        return val, None
    if kind == "date":
        if not _DATE_RE.match(val):
            return None, "E104"
        y, m, d = (int(x) for x in val.split("-"))
        try:
            parsed = _date(y, m, d)
        except ValueError:
            return None, "E104"
        if parsed > today:
            return None, "E104"
        return parsed.isoformat(), None
    if kind == "tri":
        if val not in _TRI_OK:
            return None, "E203"
        return int(float(val)), None
    if kind == "enum":
        if val not in spec.get("values", []):
            return None, "E203"
        return val, None
    if kind in ("int", "float"):
        try:
            num = float(val)
        except ValueError:
            return None, "E202"
        if num != num or num in (float("inf"), float("-inf")):
            return None, "E202"
        lo, hi = spec.get("min"), spec.get("max")
        if (lo is not None and num < lo) or (hi is not None and num > hi):
            return None, "E201"
        if kind == "int":
            if abs(num - round(num)) > 1e-9:
                return None, "E202"
            return int(round(num)), None
        return num, None
    return val, None


def _case_id_problems(val: str) -> bool:
    if not val:
        return False
    if any(p.search(val) for p in FORBIDDEN_VALUE_PATTERNS):
        return True
    return not _CASE_ID_RE.match(val)


def coerce_row(row: dict[str, str], mapping: dict[str, str], scenario: str,
               today: _date) -> tuple[dict[str, Any], list[RowError]]:
    """把一行原始字符串转成标准记录；返回 (record, errors)。"""
    line = int(row.get("__line__", 0))
    specs = spec_by_name(scenario)
    std_row: dict[str, str] = {}
    for hosp_col, std in mapping.items():
        if hosp_col in row:
            std_row[std] = row[hosp_col]

    errors: list[RowError] = []
    record: dict[str, Any] = {"__line__": line}

    seen_required = set()
    for group_name, group in (("management", MANAGEMENT_FIELDS),
                              ("features", MODEL_FIELDS)):
        bucket: dict[str, Any] = {}
        for spec in group:
            name = spec["name"]
            raw_val = std_row.get(name)
            if raw_val is None:
                if spec.get("required"):
                    errors.append(RowError(line, name, "E101",
                                           f"缺少必填列 {name}"))
                continue
            val, code = _coerce(spec, raw_val, today)
            if code:
                errors.append(RowError(line, name, code, REJECT_CODES[code]))
                continue
            bucket[name] = val
            seen_required.add(name)
        record[group_name] = bucket

    ext: dict[str, Any] = {}
    for spec in EXTENSION_FIELDS:
        name = spec["name"]
        if name not in std_row:
            continue
        val, code = _coerce(spec, std_row[name], today)
        if code:
            errors.append(RowError(line, name, code, REJECT_CODES[code]))
        else:
            ext[name] = val
    record["extension"] = ext

    if scenario == "reverse":
        rev: dict[str, Any] = {}
        for spec in REVERSE_FIELDS:
            name = spec["name"]
            raw_val = std_row.get(name)
            if raw_val is None:
                if spec.get("required"):
                    errors.append(RowError(line, name, "E101",
                                           f"逆向设计缺少必填列 {name}"))
                continue
            val, code = _coerce(spec, raw_val, today)
            if code:
                errors.append(RowError(line, name, code, REJECT_CODES[code]))
                continue
            rev[name] = val
        if rev.get("reduction_schedule") == "stepwise" and rev.get("reduction_steps") is None:
            errors.append(RowError(line, "reduction_steps", "E101",
                                   "stepwise 减量方式必须提供 reduction_steps"))
        record["reverse"] = rev

    case_id = record["management"].get("case_id")
    if case_id is not None and _case_id_problems(str(case_id)):
        errors.append(RowError(line, "case_id", "E103", REJECT_CODES["E103"]))
    return record, errors


def validate(columns: list[str], rows: list[dict[str, str]], scenario: str,
             encoding: str, batch_errors: list[RowError],
             mapping: dict[str, str] | None = None,
             limits: dict[str, int] | None = None,
             today: _date | None = None) -> ValidationResult:
    """批量预检：文件级 → 列级（黑名单）→ 映射 → 逐行校验 → 列级统计。"""
    limits = {**DEFAULT_LIMITS, **(limits or {})}
    today = today or _date.today()
    res = ValidationResult(ok=False, scenario=scenario, encoding=encoding,
                           columns=columns)
    res.batch_errors = list(batch_errors)
    codes = res.codes_seen
    for e in batch_errors:
        codes[e.code] = codes.get(e.code, 0) + 1
    if any(e.code in ("E501", "E502") for e in batch_errors):
        return res

    hits = [c for c in columns if _is_forbidden_column(c)]
    res.forbidden_hits = hits
    if hits:
        res.batch_errors.append(RowError(
            0, ",".join(hits), "E103",
            f"检测到疑似直接标识符列，已拒绝并要求脱敏：{', '.join(hits)}"))
        codes["E103"] = codes.get("E103", 0) + 1

    mp = propose_mapping(columns, scenario)
    mapping = mp["mapping"] if mapping is None else mapping
    res.unmapped_required = [n for n in required_columns(scenario)
                             if n not in set(mapping.values())]
    if res.unmapped_required:
        res.batch_errors.append(RowError(
            0, ",".join(res.unmapped_required), "E102",
            f"以下标准字段无法映射，需审核人建立映射版本：{', '.join(res.unmapped_required)}"))
        codes["E102"] = codes.get("E102", 0) + 1

    res.total_rows = len(rows)
    clean: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}
    numeric_acc: dict[str, list[float]] = {}
    for row in rows:
        record, errors = coerce_row(row, mapping, scenario, today)
        cid = record.get("management", {}).get("case_id")
        if cid is not None:
            if str(cid) in seen_ids:
                errors.append(RowError(record["__line__"], "case_id", "E103",
                                       f"case_id 与第 {seen_ids[str(cid)]} 行重复"))
            else:
                seen_ids[str(cid)] = record["__line__"]
        for e in errors:
            codes[e.code] = codes.get(e.code, 0) + 1
        if errors:
            res.errors.extend(errors)
            res.rejected_rows += 1
            continue
        for name, val in record["features"].items():
            if isinstance(val, (int, float)):
                numeric_acc.setdefault(name, []).append(float(val))
        clean.append(record)

    res.runnable_rows = len(clean)
    res.column_stats = _column_stats(numeric_acc, clean)
    res.ok = (not res.batch_errors and res.unmapped_required == []
              and res.runnable_rows > 0)
    return res


def _column_stats(numeric_acc: dict[str, list[float]],
                  clean: list[dict[str, Any]]) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    for spec in MODEL_FIELDS:
        name = spec["name"]
        if spec["kind"] == "tri":
            ones = sum(1 for r in clean if r["features"].get(name) == 1)
            zeros = sum(1 for r in clean if r["features"].get(name) == 0)
            stats[name] = {"kind": "tri", "n": ones + zeros, "ones": ones,
                           "zeros": zeros}
        else:
            vals = numeric_acc.get(name, [])
            if not vals:
                continue
            stats[name] = {
                "kind": spec["kind"], "n": len(vals),
                "min": round(min(vals), 4), "max": round(max(vals), 4),
                "mean": round(sum(vals) / len(vals), 4),
                "p50": round(sorted(vals)[len(vals) // 2], 4),
            }
    return stats


def clean_records(result_columns: list[str], rows: list[dict[str, str]],
                  scenario: str, mapping: dict[str, str],
                  today: _date | None = None) -> list[dict[str, Any]]:
    """运行阶段复用：返回通过校验的记录（错误已在 confirm 前处理）。"""
    today = today or _date.today()
    out = []
    seen_ids = set()
    for row in rows:
        record, errors = coerce_row(row, mapping, scenario, today)
        cid = record.get("management", {}).get("case_id")
        if cid is not None:
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
        if not errors:
            out.append(record)
    return out

