from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine, Base
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel
import models, json, re

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
        "is_published":   bool(s.IsPublished),
        "created_at":     str(s.CreatedAt) if s.CreatedAt else None,
        "updated_at":     str(s.UpdatedAt) if s.UpdatedAt else None,
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
        IsPublished=body.is_published, CreatedAt=datetime.utcnow(), UpdatedAt=datetime.utcnow()
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
