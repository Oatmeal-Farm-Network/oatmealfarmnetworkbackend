# routers/marketplace.py
# Farm-to-Restaurant Marketplace API
# Mount: app.include_router(marketplace_router, prefix="/api/marketplace")

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db, engine
from auth import get_current_user
from pydantic import BaseModel
from typing import Optional, List
from datetime import date

from image_service import ensure_images_for_catalog

marketplace_router = APIRouter()

# ── Auto-create MarketplaceProducts table ────────────────────────────────────
with engine.begin() as _conn:
    _conn.execute(text("""
        IF NOT EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME='MarketplaceProducts')
        BEGIN
            CREATE TABLE MarketplaceProducts (
                ProductID          INT IDENTITY(1,1) PRIMARY KEY,
                BusinessID         INT NOT NULL,
                Title              VARCHAR(500) NOT NULL,
                Description        TEXT,
                CategoryName       VARCHAR(200),
                UnitPrice          DECIMAL(10,2) NOT NULL DEFAULT 0,
                WholesalePrice     DECIMAL(10,2),
                UnitLabel          VARCHAR(50) DEFAULT 'each',
                QuantityAvailable  DECIMAL(10,2) DEFAULT 0,
                MinOrderQuantity   DECIMAL(10,2) DEFAULT 1,
                ImageURL           VARCHAR(1000),
                Tags               VARCHAR(500),
                IsActive           BIT DEFAULT 1,
                IsFeatured         BIT DEFAULT 0,
                IsOrganic          BIT DEFAULT 0,
                Weight             DECIMAL(10,2),
                WeightUnit         VARCHAR(20),
                Color              VARCHAR(200),
                Size               VARCHAR(200),
                Material           VARCHAR(200),
                SKU                VARCHAR(100),
                DeliveryOptions    VARCHAR(200) DEFAULT 'pickup',
                CreatedAt          DATETIME DEFAULT GETDATE(),
                UpdatedAt          DATETIME DEFAULT GETDATE()
            )
        END
    """))

   
# ─────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────

class CartItem(BaseModel):
    ListingID: str
    Quantity:  float

class PlaceOrderRequest(BaseModel):
    BuyerPeopleID:        int
    BuyerBusinessID:      Optional[int]  = None
    DeliveryMethod:       str            = "pickup"
    DeliveryAddress:      Optional[str]  = None
    DeliveryNotes:        Optional[str]  = None
    RequestedDeliveryDate: Optional[date] = None
    items:                List[CartItem]

class SellerActionRequest(BaseModel):
    SellerStatus:     str
    RejectionReason:  Optional[str]  = None
    EstimatedDeliveryDate: Optional[date] = None

class ShipItemRequest(BaseModel):
    TrackingNumber: Optional[str] = None
    EstimatedDeliveryDate: Optional[date] = None


# ─────────────────────────────────────────────
# CATALOG  (public — no auth required)
# Unions across Produce, MeatInventory, ProcessedFood
# ListingID format: P{id}, M{id}, F{id} encoded as
# product_type + source_id for round-tripping
# ─────────────────────────────────────────────

@marketplace_router.get("/catalog")
def get_catalog(
    background_tasks:   BackgroundTasks,
    product_type:       Optional[str]  = Query(None),
    organic:            Optional[bool] = Query(None),
    search:             Optional[str]  = Query(None),
    sort:               str            = Query("newest"),
    db:                 Session         = Depends(get_db),
):
    """
    Browse all active listings from Produce, MeatInventory, and ProcessedFood tables.
    Returns a unified list with a synthetic ListingID: type prefix + source row ID.
    """
    results = []

    search_val = f"%{search.strip()}%" if search and search.strip() else None

    # ── PRODUCE ──────────────────────────────────────────────────────────────
    if product_type in (None, "all", "produce"):
        where = ["p.ShowProduce = 1", "p.Quantity > 0"]
        params = {}

        if organic:
            where.append("p.IsOrganic = 1")
        if search_val:
            where.append("(i.IngredientName LIKE :search OR p.Notes LIKE :search)")
            params["search"] = search_val
        where.append("(p.ExpirationDate IS NULL OR p.ExpirationDate >= CAST(GETDATE() AS DATE))")

        rows = db.execute(text(f"""
            SELECT
                p.ProduceID         AS SourceID,
                'produce'           AS ProductType,
                p.BusinessID,
                p.IngredientID,
                i.IngredientName    AS Title,
                p.Notes             AS Description,
                NULL                AS CategoryName,
                p.RetailPrice       AS UnitPrice,
                p.WholesalePrice,
                'unit'              AS UnitLabel,
                p.Quantity          AS QuantityAvailable,
                p.IsOrganic,
                p.IsLocal,
                p.AvailableDate,
                p.ExpirationDate,
                i.IngredientImage   AS ImageURL,
                b.BusinessName      AS SellerName,
                a.AddressCity       AS SellerCity,
                a.AddressState      AS SellerState
            FROM Produce p
            JOIN Ingredients i ON p.IngredientID = i.IngredientID
            JOIN Business b ON p.BusinessID = b.BusinessID
            LEFT JOIN Address a ON b.AddressID = a.AddressID
            WHERE {" AND ".join(where)}
        """), params).fetchall()

        for r in rows:
            m = dict(r._mapping)
            m["ListingID"]   = f"P{m['SourceID']}"
            m["UnitPrice"]   = float(m["UnitPrice"]) if m["UnitPrice"] else 0.0
            m["WholesalePrice"] = float(m["WholesalePrice"]) if m["WholesalePrice"] else None
            m["QuantityAvailable"] = float(m["QuantityAvailable"]) if m["QuantityAvailable"] else 0.0
            m["IsOrganic"]   = bool(m["IsOrganic"])
            m["IsLocal"]     = bool(m["IsLocal"])
            m["IsFeatured"]  = False
            results.append(m)

    # ── MEAT ─────────────────────────────────────────────────────────────────
    if product_type in (None, "all", "meat"):
        where = ["m.ShowMeat = 1", "m.Quantity > 0"]
        params = {}

        if search_val:
            where.append("(i.IngredientName LIKE :search OR ic.IngredientCut LIKE :search)")
            params["search"] = search_val
        # Meat has no IsOrganic — skip that filter
        # Meat has no ExpirationDate — skip that filter

        rows = db.execute(text(f"""
            SELECT
                m.MeatInventoryID   AS SourceID,
                'meat'              AS ProductType,
                m.BusinessID,
                m.IngredientID,
                i.IngredientName + ' - ' + ISNULL(ic.IngredientCut, '') AS Title,
                NULL                AS Description,
                ic.IngredientCut    AS CategoryName,
                m.RetailPrice       AS UnitPrice,
                m.WholesalePrice,
                m.WeightUnit        AS UnitLabel,
                m.Quantity          AS QuantityAvailable,
                0                   AS IsOrganic,
                1                   AS IsLocal,
                m.AvailableDate,
                NULL                AS ExpirationDate,
                i.IngredientImage   AS ImageURL,
                b.BusinessName      AS SellerName,
                a.AddressCity       AS SellerCity,
                a.AddressState      AS SellerState
            FROM MeatInventory m
            JOIN Ingredients i ON m.IngredientID = i.IngredientID
            LEFT JOIN Cut ic ON m.IngredientCutID = ic.IngredientCutID
            JOIN Business b ON m.BusinessID = b.BusinessID
            LEFT JOIN Address a ON b.AddressID = a.AddressID
            WHERE {" AND ".join(where)}
        """), params).fetchall()

        for r in rows:
            m = dict(r._mapping)
            m["ListingID"]   = f"M{m['SourceID']}"
            m["UnitPrice"]   = float(m["UnitPrice"]) if m["UnitPrice"] else 0.0
            m["WholesalePrice"] = float(m["WholesalePrice"]) if m["WholesalePrice"] else None
            m["QuantityAvailable"] = float(m["QuantityAvailable"]) if m["QuantityAvailable"] else 0.0
            m["IsOrganic"]   = False
            m["IsLocal"]     = True
            m["IsFeatured"]  = False
            results.append(m)

    # ── PROCESSED FOOD ────────────────────────────────────────────────────────
    if product_type in (None, "all", "processed_food"):
        where = ["f.ShowProcessedFood = 1", "f.Quantity > 0"]
        params = {}

        if search_val:
            where.append("(f.Name LIKE :search OR f.Description LIKE :search)")
            params["search"] = search_val
        # ProcessedFood has no IsOrganic or ExpirationDate

        rows = db.execute(text(f"""
            SELECT
                f.ProcessedFoodID   AS SourceID,
                'processed_food'    AS ProductType,
                f.BusinessID,
                NULL                AS IngredientID,
                f.Name              AS Title,
                f.Description,
                NULL                AS CategoryName,
                f.RetailPrice       AS UnitPrice,
                f.WholesalePrice,
                'each'              AS UnitLabel,
                f.Quantity          AS QuantityAvailable,
                0                   AS IsOrganic,
                1                   AS IsLocal,
                f.AvailableDate,
                NULL                AS ExpirationDate,
                f.ImageURL,
                b.BusinessName      AS SellerName,
                a.AddressCity       AS SellerCity,
                a.AddressState      AS SellerState
            FROM ProcessedFood f
            JOIN Business b ON f.BusinessID = b.BusinessID
            LEFT JOIN Address a ON b.AddressID = a.AddressID
            WHERE {" AND ".join(where)}
        """), params).fetchall()

        for r in rows:
            m = dict(r._mapping)
            m["ListingID"]   = f"F{m['SourceID']}"
            m["UnitPrice"]   = float(m["UnitPrice"]) if m["UnitPrice"] else 0.0
            m["WholesalePrice"] = float(m["WholesalePrice"]) if m["WholesalePrice"] else None
            m["QuantityAvailable"] = float(m["QuantityAvailable"]) if m["QuantityAvailable"] else 0.0
            m["IsOrganic"]   = False
            m["IsLocal"]     = True
            m["IsFeatured"]  = False
            results.append(m)

    # ── PRODUCTS (physical goods — SFProducts) ───────────────────────────────
    if product_type in (None, "all", "product"):
        where_p = [
            "pr.Publishproduct = 1",
            "pr.ProdForSale = 1",
            "pr.ProdQuantityAvailable > 0",
        ]
        params_p = {}
        if search_val:
            where_p.append("(pr.prodName LIKE :search OR pr.prodShortDescription LIKE :search OR sc.CatName LIKE :search)")
            params_p["search"] = search_val
        rows = db.execute(text(f"""
            SELECT pr.ProdID AS SourceID, 'product' AS ProductType, pr.BusinessID,
                   NULL AS IngredientID, pr.prodName AS Title,
                   pr.prodShortDescription AS Description,
                   sc.CatName AS CategoryName,
                   pr.prodPrice AS UnitPrice, pr.SalePrice AS WholesalePrice,
                   'each' AS UnitLabel,
                   CAST(pr.ProdQuantityAvailable AS DECIMAL(10,2)) AS QuantityAvailable,
                   0 AS IsOrganic, 1 AS IsLocal, NULL AS AvailableDate, NULL AS ExpirationDate,
                   COALESCE(pp.ProductImage1, pr.prodImageSmallPath) AS ImageURL,
                   b.BusinessName AS SellerName,
                   a.AddressCity AS SellerCity, a.AddressState AS SellerState,
                   pr.prodSaleIsActive AS IsFeatured
            FROM SFProducts pr
            JOIN Business b ON pr.BusinessID = b.BusinessID
            LEFT JOIN Address a ON b.AddressID = a.AddressID
            LEFT JOIN productsphotos pp ON pp.ID = pr.ProdID
            LEFT JOIN sfcategories sc ON sc.CatID = pr.prodCategoryId
            WHERE {" AND ".join(where_p)}
        """), params_p).fetchall()
        for r in rows:
            m = dict(r._mapping)
            m["ListingID"]         = f"G{m['SourceID']}"
            m["UnitPrice"]         = float(m["UnitPrice"]) if m["UnitPrice"] else 0.0
            m["WholesalePrice"]    = float(m["WholesalePrice"]) if m["WholesalePrice"] else None
            m["QuantityAvailable"] = float(m["QuantityAvailable"]) if m["QuantityAvailable"] else 0.0
            m["IsOrganic"]         = False
            m["IsLocal"]           = True
            m["IsFeatured"]        = bool(m["IsFeatured"])
            results.append(m)

    # ── Sort combined results ─────────────────────────────────────────────────
    if sort == "price_asc":
        results.sort(key=lambda x: x["UnitPrice"])
    elif sort == "price_desc":
        results.sort(key=lambda x: x["UnitPrice"], reverse=True)
    elif sort == "name_asc":
        results.sort(key=lambda x: (x["Title"] or "").lower())
    else:  # newest — sort by SourceID desc as proxy
        results.sort(key=lambda x: x["SourceID"], reverse=True)

    # ── Fire background image generation for any missing images ──────────────
    items_needing_images = [r for r in results if not r.get("ImageURL") and r.get("IngredientID")]
    if items_needing_images:
        from database import get_db as get_db_factory
        background_tasks.add_task(ensure_images_for_catalog, items_needing_images, get_db_factory)

    return results


