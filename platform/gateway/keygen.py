"""医院侧密钥生成（方案 §9.2）。

由**医院**在院内执行，生成边界二所需的全部密钥：
  · platform  X25519 密钥对   —— 平台服务身份（收方向）
  · model     X25519 密钥对   —— 模型服务身份（收方向）
  · platform_sign / model_sign Ed25519 签名密钥对

红线：交付包内**不含**任何预置私钥；私钥权限 0600；不备份到院外；
密钥与数据分权管理、高权限密钥双人控制；轮换默认 12 个月或人员变动/疑似
泄露时立即轮换，轮换期允许多 kid 并存；吊销须留审批记录。

用法：
    python -m gateway.keygen --dir var/keys [--force] [--kid-prefix hosp-a]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .crypto import KeyStore, fingerprint, new_ed25519, new_x25519

KEY_SPECS = [
    ("platform", "x25519", "边界二·平台服务收方"),
    ("model", "x25519", "边界二·模型服务收方"),
    ("platform_sign", "ed25519", "平台服务签名"),
    ("model_sign", "ed25519", "模型服务签名"),
]


def generate(key_dir: str, kid_prefix: str, force: bool = False) -> dict[str, str]:
    store = KeyStore(key_dir)
    made: dict[str, str] = {}
    for name, kind, desc in KEY_SPECS:
        if store.exists(name) and not force:
            print(f"[skip] {name} 已存在（如需轮换请加 --force，轮换期间双 kid 并存）")
            made[name] = store.load_public(name)["kid"]
            continue
        kid = f"{kid_prefix}-{kind}-{time.strftime('%Y%m')}"
        priv, pub = new_x25519() if kind == "x25519" else new_ed25519()
        store.save_private(name, kid, priv, pub)
        made[name] = kid
        print(f"[ok]   {name:14s} {desc}  kid={kid}  fp={fingerprint(pub)}")
    _write_public_bundle(store, key_dir, made)
    return made


def _write_public_bundle(store: KeyStore, key_dir: str, kids: dict[str, str]) -> None:
    """只含公钥与指纹，可安全分发/入配置模板；私钥绝不写入。"""
    bundle = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
              "note": "本文件只含公钥，可分发；私钥文件永不出院", "keys": {}}
    for name, _kind, desc in KEY_SPECS:
        pub = store.load_public(name)
        bundle["keys"][name] = {"kid": pub["kid"], "public_b64": pub["public_b64"],
                                "key_fingerprint": pub["key_fingerprint"],
                                "purpose": desc}
    path = os.path.join(key_dir, "public_bundle.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, ensure_ascii=False, indent=2)
    print(f"[ok]   公钥汇总 → {path}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="医院侧密钥生成（私钥不出院）")
    ap.add_argument("--dir", default="var/keys", help="院内密钥目录（受限权限）")
    ap.add_argument("--kid-prefix", default="hosp")
    ap.add_argument("--force", action="store_true", help="覆盖已有密钥（轮换时使用）")
    args = ap.parse_args(argv)
    if not args.force and os.path.isdir(args.dir) and os.listdir(args.dir):
        print(f"[warn] {args.dir} 非空且未加 --force：已存在的密钥不会被覆盖")
    generate(args.dir, args.kid_prefix, args.force)
    print("\n下一步：把 var/keys 交由医院 KMS/HSM 或受限目录托管，权限 0600，")
    print("      并与数据存储分权管理。课题组不生成、不保管、不备份任何私钥。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
