from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Date, Text, Boolean, Float
from sqlalchemy import Numeric as Decimal
from app.database import Base

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
