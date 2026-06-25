# NOTE: Base is imported from the root `database` module until Dev 2's core
# move lands; switch to `from app.database import Base` after that.
from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Date, Text, Boolean, Float
from sqlalchemy import Numeric as Decimal
from database import Base

class Animal(Base):
    __tablename__ = "Animals"
    AnimalID          = Column(Integer, primary_key=True, index=True)
    BusinessID        = Column(Integer)
    PeopleID          = Column(Integer)
    SpeciesID         = Column(Integer)
    FullName          = Column(String(255))
    ShortName         = Column(String(255))
    NumberOfAnimals   = Column(Integer)
    BreedID           = Column(Integer)
    BreedID2          = Column(Integer)
    BreedID3          = Column(Integer)
    BreedID4          = Column(Integer)
    Category          = Column(Integer)
    DOBday            = Column(Integer)
    DOBMonth          = Column(Integer)
    DOBYear           = Column(Integer)
    Temperment       = Column(Integer)
    Height            = Column(Decimal(10, 2))
    Weight            = Column(Decimal(10, 2))
    Gaited            = Column(SmallInteger)
    Warmblooded       = Column(SmallInteger)
    Horns             = Column(String(20))
    Temperament       = Column(Integer)
    Description       = Column(Text)
    PublishForSale    = Column(SmallInteger)
    PublishStud       = Column(SmallInteger)
    Lastupdated       = Column(DateTime)

# ── ANIMAL REGISTRATION ──────────────────────────────────────────
class AnimalRegistration(Base):
    __tablename__ = "AnimalRegistration"
    AnimalRegistrationID = Column(Integer, primary_key=True, index=True)
    AnimalID             = Column(Integer)
    RegType              = Column(String(255))
    RegNumber            = Column(String(255))

# ── COLORS ───────────────────────────────────────────────────────
class AnimalColor(Base):
    __tablename__ = "Colors"
    ColorID   = Column(Integer, primary_key=True, index=True)
    AnimalID  = Column(Integer)
    Color1    = Column(String(100))
    Color2    = Column(String(100))
    Color3    = Column(String(100))
    Color4    = Column(String(100))

# ── ANCESTORS ────────────────────────────────────────────────────
class Ancestor(Base):
    __tablename__ = "Ancestors"
    AncestorID          = Column(Integer, primary_key=True, index=True)
    AnimalID            = Column(Integer)
    SireName            = Column(String(255))
    SireColor           = Column(String(100))
    SireARI             = Column(String(100))
    SireCLAA            = Column(String(100))
    DamName             = Column(String(255))
    DamColor            = Column(String(100))
    DamARI              = Column(String(100))
    DamCLAA             = Column(String(100))
    SireSireName        = Column(String(255))
    SireSireColor       = Column(String(100))
    SireDamName         = Column(String(255))
    SireDamColor        = Column(String(100))
    DamSireName         = Column(String(255))
    DamSireColor        = Column(String(100))
    DamDamName          = Column(String(255))
    DamDamColor         = Column(String(100))
    SireSireSireName    = Column(String(255))
    SireSireSireColor   = Column(String(100))
    SireSireDamName     = Column(String(255))
    SireSireDamColor    = Column(String(100))
    SireDamSireName     = Column(String(255))
    SireDamSireColor    = Column(String(100))
    SireDamDamName      = Column(String(255))
    SireDamDamColor     = Column(String(100))
    DamSireSireName     = Column(String(255))
    DamSireSireColor    = Column(String(100))
    DamSireDamName      = Column(String(255))
    DamSireDamColor     = Column(String(100))
    DamDamSireName      = Column(String(255))
    DamDamSireColor     = Column(String(100))
    DamDamDamName       = Column(String(255))
    DamDamDamColor      = Column(String(100))
    AncestryDescription = Column(Text)

# ── ANCESTRY PERCENTS (Alpacas) ──────────────────────────────────
class AncestryPercent(Base):
    __tablename__ = "AncestryPercents"
    AncestryPercentID    = Column(Integer, primary_key=True, index=True)
    AnimalID             = Column(Integer)
    PercentPeruvian      = Column(String(50))
    PercentChilean       = Column(String(50))
    PercentBolivian      = Column(String(50))
    PercentUnknownOther  = Column(String(50))
    PercentAccoyo        = Column(String(50))

# ── FIBER (Alpacas) ──────────────────────────────────────────────
class Fiber(Base):
    __tablename__ = "Fiber"
    FiberID        = Column(Integer, primary_key=True, index=True)
    AnimalID       = Column(Integer)
    SampleDateDay  = Column(Integer)
    SampleDateMonth= Column(Integer)
    SampleDateYear = Column(Integer)
    AFD            = Column(Decimal(10, 2))
    SD             = Column(Decimal(10, 2))
    COV            = Column(Decimal(10, 2))
    CF             = Column(Decimal(10, 2))
    GreaterThan30  = Column(Decimal(10, 2))
    Curve          = Column(Decimal(10, 2))
    CrimpPerInch   = Column(Decimal(10, 2))
    Length         = Column(Decimal(10, 2))
    ShearWeight    = Column(Decimal(10, 2))
    BlanketWeight  = Column(Decimal(10, 2))

