"""Image decode, resize, ImageNet-style normalize, left/right split."""

from __future__ import annotations

import io
from typing import Tuple

import numpy as np
from PIL import Image

IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def load_rgb(image_bytes: bytes) -> np.ndarray:
    """Decode image bytes to float32 RGB array in [0, 1], shape (H, W, 3)."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")
    arr = np.asarray(img, dtype=np.float32) / 255.0
    return arr


def resize_square(rgb: np.ndarray, size: int) -> np.ndarray:
    """Resize to size×size with bilinear via Pillow."""
    h, w = rgb.shape[:2]
    if h == size and w == size:
        return rgb
    img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    img = img.resize((size, size), Image.Resampling.BILINEAR)
    return np.asarray(img, dtype=np.float32) / 255.0


def resize_hw(rgb: np.ndarray, height: int, width: int) -> np.ndarray:
    img = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8))
    img = img.resize((width, height), Image.Resampling.BILINEAR)
    return np.asarray(img, dtype=np.float32) / 255.0


def is_dual_frame(rgb: np.ndarray) -> bool:
    """
    Detect CSIRO-style side-by-side dual camera frames.
    Phone / single pasture photos return False.
    """
    h, w = rgb.shape[:2]
    aspect = w / max(h, 1)
    if aspect >= 1.55:
        return True
    if aspect >= 1.25:
        mid = w // 2
        left_edge = rgb[:, max(0, mid - 3) : mid, :].mean(axis=(0, 1))
        right_edge = rgb[:, mid : min(w, mid + 3), :].mean(axis=(0, 1))
        if float(np.linalg.norm(left_edge - right_edge)) > 0.12:
            return True
    return False


def split_left_right(rgb: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Split wide image into left and right halves — CSIRO dual-stream."""
    h, w = rgb.shape[:2]
    mid = w // 2
    if mid < 1:
        return rgb.copy(), rgb.copy()
    left = rgb[:, :mid, :]
    right = rgb[:, mid:, :]
    target_w = min(left.shape[1], right.shape[1])
    if left.shape[1] != target_w:
        left = left[:, :target_w, :]
    if right.shape[1] != target_w:
        right = right[:, :target_w, :]
    return left, right


def to_imagenet_tensor(rgb: np.ndarray) -> np.ndarray:
    """CHW float32 normalized for optional torch backbones."""
    x = (rgb - IMAGENET_MEAN) / IMAGENET_STD
    return np.transpose(x, (2, 0, 1)).astype(np.float32)


def prepare_dual_streams(image_bytes: bytes, img_size: int = 512):
    """
    Full preprocess pipeline.
    Returns: full_rgb, left_rgb, right_rgb, stream_mode ("dual" | "single").
    Single phone/crop photos are NOT bisected — both streams are the full frame.
    """
    rgb = load_rgb(image_bytes)
    dual = is_dual_frame(rgb)
    full = resize_square(rgb, img_size)

    if dual:
        h, w = rgb.shape[:2]
        # Preserve wide layout: height → img_size, width scales, then split.
        new_h = img_size
        new_w = max(img_size * 2, int(round(w * (img_size / max(h, 1)))))
        wide = resize_hw(rgb, new_h, new_w)
        left, right = split_left_right(wide)
        left = resize_square(left, img_size)
        right = resize_square(right, img_size)
        return full, left, right, "dual"

    # Single view: identical streams (diff embedding → 0; mean = full embedding)
    return full, full.copy(), full.copy(), "single"
