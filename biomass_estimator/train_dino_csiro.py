"""
Train dual-stream DINOv2 + vegetation ridge heads on CSIRO train.csv.

One-time local cost (download DINOv2 weights + embed all train images).
No paid vision APIs.

  python -m biomass_estimator.train_dino_csiro --data-dir "C:\\Users\\supra\\Downloads\\csiro-biomass"
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ["BIOMASS_USE_DINO"] = "true"

from biomass_estimator.features import extract_features, try_dino_embedding
from biomass_estimator.model import COMPONENT_KEYS, _canopy_scores
from biomass_estimator.preprocess import prepare_dual_streams
from biomass_estimator.eval_csiro import (
    load_train_wide,
    r2_score,
    mae,
    competition_weighted_r2,
    fit_ridge,
)

TARGETS = list(COMPONENT_KEYS)


def build_feature(image_bytes: bytes, img_size: int) -> np.ndarray:
    full, left, right, _mode = prepare_dual_streams(image_bytes, img_size=img_size)
    bundle = extract_features(left, right, full)
    scores = _canopy_scores(bundle["fused"])
    fused = bundle["fused"]
    veg = np.array(
        [
            scores["green_score"],
            scores["dead_score"],
            scores["clover_score"],
            scores["cover"],
            scores["exg_n"],
            scores["vari_n"],
            fused.get("green_frac", 0.0),
            fused.get("dead_frac", 0.0),
            fused.get("soil_frac", 0.0),
            fused.get("brightness_mean", 0.0),
            fused.get("brightness_std", 0.0),
            fused.get("exg_mean", 0.0),
            fused.get("vari_mean", 0.0),
        ],
        dtype=np.float64,
    )

    emb_l = try_dino_embedding(left)
    emb_r = try_dino_embedding(right)
    if emb_l is None or emb_r is None:
        raise RuntimeError("DINOv2 embedding failed — is torch installed and BIOMASS_USE_DINO=true?")

    mean = (emb_l + emb_r) / 2.0
    diff = np.abs(emb_l - emb_r)
    # L2-normalize embedding parts for stable ridge
    def _n(v):
        n = np.linalg.norm(v) + 1e-8
        return v / n

    feat = np.concatenate([_n(mean), _n(diff), veg, np.array([1.0])])
    return feat.astype(np.float64)


def fit_pca(X: np.ndarray, n_components: int):
    """PCA on all but bias column; returns (X_reduced_with_bias, components, mean)."""
    bias = X[:, -1:]
    Z = X[:, :-1]
    mean = Z.mean(axis=0)
    Zc = Z - mean
    # economy SVD
    _, _, vt = np.linalg.svd(Zc, full_matrices=False)
    n_components = min(n_components, vt.shape[0])
    components = vt[:n_components]
    Zr = Zc @ components.T
    return np.hstack([Zr, bias]), components, mean


def transform_pca(X: np.ndarray, components: np.ndarray, mean: np.ndarray) -> np.ndarray:
    bias = X[:, -1:]
    Z = X[:, :-1]
    Zr = (Z - mean) @ components.T
    return np.hstack([Zr, bias])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True)
    ap.add_argument("--img-size", type=int, default=518)  # multiple of 14 near 512
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--pca", type=int, default=64)
    ap.add_argument("--l2", type=float, default=1.0)
    ap.add_argument(
        "--save",
        default=str(Path(__file__).resolve().parent / "calibration_dino.npz"),
    )
    ap.add_argument("--cache", default=str(Path(__file__).resolve().parent / "dino_feat_cache.npz"))
    args = ap.parse_args()

    # Snap img size to multiple of 14
    args.img_size = max(224, (args.img_size // 14) * 14)
    os.environ["BIOMASS_IMG_SIZE"] = str(args.img_size)
    os.environ["BIOMASS_USE_DINO"] = "true"

    data_dir = Path(args.data_dir)
    labels, _ = load_train_wide(data_dir)
    images = sorted(labels.keys())
    rng = np.random.default_rng(args.seed)
    idx = np.arange(len(images))
    rng.shuffle(idx)
    n_val = max(1, int(len(images) * args.val_frac))
    val_set = set(idx[:n_val].tolist())
    train_rels = [images[i] for i in idx if i not in val_set]
    val_rels = [images[i] for i in idx if i in val_set]

    print(f"DINOv2 dual-stream train | images={len(images)} train={len(train_rels)} val={len(val_rels)}")
    print(f"img_size={args.img_size} pca={args.pca} l2={args.l2}")
    print("Loading DINOv2 (first call downloads weights once)...")

    cache_path = Path(args.cache)
    feat_map = {}
    if cache_path.is_file():
        print(f"Loading feature cache {cache_path}")
        cached = np.load(cache_path, allow_pickle=True)
        keys = list(cached["keys"])
        mats = cached["feats"]
        for k, row in zip(keys, mats):
            feat_map[str(k)] = row

    missing = [r for r in images if r not in feat_map]
    if missing:
        print(f"Embedding {len(missing)} images with DINOv2...")
        for i, rel in enumerate(missing):
            path = data_dir / rel
            if not path.is_file():
                print(f"  SKIP missing file {rel}")
                continue
            feat_map[rel] = build_feature(path.read_bytes(), args.img_size)
            if (i + 1) % 10 == 0 or i == 0:
                print(f"  dino {i+1}/{len(missing)}")
        keys = np.array(sorted(feat_map.keys()))
        feats = np.vstack([feat_map[k] for k in keys])
        np.savez_compressed(cache_path, keys=keys, feats=feats)
        print(f"Saved cache → {cache_path}")

    def stack(rels):
        X, Y = [], defaultdict(list)
        for rel in rels:
            if rel not in feat_map:
                continue
            X.append(feat_map[rel])
            for t in TARGETS:
                Y[t].append(labels[rel][t])
        return np.vstack(X), {t: np.asarray(Y[t], dtype=np.float64) for t in TARGETS}

    X_train, y_train = stack(train_rels)
    X_val, y_val = stack(val_rels)
    print(f"Feature dim={X_train.shape[1]} train_n={X_train.shape[0]} val_n={X_val.shape[0]}")

    Xtr_p, components, mean = fit_pca(X_train, args.pca)
    Xva_p = transform_pca(X_val, components, mean)

    weights = {t: fit_ridge(Xtr_p, y_train[t], l2=args.l2) for t in TARGETS}

    def predict_matrix(Xp):
        raw = {t: np.maximum(0.0, Xp @ weights[t]) for t in TARGETS}
        # physics post-hoc
        green, dead, clover = raw["Dry_Green_g"], raw["Dry_Dead_g"], raw["Dry_Clover_g"] * 0.8
        dead = np.where(dead > 20, dead * 1.1, np.where(dead < 10, dead * 0.9, dead))
        gdm = green + clover
        total = gdm + dead
        return {
            "Dry_Green_g": green,
            "Dry_Dead_g": dead,
            "Dry_Clover_g": clover,
            "GDM_g": gdm,
            "Dry_Total_g": total,
        }

    preds = predict_matrix(Xva_p)
    print("\n=== DINOv2 + PCA + ridge on VAL ===")
    r2s = {}
    for t in TARGETS:
        r2s[t] = r2_score(y_val[t], preds[t])
        print(
            f"  {t:14s}  R2={r2s[t]:+.3f}  MAE={mae(y_val[t], preds[t]):.2f}  "
            f"mean_true={y_val[t].mean():.1f} mean_pred={preds[t].mean():.1f}"
        )
    w = competition_weighted_r2(r2s)
    print(f"  Weighted R2 ~ {w:+.3f}")

    out = Path(args.save)
    np.savez_compressed(
        out,
        mode=np.array("dino_pca_ridge"),
        pca_components=components,
        pca_mean=mean,
        pca_dim=args.pca,
        img_size=args.img_size,
        emb_dim=384,  # dinov2_vits14
        veg_dim=13,
        **{f"w_{t}": weights[t] for t in TARGETS},
        val_weighted_r2=w,
        backbone=np.array("dinov2_vits14"),
    )
    print(f"\nSaved → {out.resolve()}")
    print("Set BIOMASS_USE_DINO=true and BIOMASS_CALIBRATION_PATH to this file.")


if __name__ == "__main__":
    main()
