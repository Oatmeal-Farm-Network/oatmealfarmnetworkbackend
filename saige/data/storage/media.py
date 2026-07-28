# --- data/storage/media.py ---
from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, Optional, Tuple

from config import (
    GCP_PROJECT,
    SAIGE_MEDIA_GCS_BUCKET,
    SAIGE_MEDIA_GCS_PREFIX,
    SAIGE_MEDIA_LOCAL_DIR,
)

logger = logging.getLogger("farm_advisory.media")


def _object_name(business_id: str, people_id: str, ext: str = "jpg") -> str:
    return f"{SAIGE_MEDIA_GCS_PREFIX}/{business_id}/{people_id}/{uuid.uuid4().hex}.{ext}"


def store_bytes(
    *,
    data: bytes,
    people_id: str,
    business_id: str = "unknown",
    content_type: str = "image/jpeg",
    ext: str = "jpg",
) -> Dict[str, Any]:
    """Upload to GCS when bucket configured; otherwise local fallback."""
    if not data:
        raise ValueError("empty upload")

    object_name = _object_name(business_id or "unknown", people_id or "anon", ext=ext)

    if SAIGE_MEDIA_GCS_BUCKET:
        try:
            from google.cloud import storage

            client = storage.Client(project=GCP_PROJECT or None)
            bucket = client.bucket(SAIGE_MEDIA_GCS_BUCKET)
            blob = bucket.blob(object_name)
            blob.upload_from_string(data, content_type=content_type)
            uri = f"gs://{SAIGE_MEDIA_GCS_BUCKET}/{object_name}"
            logger.info("[Media] GCS upload %s (%s bytes)", uri, len(data))
            return {
                "status": "ok",
                "backend": "gcs",
                "bucket": SAIGE_MEDIA_GCS_BUCKET,
                "object": object_name,
                "uri": uri,
                "filename": os.path.basename(object_name),
                "bytes": len(data),
                "content_type": content_type,
            }
        except Exception as e:
            logger.exception("[Media] GCS upload failed: %s", e)
            raise RuntimeError(f"GCS upload failed: {e}") from e

    # Local fallback (dev only)
    os.makedirs(SAIGE_MEDIA_LOCAL_DIR, exist_ok=True)
    fname = os.path.basename(object_name)
    path = os.path.join(SAIGE_MEDIA_LOCAL_DIR, fname)
    with open(path, "wb") as f:
        f.write(data)
    logger.warning("[Media] Stored locally (no SAIGE_MEDIA_GCS_BUCKET): %s", path)
    return {
        "status": "ok",
        "backend": "local",
        "bucket": None,
        "object": fname,
        "uri": path,
        "path": path,
        "filename": fname,
        "bytes": len(data),
        "content_type": content_type,
        "message": "Stored locally; set SAIGE_MEDIA_GCS_BUCKET for production.",
    }


def signed_download_url(object_name: str, *, minutes: int = 60) -> Optional[str]:
    if not SAIGE_MEDIA_GCS_BUCKET or not object_name:
        return None
    try:
        from datetime import timedelta

        from google.cloud import storage

        client = storage.Client(project=GCP_PROJECT or None)
        blob = client.bucket(SAIGE_MEDIA_GCS_BUCKET).blob(object_name)
        return blob.generate_signed_url(expiration=timedelta(minutes=minutes), method="GET")
    except Exception as e:
        logger.warning("[Media] signed URL failed: %s", e)
        return None
