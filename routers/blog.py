from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from pydantic import BaseModel
from typing import Optional
import re
from datetime import datetime

router = APIRouter(prefix="/api/blog", tags=["blog"])




def _slugify(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s]+', '-', s)
    return s[:200]


# Run schema migration only once per process lifetime
_schema_migrated = False

def _ensure_schema(db: Session):
    """
    Add any missing columns to blog / blogcategories / blogphotos.
    Runs once per server process; each ALTER is wrapped independently
    so a single failure never aborts the rest.
    """
    global _schema_migrated
    if _schema_migrated:
        return

    additions = [
        # blog
        ("blog", "BusinessID",  "INT NULL"),
        ("blog", "Title",       "NVARCHAR(500) NULL"),
        ("blog", "Slug",        "NVARCHAR(500) NULL"),
        ("blog", "CoverImage",  "NVARCHAR(500) NULL"),
        ("blog", "Content",     "NVARCHAR(MAX) NULL"),
        ("blog", "IsPublished", "BIT NOT NULL DEFAULT 0"),
        ("blog", "IsFeatured",  "BIT NOT NULL DEFAULT 0"),
        ("blog", "CreatedAt",   "DATETIME NULL"),
        ("blog", "UpdatedAt",   "DATETIME NULL"),
        ("blog", "CustomCatID", "INT NULL"),   # personal/business category
        # blogcategories
        ("blogcategories", "BusinessID", "INT NULL"),
        ("blogcategories", "IsGlobal",   "BIT NOT NULL DEFAULT 0"),
        ("blogcategories", "IsActive",   "BIT NOT NULL DEFAULT 1"),
        ("blogcategories", "CreatedAt",  "DATETIME NULL"),
        # blogphotos
        ("blogphotos", "BlogID",       "INT NULL"),
        ("blogphotos", "ImageCaption", "NVARCHAR(500) NULL"),
    ]
    for table, col, col_def in additions:
        try:
            # Check existence and ALTER in two separate round-trips —
            # SQL Server / pyodbc does not reliably execute
            # IF NOT EXISTS + DDL as a single batch.
            exists = db.execute(text(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                "WHERE TABLE_NAME = :t AND COLUMN_NAME = :c"
            ), {"t": table, "c": col}).scalar()
            if not exists:
                db.execute(text(f"ALTER TABLE [{table}] ADD [{col}] {col_def}"))
                db.commit()
        except Exception:
            db.rollback()

    # If the old BlogCategoryDisplay NOT NULL column still exists (pre-migration),
    # add a DEFAULT 1 so our INSERTs don't have to supply it.
    try:
        has_old_col = db.execute(text(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME='blogcategories' AND COLUMN_NAME='BlogCategoryDisplay'"
        )).scalar()
        if has_old_col:
            has_default = db.execute(text(
                "SELECT COUNT(*) FROM sys.default_constraints "
                "WHERE parent_object_id = OBJECT_ID('blogcategories') "
                "AND COL_NAME(parent_object_id, parent_column_id) = 'BlogCategoryDisplay'"
            )).scalar()
            if not has_default:
                db.execute(text(
                    "ALTER TABLE blogcategories "
                    "ADD CONSTRAINT DF_blogcategories_display DEFAULT 1 FOR BlogCategoryDisplay"
                ))
                db.commit()
    except Exception:
        db.rollback()

    # Seed global categories — only if IsGlobal column now exists
    try:
        count = db.execute(text(
            "SELECT COUNT(*) FROM blogcategories WHERE IsGlobal = 1"
        )).scalar()
        if count == 0:
            db.execute(text("""
                INSERT INTO blogcategories
                    (BusinessID, IsGlobal, BlogCategoryName, BlogCategoryOrder, IsActive, CreatedAt)
                VALUES
                  (NULL,1,'General',       1,1,GETDATE()),
                  (NULL,1,'Farm News',     2,1,GETDATE()),
                  (NULL,1,'Recipes',       3,1,GETDATE()),
                  (NULL,1,'Seasonal',      4,1,GETDATE()),
                  (NULL,1,'Events',        5,1,GETDATE()),
                  (NULL,1,'Education',     6,1,GETDATE()),
                  (NULL,1,'Market Updates',7,1,GETDATE()),
                  (NULL,1,'Community',     8,1,GETDATE())
            """))
            db.commit()
    except Exception:
        db.rollback()

    _schema_migrated = True


