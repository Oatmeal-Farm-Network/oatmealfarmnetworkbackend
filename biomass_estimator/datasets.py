"""Multi-domain labeled biomass loaders (CSIRO grams + Irish kg DM/ha)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .model import COMPONENT_KEYS

# Irish phone/camera quadrat is 0.5 × 0.5 m
IRISH_SAMPLE_AREA_M2 = 0.25


def _kg_ha_to_grams(kg_ha: float, area_m2: float = IRISH_SAMPLE_AREA_M2) -> float:
    return float(kg_ha) * float(area_m2) / 10.0


def load_csiro_samples(data_dir: Path) -> List[Dict[str, Any]]:
    """CSIRO Image2Biomass train rows → list of {path, domain, targets}."""
    from .eval_csiro import load_train_wide

    labels, _meta = load_train_wide(data_dir)
    out: List[Dict[str, Any]] = []
    for rel, targets in labels.items():
        path = data_dir / rel
        if not path.is_file():
            alt = data_dir / "train" / Path(rel).name
            path = alt if alt.is_file() else path
        if not path.is_file():
            continue
        comps = {k: float(targets.get(k, 0.0)) for k in COMPONENT_KEYS}
        out.append(
            {
                "id": f"csiro:{rel}",
                "path": path,
                "domain": "csiro",
                "targets": comps,
            }
        )
    return out


def _parse_irish_csv(csv_path: Path, images_dir: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            name = (r.get("Image Name") or r.get("image") or "").strip()
            if not name:
                continue
            path = images_dir / name
            if not path.is_file():
                continue
            kg_ha = float(r["Herbage Mass (kg DM/ha)"])
            total = _kg_ha_to_grams(kg_ha)
            grass_p = float(r.get("Grass Dried") or 0.0)
            clover_p = float(r.get("Clover Dried") or 0.0)
            weeds_p = float(r.get("Weeds Dried") or 0.0)
            # Percentages → grams; weeds stand in for senescent/other (CSIRO Dead)
            green = total * grass_p / 100.0
            clover = total * clover_p / 100.0
            dead = total * weeds_p / 100.0
            # Reconcile to Total (physics)
            parts = green + clover + dead
            if parts > 1e-6 and abs(parts - total) / max(total, 1e-6) > 0.02:
                scale = total / parts
                green *= scale
                clover *= scale
                dead *= scale
            gdm = green + clover
            targets = {
                "Dry_Green_g": green,
                "Dry_Dead_g": dead,
                "Dry_Clover_g": clover,
                "GDM_g": gdm,
                "Dry_Total_g": total,
            }
            rows.append(
                {
                    "id": f"irish:{name}",
                    "path": path,
                    "domain": "irish",
                    "targets": targets,
                    "kg_ha": kg_ha,
                }
            )
    return rows


def load_irish_phone_samples(
    phone_dir: Path,
    splits: Optional[Tuple[str, ...]] = ("train", "val"),
) -> List[Dict[str, Any]]:
    """
    Irish VistaMilk phone GT.
    phone_dir should contain phone_gt_train.csv, phone_gt_val.csv, images/
    """
    images_dir = phone_dir / "images"
    out: List[Dict[str, Any]] = []
    mapping = {
        "train": phone_dir / "phone_gt_train.csv",
        "val": phone_dir / "phone_gt_val.csv",
    }
    for split in splits:
        csv_path = mapping.get(split)
        if csv_path and csv_path.is_file():
            out.extend(_parse_irish_csv(csv_path, images_dir))
    return out


def load_multidomain_samples(
    csiro_dir: Optional[Path] = None,
    irish_phone_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    if csiro_dir and Path(csiro_dir).is_dir():
        samples.extend(load_csiro_samples(Path(csiro_dir)))
    if irish_phone_dir and Path(irish_phone_dir).is_dir():
        samples.extend(load_irish_phone_samples(Path(irish_phone_dir)))
    return samples


def domain_balanced_indices(
    samples: List[Dict[str, Any]],
    rng,
    target_per_domain: Optional[int] = None,
) -> List[int]:
    """
    Oversample minority domains so each domain contributes similarly often.
    Returns a list of sample indices (with repeats).
    """
    by_dom: Dict[str, List[int]] = {}
    for i, s in enumerate(samples):
        by_dom.setdefault(s["domain"], []).append(i)
    if not by_dom:
        return []
    n_max = max(len(v) for v in by_dom.values())
    if target_per_domain is None:
        target_per_domain = n_max
    out: List[int] = []
    for _dom, idxs in by_dom.items():
        if not idxs:
            continue
        chosen = list(idxs)
        while len(chosen) < target_per_domain:
            chosen.append(int(rng.choice(idxs)))
        if len(chosen) > target_per_domain:
            chosen = list(rng.choice(chosen, size=target_per_domain, replace=False))
        out.extend(chosen)
    rng.shuffle(out)
    return out
