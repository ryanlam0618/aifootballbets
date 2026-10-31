"""Self-built shot xG model (Layer-2 afb-T3a/b/c).

Trains an XGBoost regressor (plus a LinearRegression control) on shots that
HAVE an official SofaScore xG, using only pre-shot physical/context features:

- distance to goal centre (metres, from SofaScore percentage coordinates)
- shot angle (radians, law of cosines on the two goal posts)
- shot_type / situation / body_part (one-hot)
- is_home

T3b: isotonic calibration maps self-built xG onto the official xG scale
(fitted on the calibration slice of the training data — never on evaluation
slices).

T3c: shots WITHOUT official xG get the calibrated prediction and are marked
xg_source='calibrated' (official rows keep 'official').

No leakage rule (T3d): rolling windows are computed strictly from matches
BEFORE the reference match.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# SofaScore pitch: x in [0,100] toward the opponent goal, y in [0,100] across.
PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
GOAL_X = 100.0
GOAL_Y_CENTRE = 50.0
GOAL_HALF_WIDTH_M = 3.66


def shot_features(x: float, y: float, shot_type: Optional[str], situation: Optional[str], body_part: Optional[str]) -> Dict[str, float]:
    """Physical/context features for one shot (all numeric, model-ready)."""
    dx_m = (GOAL_X - float(x)) * PITCH_LENGTH_M / 100.0
    dy_m = (float(y) - GOAL_Y_CENTRE) * PITCH_WIDTH_M / 100.0
    distance = math.sqrt(dx_m**2 + dy_m**2)
    # angle between the lines from the shot to both posts
    p1 = (dx_m, -GOAL_HALF_WIDTH_M)
    p2 = (dx_m, GOAL_HALF_WIDTH_M)
    denom = (math.hypot(*p1) * math.hypot(*p2))
    if denom > 0:
        cos_a = (p1[0] * p2[0] + p1[1] * p2[1]) / denom
        angle = math.acos(max(-1.0, min(1.0, cos_a)))
    else:
        angle = 0.0
    feats = {
        "distance_m": distance,
        "angle_rad": angle,
        "x": float(x),
        "y": float(y),
    }
    for col, value in (("shot_type", shot_type), ("situation", situation), ("body_part", body_part)):
        key = (str(value) or "unknown").strip().lower() or "unknown"
        feats[f"{col}__{key}"] = 1.0
    return feats


def build_feature_matrix(rows: List[dict]) -> Tuple[List[Dict[str, float]], List[str]]:
    """Convert shot rows (dicts with x/y/shot_type/situation/body_part) to
    feature dicts; returns (feature_dicts, sorted_feature_names)."""
    dicts = [
        shot_features(
            r["x"], r["y"], r.get("shot_type"), r.get("situation"), r.get("body_part")
        )
        for r in rows
    ]
    names = sorted({k for d in dicts for k in d})
    return dicts, names


def dicts_to_matrix(dicts: List[Dict[str, float]], names: List[str]) -> List[List[float]]:
    return [[d.get(n, 0.0) for n in names] for d in dicts]


@dataclass
class XGTrainResult:
    model: object                  # fitted XGBRegressor
    lr_model: object               # fitted LinearRegression (control)
    feature_names: List[str]
    n_train: int
    n_calib: int
    n_test: int
    calibrator: List[Tuple[float, float]]  # isotonic breakpoints (T3b)
    metrics: dict


def train_shot_xg(
    shots: List[dict],
    test_frac: float = 0.15,
    calib_frac: float = 0.15,
    random_state: int = 42,
) -> XGTrainResult:
    """Train on shots with official xG.

    Chronological split (shots sorted by match_date): first (1-test-frac)
    = train, next calib_frac = isotonic calibration, last test_frac = held-out
    evaluation. No random shuffle (time ordering matters for shot/context
    drift).
    """
    import numpy as np
    from sklearn.linear_model import LinearRegression
    from xgboost import XGBRegressor

    from models.calibration import isotonic_pava

    shots = sorted(shots, key=lambda s: (s["match_date"], s.get("shot_id") or 0))
    n = len(shots)
    n_test = int(n * test_frac)
    n_calib = int(n * calib_frac)
    n_train = n - n_test - n_calib
    if n_train < 1000 or n_calib < 200 or n_test < 200:
        raise ValueError(f"insufficient shots: train={n_train} calib={n_calib} test={n_test}")

    train_s = shots[:n_train]
    calib_s = shots[n_train : n_train + n_calib]
    test_s = shots[n_train + n_calib :]

    dicts, names = build_feature_matrix(train_s)
    X_train = np.array(dicts_to_matrix(dicts, names))
    y_train = np.array([float(s["xg"]) for s in train_s])

    model = XGBRegressor(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="reg:squarederror",
        tree_method="hist",
        random_state=random_state,
        n_jobs=4,
    )
    model.fit(X_train, y_train)

    lr = LinearRegression()
    lr.fit(X_train, y_train)

    def _predict_rows(rows: List[dict]) -> "np.ndarray":
        d, _ = build_feature_matrix(rows)
        return model.predict(np.array(dicts_to_matrix(d, names)))

    # T3b: isotonic calibration on the calibration slice (pred -> official)
    calib_pred = _predict_rows(calib_s)
    calib_official = [float(s["xg"]) for s in calib_s]
    calibrator = isotonic_pava(list(zip(calib_pred, calib_official)))

    def _calibrate(vals: "np.ndarray") -> List[float]:
        from models.calibration import isotonic_predict

        return [isotonic_predict(calibrator, float(v)) for v in vals]

    # held-out evaluation: raw vs calibrated vs LR control
    test_pred = _predict_rows(test_s)
    test_official = [float(s["xg"]) for s in test_s]
    test_pred_cal = _calibrate(test_pred)
    lr_test = lr.predict(np.array(dicts_to_matrix(build_feature_matrix(test_s)[0], names)))

    def _metrics(pred: List[float]) -> dict:
        pred = [float(p) for p in pred]
        err = [p - o for p, o in zip(pred, test_official)]
        mae = sum(abs(e) for e in err) / len(err)
        rmse = math.sqrt(sum(e * e for e in err) / len(err))
        mean_o = sum(test_official) / len(test_official)
        var_o = sum((o - mean_o) ** 2 for o in test_official) / len(test_official)
        cov = sum((p - sum(pred) / len(pred)) * (o - mean_o) for p, o in zip(pred, test_official)) / len(pred)
        sd_p = math.sqrt(sum((p - sum(pred) / len(pred)) ** 2 for p in pred) / len(pred))
        corr = cov / (math.sqrt(var_o) * sd_p) if var_o > 0 and sd_p > 0 else 0.0
        return {"mae": round(float(mae), 5), "rmse": round(float(rmse), 5), "pearson_r": round(float(corr), 5)}

    metrics = {
        "test_raw": _metrics(list(test_pred)),
        "test_calibrated": _metrics(test_pred_cal),
        "test_lr_control": _metrics([float(v) for v in lr_test]),
        "mean_official_test": round(sum(test_official) / len(test_official), 5),
    }

    return XGTrainResult(
        model=model,
        lr_model=lr,
        feature_names=names,
        n_train=n_train,
        n_calib=n_calib,
        n_test=n_test,
        calibrator=calibrator,
        metrics=metrics,
    )


def calibrate_value(raw_pred: float, calibrator: List[Tuple[float, float]]) -> float:
    from models.calibration import isotonic_predict

    return isotonic_predict(calibrator, float(raw_pred))


__all__ = [
    "XGTrainResult",
    "build_feature_matrix",
    "calibrate_value",
    "shot_features",
    "train_shot_xg",
]
