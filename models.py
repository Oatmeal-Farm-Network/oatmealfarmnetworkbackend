from sqlalchemy import Column, Integer, String, SmallInteger, DateTime, Date, Text, Boolean, Float
from sqlalchemy import Numeric as Decimal
from database import Base

from app.models.users import (  # noqa: F401
    Address,
    Business,
    BusinessAccess,
    BusinessTypeLookup,
    Country,
    People,
    StateProvince,
    Websites,
)
from app.models.accounting import (  # noqa: F401
    Account,
    AccountingCustomer,
    AccountingVendor,
    AccountType,
    Bill,
    BillLine,
    Expense,
    ExpenseLine,
    FiscalPeriod,
    FiscalYear,
    Invoice,
    InvoiceLine,
    Item,
    JournalEntry,
    JournalEntryLine,
    Payment,
    PaymentApplication,
)

# ── ANIMALS ─────────────────────────────────────────────────────
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

# ── WEBSITE BUILDER ──────────────────────────────────────────────
class BusinessWebsite(Base):
    __tablename__ = "BusinessWebsite"
    WebsiteID       = Column(Integer, primary_key=True, autoincrement=True)
    BusinessID      = Column(Integer, nullable=False, index=True)
    SiteName        = Column(String(255))
    Slug            = Column(String(100), unique=True)
    Tagline         = Column(String(500))
    LogoURL         = Column(String(1000))
    PrimaryColor    = Column(String(20), default='#3D6B34')
    SecondaryColor  = Column(String(20), default='#819360')
    AccentColor     = Column(String(20), default='#FFC567')
    BgColor         = Column(String(20), default='#FFFFFF')
    ScreenBackgroundColor = Column(String(20))
    PageBackgroundColor   = Column(String(20))
    BgImageURL      = Column(String(1000))
    BgGradient      = Column(String(500))
    BodyContentWidth= Column(String(20), default='100%')
    BodyBgWidth     = Column(String(20), default='100%')
    HeaderBgWidth   = Column(String(20), default='100%')
    FooterBgWidth   = Column(String(20), default='100%')
    TextColor       = Column(String(20), default='#111827')
    FontFamily      = Column(String(100), default='Inter, sans-serif')
    # Typography / type scale
    H1Size          = Column(String(20), default='40px')
    H1Weight        = Column(String(10), default='800')
    H1Color         = Column(String(20), default='')
    H1Align         = Column(String(10), default='left')
    H1Underline     = Column(Boolean, default=False)
    H1Italic        = Column(Boolean, default=False)
    H1Rule          = Column(Boolean, default=False)
    H1RuleColor     = Column(String(20), default='')
    H2Size          = Column(String(20), default='29px')
    H2Weight        = Column(String(10), default='700')
    H2Color         = Column(String(20), default='')
    H2Align         = Column(String(10), default='left')
    H2Underline     = Column(Boolean, default=False)
    H2Italic        = Column(Boolean, default=False)
    H2Rule          = Column(Boolean, default=False)
    H2RuleColor     = Column(String(20), default='')
    H3Size          = Column(String(20), default='21px')
    H3Weight        = Column(String(10), default='600')
    H3Color         = Column(String(20), default='')
    H3Align         = Column(String(10), default='left')
    H3Underline     = Column(Boolean, default=False)
    H3Italic        = Column(Boolean, default=False)
    H3Rule          = Column(Boolean, default=False)
    H3RuleColor     = Column(String(20), default='')
    H4Size          = Column(String(20), default='17px')
    H4Weight        = Column(String(10), default='600')
    H4Color         = Column(String(20), default='')
    H4Align         = Column(String(10), default='left')
    H4Underline     = Column(Boolean, default=False)
    H4Italic        = Column(Boolean, default=False)
    H4Rule          = Column(Boolean, default=False)
    H4RuleColor     = Column(String(20), default='')
    H1MarginTop     = Column(Integer, default=0)
    H1MarginBottom  = Column(Integer, default=8)
    H1Font          = Column(String(200), default='')
    H2MarginTop     = Column(Integer, default=0)
    H2MarginBottom  = Column(Integer, default=8)
    H2Font          = Column(String(200), default='')
    H3MarginTop     = Column(Integer, default=0)
    H3MarginBottom  = Column(Integer, default=6)
    H3Font          = Column(String(200), default='')
    H4MarginTop     = Column(Integer, default=0)
    H4MarginBottom  = Column(Integer, default=4)
    H4Font          = Column(String(200), default='')
    BodySize        = Column(String(20), default='16px')
    BodyLineHeight  = Column(String(10), default='1.75')
    BodyColor       = Column(String(20), default='')
    BodyAlign       = Column(String(10), default='left')
    BodyUnderline   = Column(Boolean, default=False)
    BodyItalic      = Column(Boolean, default=False)
    # Site-wide image styling
    ImageBorderRadius   = Column(Integer, default=0)       # percent 0-50
    ImageShadowEnabled  = Column(Boolean, default=False)
    ImageShadowColor    = Column(String(40), default='rgba(0,0,0,0.35)')
    ImageShadowDistance = Column(Integer, default=4)       # px
    ImageShadowBlur     = Column(Integer, default=8)       # px
    ImageShadowAngle    = Column(Integer, default=135)     # degrees 0-359
    BodyMarginTop   = Column(Integer, default=0)
    BodyMarginBottom= Column(Integer, default=12)
    BodyFont        = Column(String(200), default='')
    LinkColor           = Column(String(20), default='')
    LinkUnderline       = Column(Boolean, default=True)
    DropdownBgColor     = Column(String(50))
    DropdownHoverColor  = Column(String(50))
    DropdownBgColor2    = Column(String(50))
    DropdownGradientDir = Column(String(20), default='135deg')
    Phone           = Column(String(50))
    Email           = Column(String(255))
    Address         = Column(String(500))
    FacebookURL     = Column(String(500))
    InstagramURL    = Column(String(500))
    TwitterURL      = Column(String(500))
    NavTextColor    = Column(String(20), default='#FFFFFF')
    FooterBgColor   = Column(String(20))
    FooterBgImageURL= Column(String(1000))
    FooterHTML      = Column(Text)
    FooterHeight    = Column(Integer, default=200)
    FooterBottomRadius = Column(Integer, default=0)
    CopyrightBarBgColor = Column(String(20))
    CopyrightText   = Column(String(500))
    IsPublished     = Column(Boolean, default=False)
    MetaTitle       = Column(String(255))
    CanonicalURL    = Column(String(500))
    OgImageURL      = Column(String(1000))
    SeoExtrasJSON   = Column(Text)
    MenuStyleJSON   = Column(Text)
    FooterJSON      = Column(Text)
    # Width controls
    HeaderContentWidth = Column(String(20), default='100%')
    FooterContentWidth = Column(String(20), default='100%')
    # Top bar
    TopBarEnabled   = Column(Boolean, default=False)
    TopBarHTML      = Column(Text)
    TopBarBgColor   = Column(String(20), default='#f8f5ef')
    TopBarTextColor = Column(String(20), default='#333333')
    TopBarAlign     = Column(String(10), default='right')
    # Header banner
    HeaderBannerURL    = Column(String(1000))
    HeaderBannerBgColor = Column(String(20))
    HeaderHeight    = Column(Integer, default=120)
    ShowSiteName    = Column(Boolean, default=True)
    # Layout: 'banner_top' (default — logo banner above nav) or 'nav_top'
    # (slim nav above a larger centered-logo band, reference: oregonqha.com)
    HeaderLayout   = Column(String(20), default='banner_top')
    # Nav bar
    NavBgImageURL   = Column(String(1000))
    # Favicon
    FaviconURL      = Column(String(1000))
    CreatedAt       = Column(DateTime)
    UpdatedAt       = Column(DateTime)

