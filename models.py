from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Date, Text, Boolean
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
    PeoplePassword = Column(String(255))

# ── BUSINESS ────────────────────────────────────────────────────
class Business(Base):
    __tablename__ = "Business"
    BusinessID        = Column(Integer, primary_key=True, index=True)
    BusinessName      = Column(String(1000))
    BusinessEmail     = Column(String(100))
    BusinessPhone     = Column(String(50))
    AddressID         = Column(Integer)
    SubscriptionLevel = Column(Integer)
    AccessLevel       = Column(Integer)
    BusinessFacebook  = Column(String(255))
    BusinessInstagram = Column(String(255))

# ── ADDRESS ─────────────────────────────────────────────────────
class Address(Base):
    __tablename__ = "Address"
    AddressID      = Column(Integer, primary_key=True, index=True)
    AddressStreet  = Column(String(50))
    AddressCity    = Column(String(50))
    AddressState   = Column(String(365))
    AddressZip     = Column(String(48))
    AddressCountry = Column(String(50))

# ── ANIMALS ─────────────────────────────────────────────────────
class Animal(Base):
    __tablename__ = "Animals"
    ID          = Column(Integer, primary_key=True, index=True)
    BusinessID  = Column(Integer)
    PeopleID    = Column(Integer)
    SpeciesID   = Column(Integer)
    FullName    = Column(String(255))
    ShortName   = Column(String(255))
    BreedID     = Column(Integer)
    SexID       = Column(Integer)
    DOBday      = Column(Integer)
    DOBMonth    = Column(Integer)
    DOBYear     = Column(Integer)
    PublishForSale = Column(SmallInteger)
    Description = Column(String)
    Lastupdated = Column(DateTime)

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
    AssociationID          = Column(Integer, primary_key=True, index=True)
    AssociationName        = Column(String(255))
    AssociationAcronym     = Column(String(50))
    AssociationEmailaddress= Column(String(255))
    SpeciesID              = Column(Integer)
    AddressID              = Column(Integer)

# ── PRODUCE (Farm2Table) ─────────────────────────────────────────
class Produce(Base):
    __tablename__ = "Produce"
    ProduceID          = Column(Integer, primary_key=True, index=True)
    BusinessID         = Column(Integer)
    IngredientID       = Column(Integer)
    Quantity           = Column(Decimal(10,2))
    RetailPrice        = Column(Decimal(10,2))
    WholesalePrice     = Column(Decimal(10,2))
    HarvestDate        = Column(Date)
    ExpirationDate     = Column(Date)
    IsOrganic          = Column(Boolean)
    ShowProduce        = Column(SmallInteger)

# ── FIELDS (Plant/Farm) ──────────────────────────────────────────
class Field(Base):
    __tablename__ = "Fields"
    FieldID        = Column(Integer, primary_key=True, index=True)
    BusinessID     = Column(Integer)
    Name           = Column(String(255))
    CropType       = Column(String(255))
    Latitude       = Column(Decimal(9,6))
    Longitude      = Column(Decimal(9,6))
    FieldSizeHectares = Column(Decimal(10,2))
    PlantingDate   = Column(Date)