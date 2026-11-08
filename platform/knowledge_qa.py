"""知识问答（RAG）：仅依据可核对证据，让院内本地 Qwen3-8B 生成带引用的回答。

红线：只把"用户问题 + 可核对证据条目"发给院内本地模型；绝不接入真实病历；
输出必须逐条引用真实存在的 claim_id，引用不到就如实说"没有已核查证据"，
不得编造、不得给临床/减药建议。模型不可用时返回 llm_available=False，前端退回纯检索。
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.abspath(__file__))
KB_DIR = os.path.join(ROOT, "web", "knowledge-graph")
VERIFIED_STATUSES = {"已核查", "已核对", "已复算", "已核验", "交付包核对"}
PROMPT_VERSION = "knowledge_qa_prompt_2026-11-08_v2"
DISCLAIMER = "教学/研究联调结果，仅供研究参考，不能用于临床决策或患者减药。"

SYSTEM_PROMPT = (
    "你是癫痫研究平台的知识问答助手。你只能依据【给定证据】回答，证据是若干条附来源和核对状态的 claim。"
    "规则：\n"
    "1) 只使用给定证据中的信息作答，不得使用你自己的先验知识补充事实或数字；\n"
    "2) 回答里引用的每条事实都必须对应证据的 claim_id；\n"
    "3) 若给定证据不足以回答，就明确说“没有找到已核查证据可以回答该问题”，不要猜测或编造；\n"
    "4) 不提供任何临床诊断、用药或减药建议；\n"
    "5) 严格只输出一个 JSON 对象，形如 {\"answer\": \"中文回答\", \"cited_claim_ids\": [\"C001\", ...]}，"
    "cited_claim_ids 只能包含给定证据中真实存在的 claim_id，没有可引用项时为空数组。"
)


class LLMUnavailable(RuntimeError):
    pass


def _load_kb():
    claims = json.loads(open(os.path.join(KB_DIR, "evidence_claims.json"), encoding="utf-8").read())
    try:
        sources = json.loads(open(os.path.join(KB_DIR, "sources.json"), encoding="utf-8").read())
    except (OSError, ValueError):
        sources = []
    return claims, sources


def _tokens(query: str) -> list[str]:
    latin = re.findall(r"[a-z0-9]+", query.lower())
    han_runs = re.findall(r"[\u3400-\u9fff]+", query)
    parts = list(latin)
    for word in han_runs:
        if len(word) > 2:
            parts.append(word)
            parts.extend(word[i:i + 2] for i in range(len(word) - 1))
        else:
            parts.append(word)
    if "样本量" in query:
        parts.append("患者")
    return [p for p in parts if len(p) > 1]


def _score(claim: dict, query: str, parts: list[str]) -> int:
    haystack = " ".join([claim.get("statement", ""), claim.get("subject", ""),
                         claim.get("object", ""), claim.get("predicate", ""),
                         claim.get("population", ""), claim.get("source_locator", "")]).lower()
    if not parts:
        return 0
    for anchor in ("d13", "asys", "select-eeg", "温州", "苏州", "winder"):
        if anchor in query.lower() and anchor not in haystack:
            return 0
    matches = [part for part in parts if part in haystack]
    if len(parts) >= 3 and len(matches) < max(2, round(len(parts) * .4)):
        return 0
    score = 8 if query.lower() in haystack else 0
    for part in matches:
        score += 2 if len(part) > 3 else 1
    return score


def retrieve(query: str, claims: list[dict], top_k: int = 6) -> list[dict]:
    parts = _tokens(query)
    scored = [(c, _score(c, query, parts)) for c in claims if c.get("status") in VERIFIED_STATUSES]
    scored = [(c, s) for c, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored[:top_k]]


def _llm_config() -> tuple[str, str, str]:
    base = os.getenv("EPILEPSY_LLM_BASE_URL", "").rstrip("/")
    model = os.getenv("EPILEPSY_LLM_MODEL", "")
    token = os.getenv("EPILEPSY_LLM_TOKEN", "")
    parsed = urlsplit(base)
    protected = parsed.scheme == "https" or (
        parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"})
    if not (protected and parsed.netloc and not parsed.username and not parsed.password
            and not parsed.query and not parsed.fragment and model and token):
        raise LLMUnavailable("内部 LLM 服务未配置或不可用")
    return base, model, token


def _ask_llm(question: str, evidence: list[dict]) -> tuple[dict, str]:
    base, model, token = _llm_config()
    material = [{"claim_id": c.get("claim_id"), "statement": c.get("statement"),
                 "status": c.get("status"), "source_id": c.get("source_id"),
                 "source_locator": c.get("source_locator")} for c in evidence]
    user = "【给定证据】\n" + json.dumps(material, ensure_ascii=False) + "\n\n【问题】\n" + question
    payload = {"model": model, "temperature": 0, "max_tokens": 1024,
               "response_format": {"type": "json_object"},
               "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user}]}
    if os.getenv("EPILEPSY_LLM_DISABLE_THINKING", "").lower() in {"1", "true"}:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    request = urllib.request.Request(
        base + "/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            content = json.loads(response.read().decode("utf-8"))["choices"][0]["message"]["content"]
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise LLMUnavailable(f"内部 LLM 请求或响应失败：{type(exc).__name__}") from exc
    if not isinstance(content, str) or len(content) > 20000:
        raise LLMUnavailable("模型响应过长或格式无效")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable("模型未返回合法 JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMUnavailable("模型响应不是对象")
    return parsed, model


def answer_question(question: str) -> dict:
    """主入口：检索已核查证据 → 调用本地模型 → 引用护栏校验。"""
    question = (question or "").strip()[:200]
    claims, sources = _load_kb()
    source_by_id = {s.get("source_id"): s for s in sources if isinstance(s, dict)}
    evidence = retrieve(question, claims)
    valid_ids = {c.get("claim_id") for c in evidence}

    def _citation(claim: dict) -> dict:
        src = source_by_id.get(claim.get("source_id"), {})
        return {"claim_id": claim.get("claim_id"), "statement": claim.get("statement"),
                "status": claim.get("status"), "source_id": claim.get("source_id"),
                "source_title": src.get("title"), "url": src.get("url"),
                "source_locator": claim.get("source_id") and claim.get("source_locator")}

    base = {"question": question, "retrieved": sorted(valid_ids),
            "prediction_permitted": False, "research_only": True,
            "disclaimer": DISCLAIMER, "prompt_version": PROMPT_VERSION}

    if not evidence:
        return {**base, "llm_available": True if _config_present() else False,
                "grounded": False, "answer": "没有找到已核查证据可以回答该问题。",
                "citations": [], "status": "NO_EVIDENCE"}

    try:
        parsed, model = _ask_llm(question, evidence)
    except LLMUnavailable as exc:
        return {**base, "llm_available": False, "grounded": False,
                "answer": None, "citations": [_citation(c) for c in evidence],
                "status": "LLM_UNAVAILABLE", "detail": str(exc)}

    raw_ids = parsed.get("cited_claim_ids") or []
    guarded = [c for c in evidence if c.get("claim_id") in set(raw_ids)]  # 只保留真实存在的引用
    answer_text = parsed.get("answer") if isinstance(parsed.get("answer"), str) else None
    return {**base, "llm_available": True, "model": model,
            "grounded": bool(guarded),
            "answer": answer_text or "模型未能给出可核查的回答。",
            "citations": [_citation(c) for c in guarded],
            "dropped_citations": sorted(set(str(x) for x in raw_ids) - valid_ids),
            "status": "REVIEW_REQUIRED"}


def _config_present() -> bool:
    return bool(os.getenv("EPILEPSY_LLM_BASE_URL") and os.getenv("EPILEPSY_LLM_MODEL")
                and os.getenv("EPILEPSY_LLM_TOKEN"))
