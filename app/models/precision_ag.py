# NOTE: Base is imported from the root `database` module until Dev 2's core
# move lands; switch to `from app.database import Base` after that.
from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Date, Text, Boolean, Float
from sqlalchemy import Numeric as Decimal
from app.database import Base

class Field(Base):
    __tablename__ = "Field"
    FieldID                  = Column(Integer, primary_key=True, index=True, autoincrement=True)
    BusinessID               = Column(Integer)
    Name                     = Column(String(255))
    Address                  = Column(String(500))
    Latitude                 = Column(Decimal(9, 6))
    Longitude                = Column(Decimal(9, 6))
    FieldSizeHectares        = Column(Decimal(10, 2))
    CropType                 = Column(String(255))
    PlantingDate             = Column(Date)
    MonitoringEnabled        = Column(Boolean)
    MonitoringIntervalDays   = Column(Integer)
    AlertThresholdHealth     = Column(Integer)
    CreatedAt                = Column(DateTime)
    CreatedByPeopleID        = Column(Integer)
    UpdatedAt                = Column(DateTime)
    DeletedAt                = Column(DateTime)
    BoundaryGeoJSON          = Column(Text)
    FieldDescription         = Column(Text)
    AddressID                = Column(Integer)
    SoilID                   = Column(Integer)

# ── FIELD NOTES ──────────────────────────────────────────────────
class FieldNote(Base):
    __tablename__ = "FieldNote"
    NoteID     = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID    = Column(Integer, index=True)
    BusinessID = Column(Integer, index=True)
    PeopleID   = Column(Integer)
    NoteDate   = Column(Date)
    Category   = Column(String(100))
    Title      = Column(String(500))
    Content    = Column(Text)
    Severity   = Column(String(20))           # Low/Medium/High/Critical (scouting-style notes)
    Latitude   = Column(Decimal(10, 7))       # optional GPS pin
    Longitude  = Column(Decimal(10, 7))
    ImageUrl   = Column(String(1000))         # optional photo URL
    CreatedAt  = Column(DateTime)
    UpdatedAt  = Column(DateTime)

# ── BIOMASS ANALYSIS ─────────────────────────────────────────────
class FieldBiomassAnalysis(Base):
    __tablename__ = "FieldBiomassAnalysis"
    AnalysisID        = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID           = Column(Integer, index=True)
    BusinessID        = Column(Integer, index=True)
    Source            = Column(String(20))          # 'satellite' | 'upload'
    BiomassKgHa       = Column(Decimal(10, 2))
    Confidence        = Column(Decimal(5, 3))
    ImageUrl          = Column(String(1000))        # GCS or source imagery URL
    CapturedAt        = Column(DateTime)            # imagery capture date (satellite) or upload time
    ModelVersion      = Column(String(50))
    FeaturesJSON      = Column(Text)                # raw feature payload from estimator
    CreatedByPeopleID = Column(Integer)
    CreatedAt         = Column(DateTime)

# ── MATURITY SAMPLES ─────────────────────────────────────────────
# Ground-truth ripeness/quality readings from refractometer, NIR, lab, etc.
# Used by the Maturity Engine to fit a per-field curve and predict the
# peak-antioxidant harvest date.
class FieldMaturitySample(Base):
    __tablename__ = "FieldMaturitySample"
    SampleID             = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID              = Column(Integer, index=True)
    BusinessID           = Column(Integer, index=True)
    PeopleID             = Column(Integer)
    SampleDate           = Column(Date)
    Cultivar             = Column(String(100))
    SampleSize           = Column(Integer)
    LabName              = Column(String(200))
    BrixDegrees          = Column(Decimal(5, 2))
    FirmnessKgF          = Column(Decimal(5, 2))
    AnthocyaninMgG       = Column(Decimal(7, 3))
    PH                   = Column(Decimal(4, 2))
    TitratableAcidityPct = Column(Decimal(5, 2))
    ColorScoreL          = Column(Decimal(6, 2))
    ColorScoreA          = Column(Decimal(6, 2))
    ColorScoreB          = Column(Decimal(6, 2))
    DryMatterPct         = Column(Decimal(5, 2))
    Notes                = Column(Text)
    ImageUrl             = Column(String(1000))
    CreatedAt            = Column(DateTime)
    UpdatedAt            = Column(DateTime)


