# NOTE: Base is imported from the root `database` module until Dev 2's core
# move lands; switch to `from app.database import Base` after that.
from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Date, Text, Boolean, Float
from sqlalchemy import Numeric as Decimal
from app.database import Base

class Produce(Base):
    __tablename__ = "Produce"
    ProduceID      = Column(Integer, primary_key=True, index=True)
    BusinessID     = Column(Integer)
    IngredientID   = Column(Integer)
    Quantity       = Column(Decimal(10, 2))
    RetailPrice    = Column(Decimal(10, 2))
    WholesalePrice = Column(Decimal(10, 2))
    HarvestDate    = Column(Date)
    ExpirationDate = Column(Date)
    IsOrganic      = Column(Boolean)
    ShowProduce    = Column(SmallInteger)

# ── CROP ROTATION ────────────────────────────────────────────────
class CropRotationEntry(Base):
    __tablename__ = "CropRotationEntry"
    RotationID   = Column(Integer, primary_key=True, index=True, autoincrement=True)
    FieldID      = Column(Integer, index=True)
    BusinessID   = Column(Integer, index=True)
    SeasonYear   = Column(Integer)
    CropName     = Column(String(255))
    Variety      = Column(String(255))
    PlantingDate = Column(Date)
    HarvestDate  = Column(Date)
    YieldAmount  = Column(Decimal(10, 2))
    YieldUnit    = Column(String(50))
    IsCoverCrop  = Column(Boolean, default=False)
    Notes        = Column(Text)
    CreatedAt    = Column(DateTime)
    UpdatedAt    = Column(DateTime)
