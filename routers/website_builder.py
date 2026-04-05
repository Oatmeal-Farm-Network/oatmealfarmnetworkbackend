from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine, Base
from datetime import datetime, date
from typing import Optional, List
from pydantic import BaseModel
import models, json, re, uuid

router = APIRouter(prefix="/api/website", tags=["website-builder"])

Base.metadata.create_all(
    bind=engine,
    tables=[
        models.BusinessWebsite.__table__,
        models.BusinessWebPage.__table__,
        models.BusinessWebBlock.__table__,
    ],
    checkfirst=True,
)

# Auto-create supplemental tables
with engine.connect() as _conn:
    _conn.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'WebsiteHeaderImages')
        CREATE TABLE WebsiteHeaderImages (
            HeaderImageID INT IDENTITY(1,1) PRIMARY KEY,
            WebsiteID     INT NOT NULL,
            ImageURL      NVARCHAR(500) NOT NULL,
            StartDate     DATE,
            EndDate       DATE,
            SortOrder     INT DEFAULT 0,
            CreatedAt     DATETIME DEFAULT GETDATE()
        )
    """))
    _conn.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'WebsiteVersionHistory')
        CREATE TABLE WebsiteVersionHistory (
            VersionID    INT IDENTITY(1,1) PRIMARY KEY,
            WebsiteID    INT NOT NULL,
            VersionLabel NVARCHAR(255),
            SnapshotJSON NVARCHAR(MAX) NOT NULL,
            CreatedAt    DATETIME DEFAULT GETDATE()
        )
    """))
    _conn.commit()

# ── Pydantic models ──────────────────────────────────────────────

class SiteCreate(BaseModel):
    business_id: int
    site_name: str
    slug: str
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = '#3D6B34'
    secondary_color: Optional[str] = '#819360'
    accent_color: Optional[str] = '#FFC567'
    bg_color: Optional[str] = '#FFFFFF'
    text_color: Optional[str] = '#111827'
    font_family: Optional[str] = 'Inter, sans-serif'
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    facebook_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    nav_text_color: Optional[str] = '#FFFFFF'
    footer_bg_color: Optional[str] = None
    copyright_text: Optional[str] = None
    is_published: Optional[bool] = False
    meta_title: Optional[str] = None
    canonical_url: Optional[str] = None
    og_image_url: Optional[str] = None
    seo_extras_json: Optional[str] = None

class SiteUpdate(SiteCreate):
    business_id: Optional[int] = None
    site_name: Optional[str] = None
    slug: Optional[str] = None

class PageCreate(BaseModel):
    website_id: int
    business_id: int
    page_name: str
    slug: str
    page_title: Optional[str] = None
    meta_description: Optional[str] = None
    sort_order: Optional[int] = 0
    is_published: Optional[bool] = True
    is_home_page: Optional[bool] = False

class PageUpdate(BaseModel):
    page_name: Optional[str] = None
    slug: Optional[str] = None
    page_title: Optional[str] = None
    meta_description: Optional[str] = None
    sort_order: Optional[int] = None
    is_published: Optional[bool] = None
    is_home_page: Optional[bool] = None

class BlockCreate(BaseModel):
    page_id: int
    block_type: str
    block_data: dict
    sort_order: Optional[int] = 0

class BlockUpdate(BaseModel):
    block_type: Optional[str] = None
    block_data: Optional[dict] = None
    sort_order: Optional[int] = None

class BlockReorder(BaseModel):
    block_ids: List[int]  # ordered list of IDs


# ── Serializers ──────────────────────────────────────────────────

