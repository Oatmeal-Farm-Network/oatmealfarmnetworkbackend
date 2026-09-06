"""
Ensure Google Cloud resources needed for photo biomass uploads exist.

Requires Application Default Credentials:
  gcloud auth application-default login

Usage (from backend/):
  .\\.venv\\Scripts\\python.exe scripts\\ensure_biomass_gcs.py
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    try:
        from google.cloud import storage
    except ImportError:
        print("google-cloud-storage not installed", file=sys.stderr)
        return 1

    bucket_name = os.getenv("BIOMASS_GCS_BUCKET", "oatmeal-farm-network-images")
    prefix = os.getenv("BIOMASS_GCS_PREFIX", "biomass-uploads").strip("/")
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT")

    try:
        client = storage.Client(project=project) if project else storage.Client()
    except Exception as e:
        print(f"Auth failed: {e}", file=sys.stderr)
        print("Run: gcloud auth application-default login", file=sys.stderr)
        return 2

    bucket = client.lookup_bucket(bucket_name)
    if bucket:
        print(f"Bucket exists: gs://{bucket_name} (location={bucket.location})")
    else:
        location = os.getenv("BIOMASS_GCS_LOCATION", "US")
        print(f"Creating gs://{bucket_name} in {location} (project={client.project})...")
        bucket = client.create_bucket(bucket_name, location=location)
        print(f"Created gs://{bucket_name}")

    marker = bucket.blob(f"{prefix}/.keep")
    if not marker.exists():
        marker.upload_from_string(b"", content_type="text/plain")
        print(f"Wrote gs://{bucket_name}/{prefix}/.keep")
    else:
        print(f"Prefix ready: gs://{bucket_name}/{prefix}/")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
