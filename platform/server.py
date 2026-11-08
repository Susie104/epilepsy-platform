"""院内平台服务（边界一 + 边界二）。

方案对应：§5 入口、§6 CSV 契约、§7 输出与拒绝码、§8 API、§9 脱敏/密钥/审计。
默认只绑定回环地址，仅院内可达；生产部署须由医院信息科加上 HTTPS 与
统一身份认证（本文件的角色鉴权为可替换的身份桩，见 require_role）。

运行：python server.py            （默认 127.0.0.1:3000）
     CHANNEL2=1 python server.py  （启用边界二信封加密，需先 keygen）
"""
from __future__ import annotations

import json
import math
import os
import re
import secrets
import threading
import time
import uuid
from functools import wraps
from datetime import date
from typing import Any

from flask import Flask, jsonify, request, send_file, send_from_directory

from gateway.crypto import (EnvelopeError, KeyStore, NonceCache, fingerprint,
                            open_envelope, seal)
from pipeline import contract, exporter
from pipeline.audit import AuditLog, AuditRejected
from pipeline.model import (FORWARD_FILE, FORWARD_MODEL_VERSION, META_FILE,
                            REVERSE_MODEL_VERSION, IntegrityError, Predictor,
                            train_model_dir)
import knowledge_qa

ROOT = os.path.dirname(os.path.abspath(__file__))
VAR = os.path.abspath(os.environ.get("APP_VAR_DIR", os.path.join(ROOT, "var")))
APP_VERSION = "0.9.0-mvp"
BANNER = "教学/研究联调 · 不用于临床决策 · 数据不出院"

# --------------------------------------------------------------- 角色
ROLES = {"importer": "导入员", "reviewer": "审核员", "runner": "运行员",
         "viewer": "结果查看者", "exporter": "导出授权者", "admin": "系统管理"}

STORE = {
    "imports": os.path.join(VAR, "imports"),
    "runs": os.path.join(VAR, "runs"),
    "results": os.path.join(VAR, "results"),
    "mappings": os.path.join(VAR, "mappings"),
    "staging": os.path.join(VAR, "staging"),
    "exports": os.path.join(VAR, "exports"),
    "audit": os.path.join(VAR, "audit"),
    "keys": os.path.join(VAR, "keys"),
}
for d in STORE.values():
    os.makedirs(d, exist_ok=True)

CONFIG = {
    "channel2_envelope": os.environ.get("CHANNEL2", "0") == "1",
    "reverse_enabled": os.environ.get("REVERSE", "1") == "1",
    "limits": dict(contract.DEFAULT_LIMITS),
    "link_whitelist": [],          # §5.3 D4：默认空，由信息科逐个添加
    "missing_policy": "reject",    # 决策点 D5：契约冻结前空值一律拒绝
}

# 服务身份令牌（边界二）：随机生成、0600、仅本机进程可读；绝不发给浏览器
_TOKEN_PATH = os.path.join(VAR, "internal_service.token")
if os.path.exists(_TOKEN_PATH):
    INTERNAL_TOKEN = open(_TOKEN_PATH, encoding="utf-8").read().strip()
