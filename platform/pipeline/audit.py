"""审计日志（方案 §9.3）：链式哈希防篡改 + 日志脱敏红线。

禁止记录：CSV 正文、病历原文、行级明文、令牌、密钥、密码。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
import uuid
from typing import Any

from .contract import FORBIDDEN_VALUE_PATTERNS

_LOCK = threading.Lock()
_GENESIS = "0" * 64
_FORBIDDEN_KEYS = {"password", "token", "secret", "private_key", "csv_text",
                   "row_content", "authorization", "api_key"}
_SENSITIVE_HINT = re.compile(r"(?i)(password|token|secret|private_key|api_key)")


class AuditRejected(ValueError):
    """审计写入被拒绝：命中禁止字段或禁止内容模式。"""


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_client_ip(ip: str | None) -> str:
    """不存明文 IP，只存哈希（§9.3）。"""
    return _sha(ip or "")[:16]


def _assert_loggable(payload: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for k, v in payload.items():
        lk = str(k).lower()
        if lk in _FORBIDDEN_KEYS or _SENSITIVE_HINT.search(lk):
            raise AuditRejected(f"审计字段名命中红线：{k}")
        if isinstance(v, str):
            for pat in FORBIDDEN_VALUE_PATTERNS:
                if pat.search(v):
                    raise AuditRejected(f"审计内容命中直接标识符模式：字段 {k}")
        if isinstance(v, (dict, list)):
            if lk in _FORBIDDEN_KEYS:
                raise AuditRejected(f"审计字段名命中红线：{k}")
        clean[k] = v
    return clean


class AuditLog:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if not os.path.exists(self.path):
            open(self.path, "a", encoding="utf-8").close()

    def _last_hash(self) -> str:
        last = _GENESIS
        if os.path.getsize(self.path) == 0:
            return last
        with open(self.path, "rb") as fh:
            fh.seek(max(0, os.path.getsize(self.path) - 8192))
            tail = fh.read().decode("utf-8", "replace").strip().split("\n")
        for line in reversed(tail):
            line = line.strip()
            if not line:
                continue
            try:
                last = json.loads(line).get("event_hash", _GENESIS)
                break
            except json.JSONDecodeError:
                continue
        return last

    def record(self, *, actor: str, role: str, action: str, result: str,
               object_type: str = "", object_id: str = "", purpose: str = "",
               versions: dict[str, str] | None = None, client_ip: str = "",
               kid: str = "", key_fingerprint: str = "", code: str = "",
               **extra: Any) -> dict[str, Any]:
        payload = _assert_loggable({
            "actor": actor, "actor_role": role, "action": action, "result": result,
            "object_type": object_type, "object_id": object_id, "purpose": purpose,
            "versions": versions or {}, "client_ip_hash": hash_client_ip(client_ip),
            "kid": kid, "key_fingerprint": key_fingerprint, "code": code,
            **extra,
        })
        with _LOCK:
            prev = self._last_hash()
            event = {
                "event_id": uuid.uuid4().hex,
                "ts": time.time(),
                "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                **payload,
                "prev_hash": prev,
            }
            blob = json.dumps(event, ensure_ascii=False, sort_keys=True)
            event["event_hash"] = _sha(prev + blob)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, ensure_ascii=False) + "\n")
            return event

    def read(self, limit: int = 50) -> list[dict[str, Any]]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
        out = []
        for ln in lines[-limit:][::-1]:
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:
                out.append({"event_id": "?", "parse_error": True})
        return out

    def verify_chain(self) -> dict[str, Any]:
        """校验链式哈希完整性；医院可日常自查。"""
        if not os.path.exists(self.path):
            return {"ok": True, "events": 0}
        prev = _GENESIS
        count = 0
        with open(self.path, encoding="utf-8") as fh:
            for ln in fh:
                ln = ln.strip()
                if not ln:
                    continue
                ev = json.loads(ln)
                stored = ev.pop("event_hash", None)
                blob = json.dumps(ev, ensure_ascii=False, sort_keys=True)
                if ev.get("prev_hash") != prev or _sha(prev + blob) != stored:
                    return {"ok": False, "events": count,
                            "broken_at": ev.get("event_id")}
                prev = stored
                count += 1
        return {"ok": True, "events": count}

    def daily_digest(self) -> str:
        chain = self.verify_chain()
        return _sha(json.dumps(chain, sort_keys=True))[:16]