# ── AWARDS ───────────────────────────────────────────────────────
class Award(Base):
    __tablename__ = "Awards"
    AwardID       = Column(Integer, primary_key=True, index=True)
    AnimalID      = Column(Integer)
    AwardYear     = Column(Integer)
    ShowName      = Column(String(255))
    Placing       = Column(String(255))
    Type          = Column(String(255))
    Awardcomments = Column(Text)

# ── PHOTOS ───────────────────────────────────────────────────────
class Photo(Base):
    __tablename__ = "Photos"
    AnimalID      = Column(Integer, primary_key=True, index=True)
    Photo1        = Column(String(500))
    Photo2        = Column(String(500))
    Photo3        = Column(String(500))
    Photo4        = Column(String(500))
    Photo5        = Column(String(500))
    Photo6        = Column(String(500))
    Photo7        = Column(String(500))
    Photo8        = Column(String(500))
    Photo9        = Column(String(500))
    Photo10       = Column(String(500))
    Photo11       = Column(String(500))
    Photo12       = Column(String(500))
    Photo13       = Column(String(500))
    Photo14       = Column(String(500))
    Photo15       = Column(String(500))
    Photo16       = Column(String(500))
    PhotoCaption1 = Column(String(500))
    PhotoCaption2 = Column(String(500))
    PhotoCaption3 = Column(String(500))
    PhotoCaption4 = Column(String(500))
    PhotoCaption5 = Column(String(500))
    PhotoCaption6 = Column(String(500))
    PhotoCaption7 = Column(String(500))
    PhotoCaption8 = Column(String(500))
    PhotoCaption9 = Column(String(500))
    PhotoCaption10= Column(String(500))
    PhotoCaption11= Column(String(500))
    PhotoCaption12= Column(String(500))
    PhotoCaption13= Column(String(500))
    PhotoCaption14= Column(String(500))
    PhotoCaption15= Column(String(500))
    PhotoCaption16= Column(String(500))
    FiberAnalysis = Column(String(500))
    Histogram     = Column(String(500))
    ARI           = Column(String(500))
    AnimalVideo   = Column(String(1000))

# ── PRICING ──────────────────────────────────────────────────────
class Pricing(Base):
    __tablename__ = "Pricing"
    AnimalID          = Column(Integer, primary_key=True, index=True)
    Price             = Column(Decimal(10, 2))
    Price2            = Column(Decimal(10, 2))
    Price3            = Column(Decimal(10, 2))
    Price4            = Column(Decimal(10, 2))
    MinOrder1         = Column(Integer)
    MinOrder2         = Column(Integer)
    MinOrder3         = Column(Integer)
    MinOrder4         = Column(Integer)
    MaxOrder1         = Column(Integer)
    MaxOrder2         = Column(Integer)
    MaxOrder3         = Column(Integer)
    MaxOrder4         = Column(Integer)
    StudFee           = Column(Decimal(10, 2))
    ForSale           = Column(SmallInteger)
    Free              = Column(SmallInteger)
    OBO               = Column(SmallInteger)
    Foundation        = Column(SmallInteger)
    Discount          = Column(Integer)
    PriceComments     = Column(Text)
    Donor             = Column(SmallInteger)
    EmbryoPrice       = Column(Decimal(10, 2))
    SemenPrice        = Column(Decimal(10, 2))
    PayWhatYouCanStud = Column(SmallInteger)
    Sold              = Column(SmallInteger)
    SalePrice         = Column(Decimal(10, 2))
    CoOwnerBusiness1  = Column(String(255))
    CoOwnerName1      = Column(String(255))
    CoOwnerLink1      = Column(String(255))
    CoOwnerBusiness2  = Column(String(255))
    CoOwnerName2      = Column(String(255))
    CoOwnerLink2      = Column(String(255))
    CoOwnerBusiness3  = Column(String(255))
    CoOwnerName3      = Column(String(255))
    CoOwnerLink3      = Column(String(255))

# ── SPECIES LOOKUP TABLES ────────────────────────────────────────
class SpeciesAvailable(Base):
    __tablename__ = "speciesavailable"
    SpeciesID                = Column(Integer, primary_key=True, index=True)
    Species                  = Column(String(255))
    SpeciesPriority          = Column(Integer)
    SpeciesAvailableonSite   = Column(SmallInteger)

class SpeciesBreedLookup(Base):
    __tablename__ = "SpeciesBreedLookupTable"
    BreedLookupID = Column(Integer, primary_key=True, index=True)
    SpeciesID     = Column(Integer)
    Breed         = Column(String(255))

class SpeciesColorLookup(Base):
    __tablename__ = "SpeciesColorlookupTable"
    SpeciesColorID = Column(Integer, primary_key=True, index=True)
    SpeciesID      = Column(Integer)
    SpeciesColor   = Column(String(255))

class SpeciesRegistrationTypeLookup(Base):
    __tablename__ = "SpeciesRegistrationTypeLookupTable"
    SpeciesRegTypeID     = Column(Integer, primary_key=True, index=True)
    SpeciesID            = Column(Integer)
    SpeciesRegistrationType = Column(String(255))
    country_id           = Column(Integer)

class SpeciesCategory(Base):
    __tablename__ = "speciescategory"
    SpeciesCategoryID     = Column(Integer, primary_key=True, index=True)
    SpeciesID             = Column(Integer)
    SpeciesCategory       = Column(String(255))
    SpeciesCategoryPlural = Column(String(255))
    SpeciesCategoryOrder  = Column(Integer)