else:
    INTERNAL_TOKEN = secrets.token_urlsafe(32)
    fd = os.open(_TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(INTERNAL_TOKEN)
    os.chmod(_TOKEN_PATH, 0o600)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = CONFIG["limits"]["max_bytes"] + 1024
audit_log = AuditLog(os.path.join(STORE["audit"], "audit.jsonl"))
nonce_cache = NonceCache()
predictor: Predictor | None = None
_SUBMIT_LOCK = threading.Lock()
_RUN_STATE_LOCK = threading.Lock()
_STORE_LOCK = threading.RLock()


def valid_id(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value) is not None


@app.before_request
def validate_json_object():
    if request.is_json and not isinstance(request.get_json(silent=True), dict):
        return api_error("E202", "JSON 请求体必须为对象")


@app.errorhandler(413)
def oversized_request(error):
    return api_error("E501", "上传文件超过大小上限", None, 413)


def serialized_submission(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _SUBMIT_LOCK:
            return fn(*args, **kwargs)
    return wrapped


def synchronized_storage(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        # Windows replacement fails while another thread holds an open reader.
        with _STORE_LOCK:
            return fn(*args, **kwargs)
    return wrapped


def parse_target_risk(body):
    try:
        value = float(body.get("target_risk", 0.3))
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and 0 < value <= 1 else None


# ------------------------------------------------------------- 存储助手
@synchronized_storage
def _save(kind: str, obj_id: str, data: dict[str, Any]) -> str:
    """原子写入：临时文件 + os.replace，避免后台任务线程与请求线程
    并发读写时读到半截 JSON。"""
    if not valid_id(obj_id):
        raise ValueError("Invalid storage identifier")
    path = os.path.join(STORE[kind], f"{obj_id}.json")
    tmp = f"{path}.tmp-{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path


@synchronized_storage
def _load(kind: str, obj_id: str) -> dict[str, Any] | None:
    if not valid_id(obj_id):
        return None
    path = os.path.join(STORE[kind], f"{obj_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _list(kind: str) -> list[dict[str, Any]]:
    out = []
    for name in sorted(os.listdir(STORE[kind]), reverse=True):
        if name.endswith(".json"):
            rec = _load(kind, name[:-5])
            if rec:
                out.append(rec)
    return out


def api_error(code: str, message: str, details: Any = None, status: int = 400):
    return jsonify({"code": code, "message": message, "details": details,
                    "request_id": request.headers.get("X-Request-ID")
                    or uuid.uuid4().hex[:12]}), status


# --------------------------------------------------------- 身份与授权桩
def actor() -> dict[str, str]:
    """身份桩：生产环境替换为医院统一身份认证（SSO/OIDC/CAS）。

    演示用请求头 X-Demo-User / X-Demo-Role / X-Demo-Scope；服务账号与人员
    账号分开，内部接口用 X-Internal-Token，不接受演示身份。
    scope 代表科室/项目，是对象级权限（§8.1）的判定维度之一。
    """
    user = request.headers.get("X-Demo-User", "").strip() or "demo-user"
    role = request.headers.get("X-Demo-Role", "").strip() or "importer"
    if role not in ROLES:
        role = "importer"
    scope = request.headers.get("X-Demo-Scope", "").strip() or "neuro-epilepsy"
    return {"user": user, "role": role, "role_label": ROLES[role],
            "scope": scope, "service_account": False}


def audit(action: str, result: str, who: dict[str, str],
          versions: dict[str, str] | None = None, **kw: Any) -> str:
    try:
        ev = audit_log.record(actor=who["user"], role=who["role"], action=action,
                              result=result, client_ip=request.remote_addr or "",
                              versions=versions or versions_payload(), **kw)
        return ev.get("event_id", "")
    except AuditRejected as exc:
        audit_log.record(actor=who["user"], role=who["role"], action=action,
                         result="AUDIT_GUARD_TRIP", client_ip=request.remote_addr or "",
                         detail=str(exc)[:120])
        return ""


def versions_payload() -> dict[str, str]:
    return {"app_version": APP_VERSION,
            "schema_version": contract.SCHEMA_VERSION,
            "model_version": (predictor.meta.get("forward_model_version")
                              if predictor else "UNLOADED"),
            "mapping_version": ""}


def require_role(*roles: str):
    who = actor()
    if who["role"] not in roles and who["role"] != "admin":
        audit("AUTHZ_DENY", "DENY", who, object_type="role", code="E601",
              detail=f"需要 {'/'.join(roles)}，实际 {who['role']}")
        return None, api_error("E601", f"权限不足：需要 {'/'.join(ROLES[r] for r in roles)}",
                               {"your_role": ROLES[who["role"]]}, 403)
    return who, None


def require_batch_access(who: dict[str, str], rec: dict[str, Any]):
    """对象级权限（用户 × 科室/项目 × 数据批次）：不只判"是否登录"。"""
    if who["role"] == "admin":
        return None
    if rec.get("scope") and rec["scope"] == who.get("scope"):
        return None
    if rec.get("created_by") == who["user"]:
        return None
    if who["user"] in rec.get("shared_with", []):
        return None
    audit("AUTHZ_DENY", "DENY", who, object_type="import",
          object_id=rec.get("import_id", ""), code="E601",
          detail=f"对象级权限不足：批次 scope={rec.get('scope')} 请求 scope={who.get('scope')}")
    return api_error("E601", "越权访问：你不在该批次的授权范围内",
                     {"import_id": rec.get("import_id"),
                      "batch_scope": rec.get("scope"),
                      "your_scope": who.get("scope"),
                      "owner": rec.get("created_by")}, 403)


# ------------------------------------------------------------ 健康与元数据
@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok", "app_version": APP_VERSION})


@app.get("/readyz")
def readyz():
    return jsonify({"status": "ok" if predictor else "degraded",
                    "model_integrity": bool(predictor and getattr(predictor, "integrity", {}).get("ok")),
                    "audit_chain": audit_log.verify_chain()})


@app.get("/api/v1/meta/versions")
def meta_versions():
    who = actor()
    return jsonify({
        "banner": BANNER, "app_version": APP_VERSION,
        "schema_version": contract.SCHEMA_VERSION,
        "model_version": FORWARD_MODEL_VERSION,
        "reverse_model_version": REVERSE_MODEL_VERSION,
        "model_sha256": (predictor.integrity["sha256"] if predictor else {}),
        "signature_valid": bool(predictor),
        "research_only": True,
        "config": {k: v for k, v in CONFIG.items() if k != "limits"},
        "limits": CONFIG["limits"],
        "roles": ROLES,
        "actor": who,
        "retention_days": CONFIG["limits"]["retention_days"],
        "reject_codes": contract.REJECT_CODES,
        "fields": {"management": contract.MANAGEMENT_FIELDS,
                   "model": contract.MODEL_FIELDS,
                   "extension": contract.EXTENSION_FIELDS,
                   "reverse": contract.REVERSE_FIELDS},
        "channel2": {"enabled": CONFIG["channel2_envelope"],
                     "alg": "X25519+HKDF-SHA256+AES-256-GCM",
                     "sig_alg": "Ed25519"},
    })


@app.get("/api/v1/templates/<scenario>")
def template_csv(scenario: str):
    """下载 CSV 模板（列头 + 1 行示例）。用于院内自检列名与单位。"""
    if scenario not in ("forward", "reverse", "validation", "retrain"):
        return api_error("E102", "未知场景")
    cols = contract.required_columns("reverse" if scenario == "reverse" else "forward")
    cols += [f["name"] for f in contract.EXTENSION_FIELDS]
    if scenario == "reverse":
        cols += [f["name"] for f in contract.REVERSE_FIELDS if not f.get("required")]
    if scenario in ("validation", "retrain"):
        cols += [f["name"] for f in contract.VALIDATION_FIELDS]
        if scenario == "retrain":
            cols += [f["name"] for f in contract.RETRAIN_EXTRA_FIELDS]
    example = {
        "case_id": contract.make_case_id("DEMO-0001", b"hospital-side-salt"),
        "index_date": date.today().isoformat(),
        "epilepsy_duration_before_remission_years": "6.2",
        "seizure_free_months": "27", "age_at_onset": "9",
        "febrile_seizure_history": "0", "seizure_count_before_remission": "4",
        "self_limiting_syndrome": "0", "developmental_delay": "0",
        "eeg_epileptiform": "1",
        "relative_dose_reduction_pct": "20", "reduction_strategy": "stepwise",
        "asm_count": "1", "previous_asm_failure_count": "0",
        "asm_name": "LEV", "current_daily_dose_mg": "1000",
        "planned_reduction_pct": "20", "reduction_schedule": "stepwise",
        "reduction_steps": "4", "asm_polytherapy": "0",
        "previous_reduction_failure": "0",
        "follow_up_days": "730", "outcome_event": "", "censoring_status": "",
        "patient_level_group_id": "", "site_id": "",
    }
    lines = [",".join(cols)]
    if scenario in ("validation", "retrain"):
        example.update({"outcome_event": "0", "censoring_status": "none",
                        "patient_level_group_id": "g-0001"})
    lines.append(",".join(example.get(c, "") for c in cols))
    body = "\n".join(lines) + "\n"
    who = actor()
    audit("TEMPLATE_DOWNLOAD", "ALLOW", who, object_type="template",
          object_id=scenario)
    import io
    return send_file(io.BytesIO(body.encode("utf-8-sig")), mimetype="text/csv",
                     as_attachment=True,
                     download_name=f"template-{scenario}-schema-{contract.SCHEMA_VERSION}.csv")


# ------------------------------------------------------------- 导入（边界一）
_PURPOSE_TO_SCENARIO = {"prediction": "forward", "reverse": "reverse",
                        "validation": "validation", "retrain": "retrain"}


def _validate_for_scenario(columns, rows, scenario, encoding, batch_errors,
                           mapping=None, limits=None):
    """forward/reverse 走完整逐行校验；validation/retrain 先校验预测列，
    再检查 §6.4 的结局与随访必备列（缺失即整批 E101）。"""
    base = "reverse" if scenario == "reverse" else "forward"
    res = contract.validate(columns, rows, base, encoding, list(batch_errors),
                            mapping=mapping, limits=limits, today=date.today())
    if scenario in ("validation", "retrain"):
        have = set(columns)
        need = [f["name"] for f in contract.VALIDATION_FIELDS]
        if scenario == "retrain":
            need += [f["name"] for f in contract.RETRAIN_EXTRA_FIELDS
                     if f.get("required")]
        missing = [c for c in need if c not in have]
        if missing:
            from pipeline.contract import RowError, REJECT_CODES
            res.batch_errors.append(RowError(0, ",".join(missing), "E101",
                                             f"{REJECT_CODES['E101']}：{', '.join(missing)}"))
            res.codes_seen["E101"] = res.codes_seen.get("E101", 0) + 1
            res.ok = False
    return res


@app.post("/api/v1/imports/file")
def import_file():
    who, err = require_role("importer")
    if err:
        return err
    file = request.files.get("file")
    purpose = (request.form.get("purpose") or "prediction").strip()
    if purpose not in contract.PURPOSES:
        return api_error("E303", f"未知用途 {purpose}；可选 {'/'.join(contract.PURPOSES)}")
    if file is None or not file.filename:
        return api_error("E101", "缺少上传文件")
    raw = file.read()
    sha = contract.file_sha256(raw)

    import_id = f"imp-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    staging_name = f"{uuid.uuid4().hex}.csv"
    staging_path = os.path.join(STORE["staging"], staging_name)
    fd = os.open(staging_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(raw)
    os.chmod(staging_path, 0o600)

    scenario = _PURPOSE_TO_SCENARIO[purpose]
    columns, rows, encoding, batch_errors = contract.parse_raw(
        raw, declared_encoding=request.form.get("encoding"),
        limits=CONFIG["limits"])
    res = _validate_for_scenario(columns, rows, scenario, encoding, batch_errors,
                                 limits=CONFIG["limits"])

    stage = "READY" if res.ok else ("NEEDS_REVIEW" if res.total_rows else "FAILED")
    rec = {
        "import_id": import_id, "file_name": os.path.basename(file.filename),
        "sha256": sha, "bytes": len(raw), "purpose": purpose, "scenario": scenario,
        "encoding": encoding, "columns": columns, "total_rows": res.total_rows,
        "runnable_rows": res.runnable_rows, "rejected_rows": res.rejected_rows,
        "stage": stage, "validation": res.to_dict(),
        "proposed_mapping": contract.propose_mapping(columns, scenario),
        "mapping_version": None, "confirmed": False,
        "created_at": time.time(), "created_by": who["user"],
        "scope": who["scope"],
        "shared_with": [], "staging_path": staging_path,
        "retained_until": time.time()
        + CONFIG["limits"]["retention_days"] * 86400,
        "channel": "onprem",
    }
    _save("imports", import_id, rec)
    audit("IMPORT_FILE", "ALLOW" if res.ok else "NEEDS_REVIEW", who,
          object_type="import", object_id=import_id, purpose=purpose,
          code="" if res.ok else (res.batch_errors[0].code if res.batch_errors else ""),
          detail=f"sha={sha[:16]} rows={res.total_rows} runnable={res.runnable_rows}")
    return jsonify({"import_id": import_id, "file_sha256": sha, "stage": stage,
                    "validation": rec["validation"],
                    "proposed_mapping": rec["proposed_mapping"],
                    "purpose": purpose, "scenario": scenario,
                    "retained_until": rec["retained_until"],
                    "created_by": rec["created_by"], "scope": rec["scope"],
                    "banner": BANNER}), 201


@app.post("/api/v1/imports/link")
def import_link():
    """§5.3：白名单默认空 → 一律拒绝并记安全审计（含 SSRF 防护）。"""
    who, err = require_role("importer")
    if err:
        return err
    body = request.get_json(silent=True) or {}
    url = (body.get("source_url") or "").strip()
    allowed = CONFIG["link_whitelist"]
    reason = _link_check(url, allowed)
    if reason:
        audit("IMPORT_LINK", "DENY", who, object_type="link", code="E503",
              detail=reason[:160])
        return api_error("E503", f"链接被拒绝：{reason}",
                         {"whitelist": allowed, "hint":
                          "首版建议改用拖入上传；如需链接入口，请由医院信息科把内网 "
                          "HTTPS 文件服务域名逐个加入白名单"}, 403)
    audit("IMPORT_LINK", "ALLOW", who, object_type="link", detail="白名单命中，转服务端读取")
    return jsonify({"import_id": None, "note": "白名单命中后由服务端专用身份读取，"
                    "随后走与拖入完全相同的预检链（本演示环境未连院内文件服务）"}), 202


def _link_check(url: str, whitelist: list[str]) -> str:
    import ipaddress
    import socket
    from urllib.parse import urlparse
    if not url:
        return "source_url 为空"
    p = urlparse(url)
    if p.scheme not in ("https",):
        return f"仅允许 https（收到 {p.scheme or 'none'}）"
    if p.username or p.password:
        return "URL 内不得携带用户名/密码"
    host = (p.hostname or "").lower()
    if not host:
        return "缺少主机名"
    if whitelist and not any(host == w or host.endswith("." + w) for w in whitelist):
        return f"主机 {host} 不在医院批准的内网白名单"
    if not whitelist:
        return "白名单为空（D4 默认关闭链接入口）"
    try:
        infos = socket.getaddrinfo(host, p.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return "域名解析失败"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            # 院内文件服务本身就是内网地址，故仅在未显式白名单批准时阻断
            if host not in whitelist:
                return f"目标为内网/元数据地址 {ip}，疑似 SSRF"
    return ""


@app.get("/api/v1/imports")
def list_imports():
    who, err = require_role("importer", "reviewer", "runner", "viewer", "exporter")
    if err:
        return err
    items = []
    for rec in _list("imports"):
        if require_batch_access(who, rec):
            continue
        items.append({k: rec.get(k) for k in
                      ("import_id", "file_name", "purpose", "scenario", "stage",
                       "total_rows", "runnable_rows", "rejected_rows", "sha256",
                       "created_at", "created_by", "mapping_version", "confirmed",
                       "retained_until")})
    return jsonify({"items": items, "count": len(items)})


@app.get("/api/v1/imports/<import_id>/validation")
def get_validation(import_id: str):
    who, err = require_role("importer", "reviewer", "runner", "viewer")
    if err:
        return err
    rec = _load("imports", import_id)
    if not rec:
        return api_error("E102", "导入批次不存在", None, 404)
    denied = require_batch_access(who, rec)
    if denied:
        return denied
    audit("VIEW_VALIDATION", "ALLOW", who, object_type="import", object_id=import_id)
    return jsonify({
        "import_id": import_id, "stage": rec["stage"], "purpose": rec["purpose"],
        "scenario": rec["scenario"], "file_sha256": rec["sha256"],
        "columns": rec["columns"], "validation": rec["validation"],
        "proposed_mapping": rec["proposed_mapping"],
        "mapping_version": rec["mapping_version"], "confirmed": rec["confirmed"],
        "retained_until": rec["retained_until"],
        "versions": {"schema_version": contract.SCHEMA_VERSION,
                     "model_version": FORWARD_MODEL_VERSION,
                     "mapping_version": rec["mapping_version"] or ""},
    })


@app.post("/api/v1/imports/<import_id>/mappings")
def save_mapping(import_id: str):
    who, err = require_role("reviewer")
    if err:
        return err
    rec = _load("imports", import_id)
    if not rec:
        return api_error("E102", "导入批次不存在", None, 404)
    denied = require_batch_access(who, rec)
    if denied:
        return denied
    if rec.get("confirmed"):
        return api_error("E301", "批次已锁定；修改映射须重新导入", None, 409)
    if rec.get("stage") == "EXPIRED":
        return api_error("E302", "批次已到期，须重新导入")
    body = request.get_json(silent=True) or {}
    mapping = body.get("mapping") or {}
    if not isinstance(mapping, dict) or not mapping:
        return api_error("E301", "mapping 不能为空")
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in mapping.items()):
        return api_error("E301", "映射列名必须为字符串")
    if any(k not in rec["columns"] for k in mapping) or len(set(mapping.values())) != len(mapping):
        return api_error("E301", "映射来源必须存在，且多个来源不得指向同一标准字段")
    specs = contract.spec_by_name(rec["scenario"] if rec["scenario"] in ("forward", "reverse") else "forward")
    unknown = sorted({v for v in mapping.values() if v not in specs})
    if unknown:
        return api_error("E301", f"映射目标不是契约字段：{', '.join(unknown)}")
    missing = [n for n in contract.required_columns(rec["scenario"])
               if n not in set(mapping.values())]
    version = (body.get("mapping_version")
               or f"map-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}")
    if not valid_id(version):
        return api_error("E301", "mapping_version 仅允许字母、数字、下划线和连字符")
    if _load("mappings", version):
        return api_error("E301", "映射版本已存在，不得覆盖", None, 409)
    raw = open(rec["staging_path"], "rb").read()
    columns, rows, encoding, errors = contract.parse_raw(raw, limits=CONFIG["limits"])
    validation = _validate_for_scenario(columns, rows, rec["scenario"], encoding, errors,
                                        mapping=mapping, limits=CONFIG["limits"])
    record = {
        "mapping_version": version, "import_id": import_id, "mapping": mapping,
        "unmapped_required": missing, "unit_rules": body.get("unit_rules", ""),
        "null_rules": body.get("null_rules", "空值不得自动改为 0；未提及不得当作阴性"),
        "index_rule": body.get("index_rule", "以病历与审核人确认的首次实际减药日为准"),
        "created_by": who["user"], "created_at": time.time(),
        "status": "COMPLETE" if not missing else "INCOMPLETE",
    }
    _save("mappings", version, record)
    rec.update({"mapping_version": version, "proposed_mapping": {
        "mapping": mapping, "unmapped_required": missing,
        "status": record["status"], "ambiguous": [], "unknown_columns": []}})
    rec.update({"validation": validation.to_dict(), "runnable_rows": validation.runnable_rows,
                "rejected_rows": validation.rejected_rows,
                "stage": "READY" if validation.ok else "NEEDS_REVIEW"})
    _save("imports", import_id, rec)
    audit("MAP", "ALLOW", who, object_type="mapping", object_id=version,
          versions={**versions_payload(), "mapping_version": version},
          detail=f"mapped={len(mapping)} missing={len(missing)}")
    return jsonify(record)


@app.post("/api/v1/imports/<import_id>/confirm")
def confirm_import(import_id: str):
    who, err = require_role("reviewer")
    if err:
        return err
    rec = _load("imports", import_id)
    if not rec:
        return api_error("E102", "导入批次不存在", None, 404)
    denied = require_batch_access(who, rec)
    if denied:
        return denied
    if rec.get("stage") == "EXPIRED":
        return api_error("E302", "批次已到期，须重新导入")
    body = request.get_json(silent=True) or {}
    version = body.get("mapping_version") or rec.get("mapping_version")
    maprec = _load("mappings", version) if version else None
    if not maprec:
        return api_error("E301", "映射版本未确认或已被覆盖：请先由审核员建立映射")
    if version != rec.get("mapping_version") or maprec.get("import_id") != import_id:
        return api_error("E301", "映射版本与当前批次不一致")
    if body.get("purpose", rec["purpose"]) != rec["purpose"]:
        return api_error("E303", "确认用途必须与导入用途一致", None, 403)
    if maprec["status"] != "COMPLETE":
        return api_error("E301", "映射不完整",
                         {"unmapped_required": maprec["unmapped_required"]})
    if rec["validation"].get("batch_errors"):
        return api_error("E302", "存在文件级拒绝原因，须修正后重新导入",
                         {"codes_seen": rec["validation"]["codes_seen"]})
    if rec["validation"]["runnable_rows"] == 0:
        return api_error("E302", "无可运行行，不能确认运行",
                         {"codes_seen": rec["validation"]["codes_seen"]})
    rec.update({"mapping_version": version, "confirmed": True,
                "confirmed_by": who["user"], "confirmed_at": time.time(),
                "purpose_confirmed": body.get("purpose") or rec["purpose"],
                "ethics_ref": body.get("ethics_ref", ""),
                "index_rule": maprec.get("index_rule", ""),
                "stage": "READY", "note": body.get("note", "")})
    _save("imports", import_id, rec)
    audit("CONFIRM", "ALLOW", who, object_type="import", object_id=import_id,
          purpose=rec["purpose_confirmed"],
          versions={**versions_payload(), "mapping_version": version},
          detail=f"ethics={rec['ethics_ref'] or 'n/a'} rows={rec['runnable_rows']}")
    return jsonify({"import_id": import_id, "stage": rec["stage"],
                    "mapping_version": version,
                    "confirmed_by": rec["confirmed_by"],
                    "runnable_rows": rec["runnable_rows"]})


# --------------------------------------------------------- 推理（边界二）
def _infer(payload: dict[str, Any]) -> dict[str, Any]:
    """院内推理适配层：仅接受固定 schema，逐行返回状态，不回显原始病历。"""
    if predictor is None:
        return {"ok": False, "code": "E402",
                "message": contract.REJECT_CODES["E402"], "rows": []}
    if payload.get("schema_version") != contract.SCHEMA_VERSION:
        return {"ok": False, "code": "E301",
                "message": f"schema_version 不匹配：平台 {contract.SCHEMA_VERSION}",
                "rows": []}
    scenario = payload.get("scenario", "forward")
    records = payload.get("records", [])
    include_details = payload.get("batch_id") == "single" and len(records) == 1
    if scenario == "reverse":
        rows = predictor.reverse_rows(records, float(payload.get("target_risk", 0.3)),
                                      include_details=include_details)
    else:
        rows = predictor.predict_rows(records, include_details=include_details)
    ok = sum(1 for r in rows if r["status"] == "OK")
    return {"ok": True, "rows": rows, "counts": {"total": len(rows), "ok": ok,
            "rejected": len(rows) - ok},
            "model_version": rows[0]["model_version"] if rows else FORWARD_MODEL_VERSION,
            "integrity": predictor.integrity}


def _call_boundary(payload: dict[str, Any]) -> dict[str, Any]:
    """边界二调用：默认同机进程内调用；CHANNEL2=1 时改走信封加密的 HTTP 调用。"""
    if not CONFIG["channel2_envelope"]:
        return _infer(payload)
    import urllib.request
    ks = KeyStore(STORE["keys"])
    try:
        model_key = ks.load("model")          # 收件方（模型服务）公钥
        sign_key = ks.load("platform_sign")   # 发件方（平台）签名私钥
    except EnvelopeError as exc:
        return {"ok": False, "code": "E402", "message": str(exc), "rows": []}
    envelope = seal(json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                    recipient_pub=model_key["public"],
                    signing_priv=sign_key["private"], kid=sign_key["kid"])
    req = urllib.request.Request(
        f"http://127.0.0.1:{app.config['PORT']}/internal/v1/infer-batch",
        data=json.dumps(envelope).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "X-Internal-Token": INTERNAL_TOKEN,
                 "X-Sender-Fingerprint": fingerprint(sign_key["public"])},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"ok": False, "code": "E402", "message": f"边界二调用失败：{exc}",
                "rows": []}


@app.post("/internal/v1/infer-batch")
def internal_infer():
    """边界二：不对外暴露。仅接受服务身份令牌；CHANNEL2 时还须信封合法。"""
    if request.headers.get("X-Internal-Token") != INTERNAL_TOKEN:
        audit_log.record(actor="anonymous", role="none", action="INTERNAL_DENY",
                         result="DENY", code="E601", client_ip=request.remote_addr or "")
        return api_error("E601", "非服务身份：/internal/v1 不接受浏览器或外部调用",
                         None, 403)
    body = request.get_json(silent=True) or {}
    if CONFIG["channel2_envelope"]:
        ks = KeyStore(STORE["keys"])
        try:
            model_key = ks.load("model")
            sign_key = ks.load_public("platform_sign")
            plaintext = open_envelope(body, recipient_priv=model_key["private"],
                                      verify_pub=sign_key["public"],
                                      nonce_cache=nonce_cache)
            payload = json.loads(plaintext.decode("utf-8"))
        except (EnvelopeError, json.JSONDecodeError, ValueError) as exc:
            return api_error("E601", f"信封校验失败：{exc}", None, 403)
        audit_log.record(actor="platform-service", role="service",
                         action="INFER_BATCH", result="ALLOW", code="",
                         client_ip=request.remote_addr or "",
                         kid=model_key["kid"],
                         key_fingerprint=model_key["key_fingerprint"],
                         detail=f"batch={payload.get('batch_id')} rows={len(payload.get('records', []))}")
    else:
        payload = body
        audit_log.record(actor="platform-service", role="service",
                         action="INFER_BATCH_INPROC", result="ALLOW",
                         client_ip=request.remote_addr or "",
                         detail=f"batch={payload.get('batch_id')} rows={len(payload.get('records', []))}")
    result = _infer(payload)
    return jsonify(result)


# -------------------------------------------------------------- 运行
def _execute_run(run_id: str) -> None:
    run = _load("runs", run_id)
    rec = _load("imports", run["import_id"])
    who = run["created_by"], "runner"
    try:
        with _RUN_STATE_LOCK:
            run = _load("runs", run_id)
            if run.get("cancel_requested"):
                run.update({"status": "CANCELLED", "finished_at": time.time()})
            else:
                run.update({"status": "RUNNING", "started_at": time.time()})
            _save("runs", run_id, run)
        if run["status"] == "CANCELLED":
            return

        raw = open(rec["staging_path"], "rb").read()
        columns, rows, encoding, batch_errors = contract.parse_raw(
            raw, limits=CONFIG["limits"])
        if batch_errors:
            run.update({"status": "FAILED", "finished_at": time.time(),
                        "error": {"code": batch_errors[0].code,
                                  "message": batch_errors[0].message}})
            _save("runs", run_id, run)
            return
        maprec = _load("mappings", run["mapping_version"])
        records = contract.clean_records(columns, rows, rec["scenario"],
                                         maprec["mapping"])
        payload = {"batch_id": run_id, "schema_version": contract.SCHEMA_VERSION,
                   "model_version": run["model_version"],
                   "mapping_version": rec["mapping_version"],
                   "scenario": run["scenario"],
                   "target_risk": run.get("target_risk", 0.3),
                   "records": records}
        out = _call_boundary(payload)
        if not out.get("ok"):
            run.update({"status": "FAILED", "finished_at": time.time(),
                        "error": {"code": out.get("code", "E402"),
                                  "message": out.get("message", "推理失败")}})
            _save("runs", run_id, run)
            audit_log.record(actor=who[0], role=who[1], action="RUN", result="FAIL",
                             object_type="run", object_id=run_id,
                             code=out.get("code", "E402"),
                             client_ip=run.get("client_ip", ""),
                             versions=versions_payload())
            return
        rows_out = out["rows"]
        counts = out.get("counts", {})
        # 逐行拒绝（E401/E403 等契约或支持范围原因）属于"运行完成、部分行被拒"，
        # 不是运行失败；只有推理层整体报错或零行产出才算 FAILED。
        if not rows_out:
            status = "FAILED"
        elif counts.get("rejected", 0) == 0:
            status = "COMPLETED"
        else:
            status = "PARTIAL_FAILED"
        run.update({"status": status, "finished_at": time.time(),
                    "counts": {"submitted": len(records),
                               "precheck_rejected": rec["rejected_rows"],
                               **counts},
                    "model_version_returned": out.get("model_version"),
                    "integrity": out.get("integrity"),
                    "boundary": "envelope-http" if CONFIG["channel2_envelope"]
                    else "in-process"})
        with _RUN_STATE_LOCK:
            latest = _load("runs", run_id)
            if latest.get("cancel_requested"):
                run.update({"status": "CANCELLED", "cancel_requested": True})
            else:
                _save("results", run_id, {"run_id": run_id, "rows": rows_out,
                                          "generated_at": time.time()})
            _save("runs", run_id, run)
        audit_log.record(actor=who[0], role=who[1], action="RUN", result="ALLOW",
                         object_type="run", object_id=run_id,
                         purpose=rec["purpose"], client_ip=run.get("client_ip", ""),
                         versions={**versions_payload(),
                                   "model_version": run["model_version"],
                                   "mapping_version": rec["mapping_version"]},
                         detail=f"status={status} ok={counts.get('ok')} "
                                f"rejected={counts.get('rejected')}")
    except Exception as exc:                      # 兜底：错误体不含病历原文
        run.update({"status": "FAILED", "finished_at": time.time(),
                    "error": {"code": "E402", "message": f"运行异常：{type(exc).__name__}"}})
        _save("runs", run_id, run)


@app.post("/api/v1/runs")
@serialized_submission
def create_run():
    who, err = require_role("runner")
    if err:
        return err
    body = request.get_json(silent=True) or {}
    import_id = body.get("import_id", "")
    rec = _load("imports", import_id)
    if not rec:
        return api_error("E102", "导入批次不存在", None, 404)
    denied = require_batch_access(who, rec)
    if denied:
        return denied
    if rec.get("stage") == "EXPIRED":
        return api_error("E302", "批次已到期，须重新导入")
    if not rec.get("confirmed"):
        return api_error("E302", contract.REJECT_CODES["E302"],
                         {"hint": "请由审核员完成映射并 confirm 后再运行"})
    scenario = body.get("scenario") or rec["scenario"]
    if rec["purpose"] in ("validation", "retrain"):
        return api_error("E303", "该批次用途为验证/重训，不得进入预测运行队列",
                         {"purpose": rec["purpose"]}, 403)
    expected = {"prediction": "forward", "reverse": "reverse"}.get(rec["purpose"])
    if expected and scenario != expected:
        return api_error("E303", f"{contract.REJECT_CODES['E303']}：批次用途 "
                                 f"{rec['purpose']} 与运行场景 {scenario} 不一致",
                         None, 403)
    target_risk = parse_target_risk(body)
    if target_risk is None:
        return api_error("E201", "target_risk 必须为 (0,1] 内的有限数值")
    if scenario == "reverse":
        if not CONFIG["reverse_enabled"]:
            return api_error("E403", "逆向设计已关闭：未经院内独立验证前不得运行", None, 403)
        if not (0.0 < target_risk <= 1.0):
            return api_error("E201", "target_risk 必须在 (0,1] 区间")

    idem = request.headers.get("Idempotency-Key") or body.get("idempotency_key")
    if idem:
        for prev in _list("runs"):
            if (prev.get("idempotency_key") == idem
                    and prev.get("created_by") == who["user"]
                    and prev.get("scope") == who["scope"]):
                if any(prev.get(k) != v for k, v in {"import_id": import_id,
                        "scenario": scenario, "target_risk": target_risk}.items()):
                    return api_error("E302", "同一幂等键不可用于不同请求", None, 409)
                return jsonify({**prev, "idempotent_replay": True}), 200

    model_version = (REVERSE_MODEL_VERSION if scenario == "reverse"
                     else FORWARD_MODEL_VERSION)
    run_id = f"run-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    run = {"run_id": run_id, "import_id": import_id, "scenario": scenario,
           "purpose": rec["purpose"], "model_version": model_version,
           "target_risk": target_risk, "status": "QUEUED",
           "created_at": time.time(), "created_by": who["user"],
           "scope": who["scope"],
           "client_ip": request.remote_addr or "", "idempotency_key": idem or "",
           "mapping_version": rec["mapping_version"], "counts": {},
           "cancel_requested": False,
           "versions": {**versions_payload(), "model_version": model_version,
                        "mapping_version": rec["mapping_version"]}}
    _save("runs", run_id, run)
    audit("RUN_SUBMIT", "ALLOW", who, object_type="run", object_id=run_id,
          purpose=rec["purpose"],
          versions=run["versions"], detail=f"rows={rec['runnable_rows']}")
    threading.Thread(target=_execute_run, args=(run_id,), daemon=True).start()
    return jsonify({"run_id": run_id, "status": "QUEUED",
                    "model_version": model_version,
                    "state_machine": ["QUEUED", "RUNNING", "COMPLETED",
                                      "PARTIAL_FAILED", "FAILED", "CANCELLED"],
                    "banner": BANNER}), 202


@app.get("/api/v1/runs")
def list_runs():
    who, err = require_role("runner", "viewer", "reviewer", "exporter")
    if err:
        return err
    items = []
    for run in _list("runs"):
        rec = _load("imports", run["import_id"]) or {}
        if require_batch_access(who, rec):
            continue
        items.append({k: run.get(k) for k in
                      ("run_id", "import_id", "scenario", "status", "counts",
                       "model_version", "created_at", "created_by", "boundary",
                       "finished_at", "error")})
    return jsonify({"items": items, "count": len(items)})


@app.get("/api/v1/runs/<run_id>")
def get_run(run_id: str):
    who, err = require_role("runner", "viewer", "reviewer", "exporter")
    if err:
        return err
    run = _load("runs", run_id)
    if not run:
        return api_error("E102", "任务不存在", None, 404)
    rec = _load("imports", run["import_id"]) or {}
    denied = require_batch_access(who, rec)
    if denied:
        return denied
    return jsonify({**run, "banner": BANNER,
                    "support_range": (predictor.meta.get("support_range")
                                      if predictor else {})})


@app.post("/api/v1/runs/<run_id>/cancel")
def cancel_run(run_id: str):
    who, err = require_role("runner")
    if err:
        return err
    run = _load("runs", run_id)
    if not run:
        return api_error("E102", "任务不存在", None, 404)
    denied = require_batch_access(who, _load("imports", run["import_id"]) or {})
    if denied:
        return denied
    with _RUN_STATE_LOCK:
        run = _load("runs", run_id)
        if run["status"] in ("COMPLETED", "PARTIAL_FAILED", "FAILED", "CANCELLED"):
            return api_error("E302", f"任务已终态 {run['status']}，不可取消")
        run["cancel_requested"] = True
        _save("runs", run_id, run)
    audit("CANCEL", "ALLOW", who, object_type="run", object_id=run_id,
          detail=f"previous_status={run['status']}")
    return jsonify({"run_id": run_id, "cancel_requested": True})


@app.get("/api/v1/runs/<run_id>/results")
def get_results(run_id: str):
    who, err = require_role("viewer", "reviewer", "exporter")
    if err:
        return err
    run = _load("runs", run_id)
    if not run:
        return api_error("E102", "任务不存在", None, 404)
    rec = _load("imports", run["import_id"]) or {}
    denied = require_batch_access(who, rec)
    if denied:
        return denied
    if run["status"] not in ("COMPLETED", "PARTIAL_FAILED"):
        return jsonify({"run_id": run_id, "status": run["status"], "rows": [],
                        "note": "任务尚未产出结果；拒绝时不返回默认风险值"})
    data = _load("results", run_id) or {"rows": []}
    page = max(1, int(request.args.get("page", 1)))
    size = min(500, max(1, int(request.args.get("page_size", 50))))
    rows = data["rows"]
    audit("VIEW_RESULT", "ALLOW", who, object_type="run", object_id=run_id,
          versions=run.get("versions"), detail=f"page={page} size={size}")
    return jsonify({
        "run_id": run_id, "status": run["status"], "scenario": run["scenario"],
        "page": page, "page_size": size, "total": len(rows),
        "rows": rows[(page - 1) * size: page * size],
        "counts": run.get("counts", {}), "versions": run.get("versions", {}),
        "banner": BANNER, "research_only": True,
        "support_note": ("模型基于教学合成数据；真实队列性能须由院内独立验证给出，"
                         "本页数值不代表临床性能"),
        "integrity": run.get("integrity"), "boundary": run.get("boundary"),
    })


@app.post("/api/v1/runs/<run_id>/exports")
def create_export(run_id: str):
    who, err = require_role("exporter")
    if err:
        return err
    run = _load("runs", run_id)
    if not run:
        return api_error("E102", "任务不存在", None, 404)
    rec = _load("imports", run["import_id"]) or {}
    denied = require_batch_access(who, rec)
    if denied:
        return denied
    body = request.get_json(silent=True) or {}
    fmt = body.get("format", "csv")
    if fmt not in ("csv", "xlsx", "json"):
        return api_error("E202", "format 仅支持 csv/xlsx/json")
    data = _load("results", run_id)
    if not data or not data.get("rows"):
        return api_error("E302", "无可导出结果")
    # 先记审计再落盘：导出是唯一的数据出域动作，必须留痕
    ev_id = audit("EXPORT", "ALLOW", who, object_type="run", object_id=run_id,
                  purpose=body.get("purpose", "internal_research"),
                  versions=run.get("versions"),
                  detail=f"format={fmt} rows={len(data['rows'])}")
    out = exporter.export(data["rows"], out_dir=STORE["exports"], run_id=run_id,
                          scenario=run["scenario"], fmt=fmt,
                          purpose=body.get("purpose", "internal_research"),
                          actor=who["user"], versions=run.get("versions", {}),
                          event_id=ev_id)
    return jsonify({"file_name": out["file_name"], "bytes": out["bytes"],
                    "download_url": f"/api/v1/exports/download?name={out['file_name']}",
                    "meta": out["meta"], "banner": BANNER,
                    "note": "导出落盘于院内受控目录；未提供院外导出通道"})


@app.get("/api/v1/exports/download")
def download_export():
    who, err = require_role("exporter", "viewer")
    if err:
        return err
    name = os.path.basename(request.args.get("name", ""))   # 防路径穿越
    path = os.path.join(STORE["exports"], name)
    if not name or not os.path.exists(path):
        return api_error("E102", "导出文件不存在", None, 404)
    if not name.endswith((".csv", ".xlsx", ".json")) or name.endswith(".meta.json"):
        return api_error("E102", "不可下载的文件类型", None, 404)
    meta_path = path + ".meta.json"
    if not os.path.isfile(meta_path):
        return api_error("E601", "导出文件缺少批次授权记录", None, 403)
    with open(meta_path, encoding="utf-8") as fh:
        meta = json.load(fh)
    run = _load("runs", meta.get("run_id")) or {}
    rec = _load("imports", run.get("import_id")) or {}
    denied = require_batch_access(who, rec)
    if denied:
        return denied
    audit("EXPORT_DOWNLOAD", "ALLOW", who, object_type="export", object_id=name)
    return send_from_directory(STORE["exports"], name, as_attachment=True)


# ------------------------------------------------------------ 单例录入
@app.post("/api/v1/predictions")
def single_prediction():
    """单例结构化录入：与批量共用同一字段校验与推理逻辑（§5.1）。"""
    who, err = require_role("viewer", "importer", "runner")
    if err:
        return err
    body = request.get_json(silent=True) or {}
    scenario = body.get("scenario", "forward")
    if scenario not in ("forward", "reverse"):
        return api_error("E202", "scenario 仅支持 forward/reverse")
    target_risk = parse_target_risk(body)
    if target_risk is None:
        return api_error("E201", "target_risk 必须为 (0,1] 内的有限数值")
    fields = body.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        return api_error("E101", "fields 不能为空")
    if scenario == "reverse" and not CONFIG["reverse_enabled"]:
        return api_error("E403", "逆向设计已关闭：未经院内独立验证前不得运行", None, 403)
    row = {"__line__": 0, **{k: ("" if v is None else str(v)) for k, v in fields.items()}}
    record, errors = contract.coerce_row(row, {k: k for k in fields}, scenario,
                                         date.today())
    if errors:
        audit("PREDICT_SINGLE", "DENY", who, object_type="prediction",
              code=errors[0].code, detail=f"codes={[e.code for e in errors]}")
        return jsonify({"status": "REJECTED", "risk_730d": None,
                        "reject_codes": sorted({e.code for e in errors}),
                        "errors": [e.to_dict() for e in errors],
                        "research_only": True, "banner": BANNER,
                        "note": "字段不齐或非法时拒绝推理，不返回部分结果"}), 422
    out = _call_boundary({"batch_id": "single", "schema_version": contract.SCHEMA_VERSION,
                  "model_version": FORWARD_MODEL_VERSION, "scenario": scenario,
                  "target_risk": target_risk,
                  "records": [record]})
    if not out.get("ok"):
        return api_error(out.get("code", "E402"), out.get("message", "推理失败"),
                         None, 503)
    row_out = out["rows"][0]
    audit("PREDICT_SINGLE", "ALLOW" if row_out["status"] == "OK" else "DENY", who,
          object_type="prediction", code=",".join(row_out.get("reject_codes") or []),
          versions=versions_payload())
    return jsonify({**row_out, "scenario": scenario, "banner": BANNER})


# ---------------------------------------------------------- 演示数据生成
@app.get("/api/v1/demo/csv")
def demo_csv():
    """生成教学合成 CSV 供院内联调；含 flavor=bad 时故意植入各类违规行。

    明确标注：合成数据，不含任何真实病例。
    """
    import io
    import numpy as np
    from pipeline.model import synthesize, synthesize_with_reduction

    scenario = request.args.get("scenario", "forward")
    flavor = request.args.get("flavor", "ok")
    n = min(2000, max(1, int(request.args.get("n", 30))))
    DEMO_SALT = b"hospital-side-demo-salt"   # 真实环境由医院自持盐值
    X, _ = synthesize(n, seed=4242)
    rng = np.random.default_rng(7)

    cols = contract.required_columns("reverse" if scenario == "reverse" else "forward")
    cols += [f["name"] for f in contract.EXTENSION_FIELDS]
    reduction_col = None
    if scenario == "reverse":
        reduction_col = synthesize_with_reduction(n, seed=4343)[0][:, -1]
        cols += [f["name"] for f in contract.REVERSE_FIELDS]
    cols = list(dict.fromkeys(cols))

    def row_for(i: int, **override: str) -> dict[str, str]:
        x = X[i % len(X)]
        vals = {
            "case_id": contract.make_case_id(f"DEMO-{i:05d}", DEMO_SALT),
            "index_date": date.today().isoformat(),
            "epilepsy_duration_before_remission_years": f"{x[0]:.2f}",
            "seizure_free_months": f"{x[1]:.1f}",
            "age_at_onset": f"{x[2]:.1f}",
            "febrile_seizure_history": str(int(x[3])),
            "seizure_count_before_remission": str(int(x[4])),
            "self_limiting_syndrome": str(int(x[5])),
            "developmental_delay": str(int(x[6])),
            "eeg_epileptiform": str(int(x[7])),
            "relative_dose_reduction_pct": f"{rng.uniform(5, 45):.1f}",
            "reduction_strategy": "stepwise",
            "asm_count": "1",
            "previous_asm_failure_count": str(int(rng.integers(0, 3))),
        }
        if scenario == "reverse":
            vals.update({
                "asm_name": "LEV",
                "current_daily_dose_mg": f"{float(rng.integers(300, 2000)):.1f}",
                "planned_reduction_pct": f"{reduction_col[i % len(reduction_col)]:.1f}",
                "reduction_schedule": "stepwise", "reduction_steps": "4",
                "asm_polytherapy": "0", "previous_reduction_failure": "0",
            })
        vals.update(override)
        return vals

    records = [row_for(i) for i in range(n)]

    if flavor == "bad":
        # 预检演示：每类违规一行，便于逐条核对拒绝码（§7.3）
        first = records[0]
        records += [
            {**first},                                                   # E103 重复 case_id
            row_for(1, seizure_free_months="9999"),                      # E201 越界
            row_for(2, index_date="2026-13-45"),                         # E104 日期非法
            row_for(3, eeg_epileptiform=""),                             # E204 必填为空
            row_for(4, developmental_delay="2"),                         # E203 非法枚举
            row_for(5, seizure_count_before_remission="四次"),            # E202 类型非法
        ]
        cols = cols + ["patient_name"]                                   # E103 黑名单列
        for r in records[:-1]:
            r.setdefault("patient_name", "")
        records[-1]["patient_name"] = "张某某"

    body = "\n".join([",".join(cols)]
                     + [",".join(str(r.get(c, "")) for c in cols) for r in records]) + "\n"
    audit("DEMO_CSV", "ALLOW", actor(), object_type="demo", object_id=flavor,
          detail=f"scenario={scenario} n={len(records)} synthetic=true")
    return send_file(io.BytesIO(body.encode("utf-8-sig")), mimetype="text/csv",
                     as_attachment=True,
                     download_name=f"demo-{scenario}-{flavor}-{len(records)}.csv")


# -------------------------------------------------------------- 审计与自检
@app.get("/api/v1/audit")
def get_audit():
    who, err = require_role("admin")
    if err:
        return err
    limit = min(500, max(1, int(request.args.get("limit", 30))))
    return jsonify({"events": audit_log.read(limit), "count": limit,
                    "chain": audit_log.verify_chain(),
                    "daily_digest": audit_log.daily_digest(),
                    "note": "审计不含 CSV 正文/病历原文/令牌；命中红线字段会被拒写"})


@app.post("/api/v1/crypto/selftest")
def crypto_selftest():
    who, err = require_role("admin")
    if err:
        return err
    ks = KeyStore(STORE["keys"])
    if not ks.exists("model") or not ks.exists("platform_sign"):
        return jsonify({"channel2_enabled": CONFIG["channel2_envelope"],
                        "keys_present": False,
                        "next_step": "医院侧执行 python -m gateway.keygen --dir var/keys"}), 200
    model_key = ks.load("model")
    sign_key = ks.load("platform_sign")
    msg = json.dumps({"batch_id": "selftest", "records": []}).encode("utf-8")
    env = seal(msg, recipient_pub=model_key["public"],
               signing_priv=sign_key["private"], kid=sign_key["kid"])
    cache = NonceCache()
    plain = open_envelope(env, recipient_priv=model_key["private"],
                          verify_pub=sign_key["public"], nonce_cache=cache)
    replay_blocked = False
    try:
        open_envelope(env, recipient_priv=model_key["private"],
                      verify_pub=sign_key["public"], nonce_cache=cache)
    except EnvelopeError:
        replay_blocked = True
    audit("CRYPTO_SELFTEST", "ALLOW", who, object_type="crypto",
          kid=model_key["kid"], key_fingerprint=model_key["key_fingerprint"],
          detail=f"channel2={CONFIG['channel2_envelope']} roundtrip={plain == msg}")
    return jsonify({
        "channel2_enabled": CONFIG["channel2_envelope"], "keys_present": True,
        "alg": "X25519+HKDF-SHA256+AES-256-GCM", "sig_alg": "Ed25519",
        "roundtrip_ok": plain == msg, "replay_blocked": replay_blocked,
        "kid": {"model": model_key["kid"], "platform_sign": sign_key["kid"]},
        "key_fingerprint": {"model": model_key["key_fingerprint"],
                            "platform_sign": sign_key["key_fingerprint"]},
        "note": ("仅显示公钥指纹；私钥不出院，课题组零持有"
                 if not CONFIG["channel2_envelope"] else
                 "通道2已启用：边界二报文为信封密文，需服务令牌 + 合法签名"),
    })


# ---------------------------------------------------------------- 方案文档
@app.get("/plan")
def plan_doc():
    path = os.path.join(ROOT, "docs_plan.md")
    if not os.path.exists(path):
        return api_error("E102", "方案文档缺失", None, 404)
    audit("VIEW_PLAN", "ALLOW", actor(), object_type="doc", object_id="plan")
    return send_file(path, mimetype="text/markdown; charset=utf-8",
                     as_attachment=request.args.get("download") == "1",
                     download_name="医院院内部署与CSV接入API实施方案_v2.0.md")


# ---------------------------------------------------------------------- UI
@app.get("/")
def index():
    return send_from_directory(os.path.join(ROOT, "web"), "opening.html")


@app.get("/workspace")
def workspace():
    return send_from_directory(os.path.join(ROOT, "web"), "index.html")


@app.get("/static/<path:name>")
def static_files(name: str):
    return send_from_directory(os.path.join(ROOT, "web"), name)


@app.get("/knowledge-graph/")
def knowledge_graph():
    return send_from_directory(os.path.join(ROOT, "web", "knowledge-graph"), "index.html")


@app.get("/knowledge-qa/")
def knowledge_qa_page():
    return send_from_directory(os.path.join(ROOT, "web"), "knowledge-qa.html")


@app.post("/api/v1/knowledge-qa")
def knowledge_qa_ask():
    """知识问答：仅依据已核查证据、由院内本地模型生成带引用回答；不接触真实病历。"""
    who, err = require_role("importer", "reviewer", "runner", "viewer", "exporter", "admin")
    if err:
        return err
    body = request.get_json(silent=True) or {}
    question = body.get("question", "")
    if not isinstance(question, str) or not question.strip():
        return api_error("E202", "question 不能为空")
    result = knowledge_qa.answer_question(question)
    audit("KNOWLEDGE_QA", "ALLOW" if result.get("llm_available") else "DEGRADED", who,
          object_type="knowledge_qa", code=result.get("status", ""),
          detail=f"grounded={result.get('grounded')} citations={len(result.get('citations', []))} "
                 f"retrieved={len(result.get('retrieved', []))}")
    result["banner"] = BANNER
    return jsonify(result)


@app.get("/knowledge-graph/<path:name>")
def knowledge_graph_files(name: str):
    return send_from_directory(os.path.join(ROOT, "web", "knowledge-graph"), name)


# -------------------------------------------------------------------- 启动
def retention_cleanup() -> int:
    """§9 存储：到期清理暂存文件并留销毁记录。"""
    now = time.time()
    removed = 0
    for rec in _list("imports"):
        if rec.get("stage") == "EXPIRED":
            continue
        if rec.get("retained_until", 0) < now:
            path = rec.get("staging_path", "")
            if path and os.path.exists(path):
                os.remove(path)
            rec["stage"] = "EXPIRED"
            rec["staging_path"] = ""
            rec["expired_at"] = now
            _save("imports", rec["import_id"], rec)
            audit_log.record(actor="system", role="admin", action="RETENTION_PURGE",
                             result="ALLOW", object_type="import",
                             object_id=rec["import_id"],
                             detail=f"sha={rec.get('sha256', '')[:16]}")
            removed += 1
    return removed


def bootstrap() -> dict[str, Any]:
    """加载并校验模型（SHA-256 不符则拒绝提供推理，E402）。"""
    global predictor
    model_dir = os.path.join(ROOT, "model")
    info: dict[str, Any] = {"model_dir": model_dir}
    if not os.path.exists(os.path.join(model_dir, META_FILE)):
        info["trained_now"] = True
        train_model_dir(model_dir)
    try:
        predictor = Predictor(model_dir)
        info["integrity"] = "ok"
        info["sha256"] = predictor.integrity["sha256"]
        info["synthetic_metrics"] = predictor.meta.get("synthetic_internal_metrics")
    except IntegrityError as exc:
        predictor = None
        info["integrity"] = f"FAILED: {exc.detail}"
    info["retention_purged"] = retention_cleanup()
    return info


app.config["PORT"] = int(os.environ.get("PORT", "3000"))

if __name__ == "__main__":
    info = bootstrap()
    host = os.environ.get("BIND_HOST", "127.0.0.1")   # 红线：默认只绑回环
    port = app.config["PORT"]
    print(f"[i] {BANNER}")
    print(f"[i] app {APP_VERSION} · schema {contract.SCHEMA_VERSION} · "
          f"model {FORWARD_MODEL_VERSION}")
    print(f"[i] 模型完整性：{info.get('integrity')}")
    print(f"[i] 合成数据内部指标（不代表真实性能）：{info.get('synthetic_metrics')}")
    print(f"[i] 通道2 信封加密：{'启用' if CONFIG['channel2_envelope'] else '关闭（方案A）'}"
          f" · 逆向设计：{'启用' if CONFIG['reverse_enabled'] else '关闭'}")
    print(f"[i] 到期清理：{info.get('retention_purged')} 个批次")
    print(f"[i] 监听 {host}:{port}（生产须由医院加 HTTPS + 统一身份认证）")
    app.run(host=host, port=port, threaded=True, debug=False)