@marketplace_router.get("/catalog/{listing_id}")
def get_listing(listing_id: str, db: Session = Depends(get_db)):
    """
    Single listing detail. listing_id format: P{id} | M{id} | F{id}
    """
    prefix = listing_id[0].upper()
    try:
        source_id = int(listing_id[1:])
    except ValueError:
        raise HTTPException(400, "Invalid listing ID format")

    if prefix == "P":
        row = db.execute(text("""
            SELECT
                p.ProduceID AS SourceID, 'produce' AS ProductType, p.BusinessID,
                i.IngredientName AS Title, p.Notes AS Description,
                p.RetailPrice AS UnitPrice, p.WholesalePrice,
                'unit' AS UnitLabel, p.Quantity AS QuantityAvailable,
                p.IsOrganic, p.IsLocal, p.AvailableDate, p.ExpirationDate,
                i.IngredientImage AS ImageURL,
                b.BusinessName AS SellerName,
                a.AddressCity AS SellerCity, a.AddressState AS SellerState
            FROM Produce p
            JOIN Ingredients i ON p.IngredientID = i.IngredientID
            JOIN Business b ON p.BusinessID = b.BusinessID
            LEFT JOIN Address a ON b.AddressID = a.AddressID
            WHERE p.ProduceID = :sid AND p.ShowProduce = 1
        """), {"sid": source_id}).fetchone()

    elif prefix == "M":
        row = db.execute(text("""
            SELECT
                m.MeatInventoryID AS SourceID, 'meat' AS ProductType, m.BusinessID,
                i.IngredientName + ' - ' + ISNULL(ic.IngredientCut, '') AS Title,
                NULL AS Description,
                m.RetailPrice AS UnitPrice, m.WholesalePrice,
                m.WeightUnit AS UnitLabel, m.Quantity AS QuantityAvailable,
                0 AS IsOrganic, 1 AS IsLocal, m.AvailableDate, NULL AS ExpirationDate,
                i.IngredientImage AS ImageURL,
                b.BusinessName AS SellerName,
                a.AddressCity AS SellerCity, a.AddressState AS SellerState
            FROM MeatInventory m
            JOIN Ingredients i ON m.IngredientID = i.IngredientID
            LEFT JOIN Cut ic ON m.IngredientCutID = ic.IngredientCutID
            JOIN Business b ON m.BusinessID = b.BusinessID
            LEFT JOIN Address a ON b.AddressID = a.AddressID
            WHERE m.MeatInventoryID = :sid AND m.ShowMeat = 1
        """), {"sid": source_id}).fetchone()

    elif prefix == "F":
        row = db.execute(text("""
            SELECT
                f.ProcessedFoodID AS SourceID, 'processed_food' AS ProductType, f.BusinessID,
                f.Name AS Title, f.Description,
                f.RetailPrice AS UnitPrice, f.WholesalePrice,
                'each' AS UnitLabel, f.Quantity AS QuantityAvailable,
                0 AS IsOrganic, 1 AS IsLocal, f.AvailableDate, NULL AS ExpirationDate,
                f.ImageURL,
                b.BusinessName AS SellerName,
                a.AddressCity AS SellerCity, a.AddressState AS SellerState
            FROM ProcessedFood f
            JOIN Business b ON f.BusinessID = b.BusinessID
            LEFT JOIN Address a ON b.AddressID = a.AddressID
            WHERE f.ProcessedFoodID = :sid AND f.ShowProcessedFood = 1
        """), {"sid": source_id}).fetchone()

    elif prefix == "G":
        row = db.execute(text("""
            SELECT pr.ProdID AS SourceID, 'product' AS ProductType, pr.BusinessID,
                   pr.prodName AS Title, pr.prodDescription AS Description,
                   pr.prodPrice AS UnitPrice, pr.SalePrice AS WholesalePrice,
                   'each' AS UnitLabel,
                   CAST(pr.ProdQuantityAvailable AS DECIMAL(10,2)) AS QuantityAvailable,
                   0 AS IsOrganic, 1 AS IsLocal, NULL AS AvailableDate, NULL AS ExpirationDate,
                   COALESCE(pp.ProductImage1, pr.prodImageSmallPath) AS ImageURL,
                   b.BusinessName AS SellerName,
                   a.AddressCity AS SellerCity, a.AddressState AS SellerState
            FROM SFProducts pr
            JOIN Business b ON pr.BusinessID = b.BusinessID
            LEFT JOIN Address a ON b.AddressID = a.AddressID
            LEFT JOIN productsphotos pp ON pp.ID = pr.ProdID
            WHERE pr.ProdID = :sid AND pr.Publishproduct = 1
        """), {"sid": source_id}).fetchone()
    else:
        raise HTTPException(400, "Invalid listing type prefix")

    if not row:
        raise HTTPException(404, "Listing not found")

    listing = dict(row._mapping)
    listing["ListingID"]   = listing_id
    listing["UnitPrice"]   = float(listing["UnitPrice"]) if listing["UnitPrice"] else 0.0
    listing["WholesalePrice"] = float(listing["WholesalePrice"]) if listing["WholesalePrice"] else None
    listing["QuantityAvailable"] = float(listing["QuantityAvailable"]) if listing["QuantityAvailable"] else 0.0
    listing["IsOrganic"]   = bool(listing.get("IsOrganic", False))
    listing["IsLocal"]     = bool(listing.get("IsLocal", True))
    listing["IsFeatured"]  = False
    listing["reviews"]     = []
    listing["relatedListings"] = []

    return listing


# ─────────────────────────────────────────────
# ORDERS  (buyer)
# ─────────────────────────────────────────────

