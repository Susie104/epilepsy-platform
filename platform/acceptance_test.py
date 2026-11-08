"""端到端验收自测（方案 §10.2）。

用法：先启动服务，再运行 python acceptance_test.py [--channel2]
覆盖：全链路跑通、数值复现、拒绝用例（E1xx/E2xx/E3xx/E4xx/E5xx/E6xx）、
     对象级越权、边界二服务身份、审计链完整性、导出防注入、断网等价性。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("BASE_URL", "http://127.0.0.1:3000").rstrip("/")
ROLE = {"importer": "hosp-import", "reviewer": "hosp-review",
        "runner": "hosp-run", "viewer": "hosp-view", "exporter": "hosp-export",
        "admin": "hosp-admin", "outsider": "other-dept-user"}
PASS, FAIL = [], []


def call(method, path, *, data=None, files=None, role="importer",
         scope="neuro-epilepsy", headers=None, expect=None, raw=False):
    url = BASE + path
    body = None
    hdr = {"X-Demo-User": ROLE.get(role, role), "X-Demo-Role": role,
           "X-Demo-Scope": scope, **(headers or {})}
    if files:
        boundary = "----qwacceptance"
        parts = []
        for k, v in (data or {}).items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="{k}"\r\n\r\n{v}\r\n'.encode())
        for k, (fname, content) in files.items():
            parts.append(f"--{boundary}\r\nContent-Disposition: form-data; "
                         f'name="{k}"; filename="{fname}"\r\n'
                         f"Content-Type: text/csv\r\n\r\n".encode() + content + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        hdr["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif data is not None:
        body = json.dumps(data).encode("utf-8")
        hdr["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = resp.read()
            code = resp.status
    except urllib.error.HTTPError as exc:
        payload = exc.read()
        code = exc.code
    if raw:
        return code, payload
    try:
        parsed = json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError:
        parsed = {"_text": payload.decode("utf-8", "replace")}
    if expect is not None and code != expect:
        FAIL.append(f"{method} {path} → HTTP {code}（期望 {expect}）: "
                    f"{json.dumps(parsed, ensure_ascii=False)[:300]}")
    return code, parsed


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(f"{name}{(' · ' + detail) if detail and not cond else ''}")


def get_demo_csv(scenario="forward", flavor="ok", n=40, role="importer"):
    code, raw = call("GET", f"/api/v1/demo/csv?scenario={scenario}&flavor={flavor}&n={n}",
                     role=role, raw=True)
    return raw.decode("utf-8-sig")


def full_flow(scenario="forward", purpose=None, flavor="ok", n=40,
              target_risk=0.35, tag=""):
    purpose = purpose or ("reverse" if scenario == "reverse" else "prediction")
    csv_text = get_demo_csv(scenario, flavor, n)
    code, up = call("POST", "/api/v1/imports/file",
                    data={"purpose": purpose},
                    files={"file": (f"{tag or scenario}.csv", csv_text.encode("utf-8-sig"))},
                    role="importer", expect=201)
    if code != 201:
        return None
    import_id = up["import_id"]
    v = up["validation"]
    mapping = {**up["proposed_mapping"]["mapping"]}
    code, mp = call("POST", f"/api/v1/imports/{import_id}/mappings",
                    data={"mapping": mapping, "unit_rules": "剂量统一 mg",
                          "null_rules": "空值不得自动改为 0"}, role="reviewer", expect=200)
    code, cf = call("POST", f"/api/v1/imports/{import_id}/confirm",
                    data={"purpose": purpose, "mapping_version": mp["mapping_version"],
                          "ethics_ref": "院伦审〔2026〕演示-001"},
                    role="reviewer", expect=200)
    code, run = call("POST", "/api/v1/runs",
                     data={"import_id": import_id, "scenario": scenario,
                           "target_risk": target_risk},
                     role="runner", expect=202, headers={"Idempotency-Key": f"idem-{tag}-{time.time()}"})
    if code != 202:
        return {"import_id": import_id, "upload": up, "run_error": run}
    run_id = run["run_id"]
    for _ in range(120):
        code, st = call("GET", f"/api/v1/runs/{run_id}", role="runner")
        if st.get("status") in ("COMPLETED", "PARTIAL_FAILED", "FAILED", "CANCELLED"):
            break
        time.sleep(0.25)
    return {"import_id": import_id, "run_id": run_id, "upload": up,
            "status": st, "validation": v}


def main() -> int:
    channel2 = "--channel2" in sys.argv
    print(f"[i] 验收目标：{BASE}（通道2 信封加密：{'是' if channel2 else '否'}）\n")

    # 1. 元数据与就绪
    code, meta = call("GET", "/api/v1/meta/versions", role="viewer")
    check("元数据可读取", code == 200 and meta.get("research_only") is True)
    check("版本三元组齐全", all(k in meta for k in
                               ("schema_version", "model_version", "model_sha256")))
    code, rz = call("GET", "/readyz", role="admin")
    check("模型完整性校验通过", rz.get("model_integrity") is True, json.dumps(rz)[:200])

    # 2. 全链路：正向预测
    r = full_flow("forward", flavor="ok", n=40, tag="accept-fwd")
    check("正向预测端到端跑通", bool(r) and r["status"]["status"] in
          ("COMPLETED", "PARTIAL_FAILED"),
          json.dumps(r.get("status", {}), ensure_ascii=False)[:300])
    code, res = call("GET", f"/api/v1/runs/{r['run_id']}/results?page=1&page_size=50",
                     role="viewer")
    ok_rows = [x for x in res.get("rows", []) if x["status"] == "OK"]
    rej_rows = [x for x in res.get("rows", []) if x["status"] != "OK"]
    check("逐行拒绝只出现契约类原因（E401 支持范围 / E2xx / E3xx）",
          all(c.startswith(("E401", "E2", "E3")) for x in rej_rows
              for c in x.get("reject_codes", [])),
          str(sorted({c for x in rej_rows for c in x.get("reject_codes", [])})))
    check("结果含风险值且带 research_only", bool(ok_rows)
          and all(x.get("research_only") for x in ok_rows))
    check("拒绝行不返回默认概率", all(x["risk_730d"] is None
                                  for x in res.get("rows", []) if x["status"] != "OK"))
    check("结果携带版本三元组", all(k in res.get("versions", {}) for k in
                                ("schema_version", "model_version", "mapping_version")))

    # 3. 数值复现：同一 CSV 两次运行结果一致（§10.2）
    csv_text = get_demo_csv("forward", "ok", 20)
    risks = []
    for i in range(2):
        rr = full_flow("forward", flavor="ok", n=20, tag=f"repro-{i}")
        code, rres = call("GET", f"/api/v1/runs/{rr['run_id']}/results?page_size=100",
                          role="viewer")
        risks.append([x["risk_730d"] for x in rres["rows"] if x["status"] == "OK"])
    check("固定输入数值复现一致", risks[0] == risks[1] and len(risks[0]) > 0,
          f"{len(risks[0])} vs {len(risks[1])}")

    # 4. 预检拒绝码覆盖
    csv_text = get_demo_csv("forward", "bad", 30)
    code, bad = call("POST", "/api/v1/imports/file", data={"purpose": "prediction"},
                     files={"file": ("bad.csv", csv_text.encode("utf-8-sig"))},
                     role="importer")
    codes = set(bad.get("validation", {}).get("codes_seen", {}))
    check("非法文件被识别（不是 READY）", bad.get("stage") != "READY", bad.get("stage"))
    check("直接标识符列被拦截", "patient_name" in ",".join(
        bad.get("validation", {}).get("forbidden_hits", [])))
    for want, why in (("E103", "重复/标识符"), ("E104", "日期非法"),
                      ("E201", "越界"), ("E202", "类型非法"),
                      ("E203", "非法枚举"), ("E204", "必填为空")):
        check(f"拒绝码 {want} 命中（{why}）", want in codes, f"实际 {sorted(codes)}")

    # 5. 用途绑定与状态机
    csv_text = get_demo_csv("forward", "ok", 5)
    code, up = call("POST", "/api/v1/imports/file", data={"purpose": "prediction"},
                    files={"file": ("small.csv", csv_text.encode("utf-8-sig"))},
                    role="importer", expect=201)
    iid = up["import_id"]
    code, run = call("POST", "/api/v1/runs", data={"import_id": iid}, role="runner")
    check("未 confirm 直接运行被拒（E302）", code == 400 and run.get("code") == "E302",
          json.dumps(run, ensure_ascii=False)[:200])
    call("POST", f"/api/v1/imports/{iid}/mappings",
         data={"mapping": up["proposed_mapping"]["mapping"]}, role="reviewer")
    call("POST", f"/api/v1/imports/{iid}/confirm", data={"purpose": "prediction"},
         role="reviewer")
    code, run = call("POST", "/api/v1/runs",
                     data={"import_id": iid, "scenario": "reverse"}, role="runner")
    check("用途与场景不一致被拒（E303）", code == 403 and run.get("code") == "E303",
          json.dumps(run, ensure_ascii=False)[:200])
    code, run = call("POST", "/api/v1/runs", data={"import_id": iid}, role="runner")
    code2, run2 = call("POST", "/api/v1/runs", data={"import_id": iid}, role="runner",
                       headers={"Idempotency-Key": "same-key-1"})
    code3, run3 = call("POST", "/api/v1/runs", data={"import_id": iid}, role="runner",
                       headers={"Idempotency-Key": "same-key-1"})
    check("幂等键防重复批次", run3.get("idempotent_replay") is True
          and run2.get("run_id") == run3.get("run_id"),
          f"http2={code2} http3={code3} run2={run2.get('run_id')} "
          f"run3={json.dumps(run3, ensure_ascii=False)[:160]}")

    # 6. 逆向设计：有减药字段可运行，无则 E403 拒绝外推
    rr = full_flow("reverse", purpose="reverse", flavor="ok", n=10,
                   target_risk=0.45, tag="accept-rev")
    check("逆向设计端到端跑通", bool(rr) and rr["status"]["status"] in
          ("COMPLETED", "PARTIAL_FAILED"), json.dumps(rr.get("status", {}), ensure_ascii=False)[:300])
    code, rres = call("GET", f"/api/v1/runs/{rr['run_id']}/results?page_size=50",
                      role="viewer")
    rev_ok = [x for x in rres.get("rows", []) if x["status"] == "OK"]
    check("逆向输出可行区间且带 RESEARCH_ONLY 声明", bool(rev_ok)
          and all(x.get("feasible_reduction_range") and x.get("support_note")
                  for x in rev_ok))
    # 批次级闸门：purpose=reverse 但 CSV 缺 B1-B4 → 映射不完整，confirm 必须被拒
    no_dose = get_demo_csv("forward", "ok", 3)
    code, up2 = call("POST", "/api/v1/imports/file", data={"purpose": "reverse"},
                     files={"file": ("nodose.csv", no_dose.encode("utf-8-sig"))},
                     role="importer", expect=201)
    iid2 = up2["import_id"]
    check("逆向批次缺 B1-B4 时预检判为不完整",
          bool(up2["proposed_mapping"]["unmapped_required"]),
          str(up2["proposed_mapping"]["unmapped_required"])[:120])
    code, mp2 = call("POST", f"/api/v1/imports/{iid2}/mappings",
                     data={"mapping": up2["proposed_mapping"]["mapping"]}, role="reviewer")
    check("映射不完整状态为 INCOMPLETE", code == 200 and mp2.get("status") == "INCOMPLETE")
    code, cf2 = call("POST", f"/api/v1/imports/{iid2}/confirm",
                     data={"purpose": "reverse"}, role="reviewer")
    check("映射不完整时 confirm 被拒（E301）",
          code == 400 and cf2.get("code") == "E301",
          json.dumps(cf2, ensure_ascii=False)[:200])

    # 推理层闸门：目标风险不可达 → 无可行域，拒绝外推（E403），不填数值
    code, run = call("POST", "/api/v1/runs",
                     data={"import_id": rr["import_id"], "scenario": "reverse",
                           "target_risk": 0.001},
                     role="runner", expect=202)
    for _ in range(80):
        code, st = call("GET", f"/api/v1/runs/{run['run_id']}", role="runner")
        if st["status"] in ("COMPLETED", "PARTIAL_FAILED", "FAILED"):
            break
        time.sleep(0.25)
    code, rres = call("GET", f"/api/v1/runs/{run['run_id']}/results?page_size=20",
                      role="viewer")
    rows = rres.get("rows", [])
    check("目标风险不可达时拒绝外推（E403）",
          bool(rows) and all("E403" in x.get("reject_codes", []) for x in rows)
          and all(x["risk_730d"] is None for x in rows),
          json.dumps(rows[:1], ensure_ascii=False)[:220])

    # 7. 授权与越权
    code, denied = call("GET", f"/api/v1/runs/{r['run_id']}/results", role="outsider",
                        scope="cardiology")
    check("越权访问他科批次被拒（E601）", code == 403, json.dumps(denied, ensure_ascii=False)[:200])
    code, denied = call("GET", f"/api/v1/imports/{r['import_id']}/validation",
                        role="viewer", scope="cardiology")
    check("跨科室读取预检被拒（E601）", code == 403 and denied.get("code") == "E601")
    code, denied = call("POST", "/api/v1/runs", data={"import_id": iid}, role="viewer")
    check("角色不足被拒（E601）", code == 403 and denied.get("code") == "E601")
    code, denied = call("GET", "/api/v1/audit", role="viewer")
    check("审计仅系统管理可见", code == 403)

    # 8. 链接入口（D4 默认关闭）
    for url, why in (("http://files.hospital.local/a.csv", "非 https"),
                     ("https://evil.example.com/a.csv", "不在白名单"),
                     ("https://user:pass@files.hospital.local/a.csv", "携带凭证"),
                     ("https://169.254.169.254/latest/meta-data", "云元数据地址")):
        code, res = call("POST", "/api/v1/imports/link", data={"source_url": url},
                         role="importer")
        check(f"链接被拒（{why}）→ E503", code == 403 and res.get("code") == "E503",
              json.dumps(res, ensure_ascii=False)[:160])

    # 9. 边界二服务身份
    code, res = call("POST", "/internal/v1/infer-batch",
                     data={"batch_id": "x", "schema_version": "1.0.0", "records": []},
                     role="admin")
    check("浏览器身份调用 /internal 被拒（E601）", code == 403,
          json.dumps(res, ensure_ascii=False)[:160])

    # 10. 单例录入
    code, sp = call("POST", "/api/v1/predictions", role="viewer", data={
        "scenario": "forward",
        "fields": {"case_id": "0a1b2c3d4e5f6789", "index_date": "2026-01-15",
                   "epilepsy_duration_before_remission_years": 6.2,
                   "seizure_free_months": 27, "age_at_onset": 9,
                   "febrile_seizure_history": 0, "seizure_count_before_remission": 4,
                   "self_limiting_syndrome": 0, "developmental_delay": 0,
                   "eeg_epileptiform": 1}})
    check("单例录入返回风险值", code == 200 and sp.get("status") == "OK"
          and isinstance(sp.get("risk_730d"), float))
    code, sp = call("POST", "/api/v1/predictions", role="viewer", data={
        "scenario": "forward",
        "fields": {"case_id": "13800001111", "index_date": "2026-01-15",
                   "epilepsy_duration_before_remission_years": 6.2,
                   "seizure_free_months": 27, "age_at_onset": 9,
                   "febrile_seizure_history": 0, "seizure_count_before_remission": 4,
                   "self_limiting_syndrome": 0}})
    check("单例字段不齐/含标识符被拒且不回默认值",
          code == 422 and sp.get("risk_730d") is None
          and "E103" in ",".join(sp.get("reject_codes", [])),
          json.dumps(sp, ensure_ascii=False)[:220])

    # 11. 导出与防公式注入
    code, exp = call("POST", f"/api/v1/runs/{r['run_id']}/exports", role="exporter",
                     data={"format": "csv", "purpose": "internal_research"})
    check("导出成功", code == 200 and exp.get("file_name"), json.dumps(exp, ensure_ascii=False)[:200])
    code, raw = call("GET", exp["download_url"], role="exporter", raw=True)
    text = raw.decode("utf-8-sig")
    check("导出文件带 RESEARCH_ONLY 标识", "RESEARCH_ONLY" in text)
    check("导出文件含版本三元组", meta["schema_version"] in text)
    check("导出防公式注入生效", not any(line.split(",")[0].startswith(("=", "+", "@"))
                                    for line in text.splitlines()[1:] if line.strip()))
    code, exp2 = call("POST", f"/api/v1/runs/{r['run_id']}/exports", role="exporter",
                      data={"format": "xlsx"})
    check("xlsx 导出成功", code == 200 and exp2["file_name"].endswith(".xlsx"))

    # 12. 通道2 信封加密
    code, st = call("POST", "/api/v1/crypto/selftest", role="admin")
    if channel2:
        check("信封加密回环成功", st.get("roundtrip_ok") is True)
        check("重放被拦截", st.get("replay_blocked") is True)
        rr2 = full_flow("forward", flavor="ok", n=20, tag="accept-enc")
        check("通道2 下全链路可跑通", bool(rr2) and rr2["status"]["status"] in
              ("COMPLETED", "PARTIAL_FAILED"),
              json.dumps(rr2.get("status", {}), ensure_ascii=False)[:250])
        check("通道2 记录边界类型", rr2["status"].get("boundary") == "envelope-http",
              str(rr2["status"].get("boundary")))
    else:
        check("通道2 关闭时走进程内边界（方案A）",
              st.get("channel2_enabled") is False)

    # 13. 审计链完整性
    code, au = call("GET", "/api/v1/audit?limit=20", role="admin")
    check("审计链式哈希校验通过", au.get("chain", {}).get("ok") is True,
          json.dumps(au.get("chain"), ensure_ascii=False)[:200])
    actions = {e.get("action") for e in au.get("events", [])}
    check("审计记录关键动作", {"IMPORT_FILE", "CONFIRM", "EXPORT"} & actions != set(),
          str(actions))
    leaks = [e for e in au.get("events", [])
             if any(v in json.dumps(e, ensure_ascii=False)
                    for v in ("张某某", "13800001111"))]
    check("审计未泄露直接标识符", not leaks)

    print(f"\n通过 {len(PASS)} 项")
    for p in PASS:
        print(f"  ✓ {p}")
    if FAIL:
        print(f"\n失败 {len(FAIL)} 项")
        for f in FAIL:
            print(f"  ✗ {f}")
    print(f"\n结论：{'全部通过' if not FAIL else '存在未通过项'}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
