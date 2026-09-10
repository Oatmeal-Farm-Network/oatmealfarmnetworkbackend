"""
Ensure cloud + DB resources for photo biomass uploads.

Creates/verifies:
  1. FieldBiomassAnalysis table (Cloud SQL / SQL Server)
  2. GCS bucket + biomass-uploads/ prefix (optional public read for thumbnails)

Requires:
  - backend/.env with DB_* (same as the API)
  - Google ADC for GCS: gcloud auth application-default login
    OR GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json
    OR GOOGLE_CLOUD_PROJECT + workload identity on Cloud Run

Usage (from backend/):
  .\\.venv\\Scripts\\python.exe scripts\\ensure_biomass_cloud.py
  .\\.venv\\Scripts\\python.exe scripts\\ensure_biomass_cloud.py --skip-gcs
  .\\.venv\\Scripts\\python.exe scripts\\ensure_biomass_cloud.py --skip-db
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv

load_dotenv(_BACKEND / ".env", override=False)

DDL = """
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'FieldBiomassAnalysis')
BEGIN
    CREATE TABLE FieldBiomassAnalysis (
        AnalysisID         INT IDENTITY(1,1) PRIMARY KEY,
        FieldID            INT            NOT NULL,
        BusinessID         INT            NOT NULL,
        Source             VARCHAR(20)    NOT NULL,
        BiomassKgHa        DECIMAL(10, 2) NULL,
        Confidence         DECIMAL(5, 3)  NULL,
        ImageUrl           VARCHAR(1000)  NULL,
        CapturedAt         DATETIME       NULL,
        ModelVersion       VARCHAR(50)    NULL,
        FeaturesJSON       NVARCHAR(MAX)  NULL,
        CreatedByPeopleID  INT            NULL,
        CreatedAt          DATETIME       NOT NULL DEFAULT GETUTCDATE()
    );
    CREATE INDEX IX_FieldBiomassAnalysis_FieldID    ON FieldBiomassAnalysis(FieldID);
    CREATE INDEX IX_FieldBiomassAnalysis_BusinessID ON FieldBiomassAnalysis(BusinessID);
    CREATE INDEX IX_FieldBiomassAnalysis_Field_Src  ON FieldBiomassAnalysis(FieldID, Source, CapturedAt DESC);
END
"""


def ensure_db() -> int:
    from sqlalchemy import text
    from database import SessionLocal

    with SessionLocal() as db:
        db.execute(text(DDL))
        db.commit()
        row = db.execute(
            text(
                "SELECT COUNT(*) AS n FROM INFORMATION_SCHEMA.TABLES "
                "WHERE TABLE_NAME = 'FieldBiomassAnalysis'"
            )
        ).fetchone()
        n = int(row[0]) if row else 0
    if n:
        print("DB OK: FieldBiomassAnalysis table exists")
        return 0
    print("DB ERROR: table still missing after DDL", file=sys.stderr)
    return 1


def ensure_gcs() -> int:
    try:
        from google.cloud import storage
    except ImportError:
        print("GCS skip: google-cloud-storage not installed", file=sys.stderr)
        return 1

    bucket_name = os.getenv("BIOMASS_GCS_BUCKET", "oatmeal-farm-network-images")
    prefix = os.getenv("BIOMASS_GCS_PREFIX", "biomass-uploads").strip("/")
    project = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCLOUD_PROJECT") or "animated-flare-421518"
    location = os.getenv("BIOMASS_GCS_LOCATION", "US")
    make_public = os.getenv("BIOMASS_GCS_PUBLIC", "true").strip().lower() in ("1", "true", "yes")

    try:
        client = storage.Client(project=project)
    except Exception as e:
        print(f"GCS auth failed: {e}", file=sys.stderr)
        print("Fix: gcloud auth application-default login", file=sys.stderr)
        print("  or set GOOGLE_APPLICATION_CREDENTIALS to a service-account JSON", file=sys.stderr)
        return 2

    bucket = client.lookup_bucket(bucket_name)
    if bucket:
        print(f"GCS OK: gs://{bucket_name} exists (location={bucket.location})")
    else:
        print(f"GCS: creating gs://{bucket_name} in {location} (project={client.project})...")
        bucket = client.create_bucket(bucket_name, location=location)
        print(f"GCS CREATED: gs://{bucket_name}")

    marker = bucket.blob(f"{prefix}/.keep")
    if not marker.exists():
        marker.upload_from_string(b"", content_type="text/plain")
        print(f"GCS OK: wrote gs://{bucket_name}/{prefix}/.keep")
    else:
        print(f"GCS OK: prefix gs://{bucket_name}/{prefix}/ ready")

    if make_public:
        try:
            policy = bucket.get_iam_policy(requested_policy_version=3)
            role = "roles/storage.objectViewer"
            member = "allUsers"
            binding = next((b for b in policy.bindings if b.get("role") == role), None)
            if binding is None:
                policy.bindings.append({"role": role, "members": {member}})
                bucket.set_iam_policy(policy)
                print("GCS OK: granted allUsers objectViewer (public read thumbnails)")
            elif member not in binding.get("members", set()):
                members = set(binding.get("members") or [])
                members.add(member)
                binding["members"] = members
                bucket.set_iam_policy(policy)
                print("GCS OK: added allUsers to objectViewer")
            else:
                print("GCS OK: public objectViewer already set")
        except Exception as e:
            print(f"GCS WARN: could not set public read ({e})", file=sys.stderr)
            print("  Uploads still work; thumbnails may need signed URLs or manual IAM.", file=sys.stderr)

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-db", action="store_true")
    ap.add_argument("--skip-gcs", action="store_true")
    args = ap.parse_args()

    rc = 0
    if not args.skip_db:
        try:
            rc |= ensure_db()
        except Exception as e:
            print(f"DB failed: {e}", file=sys.stderr)
            rc |= 1
    if not args.skip_gcs:
        rc |= ensure_gcs()

    if rc == 0:
        print("All biomass cloud resources ready.")
    else:
        print("Completed with errors — see messages above.", file=sys.stderr)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