@marketplace_router.post("/orders")
def place_order(req: PlaceOrderRequest, db: Session = Depends(get_db)):
    if not req.items:
        raise HTTPException(400, "No items in order")

    order_items = []
    subtotal = 0.0

    for item in req.items:
        # Parse synthetic ListingID
        prefix = str(item.ListingID)[0].upper() if isinstance(item.ListingID, str) else None
        source_id = int(str(item.ListingID)[1:]) if prefix else item.ListingID

        if prefix == "P":
            listing = db.execute(text("""
                SELECT p.ProduceID AS ListingID, p.BusinessID, i.IngredientName AS Title,
                       'produce' AS ProductType, p.RetailPrice AS UnitPrice,
                       p.Quantity AS QuantityAvailable,
                       b.BusinessName AS SellerName, pe.PeopleEmail AS SellerEmail
                FROM Produce p
                JOIN Ingredients i ON p.IngredientID = i.IngredientID
                JOIN Business b ON p.BusinessID = b.BusinessID
                JOIN People pe ON b.Contact1PeopleID = pe.PeopleID
                WHERE p.ProduceID = :sid AND p.ShowProduce = 1
            """), {"sid": source_id}).fetchone()
        elif prefix == "M":
            listing = db.execute(text("""
                SELECT m.MeatInventoryID AS ListingID, m.BusinessID,
                       i.IngredientName + ' - ' + ISNULL(ic.IngredientCut,'') AS Title,
                       'meat' AS ProductType, m.RetailPrice AS UnitPrice,
                       m.Quantity AS QuantityAvailable,
                       b.BusinessName AS SellerName, pe.PeopleEmail AS SellerEmail
                FROM MeatInventory m
                JOIN Ingredients i ON m.IngredientID = i.IngredientID
                LEFT JOIN Cut ic ON m.IngredientCutID = ic.IngredientCutID
                JOIN Business b ON m.BusinessID = b.BusinessID
                JOIN People pe ON b.Contact1PeopleID = pe.PeopleID
                WHERE m.MeatInventoryID = :sid AND m.ShowMeat = 1
            """), {"sid": source_id}).fetchone()
        elif prefix == "F":
            listing = db.execute(text("""
                SELECT f.ProcessedFoodID AS ListingID, f.BusinessID, f.Name AS Title,
                       'processed_food' AS ProductType, f.RetailPrice AS UnitPrice,
                       f.Quantity AS QuantityAvailable,
                       b.BusinessName AS SellerName, pe.PeopleEmail AS SellerEmail
                FROM ProcessedFood f
                JOIN Business b ON f.BusinessID = b.BusinessID
                JOIN People pe ON b.Contact1PeopleID = pe.PeopleID
                WHERE f.ProcessedFoodID = :sid AND f.ShowProcessedFood = 1
            """), {"sid": source_id}).fetchone()
        elif prefix == "G":
            listing = db.execute(text("""
                SELECT pr.ProdID AS ListingID, pr.BusinessID, pr.prodName AS Title,
                       'product' AS ProductType, pr.prodPrice AS UnitPrice,
                       CAST(pr.ProdQuantityAvailable AS DECIMAL(10,2)) AS QuantityAvailable,
                       b.BusinessName AS SellerName, pe.PeopleEmail AS SellerEmail
                FROM SFProducts pr
                JOIN Business b ON pr.BusinessID = b.BusinessID
                JOIN People pe ON b.Contact1PeopleID = pe.PeopleID
                WHERE pr.ProdID = :sid AND pr.Publishproduct = 1 AND pr.ProdForSale = 1
            """), {"sid": source_id}).fetchone()
        else:
            raise HTTPException(400, f"Invalid listing ID: {item.ListingID}")

        if not listing:
            raise HTTPException(404, f"Listing {item.ListingID} not found or inactive")

        l = dict(listing._mapping)
        qty = float(item.Quantity)

        if qty > float(l["QuantityAvailable"]):
            raise HTTPException(400, f"Only {l['QuantityAvailable']} available for '{l['Title']}'")

        unit_price   = float(l["UnitPrice"])
        line_total   = round(unit_price * qty, 2)
        platform_cut = round(line_total * 0.025, 2)
        seller_payout = round(line_total - platform_cut, 2)
        subtotal += line_total

        order_items.append({
            "listing":        l,
            "source_id":      source_id,
            "prefix":         prefix,
            "quantity":       qty,
            "unit_price":     unit_price,
            "line_total":     line_total,
            "seller_payout":  seller_payout,
        })

    platform_fee = round(subtotal * 0.025, 2)
    total_amount = round(subtotal + platform_fee, 2)

    buyer = db.execute(text("""
        SELECT PeopleFirstName + ' ' + PeopleLastName AS FullName, PeopleEmail
        FROM People WHERE PeopleID = :pid
    """), {"pid": req.BuyerPeopleID}).fetchone()
    if not buyer:
        raise HTTPException(404, "Buyer not found")

    import random, string
    order_number = "OFN-" + "".join(random.choices(string.digits, k=8))

    db.execute(text("""
        INSERT INTO MarketplaceOrders (
            OrderNumber, BuyerPeopleID, BuyerBusinessID,
            BuyerName, BuyerEmail,
            DeliveryMethod, DeliveryAddress, DeliveryNotes,
            RequestedDeliveryDate,
            Subtotal, PlatformFee, TaxAmount, DeliveryFee, TotalAmount,
            PaymentStatus, OrderStatus, CreatedAt, UpdatedAt
        ) VALUES (
            :order_number, :buyer_pid, :buyer_bid,
            :buyer_name, :buyer_email,
            :delivery_method, :delivery_address, :delivery_notes,
            :requested_date,
            :subtotal, :platform_fee, 0, 0, :total_amount,
            'pending', 'pending', GETDATE(), GETDATE()
        )
    """), {
        "order_number":     order_number,
        "buyer_pid":        req.BuyerPeopleID,
        "buyer_bid":        req.BuyerBusinessID,
        "buyer_name":       buyer[0],
        "buyer_email":      buyer[1],
        "delivery_method":  req.DeliveryMethod,
        "delivery_address": req.DeliveryAddress,
        "delivery_notes":   req.DeliveryNotes,
        "requested_date":   req.RequestedDeliveryDate,
        "subtotal":         subtotal,
        "platform_fee":     platform_fee,
        "total_amount":     total_amount,
    })

    order_id = db.execute(text("SELECT SCOPE_IDENTITY()")).scalar()

    for oi in order_items:
        l = oi["listing"]
        db.execute(text("""
            INSERT INTO MarketplaceOrderItems (
                OrderID, ListingID, SellerBusinessID,
                ProductTitle, ProductType, SellerName,
                Quantity, UnitPrice, LineTotal, SellerPayout, PlatformFee,
                SellerStatus, CreatedAt, UpdatedAt
            ) VALUES (
                :order_id, :listing_id, :seller_bid,
                :title, :product_type, :seller_name,
                :quantity, :unit_price, :line_total, :seller_payout, :platform_fee,
                'pending', GETDATE(), GETDATE()
            )
        """), {
            "order_id":     order_id,
            "listing_id":   f"{oi['prefix']}{oi['source_id']}",
            "seller_bid":   l["BusinessID"],
            "title":        l["Title"],
            "product_type": l["ProductType"],
            "seller_name":  l["SellerName"],
            "quantity":     oi["quantity"],
            "unit_price":   oi["unit_price"],
            "line_total":   oi["line_total"],
            "seller_payout": oi["seller_payout"],
            "platform_fee": round(oi["line_total"] * 0.025, 2),
        })

        # Decrement inventory in source table
        if oi["prefix"] == "P":
            db.execute(text("UPDATE Produce SET Quantity = Quantity - :qty WHERE ProduceID = :sid"),
                       {"qty": oi["quantity"], "sid": oi["source_id"]})
        elif oi["prefix"] == "M":
            db.execute(text("UPDATE MeatInventory SET Quantity = Quantity - :qty WHERE MeatInventoryID = :sid"),
                       {"qty": oi["quantity"], "sid": oi["source_id"]})
        elif oi["prefix"] == "F":
            db.execute(text("UPDATE ProcessedFood SET Quantity = Quantity - :qty WHERE ProcessedFoodID = :sid"),
                       {"qty": oi["quantity"], "sid": oi["source_id"]})
        elif oi["prefix"] == "G":
            db.execute(text("UPDATE SFProducts SET ProdQuantityAvailable = ProdQuantityAvailable - :qty WHERE ProdID = :sid"),
                       {"qty": oi["quantity"], "sid": oi["source_id"]})

    db.commit()

    try:
        from marketplace_emails import send_order_placed_buyer, send_order_placed_seller
        send_order_placed_buyer(order_id, db)
    except Exception as e:
        print(f"[marketplace] Email send failed: {e}")

    return {
        "OrderID":     order_id,
        "OrderNumber": order_number,
        "TotalAmount": total_amount,
        "message":     "Order placed successfully",
    }


@marketplace_router.get("/orders/{order_id}")
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.execute(text("SELECT * FROM MarketplaceOrders WHERE OrderID = :oid"), {"oid": order_id}).fetchone()
    if not order:
        raise HTTPException(404, "Order not found")
    result = dict(order._mapping)
    for field in ["Subtotal", "PlatformFee", "TaxAmount", "DeliveryFee", "TotalAmount"]:
        if result.get(field) is not None:
            result[field] = float(result[field])

    items = db.execute(text("""
        SELECT oi.*, b.BusinessName
        FROM MarketplaceOrderItems oi
        LEFT JOIN Business b ON oi.SellerBusinessID = b.BusinessID
        WHERE oi.OrderID = :oid ORDER BY oi.OrderItemID
    """), {"oid": order_id}).fetchall()

    result["items"] = []
    for i in items:
        row = dict(i._mapping)
        for f in ["UnitPrice", "LineTotal", "SellerPayout", "PlatformFee"]:
            if row.get(f) is not None:
                row[f] = float(row[f])

        # Fetch image from source table
        listing_id = row.get("ListingID", "")
        image_url = None
        try:
            prefix = str(listing_id)[0].upper()
            source_id = int(str(listing_id)[1:])
            if prefix == "P":
                img = db.execute(text("""
                    SELECT i.IngredientImage FROM Produce p
                    JOIN Ingredients i ON p.IngredientID = i.IngredientID
                    WHERE p.ProduceID = :sid
                """), {"sid": source_id}).fetchone()
                image_url = img[0] if img else None
            elif prefix == "M":
                img = db.execute(text("""
                    SELECT i.IngredientImage FROM MeatInventory m
                    JOIN Ingredients i ON m.IngredientID = i.IngredientID
                    WHERE m.MeatInventoryID = :sid
                """), {"sid": source_id}).fetchone()
                image_url = img[0] if img else None
            elif prefix == "F":
                img = db.execute(text("""
                    SELECT ImageURL FROM ProcessedFood WHERE ProcessedFoodID = :sid
                """), {"sid": source_id}).fetchone()
                image_url = img[0] if img else None
            elif prefix == "G":
                img = db.execute(text("""
                    SELECT COALESCE(pp.ProductImage1, pr.prodImageSmallPath) AS ImageURL
                    FROM SFProducts pr LEFT JOIN productsphotos pp ON pp.ID = pr.ProdID
                    WHERE pr.ProdID = :sid
                """), {"sid": source_id}).fetchone()
                image_url = img[0] if img else None
        except Exception:
            image_url = None

        row["ImageURL"] = image_url
        result["items"].append(row)

    result["history"] = []
    return result


@marketplace_router.get("/orders")
def list_orders(buyer_people_id: int, db: Session = Depends(get_db)):
    orders = db.execute(text("""
        SELECT o.OrderID, o.OrderNumber, o.OrderStatus, o.PaymentStatus,
               o.TotalAmount, o.CreatedAt, o.DeliveryMethod,
               COUNT(oi.OrderItemID) AS ItemCount
        FROM MarketplaceOrders o
        LEFT JOIN MarketplaceOrderItems oi ON o.OrderID = oi.OrderID
        WHERE o.BuyerPeopleID = :pid
        GROUP BY o.OrderID, o.OrderNumber, o.OrderStatus, o.PaymentStatus,
                 o.TotalAmount, o.CreatedAt, o.DeliveryMethod
        ORDER BY o.CreatedAt DESC
    """), {"pid": buyer_people_id}).fetchall()
    result = []
    for o in orders:
        row = dict(o._mapping)
        row["TotalAmount"] = float(row["TotalAmount"]) if row["TotalAmount"] else 0.0
        result.append(row)
    return result


# ─────────────────────────────────────────────
# SELLER ACTIONS
# ─────────────────────────────────────────────

@marketplace_router.get("/seller/orders")
def get_seller_orders(business_id: int, db: Session = Depends(get_db)):
    items = db.execute(text("""
        SELECT oi.*, o.OrderNumber, o.BuyerName, o.BuyerEmail,
               o.DeliveryMethod, o.RequestedDeliveryDate, o.CreatedAt AS OrderDate
        FROM MarketplaceOrderItems oi
        JOIN MarketplaceOrders o ON oi.OrderID = o.OrderID
        WHERE oi.SellerBusinessID = :bid
        ORDER BY o.CreatedAt DESC
    """), {"bid": business_id}).fetchall()
    result = []
    for i in items:
        row = dict(i._mapping)
        for f in ["UnitPrice", "LineTotal", "SellerPayout"]:
            if row.get(f) is not None:
                row[f] = float(row[f])
        result.append(row)
    return result


