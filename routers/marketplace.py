# routers/marketplace.py
# Farm-to-Restaurant Marketplace API
# Mount: app.include_router(marketplace_router, prefix="/api/marketplace")

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
from pydantic import BaseModel
from typing import Optional, List
from datetime import date

from image_service import ensure_images_for_catalog

marketplace_router = APIRouter()

   
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
    return {"message": "Review submitted"}