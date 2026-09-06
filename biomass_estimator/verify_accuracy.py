"""
Verify DINOv2-calibrated estimator against labeled CSIRO train holdout.
Competition test.csv has no public labels — this is the honest public verification.

  python -m biomass_estimator.verify_accuracy --data-dir "C:\\Users\\supra\\Downloads\\csiro-biomass"
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import numpy as np

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ.setdefault("BIOMASS_USE_DINO", "true")
os.environ.setdefault(
    "BIOMASS_CALIBRATION_PATH",
    str(Path(__file__).resolve().parent / "calibration_dino.npz"),
)

from biomass_estimator.eval_csiro import (
    load_train_wide,
    r2_score,
    mae,
    competition_weighted_r2,
)
from biomass_estimator.model import COMPONENT_KEYS
from biomass_estimator import estimate_biomass_from_image

TARGETS = list(COMPONENT_KEYS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--examples", type=int, default=12)
    ap.add_argument("--max-images", type=int, default=0, help="limit for speed; 0=all val")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    labels, meta = load_train_wide(data_dir)
    images = sorted(labels.keys())
    rng = np.random.default_rng(args.seed)
    idx = np.arange(len(images))
    rng.shuffle(idx)
    n_val = max(1, int(len(images) * args.val_frac))
    val_rels = [images[i] for i in idx[:n_val]]
    if args.max_images > 0:
        val_rels = val_rels[: args.max_images]

    print("=" * 72)
    print("PUBLIC VERIFICATION (CSIRO train holdout — test labels are NOT public)")
    print(f"Data: {data_dir}")
    print(f"Holdout images: {len(val_rels)} | seed={args.seed} val_frac={args.val_frac}")
    print(f"Calib: {os.environ.get('BIOMASS_CALIBRATION_PATH')}")
    print("=" * 72)

    preds = {t: [] for t in TARGETS}
    trues = {t: [] for t in TARGETS}
    examples = []
    versions = set()

    for i, rel in enumerate(val_rels):
        path = data_dir / rel
        if not path.is_file():
            continue
        out = estimate_biomass_from_image(path.read_bytes())
        versions.add(out["model_version"])
        comps = out["features"]["components"]
        for t in TARGETS:
            preds[t].append(float(comps[t]))
            trues[t].append(float(labels[rel][t]))
        if len(examples) < args.examples:
            examples.append(
                {
                    "image": Path(rel).name,
                    "version": out["model_version"],
                    "true_total": labels[rel]["Dry_Total_g"],
                    "pred_total": comps["Dry_Total_g"],
                    "true_green": labels[rel]["Dry_Green_g"],
                    "pred_green": comps["Dry_Green_g"],
                    "true_dead": labels[rel]["Dry_Dead_g"],
                    "pred_dead": comps["Dry_Dead_g"],
                    "err_total": abs(comps["Dry_Total_g"] - labels[rel]["Dry_Total_g"]),
                }
            )
        if (i + 1) % 20 == 0:
            print(f"  scored {i+1}/{len(val_rels)}...")

    print(f"\nModel version(s) used: {sorted(versions)}")
    print("\n--- Metrics vs laboratory ground truth (grams) ---")
    r2s = {}
    for t in TARGETS:
        r2s[t] = r2_score(trues[t], preds[t])
        print(
            f"  {t:14s}  R2={r2s[t]:+.3f}  MAE={mae(trues[t], preds[t]):.2f}g  "
            f"mean_true={np.mean(trues[t]):.1f}  mean_pred={np.mean(preds[t]):.1f}"
        )
    w = competition_weighted_r2(r2s)
    print(f"\n  Competition-style weighted R2: {w:+.3f}")
    print("  (Kaggle 1st place was ~0.67–0.77 private; random/heuristic is << 0)")

    print("\n--- Example images: true vs pred (Dry_Total_g) ---")
    print(f"{'image':22s} {'true':>8s} {'pred':>8s} {'|err|':>8s} {'green T/P':>14s} {'dead T/P':>14s}")
    for e in examples:
        print(
            f"{e['image']:22s} {e['true_total']:8.1f} {e['pred_total']:8.1f} {e['err_total']:8.1f} "
            f"{e['true_green']:5.1f}/{e['pred_green']:5.1f}   {e['true_dead']:5.1f}/{e['pred_dead']:5.1f}"
        )

    # Sanity: kg/ha conversion note
    print("\n--- Note on UI kg DM/ha ---")
    print("CSIRO labels are grams in a ~0.21 m2 quadrat (70x30 cm).")
    print("UI converts Total_g -> kg/ha via BIOMASS_SAMPLE_AREA_M2 (default 0.25).")
    print("Compare accuracy in GRAMS above; kg/ha scales that number.")
    print("=" * 72)


if __name__ == "__main__":
    main()
