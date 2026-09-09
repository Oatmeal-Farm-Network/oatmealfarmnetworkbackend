"""
Idempotent ensure of FieldBiomassAnalysis — used by upload route before insert
so deploys work even if startup migration has not finished yet.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

_ready = False

_DDL = """
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


def ensure_biomass_table(db: Session) -> None:
    global _ready
    if _ready:
        return
    try:
        db.execute(text(_DDL))
        db.commit()
        _ready = True
    except Exception:
        db.rollback()
        raise
