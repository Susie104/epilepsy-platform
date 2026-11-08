"""方案 B：应用层信封加密（§3.3）。

X25519 密钥协商（每次请求一次性临时密钥对，提供前向保密）
  → HKDF-SHA256 派生
  → AES-256-GCM 加密载荷（96-bit IV，128-bit 认证标签）
  → Ed25519 签名规范化报头
  → nonce + timestamp 防重放

红线：所有私钥由医院生成与托管；本模块不内置任何私钥。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

ALG = "X25519+HKDF-SHA256+AES-256-GCM"
SIG_ALG = "Ed25519"
ENVELOPE_VERSION = 1
HKDF_INFO = b"epilepsy-infer-v1"
GCM_IV_BYTES = 12
GCM_TAG_BYTES = 16
NONCE_BYTES = 16
DEFAULT_TIME_WINDOW = 300


def b64e(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64d(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def fingerprint(pub_raw: bytes) -> str:
    """密钥指纹：SHA-256 前 8 字节十六进制，可写入审计日志。"""
    return hashlib.sha256(pub_raw).hexdigest()[:16]


class EnvelopeError(Exception):
    """信封校验失败：签名、时间窗、重放、算法或格式不符。"""


# ------------------------------------------------------------- 密钥生成
def new_x25519() -> tuple[bytes, bytes]:
    priv = x25519.X25519PrivateKey.generate()
    return (priv.private_bytes(serialization.Encoding.Raw,
                               serialization.PrivateFormat.Raw,
                               serialization.NoEncryption()),
            priv.public_key().public_bytes(serialization.Encoding.Raw,
                                           serialization.PublicFormat.Raw))


def new_ed25519() -> tuple[bytes, bytes]:
    priv = ed25519.Ed25519PrivateKey.generate()
    return (priv.private_bytes(serialization.Encoding.Raw,
                               serialization.PrivateFormat.Raw,
                               serialization.NoEncryption()),
            priv.public_key().public_bytes(serialization.Encoding.Raw,
                                           serialization.PublicFormat.Raw))


class KeyStore:
    """医院侧密钥目录：私钥 0600，公钥可分发；课题组零持有。"""

    def __init__(self, directory: str):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)

    def _path(self, name: str) -> str:
        return os.path.join(self.dir, name)

    def exists(self, name: str) -> bool:
        return os.path.exists(self._path(name + ".private.json"))

    def save_private(self, name: str, kid: str, priv: bytes, pub: bytes) -> str:
        path = self._path(name + ".private.json")
        payload = {"kid": kid, "private_b64": b64e(priv), "public_b64": b64e(pub)}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        os.chmod(path, 0o600)
        pub_path = self._path(name + ".public.json")
        with open(pub_path, "w", encoding="utf-8") as fh:
            json.dump({"kid": kid, "public_b64": b64e(pub),
                       "key_fingerprint": fingerprint(pub)}, fh, indent=2)
        return path

    def load(self, name: str) -> dict[str, Any]:
        path = self._path(name + ".private.json")
        if not os.path.exists(path):
            raise EnvelopeError(f"密钥缺失 {name}；请医院侧先运行 "
                                f"python -m gateway.keygen --dir {self.dir}")
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        data["private"] = b64d(data["private_b64"])
        data["public"] = b64d(data["public_b64"])
        data["key_fingerprint"] = fingerprint(data["public"])
        return data

    def load_public(self, name: str) -> dict[str, Any]:
        for suffix in (".public.json", ".private.json"):
            path = self._path(name + suffix)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                data["public"] = b64d(data["public_b64"])
                data["key_fingerprint"] = fingerprint(data["public"])
                return data
        raise EnvelopeError(f"公钥缺失 {name}")


class NonceCache:
    def __init__(self, ttl: int = DEFAULT_TIME_WINDOW * 2):
        self.ttl = ttl
        self._seen: dict[str, float] = {}

    def check_and_add(self, nonce: str, now: float) -> bool:
        """返回 True 表示首次出现；False 表示重放。"""
        self._prune(now)
        if nonce in self._seen:
            return False
        self._seen[nonce] = now + self.ttl
        return True

    def _prune(self, now: float) -> None:
        expired = [k for k, exp in self._seen.items() if exp < now]
        for k in expired:
            self._seen.pop(k, None)


def _canonical(fields: dict[str, Any]) -> str:
    order = ["v", "alg", "sig_alg", "kid", "sender_pub", "nonce", "timestamp",
             "ciphertext", "tag"]
    return "\n".join(f"{k}={fields[k]}" for k in order)


def seal(plaintext: bytes, *, recipient_pub: bytes, signing_priv: bytes,
         kid: str, nonce: bytes | None = None, timestamp: float | None = None,
         sender_priv: bytes | None = None) -> dict[str, Any]:
    """封装为信封报文。sender_priv=None 时生成一次性临时密钥对（前向保密）。"""
    ephemeral = sender_priv is None
    if ephemeral:
        sender_priv, sender_pub = new_x25519()
    else:
        sender_pub = (x25519.X25519PrivateKey.from_private_bytes(sender_priv)
                      .public_key()
                      .public_bytes(serialization.Encoding.Raw,
                                    serialization.PublicFormat.Raw))
    nonce = nonce or os.urandom(NONCE_BYTES)
    timestamp = int(timestamp or time.time())

    shared = (x25519.X25519PrivateKey.from_private_bytes(sender_priv)
              .exchange(x25519.X25519PublicKey.from_public_bytes(recipient_pub)))
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=nonce,
               info=HKDF_INFO).derive(shared)
    iv = os.urandom(GCM_IV_BYTES)
    ct_and_tag = AESGCM(key).encrypt(iv, plaintext, None)
    ciphertext, tag = ct_and_tag[:-GCM_TAG_BYTES], ct_and_tag[-GCM_TAG_BYTES:]

    fields = {
        "v": ENVELOPE_VERSION, "alg": ALG, "sig_alg": SIG_ALG, "kid": kid,
        "sender_pub": b64e(sender_pub), "nonce": b64e(nonce),
        "timestamp": timestamp, "ciphertext": b64e(iv + ciphertext),
        "tag": b64e(tag),
    }
    signing_key = ed25519.Ed25519PrivateKey.from_private_bytes(signing_priv)
    fields["signature"] = b64e(signing_key.sign(_canonical(fields).encode("utf-8")))
    fields["ephemeral_sender"] = ephemeral
    return fields


def open_envelope(envelope: dict[str, Any], *, recipient_priv: bytes,
                  verify_pub: bytes, nonce_cache: NonceCache | None = None,
                  now: float | None = None,
                  time_window: int = DEFAULT_TIME_WINDOW) -> bytes:
    """校验签名 → 校验时间窗 → 防重放 → 解密并验证 GCM 标签。"""
    for k in ("v", "alg", "sig_alg", "kid", "sender_pub", "nonce", "timestamp",
              "ciphertext", "tag", "signature"):
        if k not in envelope:
            raise EnvelopeError(f"信封缺少字段 {k}")
    if envelope["v"] != ENVELOPE_VERSION:
        raise EnvelopeError(f"信封版本不支持 v={envelope['v']}")
    if envelope["alg"] != ALG or envelope["sig_alg"] != SIG_ALG:
        raise EnvelopeError("算法不符：拒绝降级协商")

    try:
        ed25519.Ed25519PublicKey.from_public_bytes(verify_pub).verify(
            b64d(envelope["signature"]), _canonical(envelope).encode("utf-8"))
    except Exception as exc:  # 签名不符一律拒绝，不泄露细节
        raise EnvelopeError("签名校验失败") from exc

    now = time.time() if now is None else now
    ts = float(envelope["timestamp"])
    if abs(now - ts) > time_window:
        raise EnvelopeError(f"时间窗超出 ±{time_window}s")
    if nonce_cache is not None and not nonce_cache.check_and_add(envelope["nonce"], now):
        raise EnvelopeError("nonce 重复：疑似重放攻击")

    sender_pub = b64d(envelope["sender_pub"])
    shared = (x25519.X25519PrivateKey.from_private_bytes(recipient_priv)
              .exchange(x25519.X25519PublicKey.from_public_bytes(sender_pub)))
    nonce = b64d(envelope["nonce"])
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=nonce,
               info=HKDF_INFO).derive(shared)
    blob = b64d(envelope["ciphertext"])
    iv, ciphertext = blob[:GCM_IV_BYTES], blob[GCM_IV_BYTES:]
    try:
        return AESGCM(key).decrypt(iv, ciphertext + b64d(envelope["tag"]), None)
    except Exception as exc:
        raise EnvelopeError("载荷解密或完整性校验失败") from exc
