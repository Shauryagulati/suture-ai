"""Comparator: prediction vs ground-truth → per-field + aggregate metrics."""

from __future__ import annotations

from typing import Any

from ai.evals.flatten import flatten
from ai.evals.normalizers import (
    normalize_code,
    normalize_date,
    normalize_name,
    normalize_phone,
    normalize_string,
)

# Path-tail → normalizer. Determines how scalar field values are
# compared. Anything not in this map falls through to ``normalize_string``.
_TAIL_NORMALIZERS = {
    "first_name": normalize_name,
    "last_name": normalize_name,
    "phone": normalize_phone,
    "practice_phone": normalize_phone,
    "practice_fax": normalize_phone,
    "dob": normalize_date,
    "discharge_date": normalize_date,
    "admit_date": normalize_date,
    "cpt_code": normalize_code,
    "npi": normalize_code,
}

# Path tail → "this is a set-of-codes array". Mirrors flatten._SET_ARRAY_PATHS.
_CODE_ARRAY_TAILS = frozenset({"diagnosis_codes", "procedure_codes", "urgent_flags"})


def _tail(path: str) -> str:
    return path.rsplit(".", 1)[-1] if "." in path else path


def _normalize_scalar(path: str, value: Any) -> Any:
    if value is None:
        return None
    normalizer = _TAIL_NORMALIZERS.get(_tail(path))
    if normalizer is not None:
        return normalizer(value)
    return normalize_string(value)


def _compare_set(prediction: Any, truth: Any) -> dict[str, float | int]:
    pred = {normalize_code(v) for v in (prediction or []) if isinstance(v, str)}
    pred.discard(None)
    truth_set = {normalize_code(v) for v in (truth or []) if isinstance(v, str)}
    truth_set.discard(None)
    tp = len(pred & truth_set)
    fp = len(pred - truth_set)
    fn = len(truth_set - pred)
    precision = tp / (tp + fp) if (tp + fp) else (1.0 if not truth_set else 0.0)
    recall = tp / (tp + fn) if (tp + fn) else (1.0 if not pred else 0.0)
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    correct = pred == truth_set
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": 1.0 if correct else 0.0,
        "is_set": 1,
    }


def _compare_scalar(path: str, prediction: Any, truth: Any) -> dict[str, float | int]:
    p = _normalize_scalar(path, prediction)
    t = _normalize_scalar(path, truth)
    if t is None and p is None:
        return {"tp": 1, "fp": 0, "fn": 0, "accuracy": 1.0, "expected_present": 0}
    if t is None:
        return {"tp": 0, "fp": 1, "fn": 0, "accuracy": 0.0, "expected_present": 0}
    if p is None:
        return {"tp": 0, "fp": 0, "fn": 1, "accuracy": 0.0, "expected_present": 1}
    correct = p == t
    return {
        "tp": 1 if correct else 0,
        "fp": 0 if correct else 1,
        "fn": 0 if correct else 1,
        "accuracy": 1.0 if correct else 0.0,
        "expected_present": 1,
    }


def compare(prediction: dict[str, Any], truth: dict[str, Any]) -> dict[str, Any]:
    """Per-field + aggregate metrics for one prediction/truth pair."""
    flat_pred = flatten(prediction)
    flat_truth = flatten(truth)

    keys = set(flat_pred.keys()) | set(flat_truth.keys())
    per_field: dict[str, dict[str, float | int]] = {}

    for path in sorted(keys):
        if _tail(path) in _CODE_ARRAY_TAILS:
            per_field[path] = _compare_set(flat_pred.get(path), flat_truth.get(path))
        else:
            per_field[path] = _compare_scalar(
                path, flat_pred.get(path), flat_truth.get(path)
            )

    total = len(per_field)
    exact_matches = sum(1 for m in per_field.values() if m.get("accuracy", 0.0) == 1.0)
    f1_values = [
        float(m["f1"]) for m in per_field.values() if "f1" in m
    ]
    f1_macro = sum(f1_values) / len(f1_values) if f1_values else 0.0

    aggregate = {
        "total_fields": total,
        "exact_match_rate": exact_matches / total if total else 0.0,
        "f1_macro": f1_macro,
    }
    return {"per_field": per_field, "aggregate": aggregate}


def aggregate_runs(per_doc_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll up per-doc compare() results into corpus-wide per-field metrics."""
    field_totals: dict[str, dict[str, float | int]] = {}
    for result in per_doc_results:
        for path, metrics in result["per_field"].items():
            agg = field_totals.setdefault(
                path,
                {
                    "n": 0,
                    "tp": 0,
                    "fp": 0,
                    "fn": 0,
                    "correct": 0,
                    "is_set": int(metrics.get("is_set", 0)),
                },
            )
            agg["n"] += 1
            agg["tp"] += int(metrics.get("tp", 0))
            agg["fp"] += int(metrics.get("fp", 0))
            agg["fn"] += int(metrics.get("fn", 0))
            if metrics.get("accuracy", 0.0) == 1.0:
                agg["correct"] += 1

    per_field: dict[str, dict[str, float]] = {}
    for path, agg in field_totals.items():
        tp, fp, fn = int(agg["tp"]), int(agg["fp"]), int(agg["fn"])
        n = int(agg["n"])
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        per_field[path] = {
            "accuracy": agg["correct"] / n if n else 0.0,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "n": n,
        }

    total_correct = sum(int(v["correct"]) for v in field_totals.values())
    total_fields = sum(int(v["n"]) for v in field_totals.values())
    macro_f1 = (
        sum(v["f1"] for v in per_field.values()) / len(per_field) if per_field else 0.0
    )

    return {
        "per_field": per_field,
        "aggregate": {
            "num_docs": len(per_doc_results),
            "total_field_observations": total_fields,
            "exact_match_rate": total_correct / total_fields if total_fields else 0.0,
            "f1_macro": macro_f1,
        },
    }