@marketplace_router.post("/seller/orders/{order_item_id}/action")
def seller_item_action(order_item_id: int, req: SellerActionRequest, db: Session = Depends(get_db)):
    item = db.execute(text("""
        SELECT oi.*, o.OrderID FROM MarketplaceOrderItems oi
        JOIN MarketplaceOrders o ON oi.OrderID = o.OrderID
        WHERE oi.OrderItemID = :oiid
    """), {"oiid": order_item_id}).fetchone()
    if not item:
        raise HTTPException(404, "Order item not found")
    if item.SellerStatus not in ("pending",):
        raise HTTPException(400, f"Item is already '{item.SellerStatus}'")
    if req.SellerStatus not in ("confirmed", "rejected"):
        raise HTTPException(400, "Status must be 'confirmed' or 'rejected'")

    db.execute(text("""
        UPDATE MarketplaceOrderItems
        SET SellerStatus = :status, RejectionReason = :reason,
            EstimatedDeliveryDate = :edd, UpdatedAt = GETDATE()
        WHERE OrderItemID = :oiid
    """), {"status": req.SellerStatus, "reason": req.RejectionReason,
           "edd": req.EstimatedDeliveryDate, "oiid": order_item_id})

    # If rejected, restore inventory in source table
    if req.SellerStatus == "rejected":
        listing_id = item.ListingID
        prefix = str(listing_id)[0].upper()
        source_id = int(str(listing_id)[1:])
        if prefix == "P":
            db.execute(text("UPDATE Produce SET Quantity = Quantity + :qty WHERE ProduceID = :sid"),
                       {"qty": item.Quantity, "sid": source_id})
        elif prefix == "M":
            db.execute(text("UPDATE MeatInventory SET Quantity = Quantity + :qty WHERE MeatInventoryID = :sid"),
                       {"qty": item.Quantity, "sid": source_id})
        elif prefix == "F":
            db.execute(text("UPDATE ProcessedFood SET Quantity = Quantity + :qty WHERE ProcessedFoodID = :sid"),
                       {"qty": item.Quantity, "sid": source_id})
        elif prefix == "G":
            db.execute(text("UPDATE SFProducts SET ProdQuantityAvailable = ProdQuantityAvailable + :qty WHERE ProdID = :sid"),
                       {"qty": item.Quantity, "sid": source_id})

    db.commit()
    return {"message": f"Item {req.SellerStatus}", "OrderID": item.OrderID}


@marketplace_router.post("/seller/orders/{order_item_id}/ship")
def ship_item(order_item_id: int, req: ShipItemRequest, db: Session = Depends(get_db)):
    item = db.execute(text("SELECT * FROM MarketplaceOrderItems WHERE OrderItemID = :oiid"),
                      {"oiid": order_item_id}).fetchone()
    if not item:
        raise HTTPException(404, "Order item not found")
    if item.SellerStatus != "confirmed":
        raise HTTPException(400, "Item must be confirmed before shipping")
    db.execute(text("""
        UPDATE MarketplaceOrderItems
        SET SellerStatus = 'shipped', TrackingNumber = :tracking,
            EstimatedDeliveryDate = :edd, ShippedAt = GETDATE(), UpdatedAt = GETDATE()
        WHERE OrderItemID = :oiid
    """), {"tracking": req.TrackingNumber, "edd": req.EstimatedDeliveryDate, "oiid": order_item_id})
    db.commit()
    return {"message": "Item marked as shipped"}


# ─────────────────────────────────────────────
# SELLER LISTINGS  (read-only view of their inventory)
# ─────────────────────────────────────────────

@marketplace_router.get("/seller/listings")
def get_seller_listings(business_id: int, db: Session = Depends(get_db)):
    """Returns unified produce + meat + processed food for a seller."""
    results = []

    produce = db.execute(text("""
        SELECT p.ProduceID AS SourceID, 'produce' AS ProductType,
               i.IngredientName AS Title, p.RetailPrice AS UnitPrice,
               p.WholesalePrice, 'unit' AS UnitLabel,
               p.Quantity AS QuantityAvailable,
               p.IsOrganic, p.IsLocal, p.ShowProduce AS IsActive,
               p.AvailableDate, p.ExpirationDate
        FROM Produce p
        JOIN Ingredients i ON p.IngredientID = i.IngredientID
        WHERE p.BusinessID = :bid
        ORDER BY p.ProduceID DESC
    """), {"bid": business_id}).fetchall()

    for r in produce:
        m = dict(r._mapping)
        m["ListingID"]  = f"P{m['SourceID']}"
        m["UnitPrice"]  = float(m["UnitPrice"]) if m["UnitPrice"] else 0.0
        m["WholesalePrice"] = float(m["WholesalePrice"]) if m["WholesalePrice"] else None
        m["QuantityAvailable"] = float(m["QuantityAvailable"]) if m["QuantityAvailable"] else 0.0
        m["IsOrganic"]  = bool(m["IsOrganic"])
        m["IsLocal"]    = bool(m["IsLocal"])
        m["IsActive"]   = bool(m["IsActive"])
        m["IsFeatured"] = False
        results.append(m)

    meat = db.execute(text("""
        SELECT m.MeatInventoryID AS SourceID, 'meat' AS ProductType,
               i.IngredientName + ' - ' + ISNULL(ic.IngredientCut,'') AS Title,
               m.RetailPrice AS UnitPrice, m.WholesalePrice,
               m.WeightUnit AS UnitLabel, m.Quantity AS QuantityAvailable,
               0 AS IsOrganic, 1 AS IsLocal, m.ShowMeat AS IsActive,
               m.AvailableDate, NULL AS ExpirationDate
        FROM MeatInventory m
        JOIN Ingredients i ON m.IngredientID = i.IngredientID
        LEFT JOIN Cut ic ON m.IngredientCutID = ic.IngredientCutID
        WHERE m.BusinessID = :bid
        ORDER BY m.MeatInventoryID DESC
    """), {"bid": business_id}).fetchall()

    for r in meat:
        m = dict(r._mapping)
        m["ListingID"]  = f"M{m['SourceID']}"
        m["UnitPrice"]  = float(m["UnitPrice"]) if m["UnitPrice"] else 0.0
        m["WholesalePrice"] = float(m["WholesalePrice"]) if m["WholesalePrice"] else None
        m["QuantityAvailable"] = float(m["QuantityAvailable"]) if m["QuantityAvailable"] else 0.0
        m["IsOrganic"]  = False
        m["IsLocal"]    = True
        m["IsActive"]   = bool(m["IsActive"])
        m["IsFeatured"] = False
        results.append(m)

    food = db.execute(text("""
        SELECT f.ProcessedFoodID AS SourceID, 'processed_food' AS ProductType,
               f.Name AS Title, f.RetailPrice AS UnitPrice,
               f.WholesalePrice, 'each' AS UnitLabel,
               f.Quantity AS QuantityAvailable,
               0 AS IsOrganic, 1 AS IsLocal, f.ShowProcessedFood AS IsActive,
               f.AvailableDate, NULL AS ExpirationDate
        FROM ProcessedFood f
        WHERE f.BusinessID = :bid
        ORDER BY f.ProcessedFoodID DESC
    """), {"bid": business_id}).fetchall()

    for r in food:
        m = dict(r._mapping)
        m["ListingID"]  = f"F{m['SourceID']}"
        m["UnitPrice"]  = float(m["UnitPrice"]) if m["UnitPrice"] else 0.0
        m["WholesalePrice"] = float(m["WholesalePrice"]) if m["WholesalePrice"] else None
        m["QuantityAvailable"] = float(m["QuantityAvailable"]) if m["QuantityAvailable"] else 0.0
        m["IsOrganic"]  = False
        m["IsLocal"]    = True
        m["IsActive"]   = bool(m["IsActive"])
        m["IsFeatured"] = False
        results.append(m)

    products = db.execute(text("""
        SELECT pr.ProductID AS SourceID, 'product' AS ProductType,
               pr.Title, pr.UnitPrice, pr.WholesalePrice, pr.UnitLabel,
               pr.QuantityAvailable, pr.IsOrganic, pr.IsActive,
               pr.CategoryName, NULL AS ExpirationDate, NULL AS AvailableDate
        FROM MarketplaceProducts pr
        WHERE pr.BusinessID = :bid
        ORDER BY pr.ProductID DESC
    """), {"bid": business_id}).fetchall()
    for r in products:
        m = dict(r._mapping)
        m["ListingID"]         = f"G{m['SourceID']}"
        m["UnitPrice"]         = float(m["UnitPrice"]) if m["UnitPrice"] else 0.0
        m["WholesalePrice"]    = float(m["WholesalePrice"]) if m["WholesalePrice"] else None
        m["QuantityAvailable"] = float(m["QuantityAvailable"]) if m["QuantityAvailable"] else 0.0
        m["IsOrganic"]         = bool(m["IsOrganic"])
        m["IsLocal"]           = True
        m["IsActive"]          = bool(m["IsActive"])
        m["IsFeatured"]        = False
        results.append(m)

    return results


# ─────────────────────────────────────────────
# CHECKOUT  (server-side cart sync flow)
# ─────────────────────────────────────────────

class CheckoutRequest(BaseModel):
    BuyerPeopleID:         int
    BuyerBusinessID:       Optional[int]  = None
    DeliveryMethod:        str            = "pickup"
    DeliveryAddress:       Optional[str]  = None
    DeliveryNotes:         Optional[str]  = None
    RequestedDeliveryDate: Optional[date] = None


