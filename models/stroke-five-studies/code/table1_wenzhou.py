# -*- coding: utf-8 -*-
"""温州 167 例队列基线表：按 PSE 结局分组（D 论文）与按 ASM 分组（E 论文）。"""
import json
import sys

import numpy as np
import pandas as pd

COLS = ["row", "stroke_type", "sex", "age", "age_lt65", "alcohol", "smoking",
        "hypertension", "diabetes", "hyperlipidemia", "hyperuricemia",
        "seizure_type", "interval_days", "interval_gt3", "multiple_seizures",
        "status_epilepticus", "eeg", "asm", "nihss", "nihss_gt14", "infection",
        "lesion_vol", "lesion_gt10", "cortical", "multilobar", "deep",
        "ventricular_ext", "surgery", "toast", "thrombolysis", "lipid_lowering",
        "antiplatelet", "anticoag", "pse", "followup_days", "late_seizure_days",
        "censor_days"]

df = pd.read_csv(sys.argv[1])
df.columns = COLS

def med_iqr(a):
    return [round(float(np.median(a)), 1), round(float(np.percentile(a, 25)), 1),
            round(float(np.percentile(a, 75)), 1)]

def block(d):
    t = {}
    t["n"] = int(len(d))
    t["age_med_iqr"] = med_iqr(d.age)
    t["sex_male_pct"] = round(float(d.sex.mean()) * 100, 1)
    t["stroke_ischemic_pct"] = round(float((d.stroke_type == 1).mean()) * 100, 1)
    t["nihss_med_iqr"] = med_iqr(d.nihss)
    t["interval_days_med_iqr"] = med_iqr(d.interval_days)
    t["interval_gt3_pct"] = round(float(d.interval_gt3.mean()) * 100, 1)
    t["multiple_seizures_pct"] = round(float(d.multiple_seizures.mean()) * 100, 1)
    t["status_epilepticus_pct"] = round(float(d.status_epilepticus.mean()) * 100, 1)
    t["cortical_pct"] = round(float(d.cortical.mean()) * 100, 1)
    t["eeg_epileptic_pct"] = round(float((d.eeg == 1).mean()) * 100, 1)
    t["eeg_nonspecific_pct"] = round(float((d.eeg == 2).mean()) * 100, 1)
    t["eeg_normal_pct"] = round(float((d.eeg == 3).mean()) * 100, 1)
    t["sz_focal_pct"] = round(float((d.seizure_type == 1).mean()) * 100, 1)
    t["sz_btc_pct"] = round(float((d.seizure_type == 2).mean()) * 100, 1)
    t["sz_other_pct"] = round(float((d.seizure_type == 3).mean()) * 100, 1)
    t["hypertension_pct"] = round(float(d.hypertension.mean()) * 100, 1)
    t["diabetes_pct"] = round(float(d.diabetes.mean()) * 100, 1)
    t["hyperlipidemia_pct"] = round(float(d.hyperlipidemia.mean()) * 100, 1)
    t["hyperuricemia_pct"] = round(float(d.hyperuricemia.mean()) * 100, 1)
    t["smoking_pct"] = round(float(d.smoking.mean()) * 100, 1)
    t["alcohol_pct"] = round(float(d.alcohol.mean()) * 100, 1)
    t["infection_pct"] = round(float(d.infection.mean()) * 100, 1)
    t["lesion_vol_med_iqr"] = med_iqr(d.lesion_vol)
    t["multilobar_pct"] = round(float(d.multilobar.mean()) * 100, 1)
    t["deep_pct"] = round(float(d.deep.mean()) * 100, 1)
    t["asm_pct"] = round(float(d.asm.mean()) * 100, 1)
    t["followup_days_med_iqr"] = med_iqr(d.followup_days)
    t["nihss_gt14_pct"] = round(float(d.nihss_gt14.mean()) * 100, 1)
    t["thrombolysis_pct"] = round(float(d.thrombolysis.mean()) * 100, 1)
    t["surgery_pct"] = round(float(d.surgery.mean()) * 100, 1)
    return t

out = {
    "overall": block(df),
    "by_pse": {"pse_1": block(df[df.pse == 1]), "pse_0": block(df[df.pse == 0])},
    "by_asm": {"asm_1": block(df[df.asm == 1]), "asm_0": block(df[df.asm == 0])},
    "late_seizure_days": {
        "median": float(np.median(df.loc[df.pse == 1, "late_seizure_days"])),
        "min": float(df.loc[df.pse == 1, "late_seizure_days"].min()),
        "max": float(df.loc[df.pse == 1, "late_seizure_days"].max()),
        "n_le30d": int((df.loc[df.pse == 1, "late_seizure_days"] <= 30).sum()),
        "n_le90d": int((df.loc[df.pse == 1, "late_seizure_days"] <= 90).sum()),
    },
}
print(json.dumps(out, ensure_ascii=False, indent=1))
