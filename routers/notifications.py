# routers/notifications.py
# In-app notifications: per-person inbox, polled by the Header bell.
# Other modules emit via `create_notification(db, ...)` — keep that signature stable.

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine
from auth import get_current_user
import models

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ── Auto-create AppNotifications table ───────────────────────────────────────
# NOTE: table is named AppNotifications (not Notifications) because an older
# social/follow feature already owns the `Notifications` table with a different
# shape (PeopleID/ActorPeopleID/IsRead/NotificationText).
with engine.begin() as _conn:
    _conn.execute(text("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='AppNotifications')
        BEGIN
            CREATE TABLE AppNotifications (
                NotificationID       INT IDENTITY(1,1) PRIMARY KEY,
                RecipientPeopleID    INT NOT NULL,
                RecipientBusinessID  INT NULL,
                Type                 VARCHAR(80)  NOT NULL,
                Title                NVARCHAR(200) NOT NULL,
                Body                 NVARCHAR(1000) NULL,
                LinkPath             NVARCHAR(500) NULL,
                RelatedEntityType    VARCHAR(50)  NULL,
                RelatedEntityID      INT          NULL,
                ReadAt               DATETIME     NULL,
                CreatedAt            DATETIME     NOT NULL DEFAULT GETDATE()
            )
            -- EXEC() defers parsing until the CREATE TABLE has executed, so the
            -- filtered-index predicate can reference ReadAt without a parse error.
            EXEC('CREATE INDEX IX_AppNotifications_Recipient_CreatedAt
                   ON AppNotifications (RecipientPeopleID, CreatedAt DESC)')
            EXEC('CREATE INDEX IX_AppNotifications_Recipient_Unread
                   ON AppNotifications (RecipientPeopleID, ReadAt) WHERE ReadAt IS NULL')
        END
    """))


# ── Internal helper (imported by other routers) ──────────────────────────────
def create_notification(
    db: Session,
    people_id: int,
    type: str,
    title: str,
    body: str | None = None,
    link_path: str | None = None,
    business_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
):
    """Insert one notification row. Caller is responsible for commit()."""
    db.execute(text("""
        INSERT INTO AppNotifications
            (RecipientPeopleID, RecipientBusinessID, Type, Title, Body,
             LinkPath, RelatedEntityType, RelatedEntityID)
        VALUES (:pid, :bid, :t, :ti, :b, :lp, :et, :ei)
    """), {
        "pid": people_id, "bid": business_id,
        "t": type, "ti": title, "b": body, "lp": link_path,
        "et": entity_type, "ei": entity_id,
    })


def notify_business(
    db: Session,
    business_id: int,
    type: str,
    title: str,
    body: str | None = None,
    link_path: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
):
    """Fan a notification out to every active BusinessAccess row for a business."""
    rows = db.execute(text("""
        SELECT PeopleID FROM BusinessAccess
        WHERE BusinessID = :bid AND Active = 1
    """), {"bid": business_id}).fetchall()
    for r in rows:
        create_notification(
            db, people_id=r.PeopleID, type=type, title=title, body=body,
            link_path=link_path, business_id=business_id,
            entity_type=entity_type, entity_id=entity_id,
        )


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("")
def list_notifications(
    unread_only: bool = False,
    limit: int = 50,
    current_user: models.People = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = max(1, min(limit, 200))
    where = "RecipientPeopleID = :pid"
    if unread_only:
        where += " AND ReadAt IS NULL"
    rows = db.execute(text(f"""
        SELECT TOP (:lim)
               NotificationID, Type, Title, Body, LinkPath,
               RelatedEntityType, RelatedEntityID,
               RecipientBusinessID, ReadAt, CreatedAt
        FROM AppNotifications
        WHERE {where}
        ORDER BY CreatedAt DESC
    """), {"pid": current_user.PeopleID, "lim": limit}).fetchall()
    return [dict(r._mapping) for r in rows]


@router.get("/unread-count")
def unread_count(
    current_user: models.People = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    n = db.execute(text("""
        SELECT COUNT(*) FROM AppNotifications
        WHERE RecipientPeopleID = :pid AND ReadAt IS NULL
    """), {"pid": current_user.PeopleID}).scalar() or 0
    return {"count": int(n)}


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: int,
    current_user: models.People = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = db.execute(text("""
        UPDATE AppNotifications
        SET ReadAt = GETDATE()
        WHERE NotificationID = :nid
          AND RecipientPeopleID = :pid
          AND ReadAt IS NULL
    """), {"nid": notification_id, "pid": current_user.PeopleID})
    db.commit()
    if result.rowcount == 0:
        # Either not found, wrong recipient, or already read — treat as no-op.
        return {"updated": 0}
    return {"updated": result.rowcount}


@router.post("/read-all")
def mark_all_read(
    current_user: models.People = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = db.execute(text("""
        UPDATE AppNotifications
        SET ReadAt = GETDATE()
        WHERE RecipientPeopleID = :pid AND ReadAt IS NULL
    """), {"pid": current_user.PeopleID})
    db.commit()
    return {"updated": result.rowcount}
