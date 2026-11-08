# -*- coding: utf-8 -*-
r"""
================================================================================
D13 三场景建模 —— 独立审计脚本（审计方视角，不复用建模代码）
================================================================================
原则：
    - 不 import 建模脚本；只读收据（CSV/JSON），从原始预测重算全部指标再对照。
    - 对照口径：结果文件 results_metrics_*.csv、split_info.json、predictions.csv、
      fold_split.csv 之间的自洽性 + 指标重算一致性 + 数据 sha256。
    - 敏感性汇总：合并 full / dedup 两版指标 → sensitivity_full_vs_dedup.csv。
    - 任何一项 FAIL 则退出码 1；报告写入 audit_report.md。

用法：
    python audit_d13.py --root <results目录> [--data data.csv] [--out 报告目录]
    （--root 指包含 full/ 与 dedup/ 两个结果子目录的目录）
================================================================================
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

TOL = 1e-6

METRIC_FN = {"auroc": roc_auc_score, "auprc": average_precision_score,
             "brier": brier_score_loss}
FEATURE_SETS = ["A", "B", "C"]
REQUIRED_METRIC_COLS = [
    "data", "feature_set", "model",
    "auroc_mean", "auroc_sd", "auprc_mean", "auprc_sd", "brier_mean", "brier_sd",
    "auroc_oof_pooled", "auprc_oof_pooled", "brier_oof_pooled",
    "test_auroc", "test_auprc", "test_brier",
    "test_auroc_lo", "test_auroc_hi", "test_auprc_lo", "test_auprc_hi",
    "test_brier_lo", "test_brier_hi", "notes",
]


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def near(a, b, tol=TOL):
    return abs(float(a) - float(b)) <= tol


class Auditor:
    def __init__(self):
        self.fails = []
        self.lines = ["# D13 三场景建模 · 独立审计报告\n"]

    def check(self, ok, name, detail=""):
        tag = "PASS" if ok else "FAIL"
        self.lines.append(f"- [{tag}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            self.fails.append(name)
        return ok

    # ------------------------------------------------------------------
    def audit_tag(self, root, tag, data_path):
        d = os.path.join(root, tag)
        self.lines.append(f"\n## 数据版: {tag}")
        if not os.path.isdir(d):
            self.check(False, f"结果目录 {d} 存在")
            return
        expected = [f"results_metrics_{tag}.csv", "predictions.csv", "fold_split.csv",
                    "split_info.json", "env_record.txt", "run_record.md",
                    f"fig_roc_pr_{tag}.png", f"fig_calibration_{tag}.png",
                    f"fig_decision_curve_{tag}.png"]
        if tag == "full":
            expected.append("sparse_var_frequency.csv")
        for fn in expected:
            self.check(os.path.isfile(os.path.join(d, fn)), f"文件存在: {tag}/{fn}")

        need = ["results_metrics_" + tag + ".csv", "predictions.csv",
                "fold_split.csv", "split_info.json"]
        if any(not os.path.isfile(os.path.join(d, fn)) for fn in need):
            self.check(False, f"{tag} 关键收据齐全（缺少则跳过该版其余检查）")
            return
        self.check(True, f"{tag} 关键收据齐全")

        si = json.load(open(os.path.join(d, "split_info.json"), encoding="utf-8"))
        metrics = pd.read_csv(os.path.join(d, f"results_metrics_{tag}.csv"))
        preds = pd.read_csv(os.path.join(d, "predictions.csv"))
        splits = pd.read_csv(os.path.join(d, "fold_split.csv"))
        models = si.get("models", ["lr", "lgbm"])

        # —— 0. 数据 sha256 ——
        if data_path and os.path.isfile(data_path):
            actual = sha256_file(data_path)
            self.check(actual == si.get("data_sha256"),
                       f"data.csv sha256 与 split_info 一致",
                       f"split_info={si.get('data_sha256')} 实际={actual}")
        else:
            self.check(False, "--data 已提供且存在（未提供则无法核对 sha256）")

        # —— 1. 划分身份 ——
        s_tr = splits[splits.role == "train"]
        s_te = splits[splits.role == "test"]
        self.check(len(s_tr) == si["n_train"] and len(s_te) == si["n_test"],
                   "训练/测试行数与 split_info 一致",
                   f"train={len(s_tr)}/{si['n_train']} test={len(s_te)}/{si['n_test']}")
        self.check(len(set(s_tr.record_id) & set(s_te.record_id)) == 0,
                   "训练集与测试集无重叠记录")
        self.check(set(s_tr.fold.unique()) == {0, 1, 2, 3, 4},
                   "训练折编号为 0..4")
        self.check((s_te.fold == -1).all(), "测试行 fold 均为 -1")
        fold_sizes_actual = s_tr.groupby("fold").size().to_dict()
        fold_sizes_info = {int(k): v for k, v in si.get("fold_sizes", {}).items()}
        self.check(fold_sizes_actual == fold_sizes_info,
                   "各折规模与 split_info 一致",
                   f"{fold_sizes_actual} vs {fold_sizes_info}")
        fold_pos_actual = s_tr.groupby("fold")["y_true"].sum().to_dict()
        fold_pos_info = {int(k): v for k, v in si.get("fold_positive", {}).items()}
        self.check(fold_pos_actual == fold_pos_info, "各折阳性数与 split_info 一致")
        self.check(int(s_te.y_true.sum()) == si.get("test_positive"),
                   "测试集阳性数与 split_info 一致")
        self.check(len(splits) == len(s_tr) + len(s_te), "fold_split 无多余行")

        # —— 2. 预测收据覆盖 ——
        oof = preds[preds.role == "oof"]
        tes = preds[preds.role == "test"]
        n_train, n_test, n_models = si["n_train"], si["n_test"], len(models)
        self.check(len(oof) == n_train * n_models * 3,
                   "OOF 收据总数 = n_train × 模型数 × 3 特征集",
                   f"{len(oof)} vs {n_train * n_models * 3}")
        self.check(len(tes) == n_test * n_models * 3,
                   "测试收据总数 = n_test × 模型数 × 3 特征集",
                   f"{len(tes)} vs {n_test * n_models * 3}")
        self.check(oof.feature_set.isin(FEATURE_SETS).all() and
                   tes.feature_set.isin(FEATURE_SETS).all(),
                   "收据 feature_set 取值 ∈ {A,B,C}")
        # y_true 与 fold_split 一致
        ymap = dict(zip(splits.record_id, splits.y_true))
        self.check((oof.record_id.map(ymap) == oof.y_true).all() and
                   (tes.record_id.map(ymap) == tes.y_true).all(),
                   "收据 y_true 与 fold_split 一致")
        # 每个 (fs, mk) 覆盖
        for fs in FEATURE_SETS:
            for mk in models:
                o = oof[(oof.feature_set == fs) & (oof.model == mk)]
                t = tes[(tes.feature_set == fs) & (tes.model == mk)]
                self.check(len(o) == n_train and len(t) == n_test,
                           f"{fs}/{mk} 收据行数正确",
                           f"oof={len(o)}/{n_train} test={len(t)}/{n_test}")
                if len(o) == n_train:
                    self.check(o.record_id.nunique() == n_train,
                               f"{fs}/{mk} OOF 无重复记录")

        # —— 3. 指标重算对照 ——
        self.check(set(REQUIRED_METRIC_COLS).issubset(metrics.columns),
                   "results_metrics 列完整")
        rng = np.random.default_rng(si.get("seed", 42))
        n_boot = si.get("bootstrap", {}).get("n", 250)
        for fs in FEATURE_SETS:
            for mk in models:
                row = metrics[(metrics.feature_set == fs) & (metrics.model == mk)]
                self.check(len(row) == 1, f"{fs}/{mk} 指标表恰有一行")
                if len(row) != 1:
                    continue
                row = row.iloc[0]
                o = oof[(oof.feature_set == fs) & (oof.model == mk)]
                t = tes[(tes.feature_set == fs) & (tes.model == mk)]
                # 折内指标 → 均值±SD
                per_fold = {}
                for f_ in range(5):
                    fo = o[o.fold == f_]
                    per_fold[f_] = {k: METRIC_FN[k](fo.y_true, fo.proba)
                                    for k in METRIC_FN}
                for k in METRIC_FN:
                    vals = [per_fold[f_][k] for f_ in range(5)]
                    self.check(near(np.mean(vals), row[f"{k}_mean"]) and
                               near(np.std(vals), row[f"{k}_sd"]),
                               f"{fs}/{mk} CV {k} 均值±SD 重算一致",
                               f"重算 {np.mean(vals):.6f}±{np.std(vals):.6f} vs "
                               f"记录 {row[f'{k}_mean']:.6f}±{row[f'{k}_sd']:.6f}")
                # OOF 拼接（按 record_id 排序后整体算）
                o_sorted = o.sort_values("record_id")
                for k in METRIC_FN:
                    pooled = METRIC_FN[k](o_sorted.y_true, o_sorted.proba)
                    self.check(near(pooled, row[f"{k}_oof_pooled"]),
                               f"{fs}/{mk} OOF 拼接 {k} 重算一致",
                               f"重算 {pooled:.6f} vs 记录 {row[f'{k}_oof_pooled']:.6f}")
                # 测试集（按 record_id 排序；单值指标与行序无关）
                t_sorted = t.sort_values("record_id")
                for k in METRIC_FN:
                    v = METRIC_FN[k](t_sorted.y_true, t_sorted.proba)
                    self.check(near(v, row[f"test_{k}"]),
                               f"{fs}/{mk} 测试集 {k} 重算一致",
                               f"重算 {v:.6f} vs 记录 {row[f'test_{k}']:.6f}")
                # bootstrap 重放（固定模型重抽测试行；位置重抽样依赖行序，
                # 必须用 predictions.csv 原始行序 = 建模脚本 X_test 行序，不能排序）
                y_t, p_t = t.y_true.to_numpy(), t.proba.to_numpy()
                n = len(y_t)
                for k in METRIC_FN:
                    vals = []
                    for _ in range(n_boot):
                        idx = rng.integers(0, n, n)
                        vals.append(METRIC_FN[k](y_t[idx], p_t[idx]))
                    lo, hi = np.quantile(vals, [0.025, 0.975])
                    self.check(near(lo, row[f"test_{k}_lo"]) and
                               near(hi, row[f"test_{k}_hi"]),
                               f"{fs}/{mk} bootstrap {k} 95% 区间重放一致",
                               f"重放 [{lo:.6f}, {hi:.6f}] vs "
                               f"记录 [{row[f'test_{k}_lo']:.6f}, {row[f'test_{k}_hi']:.6f}]")

        # —— 4. 环境记录 ——
        env_txt = open(os.path.join(d, "env_record.txt"), encoding="utf-8").read()
        self.check("python:" in env_txt and "pip freeze" in env_txt,
                   "env_record.txt 含 python 版本与 pip freeze")
        self.check(str(si.get("lightgbm")) in env_txt or "lightgbm" in env_txt,
                   "env_record.txt 含 lightgbm 版本")

    # ------------------------------------------------------------------
    def run(self, root, data_path, out):
        self.audit_tag(root, "full", data_path)
        self.audit_tag(root, "dedup", data_path)

        # —— 敏感性汇总 ——
        sens_rows = []
        f = os.path.join(root, "full", "results_metrics_full.csv")
        d = os.path.join(root, "dedup", "results_metrics_dedup.csv")
        if os.path.isfile(f) and os.path.isfile(d):
            mf = pd.read_csv(f).set_index(["feature_set", "model"])
            md = pd.read_csv(d).set_index(["feature_set", "model"])
            for k in ["test_auroc", "test_auprc", "test_brier",
                      "auroc_oof_pooled", "auprc_oof_pooled", "brier_oof_pooled",
                      "auroc_mean", "auprc_mean", "brier_mean"]:
                for (fs_, mk_) in mf.index:
                    sens_rows.append({"feature_set": fs_, "model": mk_,
                                      "metric": k, "full": mf.loc[(fs_, mk_), k],
                                      "dedup": md.loc[(fs_, mk_), k],
                                      "delta_dedup_minus_full":
                                          md.loc[(fs_, mk_), k] - mf.loc[(fs_, mk_), k]})
            sens = pd.DataFrame(sens_rows)
            sens.to_csv(os.path.join(out, "sensitivity_full_vs_dedup.csv"),
                        index=False, encoding="utf-8-sig")
            self.check(True, "sensitivity_full_vs_dedup.csv 已合并生成",
                       f"{len(sens)} 行")
        else:
            self.check(False, "两版 results_metrics 齐全，可生成敏感性汇总")

        # —— 报告 ——
        self.lines.append(f"\n## 结论\n- 总检查项：{sum(1 for l in self.lines if l.startswith('- ['))}，"
                          f"FAIL {len(self.fails)} 项。")
        if self.fails:
            self.lines.append("- FAIL 项：" + "；".join(self.fails))
        else:
            self.lines.append("- 全部 PASS。")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "audit_report.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")
        print(f"审计完成：FAIL {len(self.fails)} 项，报告 -> {os.path.join(out, 'audit_report.md')}")
        for l in self.lines:
            if l.startswith("- [FAIL]"):
                print(l)
        return 1 if self.fails else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="含 full/ 与 dedup/ 的结果目录")
    ap.add_argument("--data", default="", help="data.csv 路径（核对 sha256）")
    ap.add_argument("--out", default="", help="报告输出目录（默认=--root）")
    a = ap.parse_args()
    out = a.out or a.root
    sys.exit(Auditor().run(a.root, a.data, out))


if __name__ == "__main__":
    main()