@marketplace_router.post("/checkout")
def checkout(req: CheckoutRequest, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT ci.ListingID, ci.Quantity
        FROM CartItems ci
        WHERE ci.BuyerPeopleID = :pid
    """), {"pid": req.BuyerPeopleID}).fetchall()

    if not rows:
        raise HTTPException(400, "Cart is empty")

    items = [CartItem(ListingID=r[0], Quantity=float(r[1])) for r in rows]
    order_req = PlaceOrderRequest(
        BuyerPeopleID=req.BuyerPeopleID,
        BuyerBusinessID=req.BuyerBusinessID,
        DeliveryMethod=req.DeliveryMethod,
        DeliveryAddress=req.DeliveryAddress,
        DeliveryNotes=req.DeliveryNotes,
        RequestedDeliveryDate=req.RequestedDeliveryDate,
        items=items,
    )
    result = place_order(order_req, db)
    db.execute(text("DELETE FROM CartItems WHERE BuyerPeopleID = :pid"), {"pid": req.BuyerPeopleID})
    db.commit()
    return result


class CartItemAdd(BaseModel):
    BuyerPeopleID:   int
    BuyerBusinessID: Optional[int] = None
    ListingID:       str
    Quantity:        float
    Notes:           Optional[str] = None


@marketplace_router.post("/cart")
def add_to_cart(data: CartItemAdd, db: Session = Depends(get_db)):
    # Look up price and seller from the source table
    prefix = str(data.ListingID)[0].upper()
    source_id = int(str(data.ListingID)[1:])

    if prefix == "P":
        row = db.execute(text("""
            SELECT p.BusinessID AS SellerBusinessID, p.RetailPrice AS UnitPrice
            FROM Produce p WHERE p.ProduceID = :sid AND p.ShowProduce = 1
        """), {"sid": source_id}).fetchone()
    elif prefix == "M":
        row = db.execute(text("""
            SELECT m.BusinessID AS SellerBusinessID, m.RetailPrice AS UnitPrice
            FROM MeatInventory m WHERE m.MeatInventoryID = :sid AND m.ShowMeat = 1
        """), {"sid": source_id}).fetchone()
    elif prefix == "F":
        row = db.execute(text("""
            SELECT f.BusinessID AS SellerBusinessID, f.RetailPrice AS UnitPrice
            FROM ProcessedFood f WHERE f.ProcessedFoodID = :sid AND f.ShowProcessedFood = 1
        """), {"sid": source_id}).fetchone()
    elif prefix == "G":
        row = db.execute(text("""
            SELECT pr.BusinessID AS SellerBusinessID, pr.prodPrice AS UnitPrice
            FROM SFProducts pr WHERE pr.ProdID = :sid AND pr.Publishproduct = 1
        """), {"sid": source_id}).fetchone()
    else:
        raise HTTPException(400, f"Invalid listing ID: {data.ListingID}")

    if not row:
        raise HTTPException(404, "Listing not found or inactive")

    seller_bid = row[0]
    unit_price = float(row[1]) if row[1] else 0.0

    existing = db.execute(text(
        "SELECT CartItemID FROM CartItems WHERE BuyerPeopleID = :pid AND ListingID = :lid"
    ), {"pid": data.BuyerPeopleID, "lid": data.ListingID}).fetchone()

    if existing:
        db.execute(text(
            "UPDATE CartItems SET Quantity = :qty, UpdatedAt = GETDATE() WHERE CartItemID = :cid"
        ), {"qty": data.Quantity, "cid": existing[0]})
    else:
        db.execute(text("""
            INSERT INTO CartItems (BuyerPeopleID, BuyerBusinessID, ListingID, SellerBusinessID, Quantity, UnitPrice, Notes, AddedAt, UpdatedAt)
            VALUES (:pid, :bid, :lid, :sbid, :qty, :price, :notes, GETDATE(), GETDATE())
        """), {
            "pid":   data.BuyerPeopleID,
            "bid":   data.BuyerBusinessID,
            "lid":   data.ListingID,
            "sbid":  seller_bid,
            "qty":   data.Quantity,
            "price": unit_price,
            "notes": data.Notes,
        })
    db.commit()
    return {"message": "Added to cart"}


# ─────────────────────────────────────────────
# REVIEWS
# ─────────────────────────────────────────────

class ReviewRequest(BaseModel):
    ListingID:        str
    ReviewerPeopleID: int
    OrderID:          int
    Rating:           int
    ReviewText:       Optional[str] = None


# ─────────────────────────────────────────────
# PRODUCTS  (physical goods — seller CRUD)
# ─────────────────────────────────────────────

class ProductCreate(BaseModel):
    BusinessID:        int
    Title:             str
    Description:       Optional[str]  = None
    CategoryName:      Optional[str]  = None
    UnitPrice:         float
    WholesalePrice:    Optional[float] = None
    UnitLabel:         str            = 'each'
    QuantityAvailable: float          = 0
    MinOrderQuantity:  float          = 1
    ImageURL:          Optional[str]  = None
    Tags:              Optional[str]  = None
    IsOrganic:         bool           = False
    IsFeatured:        bool           = False
    Weight:            Optional[float] = None
    WeightUnit:        Optional[str]  = None
    Color:             Optional[str]  = None
    Size:              Optional[str]  = None
    Material:          Optional[str]  = None
    SKU:               Optional[str]  = None
    DeliveryOptions:   str            = 'pickup'


def _ser_product(r):
    m = dict(r._mapping)
    for f in ["UnitPrice", "WholesalePrice", "QuantityAvailable", "MinOrderQuantity", "Weight"]:
        if m.get(f) is not None:
            m[f] = float(m[f])
    m["IsActive"]   = bool(m.get("IsActive", 1))
    m["IsOrganic"]  = bool(m.get("IsOrganic", 0))
    m["IsFeatured"] = bool(m.get("IsFeatured", 0))
    m["ListingID"]  = f"G{m['ProductID']}"
    return m


@marketplace_router.get("/products")
def list_products(
    business_id: Optional[int]  = Query(None),
    search:      Optional[str]  = Query(None),
    category:    Optional[str]  = Query(None),
    sort:        str            = Query("newest"),
    db:          Session        = Depends(get_db),
):
    where = ["pr.IsActive = 1"]
    params = {}
    if business_id:
        where.append("pr.BusinessID = :bid")
        params["bid"] = business_id
    if search and search.strip():
        where.append("(pr.Title LIKE :search OR pr.Description LIKE :search OR pr.CategoryName LIKE :search)")
        params["search"] = f"%{search.strip()}%"
    if category and category != "all":
        where.append("pr.CategoryName = :cat")
        params["cat"] = category
    order = {"price_asc": "pr.UnitPrice ASC", "price_desc": "pr.UnitPrice DESC",
             "name_asc": "pr.Title ASC"}.get(sort, "pr.ProductID DESC")
    rows = db.execute(text(f"""
        SELECT pr.*, b.BusinessName AS SellerName, a.AddressCity AS SellerCity, a.AddressState AS SellerState
        FROM MarketplaceProducts pr
        JOIN Business b ON pr.BusinessID = b.BusinessID
        LEFT JOIN Address a ON b.AddressID = a.AddressID
        WHERE {" AND ".join(where)}
        ORDER BY pr.IsFeatured DESC, {order}
    """), params).fetchall()
    return [_ser_product(r) for r in rows]


@marketplace_router.get("/products/categories")
def list_product_categories(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT DISTINCT CategoryName FROM MarketplaceProducts
        WHERE IsActive = 1 AND CategoryName IS NOT NULL AND CategoryName != ''
        ORDER BY CategoryName
    """)).fetchall()
    return [r[0] for r in rows]


@marketplace_router.get("/products/seller")
def seller_products(business_id: int, db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT pr.*, b.BusinessName AS SellerName, NULL AS SellerCity, NULL AS SellerState
        FROM MarketplaceProducts pr
        JOIN Business b ON pr.BusinessID = b.BusinessID
        WHERE pr.BusinessID = :bid
        ORDER BY pr.ProductID DESC
    """), {"bid": business_id}).fetchall()
    return [_ser_product(r) for r in rows]


@marketplace_router.get("/products/{product_id}")
def get_product(product_id: int, db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT pr.*, b.BusinessName AS SellerName, a.AddressCity AS SellerCity, a.AddressState AS SellerState
        FROM MarketplaceProducts pr
        JOIN Business b ON pr.BusinessID = b.BusinessID
        LEFT JOIN Address a ON b.AddressID = a.AddressID
        WHERE pr.ProductID = :pid
    """), {"pid": product_id}).fetchone()
    if not row:
        raise HTTPException(404, "Product not found")
    return _ser_product(row)


@marketplace_router.post("/products")
def create_product(data: ProductCreate, db: Session = Depends(get_db)):
    db.execute(text("""
        INSERT INTO MarketplaceProducts
            (BusinessID, Title, Description, CategoryName, UnitPrice, WholesalePrice,
             UnitLabel, QuantityAvailable, MinOrderQuantity, ImageURL, Tags,
             IsOrganic, IsFeatured, Weight, WeightUnit, Color, Size, Material, SKU, DeliveryOptions,
             IsActive, CreatedAt, UpdatedAt)
        VALUES
            (:bid, :title, :desc, :cat, :price, :wprice,
             :unit, :qty, :minqty, :img, :tags,
             :organic, :featured, :weight, :wunit, :color, :size, :material, :sku, :delivery,
             1, GETDATE(), GETDATE())
    """), {
        "bid": data.BusinessID, "title": data.Title, "desc": data.Description,
        "cat": data.CategoryName, "price": data.UnitPrice, "wprice": data.WholesalePrice,
        "unit": data.UnitLabel, "qty": data.QuantityAvailable, "minqty": data.MinOrderQuantity,
        "img": data.ImageURL, "tags": data.Tags,
        "organic": int(data.IsOrganic), "featured": int(data.IsFeatured),
        "weight": data.Weight, "wunit": data.WeightUnit, "color": data.Color,
        "size": data.Size, "material": data.Material, "sku": data.SKU,
        "delivery": data.DeliveryOptions,
    })
    product_id = db.execute(text("SELECT SCOPE_IDENTITY()")).scalar()
    db.commit()
    return get_product(int(product_id), db)


@marketplace_router.put("/products/{product_id}")
def update_product(product_id: int, data: dict, db: Session = Depends(get_db)):
    allowed = {"Title", "Description", "CategoryName", "UnitPrice", "WholesalePrice",
               "UnitLabel", "QuantityAvailable", "MinOrderQuantity", "ImageURL", "Tags",
               "IsOrganic", "IsFeatured", "IsActive", "Weight", "WeightUnit",
               "Color", "Size", "Material", "SKU", "DeliveryOptions"}
    sets = [f"{k} = :{k}" for k in data if k in allowed]
    if not sets:
        raise HTTPException(400, "No valid fields to update")
    sets.append("UpdatedAt = GETDATE()")
    db.execute(text(f"UPDATE MarketplaceProducts SET {', '.join(sets)} WHERE ProductID = :pid"),
               {**{k: v for k, v in data.items() if k in allowed}, "pid": product_id})
    db.commit()
    return get_product(product_id, db)


