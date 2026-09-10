
# =============================================================================
# users.py
#
# Data models for the "users" domain of the Oatmeal Farm Network backend app.
# This file defines SQLAlchemy ORM classes mapping to database tables involved 
# with users, businesses, addresses, and associated lookup tables for the app.
#
# Key models include:
#   - People: User accounts, authentication, and primary user information.
#   - Business: Farm/business account details, subscription, and contact.
#   - Address: Mailing and location addresses used by People and Business.
#   - BusinessAccess: Permissions and access control for user-business links.
#   - BusinessTypeLookup, Country, StateProvince, Websites: Various lookup tables.
#
# Imported by: main models.py and service layers.
# =============================================================================


from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Text
from app.database import Base

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
    LKMAccessLevel    = Column(Integer)
    Subscriptionlevel = Column(Integer)
    AddressID         = Column(Integer)
    BusinessId        = Column(Integer)
    PeopleCreationDate= Column(DateTime)
    PeoplePassword    = Column(String(255))

# ── BUSINESS ────────────────────────────────────────────────────
class Business(Base):
    __tablename__ = "Business"
    BusinessID              = Column(Integer, primary_key=True, index=True)
    BusinessTypeID          = Column(Integer, index=True)
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
    WebsitesID              = Column(Integer)
    BusinessDescription     = Column(Text)

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

#--- WEBSITE/--------
class Websites(Base):
    __tablename__ = "Websites"
    WebsitesID  = Column(Integer, primary_key=True, index=True)
    Website     = Column(String(500))
    websitepath = Column(String(500))
    watermark   = Column(DateTime)