class PostIn(BaseModel):
    title: str
    content: Optional[str] = None
    cover_image: Optional[str] = None
    author: Optional[str] = None
    author_link: Optional[str] = None
    blog_cat_id: Optional[int] = None     # public / global category
    custom_cat_id: Optional[int] = None  # personal / business category
    is_published: bool = False
    is_featured: bool = False


class CategoryIn(BaseModel):
    name: str
    description: Optional[str] = None
    order: int = 0


class PhotoIn(BaseModel):
    blog_id: int
    image: str
    image_title: Optional[str] = None
    image_caption: Optional[str] = None
    photo_order: int = 0


def _post_row(r) -> dict:
    return {
        "blog_id":       r.BlogID,
        "business_id":   r.BusinessID,
        "blog_cat_id":   r.BlogCatID,
        "custom_cat_id": getattr(r, "CustomCatID", None),
        "title":         r.Title,
        "slug":          r.Slug,
        "author":        r.Author,
        "author_link":   r.AuthorLink,
        "cover_image":   r.CoverImage,
        "content":       r.Content,
        "is_published":  bool(r.IsPublished),
        "is_featured":   bool(r.IsFeatured),
        "created_at":    str(r.CreatedAt) if r.CreatedAt else None,
        "updated_at":    str(r.UpdatedAt) if r.UpdatedAt else None,
    }


# ── Global / network categories ─────────────────────────────────

@router.get("/categories/global")
def list_global_categories(db: Session = Depends(get_db)):
    """Return network-wide categories (IsGlobal=1)."""
    _ensure_schema(db)
    rows = db.execute(text("""
        SELECT BlogCatID, BlogCategoryName, BlogCategoryDescription, BlogCategoryOrder
        FROM blogcategories
        WHERE IsGlobal = 1 AND IsActive = 1
        ORDER BY BlogCategoryOrder, BlogCategoryName
    """)).fetchall()
    return [{"id": r.BlogCatID, "name": r.BlogCategoryName,
             "description": r.BlogCategoryDescription, "order": r.BlogCategoryOrder}
            for r in rows]


# ── Business-specific custom categories ─────────────────────────

@router.get("/categories/custom")
def list_custom_categories(business_id: int, db: Session = Depends(get_db)):
    """Return a business's own custom categories."""
    _ensure_schema(db)
    rows = db.execute(text("""
        SELECT BlogCatID, BlogCategoryName, BlogCategoryDescription, BlogCategoryOrder, IsActive
        FROM blogcategories
        WHERE BusinessID = :bid AND IsGlobal = 0
        ORDER BY BlogCategoryOrder, BlogCategoryName
    """), {"bid": business_id}).fetchall()
    return [{"id": r.BlogCatID, "name": r.BlogCategoryName,
             "description": r.BlogCategoryDescription,
             "order": r.BlogCategoryOrder, "is_active": bool(r.IsActive)}
            for r in rows]


@router.post("/categories/custom")
def create_custom_category(business_id: int, body: CategoryIn, db: Session = Depends(get_db)):
    """Add a custom category for a business."""
    _ensure_schema(db)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Category name required")
    existing = db.execute(text("""
        SELECT BlogCatID FROM blogcategories
        WHERE BusinessID = :bid AND IsGlobal = 0 AND LOWER(BlogCategoryName) = LOWER(:name)
    """), {"bid": business_id, "name": name}).fetchone()
    if existing:
        raise HTTPException(409, "Category already exists")
    result = db.execute(text("""
        INSERT INTO blogcategories (BusinessID, IsGlobal, BlogCategoryName, BlogCategoryDescription,
                                    BlogCategoryOrder, IsActive, CreatedAt)
        OUTPUT INSERTED.BlogCatID
        VALUES (:bid, 0, :name, :desc, :ord, 1, GETDATE())
    """), {"bid": business_id, "name": name, "desc": body.description, "ord": body.order})
    cat_id = result.fetchone()[0]
    db.commit()
    return {"id": cat_id, "name": name}