@marketplace_router.delete("/products/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    db.execute(text("DELETE FROM MarketplaceProducts WHERE ProductID = :pid"), {"pid": product_id})
    db.commit()
    return {"message": "Product deleted"}


@marketplace_router.post("/reviews")
def submit_review(req: ReviewRequest, db: Session = Depends(get_db)):
    if not 1 <= req.Rating <= 5:
        raise HTTPException(400, "Rating must be between 1 and 5")
    db.execute(text("""
        INSERT INTO MarketplaceReviews (ListingID, ReviewerPeopleID, OrderID, Rating, ReviewText, CreatedAt)
        VALUES (:lid, :pid, :oid, :rating, :text, GETDATE())
    """), {"lid": req.ListingID, "pid": req.ReviewerPeopleID,
           "oid": req.OrderID, "rating": req.Rating, "text": req.ReviewText})
    db.commit()


# ── Livestock Marketplace endpoints ──────────────────────────────────────────
# These serve LivestockForSale.jsx, LivestockMarketplace.jsx, and RanchList.jsx

import time as _time
_livestock_cache: dict = {}
_CACHE_TTL = 300  # 5 minutes

GCP_ANIMALS = "https://storage.googleapis.com/oatmeal-farm-network-images/Animals"

SLUG_TO_SPECIES_ID = {
    'alpacas': 2, 'bison': 9, 'buffalo': 34, 'camels': 18, 'cattle': 8,
    'chickens': 13, 'crocodiles': 25, 'dogs': 3, 'deer': 21, 'donkeys': 7,
    'ducks': 15, 'emus': 19, 'geese': 22, 'goats': 6, 'guinea-fowl': 26,
    'honey-bees': 23, 'horses': 5, 'llamas': 4, 'musk-ox': 27,
    'ostriches': 28, 'pheasants': 29, 'pigs': 12, 'pigeons': 30,
    'quails': 31, 'rabbits': 11, 'sheep': 10, 'snails': 33,
    'turkeys': 14, 'yaks': 17,
}

SLUG_TO_SINGULAR = {
    'alpacas': 'Alpaca', 'bison': 'Bison', 'buffalo': 'Buffalo',
    'camels': 'Camel', 'cattle': 'Cattle', 'chickens': 'Chicken',
    'crocodiles': 'Crocodile', 'deer': 'Deer', 'dogs': 'Working Dog',
    'donkeys': 'Donkey', 'ducks': 'Duck', 'emus': 'Emu', 'geese': 'Goose',
    'goats': 'Goat', 'guinea-fowl': 'Guinea Fowl', 'honey-bees': 'Honey Bee',
    'horses': 'Horse', 'llamas': 'Llama', 'musk-ox': 'Musk Ox',
    'ostriches': 'Ostrich', 'pheasants': 'Pheasant', 'pigs': 'Pig',
    'pigeons': 'Pigeon', 'quails': 'Quail', 'rabbits': 'Rabbit',
    'sheep': 'Sheep', 'snails': 'Snail', 'turkeys': 'Turkey', 'yaks': 'Yak',
}


def _unescape(s) -> str:
    """Replace SQL-escaped double single-quotes ('' ) with a real apostrophe."""
    if not s:
        return s
    return str(s).replace("''", "'")


_GCS_PREFIX = "https://storage.googleapis.com/oatmeal-farm-network-images/"

def _animal_photo(row) -> str | None:
    """Return the first confirmed GCS URL for a listing card, or None.

    Only values that are already GCS URLs are trusted — old-style filenames
    or upload paths may not exist in the bucket and would cause 404s.
    """
    for field in ('ListPageImage', 'Photo1', 'Photo2', 'Photo3', 'Photo4',
                  'Photo5', 'Photo6', 'Photo7', 'Photo8'):
        v = getattr(row, field, None)
        if not v:
            continue
        s = str(v).strip()
        if s and s.startswith(_GCS_PREFIX):
            return s
    return None


def _animal_dict(row, studs: bool = False) -> dict:
    breeds = [b for b in [
        getattr(row, 'Breed1', None) or '',
        getattr(row, 'Breed2', None) or '',
    ] if b]
    price = None
    try:
        raw = float(row.StudFee if studs else row.Price)
        if raw > 0:
            price = raw
    except Exception:
        pass
    return {
        "animal_id":  row.AnimalID,
        "full_name":  _unescape(getattr(row, 'FullName', '') or ''),
        "photo":      _animal_photo(row),
        "price":      price if not studs else None,
        "stud_fee":   price if studs else None,
        "breeds":     [_unescape(b) for b in breeds],
        "location":   getattr(row, 'AddressState', '') or '',
        "seller":     _unescape(getattr(row, 'BusinessName', '') or ''),
        "species_id": getattr(row, 'SpeciesID', None),
    }


@marketplace_router.get("/homepage-listings")
def livestock_homepage_listings(db: Session = Depends(get_db)):
    """Return up to 24 recent for-sale animals across all species for the homepage."""
    cached = _livestock_cache.get("homepage")
    if cached and _time.time() - cached["ts"] < _CACHE_TTL:
        return cached["data"]
    try:
        rows = db.execute(text("""
            SELECT TOP 60
                a.AnimalID, a.FullName, a.SpeciesID,
                ph.Photo1, ph.Photo2, ph.Photo3, ph.Photo4, ph.Photo5,
                ph.Photo6, ph.Photo7, ph.Photo8, ph.ListPageImage,
                p.Price,
                b1.Breed AS Breed1, b2.Breed AS Breed2,
                biz.BusinessName,
                addr.AddressState
            FROM Animals a
            JOIN Pricing p          ON p.AnimalID       = a.AnimalID
            LEFT JOIN Photos ph     ON ph.AnimalID      = a.AnimalID
            LEFT JOIN SpeciesBreedLookupTable b1  ON b1.BreedLookupID = a.BreedID
            LEFT JOIN SpeciesBreedLookupTable b2  ON b2.BreedLookupID = a.BreedID2
            LEFT JOIN BusinessAccess ba ON ba.PeopleID  = a.PeopleID AND ba.Active = 1
            LEFT JOIN Business biz  ON biz.BusinessID  = ba.BusinessID
            LEFT JOIN Address addr  ON addr.AddressID   = biz.AddressID
            WHERE a.PublishForSale = 1
            ORDER BY
                CASE WHEN (
                    (ph.ListPageImage IS NOT NULL AND ph.ListPageImage != '' AND ph.ListPageImage != '0')
                    OR (ph.Photo1 IS NOT NULL AND ph.Photo1 != '' AND ph.Photo1 != '0')
                    OR (ph.Photo2 IS NOT NULL AND ph.Photo2 != '' AND ph.Photo2 != '0')
                    OR (ph.Photo3 IS NOT NULL AND ph.Photo3 != '' AND ph.Photo3 != '0')
                    OR (ph.Photo4 IS NOT NULL AND ph.Photo4 != '' AND ph.Photo4 != '0')
                    OR (ph.Photo5 IS NOT NULL AND ph.Photo5 != '' AND ph.Photo5 != '0')
                    OR (ph.Photo6 IS NOT NULL AND ph.Photo6 != '' AND ph.Photo6 != '0')
                    OR (ph.Photo7 IS NOT NULL AND ph.Photo7 != '' AND ph.Photo7 != '0')
                    OR (ph.Photo8 IS NOT NULL AND ph.Photo8 != '' AND ph.Photo8 != '0')
                ) THEN 0 ELSE 1 END ASC,
                a.LastUpdated DESC
        """)).fetchall()
        animals = [_animal_dict(r) for r in rows]

        with_photo = [a for a in animals if a.get("photo")]
        no_photo   = [a for a in animals if not a.get("photo")]

        # Diversity sort: round-robin through species so no species dominates
        # any section of the page.  Within each species the SQL ORDER BY already
        # put the most-recently-updated animal first.
        #
        # Cap each species first so a dominant species (e.g. alpacas) can't
        # flood the tail after smaller species are exhausted.
        # Formula: ceil(30 / n_species), minimum 3 per species.
        from collections import defaultdict
        sp_groups: dict = defaultdict(list)
        for a in with_photo:
            sp_groups[a.get("species_id")].append(a)

        n_species = max(len(sp_groups), 1)
        per_cap   = max(3, -(-30 // n_species))   # ceiling division
        sp_groups = {k: v[:per_cap] for k, v in sp_groups.items()}

        diverse: list = []
        while sp_groups:
            for sp in list(sp_groups.keys()):
                if sp_groups[sp]:
                    diverse.append(sp_groups[sp].pop(0))
            sp_groups = {k: v for k, v in sp_groups.items() if v}

        # Homepage only shows animals with confirmed GCS photos.
        # Return 30 so the frontend can trim to full rows at any breakpoint.
        result = diverse[:30]

        _livestock_cache["homepage"] = {"data": result, "ts": _time.time()}
        return result
    except Exception as e:
        import traceback; traceback.print_exc()
        return []


@marketplace_router.get("/species/{slug}")
def livestock_species_info(slug: str):
    """Return singular term and label for a species slug."""
    return {
        "slug":          slug,
        "singular_term": SLUG_TO_SINGULAR.get(slug, ''),
        "label":         slug.replace('-', ' ').title(),
    }


@marketplace_router.get("/filters/{slug}")
def livestock_filters(slug: str, db: Session = Depends(get_db)):
    """Return available breeds and states for the given species slug."""
    species_id = SLUG_TO_SPECIES_ID.get(slug)
    if not species_id:
        return {"breeds": [], "states": [], "ranches": []}
    try:
        breed_rows = db.execute(text("""
            SELECT DISTINCT sbl.BreedLookupID AS id, sbl.Breed AS name
            FROM SpeciesBreedLookupTable sbl
            JOIN Animals a ON a.BreedID = sbl.BreedLookupID
            JOIN Pricing p ON p.AnimalID = a.AnimalID
            WHERE sbl.SpeciesID = :sid
              AND (a.PublishForSale = 1 OR a.PublishStud = 1)
            ORDER BY sbl.Breed
        """), {"sid": species_id}).fetchall()

        state_rows = db.execute(text("""
            SELECT DISTINCT addr.AddressState AS state, addr.StateIndex AS state_index
            FROM Animals a
            LEFT JOIN BusinessAccess ba ON ba.PeopleID = a.PeopleID AND ba.Active = 1
            JOIN Business biz      ON biz.BusinessID = COALESCE(a.BusinessID, ba.BusinessID)
            JOIN Address addr      ON addr.AddressID = biz.AddressID
            WHERE a.SpeciesID = :sid
              AND (a.PublishForSale = 1 OR a.PublishStud = 1)
              AND addr.AddressState IS NOT NULL
            ORDER BY addr.AddressState
        """), {"sid": species_id}).fetchall()

        ranch_rows = db.execute(text("""
            SELECT DISTINCT biz.BusinessID AS id, biz.BusinessName AS name
            FROM Animals a
            LEFT JOIN BusinessAccess ba ON ba.PeopleID = a.PeopleID AND ba.Active = 1
            JOIN Business biz      ON biz.BusinessID = COALESCE(a.BusinessID, ba.BusinessID)
            WHERE a.SpeciesID = :sid
              AND (a.PublishForSale = 1 OR a.PublishStud = 1)
              AND biz.BusinessName IS NOT NULL
              AND LTRIM(RTRIM(biz.BusinessName)) <> ''
            ORDER BY biz.BusinessName
        """), {"sid": species_id}).fetchall()

        return {
            "breeds":  [{"id": r.id, "name": r.name} for r in breed_rows],
            "states":  [{"state": r.state, "state_index": r.state_index} for r in state_rows],
            "ranches": [{"id": r.id, "name": r.name} for r in ranch_rows],
        }
    except Exception:
        import traceback; traceback.print_exc()
        return {"breeds": [], "states": [], "ranches": []}


def _livestock_listing(
    slug: str, studs: bool, page: int,
    breed_id: int, state_index: int,
    min_price: float, max_price: float,
    ancestry: str, sort_by: str, order_by: str,
    db: Session,
    business_id: int = 0,
) -> dict:
    PER_PAGE = 10
    species_id = SLUG_TO_SPECIES_ID.get(slug)
    if not species_id:
        return {"total": 0, "page": page, "per_page": PER_PAGE, "total_pages": 0, "animals": [], "label": slug}

    publish_flag = "a.PublishStud = 1" if studs else "a.PublishForSale = 1"
    price_col    = "p.StudFee"         if studs else "p.Price"

    sort_map = {
        "lastupdated": "a.LastUpdated",
        "price":       price_col,
        "name":        "a.FullName",
        "breed":       "b1.Breed",
    }
    order_sql  = sort_map.get(sort_by, "a.LastUpdated")
    dir_sql    = "ASC" if order_by == "asc" else "DESC"

    filters = [f"a.SpeciesID = :sid", publish_flag,
               f"{price_col} >= :min_price", f"{price_col} <= :max_price"]
    params: dict = {"sid": species_id, "min_price": min_price, "max_price": max_price}

    if breed_id and breed_id != 0:
        filters.append("(a.BreedID = :breed_id OR a.BreedID2 = :breed_id)")
        params["breed_id"] = breed_id

    if state_index and state_index != 0:
        filters.append("addr.StateIndex = :state_index")
        params["state_index"] = state_index

    if business_id and business_id != 0:
        filters.append("biz.BusinessID = :business_id")
        params["business_id"] = business_id

    where = " AND ".join(filters)

    join_block = """
        JOIN Pricing p          ON p.AnimalID      = a.AnimalID
        LEFT JOIN Photos ph     ON ph.AnimalID     = a.AnimalID
        LEFT JOIN SpeciesBreedLookupTable b1 ON b1.BreedLookupID = a.BreedID
        LEFT JOIN SpeciesBreedLookupTable b2 ON b2.BreedLookupID = a.BreedID2
        LEFT JOIN BusinessAccess ba ON ba.PeopleID = a.PeopleID AND ba.Active = 1
        LEFT JOIN Business biz  ON biz.BusinessID  = COALESCE(a.BusinessID, ba.BusinessID)
        LEFT JOIN Address addr  ON addr.AddressID  = biz.AddressID
    """

    total = db.execute(text(f"""
        SELECT COUNT(*) FROM Animals a {join_block} WHERE {where}
    """), params).scalar() or 0

    offset = (page - 1) * PER_PAGE
    rows = db.execute(text(f"""
        SELECT a.AnimalID, a.FullName, a.LastUpdated,
               ph.Photo1, ph.Photo2, ph.ListPageImage,
               p.Price, p.StudFee,
               b1.Breed AS Breed1, b2.Breed AS Breed2,
               biz.BusinessName, addr.AddressState
        FROM Animals a {join_block}
        WHERE {where}
        ORDER BY {order_sql} {dir_sql}
        OFFSET :offset ROWS FETCH NEXT :per_page ROWS ONLY
    """), {**params, "offset": offset, "per_page": PER_PAGE}).fetchall()

    return {
        "total":       total,
        "page":        page,
        "per_page":    PER_PAGE,
        "total_pages": max(1, -(-total // PER_PAGE)),
        "label":       slug.replace('-', ' ').title(),
        "animals":     [_animal_dict(r, studs) for r in rows],
    }


@marketplace_router.get("/for-sale/{slug}")
def livestock_for_sale(
    slug: str,
    page:        int   = Query(1,          ge=1),
    breed_id:    int   = Query(0),
    state_index: int   = Query(0),
    business_id: int   = Query(0),
    min_price:   float = Query(0),
    max_price:   float = Query(100_000_000),
    ancestry:    str   = Query("Any"),
    sort_by:     str   = Query("lastupdated"),
    order_by:    str   = Query("desc"),
    db: Session = Depends(get_db),
):
    try:
        return _livestock_listing(slug, False, page, breed_id, state_index,
                                  min_price, max_price, ancestry, sort_by, order_by, db,
                                  business_id=business_id)
    except Exception:
        import traceback; traceback.print_exc()
        return {"total": 0, "page": page, "per_page": 10, "total_pages": 0, "animals": [], "label": slug}


@marketplace_router.get("/studs/{slug}")
def livestock_studs(
    slug: str,
    page:        int   = Query(1,          ge=1),
    breed_id:    int   = Query(0),
    state_index: int   = Query(0),
    business_id: int   = Query(0),
    min_stud_fee:  float = Query(0),
    max_stud_fee:  float = Query(100_000_000),
    ancestry:    str   = Query("Any"),
    sort_by:     str   = Query("lastupdated"),
    order_by:    str   = Query("desc"),
    db: Session = Depends(get_db),
):
    try:
        return _livestock_listing(slug, True, page, breed_id, state_index,
                                  min_stud_fee, max_stud_fee, ancestry, sort_by, order_by, db,
                                  business_id=business_id)
    except Exception:
        import traceback; traceback.print_exc()
        return {"total": 0, "page": page, "per_page": 10, "total_pages": 0, "animals": [], "label": slug}


# ── Animal detail page ────────────────────────────────────────────────────────

SPECIES_ID_TO_SLUG = {v: k for k, v in SLUG_TO_SPECIES_ID.items()}

def _photo_url(filename) -> str | None:
    """Return a GCS URL for the given filename value, or None.

    If the value is already a GCS URL it is returned as-is.
    Otherwise we construct one from the bare filename so the browser can
    attempt to load it — onError handlers on the frontend hide any that 404.
    """
    if not filename:
        return None
    s = str(filename).strip()
    if not s or s == "0" or len(s) < 3:
        return None
    if s.startswith(_GCS_PREFIX):
        return s
    from urllib.parse import quote
    fname = s.split("/")[-1].strip()
    if not fname or len(fname) < 3:
        return None
    return f"{GCP_ANIMALS}/{quote(fname, safe='')}"


@marketplace_router.get("/animal/{animal_id}/progeny")
def get_animal_progeny(animal_id: int, db: Session = Depends(get_db)):
    """Return all animals for which this animal is a direct parent (Sire or Dam).

    Matches Ancestors.SireLink/DamLink on this animal's ID, and falls back to
    matching Ancestors.Sire/Ancestors.Dam on the animal's FullName for legacy
    data that was entered as free text."""
    parent = db.execute(text(
        "SELECT AnimalID, FullName, Category FROM Animals WHERE AnimalID = :aid"
    ), {"aid": animal_id}).fetchone()
    if not parent:
        raise HTTPException(status_code=404, detail="Animal not found")
    parent_d = dict(parent._mapping)
    parent_name = (parent_d.get("FullName") or "").strip()
    parent_cat  = (parent_d.get("Category") or "").lower()

    link_like = f"%/animal/{animal_id}"
    sql = (
        "SELECT DISTINCT a.AnimalID, a.FullName, a.SpeciesID, a.Category, "
        "       a.DOBMonth, a.DOBDay, a.DOBYear, "
        "       p.Photo1, "
        "       c.Color1, c.Color2, c.Color3, c.Color4, c.Color5 "
        "FROM Animals a "
        "JOIN Ancestors anc ON anc.AnimalID = a.AnimalID "
        "LEFT JOIN Photos p ON p.AnimalID = a.AnimalID "
        "LEFT JOIN Colors c ON c.AnimalID = a.AnimalID "
        "WHERE anc.SireLink LIKE :link_like "
        "   OR anc.DamLink  LIKE :link_like "
    )
    params = {"link_like": link_like}
    if parent_name:
        sql += "   OR RTRIM(LTRIM(anc.Sire)) = :pname OR RTRIM(LTRIM(anc.Dam)) = :pname "
        params["pname"] = parent_name
    sql += "ORDER BY a.DOBYear DESC, a.DOBMonth DESC, a.DOBDay DESC, a.FullName"
    rows = db.execute(text(sql), params).fetchall()

    out = []
    for r in rows:
        d = dict(r._mapping)
        colors = [d.get(f"Color{i}") for i in range(1, 6)]
        colors = [c for c in colors if c and str(c).strip()]
        out.append({
            "animal_id":  d["AnimalID"],
            "full_name":  d.get("FullName") or "",
            "species_id": d.get("SpeciesID"),
            "category":   d.get("Category") or "",
            "dob_year":   d.get("DOBYear"),
            "dob_month":  d.get("DOBMonth"),
            "dob_day":    d.get("DOBDay"),
            "photo":      _photo_url(d.get("Photo1")),
            "colors":     ", ".join(colors),
        })
    return {
        "parent_id":   animal_id,
        "parent_name": parent_name,
        "parent_gender": "female" if any(w in parent_cat for w in ("female", "dam", "maiden"))
                         else ("male" if any(w in parent_cat for w in ("male", "herdsire", "stud")) else None),
        "progeny":     out,
    }


@marketplace_router.get("/animal/{animal_id}")
def get_animal_detail(animal_id: int, db: Session = Depends(get_db)):
    """Public endpoint — returns everything needed for the animal detail page."""

    # ── core animal fields (no fragile outer joins) ───────────────────────────
    row = db.execute(text("""
        SELECT
            a.AnimalID, a.FullName, a.SpeciesID, a.Description, a.StudDescription,
            a.DOBMonth, a.DOBDay, a.DOBYear,
            a.Category, a.BreedID, a.BreedID2, a.BreedID3, a.BreedID4,
            a.Weight, a.Height, a.Horns, a.Gaited, a.Warmblooded, a.Temperment,
            a.Vaccinations, a.PublishStud, a.PublishForSale,
            a.LastUpdated, a.PeopleID, a.BusinessID,
            a.CoOwnerName1, a.CoOwnerLink1, a.CoOwnerBusiness1,
            a.CoOwnerName2, a.CoOwnerLink2, a.CoOwnerBusiness2,
            a.CoOwnerName3, a.CoOwnerLink3, a.CoOwnerBusiness3
        FROM Animals a
        WHERE a.AnimalID = :aid
    """), {"aid": animal_id}).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Animal not found")

    d = dict(row._mapping)
    people_id = d.get("PeopleID")

    # ── pricing ───────────────────────────────────────────────────────────────
    pr = db.execute(text(
        "SELECT Price, StudFee, Free, Sold, PriceComments, Financeterms "
        "FROM Pricing WHERE AnimalID = :aid"
    ), {"aid": animal_id}).fetchone()
    pr = dict(pr._mapping) if pr else {}

    # ── colors ────────────────────────────────────────────────────────────────
    cr = db.execute(text(
        "SELECT Color1, Color2, Color3, Color4, Color5 FROM Colors WHERE AnimalID = :aid"
    ), {"aid": animal_id}).fetchone()
    cr = dict(cr._mapping) if cr else {}

    # ── ancestry ─────────────────────────────────────────────────────────────
    anc_row = db.execute(text("SELECT * FROM Ancestors WHERE AnimalID = :aid"), {"aid": animal_id}).fetchone()
    # DB column casing is inconsistent (e.g. Siredam, Damsire, DamAri). Build a
    # case-insensitive accessor so downstream .get("SireDam") works regardless.
    _anc_raw = dict(anc_row._mapping) if anc_row else {}
    _anc_ci = {k.lower(): v for k, v in _anc_raw.items()}
    class _AncCI:
        def get(self, key, default=None):
            return _anc_ci.get(key.lower(), default)
    anc = _AncCI()

    # ── alpaca bloodline percentages (optional; columns may not exist) ───────
    bloodline = {}
    try:
        pct_row = db.execute(text(
            "SELECT PercentPeruvian, PercentChilean, PercentBolivian, "
            "PercentUnknownOther, PercentAccoyo FROM Animals WHERE AnimalID = :aid"
        ), {"aid": animal_id}).fetchone()
        if pct_row:
            for key, label in (
                ("PercentPeruvian",     "Peruvian"),
                ("PercentChilean",      "Chilean"),
                ("PercentBolivian",     "Bolivian"),
                ("PercentUnknownOther", "Unknown / Other"),
                ("PercentAccoyo",       "Accoyo"),
            ):
                val = getattr(pct_row, key, None)
                if val and str(val).strip():
                    bloodline[label] = str(val).strip()
    except Exception:
        db.rollback()

    # ── photos (up to 16) ─────────────────────────────────────────────────────
    photos_row = db.execute(text(
        "SELECT Photo1,Photo2,Photo3,Photo4,Photo5,Photo6,Photo7,Photo8,"
        "Photo9,Photo10,Photo11,Photo12,Photo13,Photo14,Photo15,Photo16,"
        "AnimalVideo,Histogram,FiberAnalysis,ARI "
        "FROM Photos WHERE AnimalID = :aid"
    ), {"aid": animal_id}).fetchone()

    photos = []
    video_url = histogram_url = fiber_analysis_url = registration_url = None
    if photos_row:
        for i in range(1, 17):
            url = _photo_url(getattr(photos_row, f"Photo{i}", None))
            if url:
                photos.append(url)
        video_url          = _photo_url(getattr(photos_row, "AnimalVideo", None))
        histogram_url      = _photo_url(getattr(photos_row, "Histogram", None))
        fiber_analysis_url = _photo_url(getattr(photos_row, "FiberAnalysis", None))
        registration_url   = _photo_url(getattr(photos_row, "ARI", None))

    # ── owner: prefer Animals.BusinessID direct link, fall back to People → BusinessAccess ──
    owner_info = {"business_name": None, "business_id": None, "city": None,
                  "state": None, "logo": None, "people_id": people_id}
    direct_biz_id = d.get("BusinessID")
    biz_row = None
    if direct_biz_id:
        biz_row = db.execute(text("""
            SELECT b.BusinessName, b.BusinessID, b.Logo, addr.AddressCity, addr.AddressState
            FROM Business b
            LEFT JOIN Address addr ON addr.AddressID = b.AddressID
            WHERE b.BusinessID = :bid
        """), {"bid": direct_biz_id}).fetchone()
    if not biz_row and people_id:
        biz_row = db.execute(text("""
            SELECT b.BusinessName, b.BusinessID, b.Logo, addr.AddressCity, addr.AddressState
            FROM BusinessAccess ba
            JOIN Business b   ON b.BusinessID  = ba.BusinessID
            LEFT JOIN Address addr ON addr.AddressID = b.AddressID
            WHERE ba.PeopleID = :pid AND ba.Active = 1
        """), {"pid": people_id}).fetchone()
    if biz_row:
        owner_info["business_name"] = biz_row.BusinessName
        owner_info["business_id"]   = biz_row.BusinessID
        owner_info["city"]          = biz_row.AddressCity
        owner_info["state"]         = biz_row.AddressState
        owner_info["logo"]          = _photo_url(biz_row.Logo)

    # ── species singular/plural terms ─────────────────────────────────────────
    species_id = d.get("SpeciesID")

    # ── resolve Category (stored as SpeciesCategoryID) to a readable name ─────
    category_display = d.get("Category")
    if category_display is not None:
        raw_cat = str(category_display).strip()
        if raw_cat.isdigit():
            cat_row = db.execute(text(
                "SELECT SpeciesCategory FROM speciescategory WHERE SpeciesCategoryID = :cid"
            ), {"cid": int(raw_cat)}).fetchone()
            if cat_row:
                category_display = cat_row[0]
            elif raw_cat == "0":
                category_display = None

    # ── breed names ───────────────────────────────────────────────────────────
    breed_names = []
    for bid_col in ("BreedID", "BreedID2", "BreedID3", "BreedID4"):
        bid = d.get(bid_col)
        if bid:
            br = db.execute(text(
                "SELECT Breed FROM SpeciesBreedLookupTable WHERE BreedLookupID = :bid"
            ), {"bid": bid}).fetchone()
            if br:
                breed_names.append(br[0])

    # ── registration numbers ──────────────────────────────────────────────────
    reg_rows = db.execute(text("""
        SELECT DISTINCT RegType, RegNumber FROM AnimalRegistration
        WHERE AnimalID = :aid AND RegNumber IS NOT NULL AND RegNumber != ''
        ORDER BY RegType
    """), {"aid": animal_id}).fetchall()
    registrations = [{"type": r.RegType, "number": r.RegNumber} for r in reg_rows]

    # ── awards ────────────────────────────────────────────────────────────────
    award_rows = db.execute(text("""
        SELECT AwardYear, ShowName, Placing, Type, Awardcomments
        FROM Awards WHERE AnimalID = :aid ORDER BY Placing ASC
    """), {"aid": animal_id}).fetchall()
    awards = [
        {
            "AwardYear":     r.AwardYear,
            "ShowName":      r.ShowName,
            "Placing":       r.Placing,
            "AwardClass":    r.Type,
            "AwardComments": r.Awardcomments,
        }
        for r in award_rows
        if any([r.AwardYear and str(r.AwardYear) != "0",
                r.ShowName and str(r.ShowName).strip(),
                r.Placing and str(r.Placing).strip(),
                r.Type and str(r.Type).strip()])
    ]

    # ── fiber stats (correct casing from actual table) ────────────────────────
    fiber_rows = db.execute(text("""
        SELECT SampleDateMonth, SampleDateDay, SampleDateYear,
               Average, StandardDev, COV, GreaterThan30,
               BlanketWeight, ShearWeight, CF, Length, Curve, CrimpPerInch
        FROM Fiber WHERE AnimalID = :aid
        ORDER BY SampleDateYear DESC, Average DESC
    """), {"aid": animal_id}).fetchall()
    fiber_stats = [dict(r._mapping) for r in fiber_rows]

    # ── species slug ──────────────────────────────────────────────────────────
    species_slug     = SPECIES_ID_TO_SLUG.get(species_id)
    species_singular = SLUG_TO_SINGULAR.get(species_slug, "Animal")

    return {
        "animal_id":        d["AnimalID"],
        "full_name":        _unescape(d.get("FullName") or ""),
        "species_id":       species_id,
        "species_slug":     species_slug,
        "species_singular": species_singular,
        "description":      _unescape(d.get("Description") or ""),
        "stud_description": _unescape(d.get("StudDescription") or ""),
        "dob": {"month": d.get("DOBMonth"), "day": d.get("DOBDay"), "year": d.get("DOBYear")},
        "category":     category_display,
        "breeds":       [_unescape(b) for b in breed_names],
        "colors":       [x.strip() for x in [cr.get("Color1"), cr.get("Color2"), cr.get("Color3"), cr.get("Color4"), cr.get("Color5")] if x and str(x).strip()],
        "weight":       d.get("Weight"),
        "height":       d.get("Height"),
        "horns":        d.get("Horns"),
        "gaited":       d.get("Gaited"),
        "warmblooded":  d.get("Warmblooded"),
        "temperament":  d.get("Temperment"),
        "vaccinations": d.get("Vaccinations"),
        "pricing": {
            "price":          float(pr["Price"])   if pr.get("Price")   else None,
            "stud_fee":       float(pr["StudFee"]) if pr.get("StudFee") else None,
            "free":           bool(pr.get("Free")),
            "sold":           bool(pr.get("Sold")),
            "price_comments": pr.get("PriceComments"),
        },
        "sold":             bool(pr.get("Sold")),
        "sale_pending":     False,
        "publish_stud":     bool(d.get("PublishStud")),
        "publish_for_sale": bool(d.get("PublishForSale")),
        "finance_terms":    pr.get("Financeterms"),
        "last_updated":     str(d["LastUpdated"]) if d.get("LastUpdated") else None,
        "co_owners": [x for x in [
            {"name": d.get("CoOwnerName1"), "business": d.get("CoOwnerBusiness1"), "link": d.get("CoOwnerLink1")} if d.get("CoOwnerName1") or d.get("CoOwnerBusiness1") else None,
            {"name": d.get("CoOwnerName2"), "business": d.get("CoOwnerBusiness2"), "link": d.get("CoOwnerLink2")} if d.get("CoOwnerName2") or d.get("CoOwnerBusiness2") else None,
            {"name": d.get("CoOwnerName3"), "business": d.get("CoOwnerBusiness3"), "link": d.get("CoOwnerLink3")} if d.get("CoOwnerName3") or d.get("CoOwnerBusiness3") else None,
        ] if x],
        "owner": owner_info,
        "ancestry": {
            "sire_term": "Sire",
            "dam_term":  "Dam",
            "sire":          {"name": _unescape(anc.get("Sire")),         "color": anc.get("SireColor"),         "link": anc.get("SireLink"),         "reg": anc.get("SireARI")},
            "sire_sire":     {"name": _unescape(anc.get("SireSire")),     "color": anc.get("SireSireColor"),     "link": anc.get("SireSireLink"),     "reg": anc.get("SireSireARI")},
            "sire_dam":      {"name": _unescape(anc.get("SireDam")),      "color": anc.get("SireDamColor"),      "link": anc.get("SireDamLink"),      "reg": anc.get("SireDamARI")},
            "sire_sire_sire":{"name": _unescape(anc.get("SireSireSire")), "color": anc.get("SireSireSireColor"), "link": anc.get("SireSireSireLink"), "reg": anc.get("SireSireSireARI")},
            "sire_sire_dam": {"name": _unescape(anc.get("SireSireDam")),  "color": anc.get("SireSireDamColor"),  "link": anc.get("SireSireDamLink"),  "reg": anc.get("SireSireDamARI")},
            "sire_dam_sire": {"name": _unescape(anc.get("SireDamSire")),  "color": anc.get("SireDamSireColor"),  "link": anc.get("SireDamSireLink"),  "reg": anc.get("SireDamSireARI")},
            "sire_dam_dam":  {"name": _unescape(anc.get("SireDamDam")),   "color": anc.get("SireDamDamColor"),   "link": anc.get("SireDamDamLink"),   "reg": anc.get("SireDamDamARI")},
            "dam":           {"name": _unescape(anc.get("Dam")),          "color": anc.get("DamColor"),          "link": anc.get("DamLink"),          "reg": anc.get("DamARI") or anc.get("DamAri")},
            "dam_sire":      {"name": _unescape(anc.get("DamSire")),      "color": anc.get("DamSireColor"),      "link": anc.get("DamSireLink"),      "reg": anc.get("DamSireARI")},
            "dam_dam":       {"name": _unescape(anc.get("DamDam")),       "color": anc.get("DamDamColor"),       "link": anc.get("DamDamLink"),       "reg": anc.get("DamDamARI")},
            "dam_sire_sire": {"name": _unescape(anc.get("DamSireSire")),  "color": anc.get("DamSireSireColor"),  "link": anc.get("DamSireSireLink"),  "reg": anc.get("DamSireSireARI")},
            "dam_sire_dam":  {"name": _unescape(anc.get("DamSireDam")),   "color": anc.get("DamSireDamColor"),   "link": anc.get("DamSireDamLink"),   "reg": anc.get("DamSireDamARI")},
            "dam_dam_sire":  {"name": _unescape(anc.get("DamDamSire")),   "color": anc.get("DamDamSireColor"),   "link": anc.get("DamDamSireLink"),   "reg": anc.get("DamDamSireARI")},
            "dam_dam_dam":   {"name": _unescape(anc.get("DamDamDam")),    "color": anc.get("DamDamDamColor"),    "link": anc.get("DamDamDamLink"),    "reg": anc.get("DamDamDamARI")},
            "bloodline":     bloodline,
        },
        "photos":             photos,
        "video_url":          video_url,
        "histogram_url":      histogram_url,
        "fiber_analysis_url": fiber_analysis_url,
        "registration_url":   registration_url,
        "registrations":      registrations,
        "awards":             awards,
        "fiber_stats":        fiber_stats,
    }