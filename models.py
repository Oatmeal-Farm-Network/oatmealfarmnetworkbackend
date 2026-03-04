from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Date, Text, Boolean, Float
from sqlalchemy import Numeric as Decimal
from database import Base

# ── PEOPLE / ACCOUNTS ──────────────────────────────────────────
class People(Base):
    __tablename__ = "People"
    PeopleID          = Column(Integer, primary_key=True, index=True)
    PeopleFirstName   = Column(String(100))
    PeopleLastName    = Column(String(100))
    PeopleEmail       = Column(String(255))
    PeoplePhone       = Column(String(50))
    PeopleActive      = Column(SmallInteger)
    accesslevel       = Column(Integer)
    Subscriptionlevel = Column(Integer)
    AddressID         = Column(Integer)
    BusinessId        = Column(Integer)
    PeopleCreationDate= Column(DateTime)
    PeoplePassword    = Column(String(255))

# ── BUSINESS ────────────────────────────────────────────────────
class Business(Base):
    __tablename__ = "Business"
    BusinessID              = Column(Integer, primary_key=True, index=True)
    BusinessTypeID          = Column(Integer)
    BusinessName            = Column(String(1000))
    BusinessEmail           = Column(String(100))
    BusinessPhone           = Column(String(50))
    AddressID               = Column(Integer)
    SubscriptionLevel       = Column(Integer)
    SubscriptionEndDate     = Column(DateTime)
    SubscriptionStartDate   = Column(DateTime)
    AccessLevel             = Column(Integer)
    Logo = Column(String(255))
    BusinessFacebook        = Column(String(255))
    BusinessInstagram       = Column(String(255))
    BusinessLinkedIn        = Column(String(255))
    BusinessX               = Column(String(255))
    BusinessPinterest       = Column(String(255))
    BusinessYouTube         = Column(String(255))
    BusinessTruthSocial     = Column(String(255))
    BusinessBlog            = Column(String(255))
    BusinessOtherSocial1    = Column(String(255))
    BusinessOtherSocial2    = Column(String(255))
    WebsitesID = Column(Integer) 

# ── ADDRESS ─────────────────────────────────────────────────────
class Address(Base):
    __tablename__ = "Address"
    AddressID      = Column(Integer, primary_key=True, index=True)
    AddressStreet  = Column(String(50))
    AddressCity    = Column(String(50))
    AddressState   = Column(String(365))
    AddressZip     = Column(String(48))
    AddressCountry = Column(String(50))
    country_id     = Column(Integer)

# ── ANIMALS ─────────────────────────────────────────────────────
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

# ── EVENTS ──────────────────────────────────────────────────────
class Event(Base):
    __tablename__ = "Event"
    EventID          = Column(Integer, primary_key=True, index=True)
    PeopleID         = Column(Integer)
    EventName        = Column(String(255))
    EventTypeID      = Column(Integer)
    AddressID        = Column(Integer)
    EventStartMonth  = Column(Integer)
    EventStartDay    = Column(Integer)
    EventStartYear   = Column(Integer)
    EventEndMonth    = Column(Integer)
    EventEndDay      = Column(Integer)
    EventEndYear     = Column(Integer)
    EventDescription = Column(String)
    EventStatus      = Column(String(50))

# ── ASSOCIATIONS ─────────────────────────────────────────────────
class Association(Base):
    __tablename__ = "Associations"
    AssociationID           = Column(Integer, primary_key=True, index=True)
    AssociationName         = Column(String(255))
    AssociationAcronym      = Column(String(50))
    AssociationEmailaddress = Column(String(255))
    SpeciesID               = Column(Integer)
    AddressID               = Column(Integer)

# ── PRODUCE ──────────────────────────────────────────────────────
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

# ── FIELDS ───────────────────────────────────────────────────────
class Field(Base):
    __tablename__ = "Fields"
    FieldID           = Column(Integer, primary_key=True, index=True)
    BusinessID        = Column(Integer)
    Name              = Column(String(255))
    CropType          = Column(String(255))
    Latitude          = Column(Decimal(9, 6))
    Longitude         = Column(Decimal(9, 6))
    FieldSizeHectares = Column(Decimal(10, 2))
    PlantingDate      = Column(Date)

# ── BUSINESS ACCESS ──────────────────────────────────────────────
class BusinessAccess(Base):
    __tablename__ = "BusinessAccess"
    BusinessAccessID = Column(Integer, primary_key=True, index=True)
    BusinessID       = Column(Integer)
    PeopleID         = Column(Integer)
    AccessLevelID    = Column(Integer)
    Active           = Column(SmallInteger)
    CreatedAt        = Column(DateTime)
    RevokedAt        = Column(DateTime)
    Role             = Column(String(100))

# ── BUSINESS TYPE LOOKUP ─────────────────────────────────────────
class BusinessTypeLookup(Base):
    __tablename__ = "businesstypelookup"
    BusinessTypeID      = Column(Integer, primary_key=True, index=True)
    BusinessType        = Column(String(255))
    BusinessTypeIcon    = Column(String(255))
    BusinessTypeIDOrder = Column(Integer)

    # ── COUNTRY ──────────────────────────────────────────────────────
class Country(Base):
    __tablename__ = "country"
    country_id = Column(Integer, primary_key=True, index=True)
    name       = Column(String(100))
    iso_code   = Column(String(10))


    # ── STATE / PROVINCE ─────────────────────────────────────────────
class StateProvince(Base):
    __tablename__ = "state_province"
    StateIndex   = Column(Integer, primary_key=True, index=True)
    name         = Column(String(100))
    abbreviation = Column(String(10))
    country_id   = Column(Integer)

class Websites(Base):
    __tablename__ = "Websites"
    WebsitesID  = Column(Integer, primary_key=True, index=True)
    Website     = Column(String(500))
    websitepath = Column(String(500))
    watermark   = Column(DateTime)