class FieldHarvestTarget(Base):
    __tablename__ = "FieldHarvestTarget"
    TargetID         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID          = Column(Integer, index=True)
    BusinessID       = Column(Integer, index=True)
    DestinationLabel = Column(String(200))
    DestinationMiles = Column(Decimal(7, 1))    # one-way road miles farm → DC
    ReceivingLagDays = Column(Integer)
    ShelfTargetDate  = Column(Date)
    Notes            = Column(Text)
    CreatedAt        = Column(DateTime)
    UpdatedAt        = Column(DateTime)


# ── FIELD ASSESSMENT REPORTS ─────────────────────────────────────
# Persisted Saige-authored consultant reports. ReportJSON is the parsed
# structured payload the UI renders; RawText is the raw LLM output kept for
# audit; ContextJSON is the input data snapshot so we can replay or RAG it.
class FieldAssessmentReport(Base):
    __tablename__ = "FieldAssessmentReport"
    ReportID      = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID       = Column(Integer, index=True)
    BusinessID    = Column(Integer, index=True)
    PeopleID      = Column(Integer)
    GeneratedAt   = Column(DateTime)
    Headline      = Column(String(500))
    OverallHealth = Column(String(100))
    Confidence    = Column(String(20))
    ReportJSON    = Column(Text)
    RawText       = Column(Text)
    ContextJSON   = Column(Text)
    DeletedAt     = Column(DateTime)

# ── FIELD SCOUTING ───────────────────────────────────────────────
class FieldScout(Base):
    __tablename__ = "FieldScout"
    ScoutID    = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID    = Column(Integer, index=True)
    BusinessID = Column(Integer, index=True)
    PeopleID   = Column(Integer)
    ObservedAt = Column(DateTime)
    Category   = Column(String(50))
    Severity   = Column(String(20))
    Notes      = Column(Text)
    Latitude   = Column(Decimal(10, 7))
    Longitude  = Column(Decimal(10, 7))
    ImageUrl   = Column(String(1000))
    CreatedAt  = Column(DateTime)

# ── SOIL SAMPLES ─────────────────────────────────────────────────
class FieldSoilSample(Base):
    __tablename__ = "FieldSoilSample"
    SampleID      = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID       = Column(Integer, index=True)
    BusinessID    = Column(Integer, index=True)
    SampleDate    = Column(Date)
    SampleLabel   = Column(String(100))
    Latitude      = Column(Decimal(10, 7))
    Longitude     = Column(Decimal(10, 7))
    Depth_cm      = Column(Integer)
    pH            = Column(Decimal(4, 2))
    OrganicMatter = Column(Decimal(5, 2))
    Nitrogen      = Column(Decimal(8, 2))
    Phosphorus    = Column(Decimal(8, 2))
    Potassium     = Column(Decimal(8, 2))
    Sulfur        = Column(Decimal(8, 2))
    Calcium       = Column(Decimal(8, 2))
    Magnesium     = Column(Decimal(8, 2))
    CEC           = Column(Decimal(6, 2))
    Notes         = Column(Text)
    CreatedAt     = Column(DateTime)

# ── PRESCRIPTIONS ─────────────────────────────────────────────────
class FieldPrescription(Base):
    __tablename__ = "FieldPrescription"
    PrescriptionID = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID        = Column(Integer, index=True)
    BusinessID     = Column(Integer, index=True)
    Name           = Column(String(255))
    Product        = Column(String(255))
    Unit           = Column(String(50))
    IndexKey       = Column(String(20))
    ZoneMethod     = Column(String(50))
    NumZones       = Column(Integer)
    ZoneRatesJSON  = Column(Text)
    AnalysisDate   = Column(Date)
    Notes          = Column(Text)
    CreatedAt      = Column(DateTime)

# ── FIELD ACTIVITY LOG ───────────────────────────────────────────
class FieldActivityLog(Base):
    __tablename__ = "FieldActivityLog"
    ActivityID   = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID      = Column(Integer, index=True)
    BusinessID   = Column(Integer, index=True)
    PeopleID     = Column(Integer)
    ActivityDate = Column(Date)
    ActivityType = Column(String(50))
    Product      = Column(String(255))
    Rate         = Column(Decimal(10, 2))
    RateUnit     = Column(String(50))
    OperatorName = Column(String(255))
    Notes        = Column(Text)
    CreatedAt    = Column(DateTime)