@router.put("/categories/custom/{cat_id}")
def update_custom_category(cat_id: int, business_id: int, body: CategoryIn,
                            db: Session = Depends(get_db)):
    """Rename / reorder a custom category."""
    _ensure_schema(db)
    result = db.execute(text("""
        UPDATE blogcategories
        SET BlogCategoryName=:name, BlogCategoryDescription=:desc, BlogCategoryOrder=:ord
        WHERE BlogCatID=:cid AND BusinessID=:bid AND IsGlobal=0
    """), {"cid": cat_id, "bid": business_id, "name": body.name.strip(),
           "desc": body.description, "ord": body.order})
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Category not found")
    return {"id": cat_id, "name": body.name.strip()}


@router.delete("/categories/custom/{cat_id}")
def delete_custom_category(cat_id: int, business_id: int, db: Session = Depends(get_db)):
    """Delete a custom category (must belong to this business)."""
    _ensure_schema(db)
    result = db.execute(text("""
        DELETE FROM blogcategories WHERE BlogCatID=:cid AND BusinessID=:bid AND IsGlobal=0
    """), {"cid": cat_id, "bid": business_id})
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Category not found")
    return {"deleted": cat_id}


# ── Public post endpoints ────────────────────────────────────────

@router.get("/posts")
def list_public_posts(
    business_id: Optional[int] = None,
    blog_cat_id: Optional[int] = None,
    category_name: Optional[str] = None,
    featured_only: bool = False,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List published posts, optionally filtered by business, category, or featured."""
    _ensure_schema(db)
    where = ["b.IsPublished = 1"]
    params: dict = {"limit": limit, "offset": offset}

    if business_id is not None:
        where.append("b.BusinessID = :bid")
        params["bid"] = business_id
    if blog_cat_id is not None:
        where.append("b.BlogCatID = :cid")
        params["cid"] = blog_cat_id
    if category_name:
        where.append("(bc.BlogCategoryName = :cname OR cc.BlogCategoryName = :cname)")
        params["cname"] = category_name
    if featured_only:
        where.append("b.IsFeatured = 1")

    where_sql = " AND ".join(where)
    rows = db.execute(text(f"""
        SELECT b.BlogID, b.BusinessID, b.BlogCatID, b.CustomCatID,
               b.Title, b.Slug, b.Author, b.AuthorLink, b.CoverImage, b.Content,
               b.IsPublished, b.IsFeatured, b.CreatedAt, b.UpdatedAt,
               biz.BusinessName,
               bc.BlogCategoryName,
               cc.BlogCategoryName AS CustomCategoryName
        FROM blog b
        JOIN Business biz ON biz.BusinessID = b.BusinessID
        LEFT JOIN blogcategories bc ON bc.BlogCatID = b.BlogCatID
        LEFT JOIN blogcategories cc ON cc.BlogCatID = b.CustomCatID
        WHERE {where_sql}
        ORDER BY b.IsFeatured DESC, b.CreatedAt DESC
        OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
    """), params).fetchall()

    return [
        {
            **_post_row(r),
            "business_name":      r.BusinessName,
            "category_name":      r.BlogCategoryName,
            "custom_category_name": r.CustomCategoryName,
        }
        for r in rows
    ]


@router.get("/posts/{blog_id}")
def get_post(blog_id: int, db: Session = Depends(get_db)):
    """Get a single published post with its photos."""
    _ensure_schema(db)
    row = db.execute(text("""
        SELECT b.BlogID, b.BusinessID, b.BlogCatID, b.CustomCatID,
               b.Title, b.Slug, b.Author, b.AuthorLink, b.CoverImage, b.Content,
               b.IsPublished, b.IsFeatured, b.CreatedAt, b.UpdatedAt,
               biz.BusinessName,
               bc.BlogCategoryName,
               cc.BlogCategoryName AS CustomCategoryName
        FROM blog b
        JOIN Business biz ON biz.BusinessID = b.BusinessID
        LEFT JOIN blogcategories bc ON bc.BlogCatID = b.BlogCatID
        LEFT JOIN blogcategories cc ON cc.BlogCatID = b.CustomCatID
        WHERE b.BlogID = :id AND b.IsPublished = 1
    """), {"id": blog_id}).fetchone()
    if not row:
        raise HTTPException(404, "Post not found")

    photos = db.execute(text("""
        SELECT PhotoID, PhotoOrder, Image, ImageTitle, ImageCaption
        FROM blogphotos WHERE BlogID = :id ORDER BY PhotoOrder
    """), {"id": blog_id}).fetchall()

    return {
        **_post_row(row),
        "business_name":        row.BusinessName,
        "category_name":        row.BlogCategoryName,
        "custom_category_name": row.CustomCategoryName,
        "photos": [
            {"photo_id": p.PhotoID, "order": p.PhotoOrder,
             "image": p.Image, "title": p.ImageTitle, "caption": p.ImageCaption}
            for p in photos
        ],
    }


# ── Management endpoints ─────────────────────────────────────────

@router.get("/manage")
def manage_list(business_id: int, db: Session = Depends(get_db)):
    """List all posts (published + drafts) for a business."""
    _ensure_schema(db)
    rows = db.execute(text("""
        SELECT b.BlogID, b.BusinessID, b.BlogCatID, b.CustomCatID,
               b.Title, b.Slug, b.Author, b.AuthorLink, b.CoverImage, b.Content,
               b.IsPublished, b.IsFeatured, b.CreatedAt, b.UpdatedAt,
               bc.BlogCategoryName,
               cc.BlogCategoryName AS CustomCategoryName
        FROM blog b
        LEFT JOIN blogcategories bc ON bc.BlogCatID = b.BlogCatID
        LEFT JOIN blogcategories cc ON cc.BlogCatID = b.CustomCatID
        WHERE b.BusinessID = :bid
        ORDER BY b.CreatedAt DESC
    """), {"bid": business_id}).fetchall()
    return [
        {**_post_row(r), "category_name": r.BlogCategoryName,
         "custom_category_name": r.CustomCategoryName}
        for r in rows
    ]


@router.post("/manage")
def create_post(business_id: int, body: PostIn, db: Session = Depends(get_db)):
    """Create a new blog post."""
    _ensure_schema(db)
    slug = _slugify(body.title)
    now = datetime.utcnow()
    result = db.execute(text("""
        INSERT INTO blog
            (BusinessID, BlogCatID, CustomCatID, Title, Slug, Author, AuthorLink,
             CoverImage, Content, IsPublished, IsFeatured, CreatedAt, UpdatedAt)
        OUTPUT INSERTED.BlogID
        VALUES
            (:bid, :cat, :ccat, :title, :slug, :author, :author_link,
             :cover, :content, :pub, :feat, :now, :now)
    """), {
        "bid":         business_id,
        "cat":         body.blog_cat_id,
        "ccat":        body.custom_cat_id,
        "title":       body.title,
        "slug":        slug,
        "author":      body.author,
        "author_link": body.author_link,
        "cover":       body.cover_image,
        "content":     body.content,
        "pub":         1 if body.is_published else 0,
        "feat":        1 if body.is_featured else 0,
        "now":         now,
    })
    blog_id = result.fetchone()[0]
    db.commit()
    return {"blog_id": blog_id, "slug": slug}


@router.put("/manage/{blog_id}")
def update_post(blog_id: int, business_id: int, body: PostIn, db: Session = Depends(get_db)):
    """Update a blog post."""
    _ensure_schema(db)
    slug = _slugify(body.title)
    result = db.execute(text("""
        UPDATE blog
        SET BlogCatID=:cat, CustomCatID=:ccat, Title=:title, Slug=:slug,
            Author=:author, AuthorLink=:author_link, CoverImage=:cover,
            Content=:content, IsPublished=:pub, IsFeatured=:feat, UpdatedAt=:now
        WHERE BlogID=:id AND BusinessID=:bid
    """), {
        "id":          blog_id,
        "bid":         business_id,
        "cat":         body.blog_cat_id,
        "ccat":        body.custom_cat_id,
        "title":       body.title,
        "slug":        slug,
        "author":      body.author,
        "author_link": body.author_link,
        "cover":       body.cover_image,
        "content":     body.content,
        "pub":         1 if body.is_published else 0,
        "feat":        1 if body.is_featured else 0,
        "now":         datetime.utcnow(),
    })
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Post not found")
    return {"blog_id": blog_id, "slug": slug}


@router.delete("/manage/{blog_id}")
def delete_post(blog_id: int, business_id: int, db: Session = Depends(get_db)):
    """Delete a blog post and its photos."""
    _ensure_schema(db)
    db.execute(text("DELETE FROM blogphotos WHERE BlogID=:id"), {"id": blog_id})
    result = db.execute(text(
        "DELETE FROM blog WHERE BlogID=:id AND BusinessID=:bid"
    ), {"id": blog_id, "bid": business_id})
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, "Post not found")
    return {"deleted": blog_id}


# ── Photo management ─────────────────────────────────────────────

@router.get("/manage/{blog_id}/photos")
def list_photos(blog_id: int, business_id: int, db: Session = Depends(get_db)):
    """List photos for a post (verifies business ownership)."""
    _ensure_schema(db)
    owner = db.execute(text(
        "SELECT BlogID FROM blog WHERE BlogID=:id AND BusinessID=:bid"
    ), {"id": blog_id, "bid": business_id}).fetchone()
    if not owner:
        raise HTTPException(404, "Post not found")
    rows = db.execute(text("""
        SELECT PhotoID, BlogID, PhotoOrder, Image, ImageTitle, ImageCaption
        FROM blogphotos WHERE BlogID=:id ORDER BY PhotoOrder
    """), {"id": blog_id}).fetchall()
    return [{"photo_id": r.PhotoID, "blog_id": r.BlogID, "order": r.PhotoOrder,
             "image": r.Image, "title": r.ImageTitle, "caption": r.ImageCaption}
            for r in rows]


@router.post("/manage/{blog_id}/photos")
def add_photo(blog_id: int, business_id: int, body: PhotoIn,
              db: Session = Depends(get_db)):
    """Add a photo to a post."""
    _ensure_schema(db)
    owner = db.execute(text(
        "SELECT BlogID FROM blog WHERE BlogID=:id AND BusinessID=:bid"
    ), {"id": blog_id, "bid": business_id}).fetchone()
    if not owner:
        raise HTTPException(404, "Post not found")
    result = db.execute(text("""
        INSERT INTO blogphotos (BlogID, PhotoOrder, Image, ImageTitle, ImageCaption)
        OUTPUT INSERTED.PhotoID
        VALUES (:bid, :ord, :img, :title, :cap)
    """), {"bid": blog_id, "ord": body.photo_order,
           "img": body.image, "title": body.image_title, "cap": body.image_caption})
    photo_id = result.fetchone()[0]
    db.commit()
    return {"photo_id": photo_id}


@router.delete("/manage/{blog_id}/photos/{photo_id}")
def delete_photo(blog_id: int, photo_id: int, business_id: int,
                 db: Session = Depends(get_db)):
    """Delete a photo."""
    _ensure_schema(db)
    owner = db.execute(text(
        "SELECT BlogID FROM blog WHERE BlogID=:id AND BusinessID=:bid"
    ), {"id": blog_id, "bid": business_id}).fetchone()
    if not owner:
        raise HTTPException(404, "Post not found")
    db.execute(text(
        "DELETE FROM blogphotos WHERE PhotoID=:pid AND BlogID=:bid"
    ), {"pid": photo_id, "bid": blog_id})
    db.commit()
    return {"deleted": photo_id}