class BusinessWebPage(Base):
    __tablename__ = "BusinessWebPage"
    PageID          = Column(Integer, primary_key=True, autoincrement=True)
    WebsiteID       = Column(Integer, nullable=False, index=True)
    BusinessID      = Column(Integer, nullable=False)
    PageName        = Column(String(255))
    Slug            = Column(String(100))
    PageTitle       = Column(String(255))
    MetaDescription = Column(String(500))
    SortOrder       = Column(Integer, default=0)
    IsPublished     = Column(Boolean, default=True)
    IsHomePage      = Column(Boolean, default=False)
    ParentPageID    = Column(Integer, nullable=True)
    IsNavHeading    = Column(Boolean, default=False)
    LinkURL         = Column(String(500), nullable=True)
    CreatedAt       = Column(DateTime)
    UpdatedAt       = Column(DateTime)

class BusinessWebBlock(Base):
    __tablename__ = "BusinessWebBlock"
    BlockID     = Column(Integer, primary_key=True, autoincrement=True)
    PageID      = Column(Integer, nullable=False, index=True)
    BlockType   = Column(String(50))
    BlockData   = Column(Text)   # JSON string
    SortOrder   = Column(Integer, default=0)
    CreatedAt   = Column(DateTime)
    UpdatedAt   = Column(DateTime)


class WebsiteCustomDomain(Base):
    """Indexed lookup table: one row per custom domain pointing to a WebsiteID.
    Populated automatically when CanonicalURL is saved and used for fast
    O(log n) domain resolution instead of a full-table LIKE scan."""
    __tablename__ = "WebsiteCustomDomain"
    DomainID  = Column(Integer, primary_key=True, autoincrement=True)
    WebsiteID = Column(Integer, nullable=False, index=True)
    Domain    = Column(String(255), nullable=False, unique=True)
    IsActive  = Column(Boolean, default=True)
    CreatedAt = Column(DateTime)


# ── SITE SETTINGS (single-row control table) ─────────────────────
class SiteSettings(Base):
    __tablename__ = "SiteSettings"
    id              = Column(Integer, primary_key=True, default=1)
    team_only_login = Column(Boolean, nullable=False, default=True)   # True = team members only
    signup_open     = Column(Boolean, nullable=False, default=False)  # True = join page visible




# ── BUSINESS BLOG POSTS ──────────────────────────────────────────
class BusinessBlogPost(Base):
    __tablename__ = "BusinessBlogPosts"
    PostID       = Column(Integer, primary_key=True, autoincrement=True)
    BusinessID   = Column(Integer, nullable=False, index=True)
    Title        = Column(String(500), nullable=False)
    Slug         = Column(String(500))
    Excerpt      = Column(String(1000))
    Content      = Column(Text)
    CoverImage   = Column(String(500))
    Category     = Column(String(100))
    IsPublished  = Column(Boolean, default=False)
    CreatedAt    = Column(DateTime)
    UpdatedAt    = Column(DateTime)

