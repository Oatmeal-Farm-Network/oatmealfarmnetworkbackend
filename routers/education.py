"""Educational Content — courses, articles, and enrollment tracking."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine
from typing import Optional
from pydantic import BaseModel

router = APIRouter(prefix="/api/education", tags=["education"])

with engine.begin() as _c:
    _c.execute(text("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='EduCourses')
        CREATE TABLE EduCourses (
            CourseID        INT IDENTITY(1,1) PRIMARY KEY,
            BusinessID      INT NULL,
            Title           NVARCHAR(300) NOT NULL,
            Description     NVARCHAR(MAX) NULL,
            Category        VARCHAR(60) NULL,
            Difficulty      VARCHAR(20) NULL,
            DurationMin     INT NULL,
            AuthorName      NVARCHAR(150) NULL,
            ThumbnailUrl    NVARCHAR(500) NULL,
            ContentUrl      NVARCHAR(500) NULL,
            ContentType     VARCHAR(30) NOT NULL DEFAULT 'article',
            IsFree          BIT NOT NULL DEFAULT 1,
            IsPublished     BIT NOT NULL DEFAULT 1,
            ViewCount       INT NOT NULL DEFAULT 0,
            CreatedAt       DATETIME NOT NULL DEFAULT GETDATE()
        )
    """))
    _c.execute(text("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='EduEnrollments')
        CREATE TABLE EduEnrollments (
            EnrollmentID    INT IDENTITY(1,1) PRIMARY KEY,
            CourseID        INT NOT NULL,
            PeopleID        INT NOT NULL,
            ProgressPct     INT NOT NULL DEFAULT 0,
            CompletedAt     DATETIME NULL,
            CreatedAt       DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT UQ_EduEnroll UNIQUE (CourseID, PeopleID)
        )
    """))
    _c.execute(text("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='EduBookmarks')
        CREATE TABLE EduBookmarks (
            BookmarkID      INT IDENTITY(1,1) PRIMARY KEY,
            CourseID        INT NOT NULL,
            PeopleID        INT NOT NULL,
            CreatedAt       DATETIME NOT NULL DEFAULT GETDATE(),
            CONSTRAINT UQ_EduBook UNIQUE (CourseID, PeopleID)
        )
    """))
    # Seed starter content
    _c.execute(text("""
        IF NOT EXISTS (SELECT 1 FROM EduCourses)
        INSERT INTO EduCourses (Title,Category,Difficulty,DurationMin,AuthorName,ContentType,IsFree,Description) VALUES
        ('Cover Crop Selection Guide','Soil Health','Beginner',15,'OFN Extension',
         'article',1,'How to choose the right cover crops for your region, soil type, and production goals.'),
        ('Understanding NDVI and Satellite Imagery','Precision Ag','Intermediate',20,'OFN Extension',
         'article',1,'What NDVI means, how to interpret health maps, and when to act on low scores.'),
        ('Farm Financial Basics: Cash Flow Planning','Business','Beginner',25,'OFN Extension',
         'article',1,'Building a simple 12-month cash flow model for your farm operation.'),
        ('USDA Organic Certification: Step-by-Step','Certifications','Beginner',30,'OFN Extension',
         'article',1,'What you need to do to achieve and maintain USDA organic certification.'),
        ('Rotational Grazing 101','Livestock','Beginner',20,'OFN Extension',
         'article',1,'Paddock design, stocking rates, and rest period planning for sustainable grazing.'),
        ('Crop Scouting Best Practices','Crop Management','Intermediate',18,'OFN Extension',
         'article',1,'How to build a scouting program: timing, sampling methods, and record keeping.')
    """))

CATEGORIES = [
    "Soil Health", "Crop Management", "Livestock", "Precision Ag", "Business",
    "Certifications", "Sustainability", "Marketing & Sales", "Equipment", "General",
]


class CourseCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    difficulty: Optional[str] = None
    duration_min: Optional[int] = None
    author_name: Optional[str] = None
    thumbnail_url: Optional[str] = None
    content_url: Optional[str] = None
    content_type: str = 'article'
    is_free: bool = True


def _ser(r): return dict(r._mapping)


@router.get("/categories")
def get_categories():
    return CATEGORIES


@router.get("")
def browse(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    filters = ["c.IsPublished=1"]
    params: dict = {}
    if category:
        filters.append("c.Category=:cat"); params["cat"] = category
    if difficulty:
        filters.append("c.Difficulty=:diff"); params["diff"] = difficulty
    if q:
        filters.append("(c.Title LIKE :q OR c.Description LIKE :q OR c.AuthorName LIKE :q)")
        params["q"] = f"%{q}%"
    where = " AND ".join(filters)
    rows = db.execute(text(f"""
        SELECT c.*,
               (SELECT COUNT(*) FROM EduEnrollments e WHERE e.CourseID=c.CourseID) AS EnrollmentCount
        FROM EduCourses c WHERE {where} ORDER BY c.ViewCount DESC, c.CreatedAt DESC
    """), params).fetchall()
    return [_ser(r) for r in rows]


@router.get("/{course_id}")
def get_course(course_id: int, db: Session = Depends(get_db)):
    db.execute(text("UPDATE EduCourses SET ViewCount=ViewCount+1 WHERE CourseID=:id"), {"id": course_id})
    db.commit()
    row = db.execute(text("SELECT * FROM EduCourses WHERE CourseID=:id"), {"id": course_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")
    return _ser(row)


@router.post("")
def create_course(course: CourseCreate, business_id: Optional[int] = None, db: Session = Depends(get_db)):
    row = db.execute(text("""
        INSERT INTO EduCourses
            (BusinessID,Title,Description,Category,Difficulty,DurationMin,AuthorName,
             ThumbnailUrl,ContentUrl,ContentType,IsFree)
        OUTPUT INSERTED.CourseID
        VALUES (:bid,:title,:desc,:cat,:diff,:dur,:author,:thumb,:content,:ctype,:free)
    """), {
        "bid": business_id, "title": course.title, "desc": course.description,
        "cat": course.category, "diff": course.difficulty, "dur": course.duration_min,
        "author": course.author_name, "thumb": course.thumbnail_url,
        "content": course.content_url, "ctype": course.content_type,
        "free": 1 if course.is_free else 0,
    }).fetchone()
    db.commit()
    return {"course_id": row[0]}


@router.post("/{course_id}/enroll")
def enroll(course_id: int, body: dict, db: Session = Depends(get_db)):
    people_id = body.get("people_id")
    if not people_id:
        raise HTTPException(status_code=400, detail="people_id required")
    try:
        db.execute(text("INSERT INTO EduEnrollments (CourseID,PeopleID) VALUES (:c,:p)"), {"c": course_id, "p": people_id})
        db.commit()
    except Exception:
        db.rollback()
    return {"ok": True}


@router.patch("/{course_id}/progress")
def update_progress(course_id: int, body: dict, db: Session = Depends(get_db)):
    people_id = body.get("people_id")
    pct = int(body.get("progress_pct") or 0)
    completed_at = "GETDATE()" if pct >= 100 else "NULL"
    db.execute(text(f"""
        UPDATE EduEnrollments SET ProgressPct=:pct, CompletedAt={completed_at}
        WHERE CourseID=:c AND PeopleID=:p
    """), {"pct": pct, "c": course_id, "p": people_id})
    db.commit()
    return {"ok": True}


@router.get("/people/{people_id}/enrollments")
def my_enrollments(people_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT e.*, c.Title, c.Category, c.Difficulty, c.DurationMin, c.ThumbnailUrl
        FROM EduEnrollments e
        JOIN EduCourses c ON c.CourseID=e.CourseID
        WHERE e.PeopleID=:p ORDER BY e.CreatedAt DESC
    """), {"p": people_id}).fetchall()
    return [_ser(r) for r in rows]