def _ser_site(s: models.BusinessWebsite) -> dict:
    return {
        "website_id":     s.WebsiteID,
        "business_id":    s.BusinessID,
        "site_name":      s.SiteName,
        "slug":           s.Slug,
        "tagline":        s.Tagline,
        "logo_url":       s.LogoURL,
        "primary_color":  s.PrimaryColor or '#3D6B34',
        "secondary_color":s.SecondaryColor or '#819360',
        "accent_color":   s.AccentColor or '#FFC567',
        "bg_color":       s.BgColor or '#FFFFFF',
        "text_color":     s.TextColor or '#111827',
        "font_family":    s.FontFamily or 'Inter, sans-serif',
        "phone":          s.Phone,
        "email":          s.Email,
        "address":        s.Address,
        "facebook_url":   s.FacebookURL,
        "instagram_url":  s.InstagramURL,
        "twitter_url":    s.TwitterURL,
        "nav_text_color":  s.NavTextColor or '#FFFFFF',
        "footer_bg_color": s.FooterBgColor or s.PrimaryColor or '#3D6B34',
        "copyright_text":  s.CopyrightText,
        "is_published":    bool(s.IsPublished),
        "meta_title":      s.MetaTitle,
        "canonical_url":   s.CanonicalURL,
        "og_image_url":    s.OgImageURL,
        "seo_extras_json": s.SeoExtrasJSON,
        "created_at":      str(s.CreatedAt) if s.CreatedAt else None,
        "updated_at":      str(s.UpdatedAt) if s.UpdatedAt else None,
    }

def _ser_page(p: models.BusinessWebPage) -> dict:
    return {
        "page_id":          p.PageID,
        "website_id":       p.WebsiteID,
        "business_id":      p.BusinessID,
        "page_name":        p.PageName,
        "slug":             p.Slug,
        "page_title":       p.PageTitle,
        "meta_description": p.MetaDescription,
        "sort_order":       p.SortOrder or 0,
        "is_published":     bool(p.IsPublished),
        "is_home_page":     bool(p.IsHomePage),
        "created_at":       str(p.CreatedAt) if p.CreatedAt else None,
    }

def _ser_block(b: models.BusinessWebBlock) -> dict:
    try:
        data = json.loads(b.BlockData) if b.BlockData else {}
    except Exception:
        data = {}
    return {
        "block_id":   b.BlockID,
        "page_id":    b.PageID,
        "block_type": b.BlockType,
        "block_data": data,
        "sort_order": b.SortOrder or 0,
        "created_at": str(b.CreatedAt) if b.CreatedAt else None,
    }


# ── Site endpoints ───────────────────────────────────────────────

@router.get("/site")
def get_site(business_id: int, db: Session = Depends(get_db)):
    site = db.query(models.BusinessWebsite).filter(
        models.BusinessWebsite.BusinessID == business_id
    ).first()
    if not site:
        return None
    return _ser_site(site)

@router.get("/site/slug/{slug}")
def get_site_by_slug(slug: str, db: Session = Depends(get_db)):
    site = db.query(models.BusinessWebsite).filter(
        models.BusinessWebsite.Slug == slug
    ).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return _ser_site(site)

