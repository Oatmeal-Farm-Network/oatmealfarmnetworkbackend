"""
Train DINOv2 + PCA + ridge on CSIRO + Irish phone pasture images.

  python -m biomass_estimator.train_dino_multidomain \\
    --csiro-dir "C:\\Users\\supra\\Downloads\\csiro-biomass" \\
    --irish-dir "C:\\Users\\supra\\Downloads\\irish-grass-clover\\phone"
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ["BIOMASS_USE_DINO"] = "true"

from biomass_estimator.datasets import domain_balanced_indices, load_multidomain_samples
from biomass_estimator.eval_csiro import competition_weighted_r2, fit_ridge, mae, r2_score
from biomass_estimator.features import extract_features, try_dino_embedding
from biomass_estimator.model import COMPONENT_KEYS, _canopy_scores
from biomass_estimator.preprocess import prepare_dual_streams
from biomass_estimator.train_dino_csiro import fit_pca, transform_pca

TARGETS = list(COMPONENT_KEYS)
MODEL_VERSION = "pasture-dinov2-v2"


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

    def _n(v):
        return v / (np.linalg.norm(v) + 1e-8)

    mean = _n((emb_l + emb_r) / 2.0)
    diff = _n(np.abs(emb_l - emb_r))
    return np.concatenate([mean, diff, veg, np.array([1.0])]).astype(np.float64)


def _split_by_domain(samples, val_frac: float, seed: int):
    """Per-domain holdout so Irish and CSIRO are both represented in val."""
    rng = np.random.default_rng(seed)
    train_idx, val_idx = [], []
    by_dom = defaultdict(list)
    for i, s in enumerate(samples):
        by_dom[s["domain"]].append(i)
    for _dom, idxs in by_dom.items():
        idxs = list(idxs)
        rng.shuffle(idxs)
        n_val = max(1, int(len(idxs) * val_frac)) if len(idxs) > 4 else max(1, len(idxs) // 5)
        val_idx.extend(idxs[:n_val])
        train_idx.extend(idxs[n_val:])
    return train_idx, val_idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csiro-dir", default=r"C:\Users\supra\Downloads\csiro-biomass")
    ap.add_argument("--irish-dir", default=r"C:\Users\supra\Downloads\irish-grass-clover\phone")
    ap.add_argument("--img-size", type=int, default=518)
    ap.add_argument("--val-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--pca", type=int, default=64)
    ap.add_argument("--l2", type=float, default=1.0)
    ap.add_argument(
        "--save",
        default=str(Path(__file__).resolve().parent / "calibration_multidomain.npz"),
    )
    ap.add_argument(
        "--cache",
        default=str(Path(__file__).resolve().parent / "dino_feat_cache_multidomain.npz"),
    )
    ap.add_argument(
        "--use-legacy-cache",
        action="store_true",
        help="Merge old CSIRO-only dino_feat_cache.npz (may mismatch new preprocess)",
    )
    args = ap.parse_args()

    args.img_size = max(224, (args.img_size // 14) * 14)
    os.environ["BIOMASS_IMG_SIZE"] = str(args.img_size)
    os.environ["BIOMASS_USE_DINO"] = "true"

    samples = load_multidomain_samples(
        csiro_dir=Path(args.csiro_dir) if args.csiro_dir else None,
        irish_phone_dir=Path(args.irish_dir) if args.irish_dir else None,
    )
    if len(samples) < 20:
        raise SystemExit(f"Too few samples ({len(samples)}). Check --csiro-dir / --irish-dir.")

    counts = defaultdict(int)
    for s in samples:
        counts[s["domain"]] += 1
    print(f"Loaded {len(samples)} samples: {dict(counts)}")

    train_idx, val_idx = _split_by_domain(samples, args.val_frac, args.seed)
    rng = np.random.default_rng(args.seed)
    # Domain-balance the training set (oversample Irish)
    train_samples = [samples[i] for i in train_idx]
    bal_local = domain_balanced_indices(train_samples, rng)
    # map local indices back to absolute
    train_bal = [train_idx[i] for i in bal_local]

    print(f"train unique={len(train_idx)} train balanced={len(train_bal)} val={len(val_idx)}")
    print(f"img_size={args.img_size} pca={args.pca} l2={args.l2}")

    cache_path = Path(args.cache)
    feat_map = {}
    if cache_path.is_file():
        print(f"Loading feature cache {cache_path}")
        cached = np.load(cache_path, allow_pickle=True)
        for k, row in zip(cached["keys"], cached["feats"]):
            feat_map[str(k)] = row

    # Optionally reuse CSIRO-only cache (keys were relative image paths)
    legacy = Path(__file__).resolve().parent / "dino_feat_cache.npz"
    if args.use_legacy_cache and legacy.is_file():
        print(f"Merging legacy CSIRO cache {legacy}")
        cached = np.load(legacy, allow_pickle=True)
        for k, row in zip(cached["keys"], cached["feats"]):
            kid = str(k)
            feat_map.setdefault(f"csiro:{kid}", row)
            feat_map.setdefault(f"csiro:train/{Path(kid).name}", row)

    missing = [s for s in samples if s["id"] not in feat_map]
    if missing:
        print(f"Embedding {len(missing)} images with DINOv2...")
        for i, s in enumerate(missing):
            feat_map[s["id"]] = build_feature(s["path"].read_bytes(), args.img_size)
            if (i + 1) % 10 == 0 or i == 0:
                print(f"  dino {i+1}/{len(missing)}")
        keys = np.array(sorted(feat_map.keys()))
        feats = np.vstack([feat_map[k] for k in keys])
        np.savez_compressed(cache_path, keys=keys, feats=feats)
        print(f"Saved cache → {cache_path}")

    def stack(idxs):
        X, Y = [], defaultdict(list)
        domains = []
        for i in idxs:
            s = samples[i]
            if s["id"] not in feat_map:
                continue
            X.append(feat_map[s["id"]])
            domains.append(s["domain"])
            for t in TARGETS:
                Y[t].append(s["targets"][t])
        return (
            np.vstack(X),
            {t: np.asarray(Y[t], dtype=np.float64) for t in TARGETS},
            domains,
        )

    X_train, y_train, _ = stack(train_bal)
    X_val, y_val, val_domains = stack(val_idx)
    print(f"Feature dim={X_train.shape[1]} train_n={X_train.shape[0]} val_n={X_val.shape[0]}")

    Xtr_p, components, mean = fit_pca(X_train, args.pca)
    Xva_p = transform_pca(X_val, components, mean)
    weights = {t: fit_ridge(Xtr_p, y_train[t], l2=args.l2) for t in TARGETS}

    def predict_matrix(Xp):
        raw = {t: np.maximum(0.0, Xp @ weights[t]) for t in TARGETS}
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
    print("\n=== Multi-domain DINOv2 VAL (all) ===")
    r2s = {}
    for t in TARGETS:
        r2s[t] = r2_score(y_val[t], preds[t])
        print(
            f"  {t:14s}  R2={r2s[t]:+.3f}  MAE={mae(y_val[t], preds[t]):.2f}  "
            f"mean_true={y_val[t].mean():.1f} mean_pred={preds[t].mean():.1f}"
        )
    w = competition_weighted_r2(r2s)
    print(f"  Weighted R2 ~ {w:+.3f}")

    # Per-domain Total metrics
    val_domains = np.asarray(val_domains)
    for dom in sorted(set(val_domains.tolist())):
        m = val_domains == dom
        yt = y_val["Dry_Total_g"][m]
        yp = preds["Dry_Total_g"][m]
        print(
            f"  [{dom}] Total R2={r2_score(yt, yp):+.3f} MAE={mae(yt, yp):.2f}g "
            f"n={m.sum()}  (≈ kg/ha MAE={mae(yt, yp)*10/0.25:.0f})"
        )

    out = Path(args.save)
    np.savez_compressed(
        out,
        mode=np.array("dino_pca_ridge"),
        model_version=np.array(MODEL_VERSION),
        pca_components=components,
        pca_mean=mean,
        pca_dim=args.pca,
        img_size=args.img_size,
        emb_dim=384,
        veg_dim=13,
        domains=np.array(["csiro", "irish"]),
        **{f"w_{t}": weights[t] for t in TARGETS},
        val_weighted_r2=w,
        backbone=np.array("dinov2_vits14"),
    )
    print(f"\nSaved → {out.resolve()}")
    print(f"model_version={MODEL_VERSION}")
    print("Set BIOMASS_CALIBRATION_PATH to this file and BIOMASS_USE_DINO=true.")


if __name__ == "__main__":
    main()