@router.post("/site")
def create_site(body: SiteCreate, db: Session = Depends(get_db)):
    # Check slug uniqueness
    existing = db.query(models.BusinessWebsite).filter(
        models.BusinessWebsite.Slug == body.slug
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Slug already taken")
    site = models.BusinessWebsite(
        BusinessID=body.business_id, SiteName=body.site_name, Slug=body.slug,
        Tagline=body.tagline, LogoURL=body.logo_url,
        PrimaryColor=body.primary_color, SecondaryColor=body.secondary_color,
        AccentColor=body.accent_color, BgColor=body.bg_color, TextColor=body.text_color,
        FontFamily=body.font_family, Phone=body.phone, Email=body.email, Address=body.address,
        FacebookURL=body.facebook_url, InstagramURL=body.instagram_url, TwitterURL=body.twitter_url,
        NavTextColor=body.nav_text_color or '#FFFFFF',
        FooterBgColor=body.footer_bg_color,
        CopyrightText=body.copyright_text,
        IsPublished=body.is_published,
        MetaTitle=body.meta_title,
        CanonicalURL=body.canonical_url,
        OgImageURL=body.og_image_url,
        SeoExtrasJSON=body.seo_extras_json,
        CreatedAt=datetime.utcnow(), UpdatedAt=datetime.utcnow()
    )
    db.add(site); db.commit(); db.refresh(site)
    return _ser_site(site)

@router.put("/site/{website_id}")
def update_site(website_id: int, body: SiteUpdate, db: Session = Depends(get_db)):
    site = db.query(models.BusinessWebsite).filter(
        models.BusinessWebsite.WebsiteID == website_id
    ).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    if body.site_name is not None: site.SiteName = body.site_name
    if body.slug is not None:
        conflict = db.query(models.BusinessWebsite).filter(
            models.BusinessWebsite.Slug == body.slug,
            models.BusinessWebsite.WebsiteID != website_id
        ).first()
        if conflict:
            raise HTTPException(status_code=400, detail="Slug already taken")
        site.Slug = body.slug
    if body.tagline is not None: site.Tagline = body.tagline
    if body.logo_url is not None: site.LogoURL = body.logo_url
    if body.primary_color is not None: site.PrimaryColor = body.primary_color
    if body.secondary_color is not None: site.SecondaryColor = body.secondary_color
    if body.accent_color is not None: site.AccentColor = body.accent_color
    if body.bg_color is not None: site.BgColor = body.bg_color
    if body.text_color is not None: site.TextColor = body.text_color
    if body.font_family is not None: site.FontFamily = body.font_family
    if body.phone is not None: site.Phone = body.phone
    if body.email is not None: site.Email = body.email
    if body.address is not None: site.Address = body.address
    if body.facebook_url is not None: site.FacebookURL = body.facebook_url
    if body.instagram_url is not None: site.InstagramURL = body.instagram_url
    if body.twitter_url is not None: site.TwitterURL = body.twitter_url
    if body.is_published is not None: site.IsPublished = body.is_published
    if body.nav_text_color is not None: site.NavTextColor = body.nav_text_color
    if body.footer_bg_color is not None: site.FooterBgColor = body.footer_bg_color
    if body.copyright_text is not None: site.CopyrightText = body.copyright_text
    if body.meta_title is not None: site.MetaTitle = body.meta_title
    if body.canonical_url is not None: site.CanonicalURL = body.canonical_url
    if body.og_image_url is not None: site.OgImageURL = body.og_image_url
    if body.seo_extras_json is not None: site.SeoExtrasJSON = body.seo_extras_json
    site.UpdatedAt = datetime.utcnow()
    db.commit(); db.refresh(site)
    return _ser_site(site)


# ── Page endpoints ───────────────────────────────────────────────

@router.get("/pages")
def list_pages(website_id: int, db: Session = Depends(get_db)):
    pages = db.query(models.BusinessWebPage).filter(
        models.BusinessWebPage.WebsiteID == website_id
    ).order_by(models.BusinessWebPage.SortOrder).all()
    return [_ser_page(p) for p in pages]

@router.post("/pages")
def create_page(body: PageCreate, db: Session = Depends(get_db)):
    page = models.BusinessWebPage(
        WebsiteID=body.website_id, BusinessID=body.business_id,
        PageName=body.page_name, Slug=body.slug, PageTitle=body.page_title,
        MetaDescription=body.meta_description, SortOrder=body.sort_order,
        IsPublished=body.is_published, IsHomePage=body.is_home_page,
        CreatedAt=datetime.utcnow(), UpdatedAt=datetime.utcnow()
    )
    db.add(page); db.commit(); db.refresh(page)
    return _ser_page(page)

@router.put("/pages/{page_id}")
def update_page(page_id: int, body: PageUpdate, db: Session = Depends(get_db)):
    page = db.query(models.BusinessWebPage).filter(
        models.BusinessWebPage.PageID == page_id
    ).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    if body.page_name is not None: page.PageName = body.page_name
    if body.slug is not None: page.Slug = body.slug
    if body.page_title is not None: page.PageTitle = body.page_title
    if body.meta_description is not None: page.MetaDescription = body.meta_description
    if body.sort_order is not None: page.SortOrder = body.sort_order
    if body.is_published is not None: page.IsPublished = body.is_published
    if body.is_home_page is not None: page.IsHomePage = body.is_home_page
    page.UpdatedAt = datetime.utcnow()
    db.commit(); db.refresh(page)
    return _ser_page(page)

@router.delete("/pages/{page_id}")
def delete_page(page_id: int, db: Session = Depends(get_db)):
    page = db.query(models.BusinessWebPage).filter(
        models.BusinessWebPage.PageID == page_id
    ).first()
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    db.query(models.BusinessWebBlock).filter(
        models.BusinessWebBlock.PageID == page_id
    ).delete()
    db.delete(page); db.commit()
    return {"success": True}


# ── Block endpoints ──────────────────────────────────────────────

@router.get("/blocks/{page_id}")
def list_blocks(page_id: int, db: Session = Depends(get_db)):
    blocks = db.query(models.BusinessWebBlock).filter(
        models.BusinessWebBlock.PageID == page_id
    ).order_by(models.BusinessWebBlock.SortOrder).all()
    return [_ser_block(b) for b in blocks]

@router.post("/blocks")
def create_block(body: BlockCreate, db: Session = Depends(get_db)):
    block = models.BusinessWebBlock(
        PageID=body.page_id, BlockType=body.block_type,
        BlockData=json.dumps(body.block_data), SortOrder=body.sort_order,
        CreatedAt=datetime.utcnow(), UpdatedAt=datetime.utcnow()
    )
    db.add(block); db.commit(); db.refresh(block)
    return _ser_block(block)

@router.put("/blocks/{block_id}")
def update_block(block_id: int, body: BlockUpdate, db: Session = Depends(get_db)):
    block = db.query(models.BusinessWebBlock).filter(
        models.BusinessWebBlock.BlockID == block_id
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    if body.block_type is not None: block.BlockType = body.block_type
    if body.block_data is not None: block.BlockData = json.dumps(body.block_data)
    if body.sort_order is not None: block.SortOrder = body.sort_order
    block.UpdatedAt = datetime.utcnow()
    db.commit(); db.refresh(block)
    return _ser_block(block)

@router.delete("/blocks/{block_id}")
def delete_block(block_id: int, db: Session = Depends(get_db)):
    block = db.query(models.BusinessWebBlock).filter(
        models.BusinessWebBlock.BlockID == block_id
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="Block not found")
    db.delete(block); db.commit()
    return {"success": True}

@router.post("/blocks/reorder")
def reorder_blocks(body: BlockReorder, db: Session = Depends(get_db)):
    for idx, bid in enumerate(body.block_ids):
        db.query(models.BusinessWebBlock).filter(
            models.BusinessWebBlock.BlockID == bid
        ).update({"SortOrder": idx, "UpdatedAt": datetime.utcnow()})
    db.commit()
    return {"success": True}


# ── Live content endpoints (for dynamic blocks) ──────────────────

@router.get("/content/livestock")
def get_livestock(business_id: int, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT TOP 20 a.AnimalID, a.FullName, a.ShortName, a.Description,
                   a.PublishForSale, a.PublishStud, a.Category, a.Breed,
                   a.StudDescription, a.Financeterms,
                   p.Photo1
            FROM animals a
            LEFT JOIN productsphotos p ON p.AnimalID = a.AnimalID
            WHERE a.BusinessID = :bid AND (a.PublishForSale = 1 OR a.PublishStud = 1)
            ORDER BY a.AnimalID DESC
        """), {"bid": business_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        return []

@router.get("/content/produce")
def get_produce(business_id: int, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT TOP 20 p.ProduceID, i.IngredientName, p.Quantity,
                   p.QuantityMeasurement, p.RetailPrice, p.WholesalePrice,
                   p.IsOrganic, p.IsLocal, p.HarvestDate, p.AvailableDate
            FROM Produce p
            JOIN Ingredients i ON i.IngredientID = p.IngredientID
            WHERE p.BusinessID = :bid AND p.ShowProduce = 1
            ORDER BY p.ProduceID DESC
        """), {"bid": business_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        return []

@router.get("/content/meat")
def get_meat(business_id: int, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT TOP 20 m.MeatInventoryID, i.IngredientName, m.Weight,
                   m.WeightUnit, m.Quantity, m.RetailPrice, m.WholesalePrice, m.AvailableDate
            FROM MeatInventory m
            JOIN Ingredients i ON i.IngredientID = m.IngredientID
            WHERE m.BusinessID = :bid AND m.ShowMeat = 1
            ORDER BY m.MeatInventoryID DESC
        """), {"bid": business_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        return []

@router.get("/content/processed-food")
def get_processed_food(business_id: int, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT TOP 20 ProcessedFoodID, Name, Description, Quantity,
                   RetailPrice, WholesalePrice, ImageURL, AvailableDate
            FROM ProcessedFood
            WHERE BusinessID = :bid AND ShowProcessedFood = 1
            ORDER BY ProcessedFoodID DESC
        """), {"bid": business_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        return []

@router.get("/content/services")
def get_services(business_id: int, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT TOP 20 ServicesID, ServiceTitle, ServicesDescription,
                   ServicePrice, Price2, Photo1
            FROM services
            WHERE BusinessID = :bid AND ServiceAvailable = 1
            ORDER BY ServicesID DESC
        """), {"bid": business_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        return []

@router.get("/content/marketplace")
def get_marketplace(business_id: int, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT TOP 20 ListingID, Title, Description, CategoryName,
                   UnitPrice, UnitLabel, QuantityAvailable, ImageURL,
                   IsOrganic, IsLocal, IsFeatured, ProductType
            FROM MarketplaceListings
            WHERE BusinessID = :bid AND IsActive = 1
            ORDER BY IsFeatured DESC, ListingID DESC
        """), {"bid": business_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        return []

@router.get("/content/blog")
def get_blog(business_id: int, db: Session = Depends(get_db)):
    try:
        # blog is linked to PeopleID, find via business
        rows = db.execute(text("""
            SELECT TOP 10 b.BlogID, b.BlogHeadline, b.Author,
                   b.BlogYear, b.BlogMonth, b.BlogDay,
                   b.BlogText1, b.BlogImage1
            FROM blog b
            JOIN BusinessAccess ba ON ba.PeopleID = b.PeopleID
            WHERE ba.BusinessID = :bid AND b.BlogDisplay = 1
            ORDER BY b.BlogYear DESC, b.BlogMonth DESC, b.BlogDay DESC
        """), {"bid": business_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        return []

@router.get("/content/gallery")
def get_gallery(business_id: int, db: Session = Depends(get_db)):
    try:
        rows = db.execute(text("""
            SELECT TOP 50 g.GalleryID, g.GalleryImage, g.GalleryCaption,
                   gc.GalleryCategoryName
            FROM gallery g
            LEFT JOIN gallerycategories gc ON gc.GalleryCatID = g.GalleryCatID
            JOIN BusinessAccess ba ON ba.PeopleID = g.PeopleID
            WHERE ba.BusinessID = :bid
            ORDER BY g.ImageOrder, g.GalleryID
        """), {"bid": business_id}).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        return []


# ── Content availability check ───────────────────────────────────

@router.get("/content/check")
def check_content(business_id: int, db: Session = Depends(get_db)):
    """Returns which content types the business has live data for."""
    def has(query, params):
        try:
            row = db.execute(text(query), params).fetchone()
            return row is not None and row[0] > 0
        except:
            return False

    bid = {"bid": business_id}
    return {
        "livestock_for_sale": has("SELECT COUNT(1) FROM animals WHERE BusinessID=:bid AND PublishForSale=1", bid),
        "studs":              has("SELECT COUNT(1) FROM animals WHERE BusinessID=:bid AND PublishStud=1", bid),
        "produce":            has("SELECT COUNT(1) FROM Produce WHERE BusinessID=:bid AND ShowProduce=1", bid),
        "meat":               has("SELECT COUNT(1) FROM MeatInventory WHERE BusinessID=:bid AND ShowMeat=1", bid),
        "processed_food":     has("SELECT COUNT(1) FROM ProcessedFood WHERE BusinessID=:bid AND ShowProcessedFood=1", bid),
        "services":           has("SELECT COUNT(1) FROM services WHERE BusinessID=:bid AND ServiceAvailable=1", bid),
        "products":           has("SELECT COUNT(1) FROM products WHERE BusinessID=:bid AND IsActive=1", bid),
        "marketplace":        has("SELECT COUNT(1) FROM MarketplaceListings WHERE BusinessID=:bid AND IsActive=1", bid),
    }


# ── Full site bundle (for public renderer) ───────────────────────

@router.get("/bundle/{slug}")
def get_site_bundle(slug: str, db: Session = Depends(get_db)):
    """Returns site + all pages + all blocks in a single request for the public renderer."""
    site = db.query(models.BusinessWebsite).filter(
        models.BusinessWebsite.Slug == slug
    ).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    pages = db.query(models.BusinessWebPage).filter(
        models.BusinessWebPage.WebsiteID == site.WebsiteID,
        models.BusinessWebPage.IsPublished == True
    ).order_by(models.BusinessWebPage.SortOrder).all()

    result_pages = []
    for page in pages:
        blocks = db.query(models.BusinessWebBlock).filter(
            models.BusinessWebBlock.PageID == page.PageID
        ).order_by(models.BusinessWebBlock.SortOrder).all()
        p = _ser_page(page)
        p["blocks"] = [_ser_block(b) for b in blocks]
        result_pages.append(p)

    site_data = _ser_site(site)
    site_data["pages"] = result_pages
    return site_data


# ── Image upload ─────────────────────────────────────────────────

GCS_BUCKET  = "oatmeal-farm-network-images"
GCS_PREFIX  = "website-images"

@router.delete("/site/{website_id}")
def delete_site(website_id: int, db: Session = Depends(get_db)):
    site = db.query(models.BusinessWebsite).filter(
        models.BusinessWebsite.WebsiteID == website_id
    ).first()
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    # Delete all child data first
    page_ids = [p.PageID for p in db.query(models.BusinessWebPage).filter(
        models.BusinessWebPage.WebsiteID == website_id
    ).all()]
    if page_ids:
        db.query(models.BusinessWebBlock).filter(
            models.BusinessWebBlock.PageID.in_(page_ids)
        ).delete(synchronize_session=False)
    db.query(models.BusinessWebPage).filter(
        models.BusinessWebPage.WebsiteID == website_id
    ).delete(synchronize_session=False)
    db.execute(text("DELETE FROM WebsiteHeaderImages WHERE WebsiteID=:wid"), {"wid": website_id})
    db.delete(site)
    db.commit()
    return {"ok": True}


@router.post("/upload-image")
async def upload_website_image(file: UploadFile = File(...)):
    """Upload an image to GCS and return its public URL."""
    try:
        from google.cloud import storage as gcs
        contents = await file.read()
        ext = (file.filename or "image.jpg").rsplit(".", 1)[-1].lower()
        filename = f"{GCS_PREFIX}/{uuid.uuid4().hex}.{ext}"
        client = gcs.Client()
        bucket = client.bucket(GCS_BUCKET)
        blob = bucket.blob(filename)
        blob.upload_from_string(contents, content_type=file.content_type or "image/jpeg")
        url = f"https://storage.googleapis.com/{GCS_BUCKET}/{filename}"
        return {"url": url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# ── Header images ─────────────────────────────────────────────────

class HeaderImageCreate(BaseModel):
    website_id: int
    image_url: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    sort_order: Optional[int] = 0

class HeaderImageUpdate(BaseModel):
    image_url: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    sort_order: Optional[int] = None

def _ser_header_image(row) -> dict:
    return {
        "header_image_id": row.HeaderImageID,
        "website_id":      row.WebsiteID,
        "image_url":       row.ImageURL,
        "start_date":      str(row.StartDate) if row.StartDate else None,
        "end_date":        str(row.EndDate) if row.EndDate else None,
        "sort_order":      row.SortOrder or 0,
    }

@router.get("/header-images/{website_id}")
def list_header_images(website_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        text("SELECT * FROM WebsiteHeaderImages WHERE WebsiteID=:wid ORDER BY StartDate, SortOrder"),
        {"wid": website_id}
    ).fetchall()
    return [_ser_header_image(r) for r in rows]

@router.post("/header-images")
def create_header_image(body: HeaderImageCreate, db: Session = Depends(get_db)):
    db.execute(text("""
        INSERT INTO WebsiteHeaderImages (WebsiteID, ImageURL, StartDate, EndDate, SortOrder)
        VALUES (:wid, :url, :sd, :ed, :so)
    """), {"wid": body.website_id, "url": body.image_url,
           "sd": body.start_date, "ed": body.end_date, "so": body.sort_order or 0})
    db.commit()
    row = db.execute(
        text("SELECT TOP 1 * FROM WebsiteHeaderImages WHERE WebsiteID=:wid ORDER BY HeaderImageID DESC"),
        {"wid": body.website_id}
    ).fetchone()
    return _ser_header_image(row)

@router.put("/header-images/{header_image_id}")
def update_header_image(header_image_id: int, body: HeaderImageUpdate, db: Session = Depends(get_db)):
    sets, params = [], {"hid": header_image_id}
    if body.image_url is not None:  sets.append("ImageURL=:url");   params["url"] = body.image_url
    if body.start_date is not None: sets.append("StartDate=:sd");   params["sd"]  = body.start_date
    if body.end_date is not None:   sets.append("EndDate=:ed");     params["ed"]  = body.end_date
    if body.sort_order is not None: sets.append("SortOrder=:so");   params["so"]  = body.sort_order
    if sets:
        db.execute(text(f"UPDATE WebsiteHeaderImages SET {', '.join(sets)} WHERE HeaderImageID=:hid"), params)
        db.commit()
    row = db.execute(text("SELECT * FROM WebsiteHeaderImages WHERE HeaderImageID=:hid"), {"hid": header_image_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Header image not found")
    return _ser_header_image(row)

@router.delete("/header-images/{header_image_id}")
def delete_header_image(header_image_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM WebsiteHeaderImages WHERE HeaderImageID=:hid"), {"hid": header_image_id})
    db.commit()
    return {"ok": True}


# ── Version History ───────────────────────────────────────────────

class VersionCreate(BaseModel):
    website_id: int
    version_label: Optional[str] = None

def _build_snapshot(website_id: int, db: Session) -> str:
    """Capture full site state: site + pages + blocks."""
    site = db.query(models.BusinessWebsite).filter(models.BusinessWebsite.WebsiteID == website_id).first()
    if not site:
        return "{}"
    pages = db.query(models.BusinessWebPage).filter(models.BusinessWebPage.WebsiteID == website_id).all()
    result = {"site": _ser_site(site), "pages": []}
    for page in pages:
        blocks = db.query(models.BusinessWebBlock).filter(models.BusinessWebBlock.PageID == page.PageID).all()
        p = _ser_page(page)
        p["blocks"] = [_ser_block(b) for b in blocks]
        result["pages"].append(p)
    return json.dumps(result)

@router.get("/versions/{website_id}")
def list_versions(website_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        text("SELECT TOP 20 VersionID, WebsiteID, VersionLabel, CreatedAt FROM WebsiteVersionHistory WHERE WebsiteID=:wid ORDER BY CreatedAt DESC"),
        {"wid": website_id}
    ).fetchall()
    return [{"version_id": r.VersionID, "website_id": r.WebsiteID, "version_label": r.VersionLabel, "created_at": str(r.CreatedAt)} for r in rows]

@router.post("/versions")
def save_version(body: VersionCreate, db: Session = Depends(get_db)):
    snapshot = _build_snapshot(body.website_id, db)
    label = body.version_label or f"Saved {datetime.utcnow().strftime('%b %d %Y %H:%M')}"
    db.execute(text("""
        INSERT INTO WebsiteVersionHistory (WebsiteID, VersionLabel, SnapshotJSON)
        VALUES (:wid, :label, :snap)
    """), {"wid": body.website_id, "label": label, "snap": snapshot})
    db.commit()
    row = db.execute(
        text("SELECT TOP 1 * FROM WebsiteVersionHistory WHERE WebsiteID=:wid ORDER BY VersionID DESC"),
        {"wid": body.website_id}
    ).fetchone()
    return {"version_id": row.VersionID, "version_label": row.VersionLabel, "created_at": str(row.CreatedAt)}

@router.post("/versions/{version_id}/restore")
def restore_version(version_id: int, db: Session = Depends(get_db)):
    row = db.execute(text("SELECT * FROM WebsiteVersionHistory WHERE VersionID=:vid"), {"vid": version_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found")
    snapshot = json.loads(row.SnapshotJSON)
    website_id = row.WebsiteID

    # Restore site fields
    site_data = snapshot.get("site", {})
    site = db.query(models.BusinessWebsite).filter(models.BusinessWebsite.WebsiteID == website_id).first()
    if site and site_data:
        for field, col in [
            ("site_name","SiteName"),("tagline","Tagline"),("logo_url","LogoURL"),
            ("primary_color","PrimaryColor"),("secondary_color","SecondaryColor"),
            ("accent_color","AccentColor"),("bg_color","BgColor"),("text_color","TextColor"),
            ("font_family","FontFamily"),("nav_text_color","NavTextColor"),
            ("footer_bg_color","FooterBgColor"),("copyright_text","CopyrightText"),
        ]:
            if field in site_data:
                setattr(site, col, site_data[field])
        site.UpdatedAt = datetime.utcnow()

    # Restore pages and blocks
    existing_pages = db.query(models.BusinessWebPage).filter(models.BusinessWebPage.WebsiteID == website_id).all()
    existing_page_ids = [p.PageID for p in existing_pages]
    if existing_page_ids:
        db.query(models.BusinessWebBlock).filter(models.BusinessWebBlock.PageID.in_(existing_page_ids)).delete(synchronize_session=False)
    db.query(models.BusinessWebPage).filter(models.BusinessWebPage.WebsiteID == website_id).delete(synchronize_session=False)

    for pg in snapshot.get("pages", []):
        new_page = models.BusinessWebPage(
            WebsiteID=website_id, BusinessID=site_data.get("business_id", 0),
            PageName=pg["page_name"], Slug=pg["slug"],
            PageTitle=pg.get("page_title"), MetaDescription=pg.get("meta_description"),
            SortOrder=pg.get("sort_order", 0), IsPublished=pg.get("is_published", True),
            IsHomePage=pg.get("is_home_page", False),
            CreatedAt=datetime.utcnow(), UpdatedAt=datetime.utcnow()
        )
        db.add(new_page); db.flush()
        for blk in pg.get("blocks", []):
            db.add(models.BusinessWebBlock(
                PageID=new_page.PageID, BlockType=blk["block_type"],
                BlockData=json.dumps(blk["block_data"]), SortOrder=blk.get("sort_order", 0),
                CreatedAt=datetime.utcnow(), UpdatedAt=datetime.utcnow()
            ))

    db.commit()
    return {"ok": True, "website_id": website_id}
