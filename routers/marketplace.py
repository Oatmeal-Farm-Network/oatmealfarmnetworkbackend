# routers/marketplace.py
# Farm-to-Restaurant Marketplace API
# Mount: app.include_router(marketplace_router, prefix="/api/marketplace")

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from database import get_db
from auth import get_current_user
from pydantic import BaseModel
from typing import Optional, List
from datetime import date

marketplace_router = APIRouter()

   
# ─────────────────────────────────────────────
# PYDANTIC MODELS
# ─────────────────────────────────────────────

class CartItem(BaseModel):
    ListingID: int
    Quantity:  float

class PlaceOrderRequest(BaseModel):
    BuyerPeopleID:        int
    BuyerBusinessID:      Optional[int]  = None
    DeliveryMethod:       str            = "pickup"   # pickup | local_delivery | shipping
    DeliveryAddress:      Optional[str]  = None
    DeliveryNotes:        Optional[str]  = None
    RequestedDeliveryDate: Optional[date] = None
    items:                List[CartItem]

class SellerActionRequest(BaseModel):
    SellerStatus:     str            # confirmed | rejected
    RejectionReason:  Optional[str]  = None
    EstimatedDeliveryDate: Optional[date] = None

class ShipItemRequest(BaseModel):
    TrackingNumber: Optional[str] = None
    EstimatedDeliveryDate: Optional[date] = None


# ─────────────────────────────────────────────
# CATALOG  (public — no auth required)
# ─────────────────────────────────────────────

@marketplace_router.get("/catalog")
def get_catalog(
    product_type: Optional[str] = Query(None),
    organic:      Optional[bool] = Query(None),
    search:       Optional[str]  = Query(None),
    sort:         str             = Query("newest"),
    db:           Session         = Depends(get_db),
):
    """
    Browse all active listings.
    Joins to Business to get seller name/location.
    """
    where = ["ml.IsActive = 1", "ml.QuantityAvailable > 0"]
    params: dict = {}

    if product_type:
        where.append("ml.ProductType = :product_type")
        params["product_type"] = product_type

    if organic:
        where.append("ml.IsOrganic = 1")

    if search:
        where.append("(ml.Title LIKE :search OR ml.Description LIKE :search OR ml.CategoryName LIKE :search)")
        params["search"] = f"%{search}%"

    # Expiration guard
    where.append("(ml.ExpirationDate IS NULL OR ml.ExpirationDate >= CAST(GETDATE() AS DATE))")

    sort_map = {
        "newest":     "ml.ListingID DESC",
        "price_asc":  "ml.UnitPrice ASC",
        "price_desc": "ml.UnitPrice DESC",
        "name_asc":   "ml.Title ASC",
    }
    order_by = sort_map.get(sort, "ml.ListingID DESC")

    sql = f"""
        SELECT
            ml.ListingID, ml.BusinessID, ml.ProductType, ml.SourceID,
            ml.Title, ml.Description, ml.CategoryName,
            ml.UnitPrice, ml.WholesalePrice, ml.UnitLabel,
            ml.QuantityAvailable, ml.MinOrderQuantity, ml.MaxOrderQuantity,
            ml.ImageURL, ml.IsOrganic, ml.IsLocal, ml.IsFeatured,
            ml.AvailableDate,
            b.BusinessName  AS SellerName,
            a.AddressCity   AS SellerCity,
            a.AddressState  AS SellerState,
            a.AddressZip    AS SellerZip
        FROM MarketplaceListings ml
        JOIN Business b ON ml.BusinessID = b.BusinessID
        LEFT JOIN Address a ON b.AddressID = a.AddressID
        WHERE {" AND ".join(where)}
        ORDER BY ml.IsFeatured DESC, {order_by}
    """

    rows = db.execute(text(sql), params).fetchall()
    result = []
    for r in rows:
        m = dict(r._mapping)
        m["UnitPrice"]       = float(m["UnitPrice"])       if m["UnitPrice"]       else 0.0
        m["WholesalePrice"]  = float(m["WholesalePrice"])  if m["WholesalePrice"]  else None
        m["QuantityAvailable"] = float(m["QuantityAvailable"]) if m["QuantityAvailable"] else 0.0
        m["IsOrganic"]       = bool(m["IsOrganic"])
        m["IsLocal"]         = bool(m["IsLocal"])
        m["IsFeatured"]      = bool(m["IsFeatured"])
        result.append(m)
    return result  # flat list — frontend handles both flat and {listings:[]} formats


@marketplace_router.get("/catalog/{listing_id}")
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    """Single listing detail with reviews and related listings."""
    row = db.execute(text("""
        SELECT
            ml.*,
            b.BusinessName  AS SellerName,
            a.AddressCity   AS SellerCity,
            a.AddressState  AS SellerState,
            a.AddressZip    AS SellerZip
        FROM MarketplaceListings ml
        JOIN Business b ON ml.BusinessID = b.BusinessID
        LEFT JOIN Address a ON b.AddressID = a.AddressID
        WHERE ml.ListingID = :lid AND ml.IsActive = 1
    """), {"lid": listing_id}).fetchone()

    if not row:
        raise HTTPException(404, "Listing not found")

    listing = dict(row._mapping)
    listing["UnitPrice"]      = float(listing["UnitPrice"])      if listing["UnitPrice"]      else 0.0
    listing["WholesalePrice"] = float(listing["WholesalePrice"]) if listing["WholesalePrice"] else None
    listing["QuantityAvailable"] = float(listing["QuantityAvailable"]) if listing["QuantityAvailable"] else 0.0
    listing["IsOrganic"]      = bool(listing["IsOrganic"])
    listing["IsLocal"]        = bool(listing["IsLocal"])
    listing["IsFeatured"]     = bool(listing["IsFeatured"])

    # Reviews
    reviews = db.execute(text("""
        SELECT r.Rating, r.ReviewText, r.CreatedAt,
               p.PeopleFirstName + ' ' + LEFT(p.PeopleLastName, 1) + '.' AS ReviewerName
        FROM MarketplaceReviews r
        JOIN People p ON r.ReviewerPeopleID = p.PeopleID
        WHERE r.ListingID = :lid
        ORDER BY r.CreatedAt DESC
    """), {"lid": listing_id}).fetchall()
    listing["reviews"] = [dict(r._mapping) for r in reviews]

    # Related listings from same seller
    related = db.execute(text("""
        SELECT TOP 3 ListingID, Title, UnitPrice, UnitLabel, ImageURL, ProductType
        FROM MarketplaceListings
        WHERE BusinessID = :bid AND ListingID != :lid AND IsActive = 1 AND QuantityAvailable > 0
        ORDER BY IsFeatured DESC, ListingID DESC
    """), {"bid": listing["BusinessID"], "lid": listing_id}).fetchall()
    listing["relatedListings"] = [dict(r._mapping) for r in related]

    return listing


# ─────────────────────────────────────────────
# ORDERS  (buyer)
# ─────────────────────────────────────────────

@marketplace_router.post("/orders")
def place_order(req: PlaceOrderRequest, db: Session = Depends(get_db)):
    """
    Place an order. Creates MarketplaceOrders + MarketplaceOrderItems.
    Sends email notifications to buyer and each seller.
    """
    if not req.items:
        raise HTTPException(400, "No items in order")

    # Validate listings and compute totals
    order_items = []
    subtotal = 0.0

    for item in req.items:
        listing = db.execute(text("""
            SELECT ml.*, b.BusinessName AS SellerName,
                   p.PeopleEmail AS SellerEmail
            FROM MarketplaceListings ml
            JOIN Business b ON ml.BusinessID = b.BusinessID
            JOIN People p ON b.PeopleID = p.PeopleID
            WHERE ml.ListingID = :lid AND ml.IsActive = 1
        """), {"lid": item.ListingID}).fetchone()

        if not listing:
            raise HTTPException(404, f"Listing {item.ListingID} not found or inactive")

        l = dict(listing._mapping)
        qty = float(item.Quantity)

        if qty > float(l["QuantityAvailable"]):
            raise HTTPException(400, f"Only {l['QuantityAvailable']} available for '{l['Title']}'")

        unit_price  = float(l["UnitPrice"])
        line_total  = round(unit_price * qty, 2)
        platform_cut = round(line_total * 0.025, 2)
        seller_payout = round(line_total - platform_cut, 2)
        subtotal += line_total

        order_items.append({
            "listing":       l,
            "quantity":      qty,
            "unit_price":    unit_price,
            "line_total":    line_total,
            "seller_payout": seller_payout,
        })

    platform_fee = round(subtotal * 0.025, 2)
    total_amount = round(subtotal + platform_fee, 2)

    # Get buyer info
    buyer = db.execute(text("""
        SELECT PeopleFirstName + ' ' + PeopleLastName AS FullName, PeopleEmail, PeoplePhone
        FROM People WHERE PeopleID = :pid
    """), {"pid": req.BuyerPeopleID}).fetchone()
    if not buyer:
        raise HTTPException(404, "Buyer not found")

    # Generate order number
    order_number = db.execute(text("""
        SELECT 'OFN-' + FORMAT(GETDATE(), 'yyyyMMdd') + '-' + RIGHT('0000' + CAST(NEXT VALUE FOR OrderNumberSeq AS NVARCHAR), 4)
    """)).scalar()
    # Fallback if sequence doesn't exist
    if not order_number:
        import random, string
        order_number = "OFN-" + "".join(random.choices(string.digits, k=8))

    # Insert order
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
        "order_number":    order_number,
        "buyer_pid":       req.BuyerPeopleID,
        "buyer_bid":       req.BuyerBusinessID,
        "buyer_name":      buyer[0],
        "buyer_email":     buyer[1],
        "delivery_method": req.DeliveryMethod,
        "delivery_address": req.DeliveryAddress,
        "delivery_notes":  req.DeliveryNotes,
        "requested_date":  req.RequestedDeliveryDate,
        "subtotal":        subtotal,
        "platform_fee":    platform_fee,
        "total_amount":    total_amount,
    })

    order_id = db.execute(text("SELECT SCOPE_IDENTITY()")).scalar()

    # Insert order items
    seller_ids_notified = set()
    for oi in order_items:
        l = oi["listing"]
        db.execute(text("""
            INSERT INTO MarketplaceOrderItems (
                OrderID, ListingID, SellerBusinessID,
                ProductTitle, ProductType, SellerName,
                Quantity, UnitPrice, LineTotal, SellerPayout,
                SellerStatus, CreatedAt, UpdatedAt
            ) VALUES (
                :order_id, :listing_id, :seller_bid,
                :title, :product_type, :seller_name,
                :quantity, :unit_price, :line_total, :seller_payout,
                'pending', GETDATE(), GETDATE()
            )
        """), {
            "order_id":     order_id,
            "listing_id":   l["ListingID"],
            "seller_bid":   l["BusinessID"],
            "title":        l["Title"],
            "product_type": l["ProductType"],
            "seller_name":  l["SellerName"],
            "quantity":     oi["quantity"],
            "unit_price":   oi["unit_price"],
            "line_total":   oi["line_total"],
            "seller_payout": oi["seller_payout"],
        })

        # Decrement inventory
        db.execute(text("""
            UPDATE MarketplaceListings
            SET QuantityAvailable = QuantityAvailable - :qty, UpdatedAt = GETDATE()
            WHERE ListingID = :lid
        """), {"qty": oi["quantity"], "lid": l["ListingID"]})

        seller_ids_notified.add(l["BusinessID"])

    # Insert platform fee record
    db.execute(text("""
        INSERT INTO PlatformFees (OrderID, Amount, Status, CreatedAt)
        VALUES (:oid, :amount, 'pending', GETDATE())
    """), {"oid": order_id, "amount": platform_fee})

    # Log initial status
    db.execute(text("""
        INSERT INTO OrderStatusHistory (OrderID, NewStatus, ChangedByRole, Notes, CreatedAt)
        VALUES (:oid, 'pending', 'system', 'Order placed', GETDATE())
    """), {"oid": order_id})

    db.commit()

    # Send emails (non-blocking — fail silently)
    try:
        from marketplace_emails import send_order_placed_buyer, send_order_placed_seller
        send_order_placed_buyer(order_id, db)
        for seller_bid in seller_ids_notified:
            send_order_placed_seller(order_id, seller_bid, db)
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
    """Full order detail including items and status history."""
    order = db.execute(text("""
        SELECT * FROM MarketplaceOrders WHERE OrderID = :oid
    """), {"oid": order_id}).fetchone()
    if not order:
        raise HTTPException(404, "Order not found")

    result = dict(order._mapping)
    for field in ["Subtotal", "PlatformFee", "TaxAmount", "DeliveryFee", "TotalAmount"]:
        if result.get(field) is not None:
            result[field] = float(result[field])

    # Order items
    items = db.execute(text("""
        SELECT oi.*, b.BusinessName
        FROM MarketplaceOrderItems oi
        LEFT JOIN Business b ON oi.SellerBusinessID = b.BusinessID
        WHERE oi.OrderID = :oid
        ORDER BY oi.OrderItemID
    """), {"oid": order_id}).fetchall()
    result["items"] = []
    for i in items:
        row = dict(i._mapping)
        for f in ["UnitPrice", "LineTotal", "SellerPayout"]:
            if row.get(f) is not None:
                row[f] = float(row[f])
        result["items"].append(row)

    # Status history
    try:
        history = db.execute(text("""
            SELECT * FROM OrderStatusHistory WHERE OrderID = :oid ORDER BY CreatedAt ASC
        """), {"oid": order_id}).fetchall()
        result["history"] = [dict(h._mapping) for h in history]
    except Exception:
        result["history"] = []

    return result


@marketplace_router.get("/orders")
def list_orders(buyer_people_id: int, db: Session = Depends(get_db)):
    """All orders for a buyer."""
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
    """All order items for a seller's business."""
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
def seller_item_action(
    order_item_id: int,
    req: SellerActionRequest,
    db: Session = Depends(get_db),
):
    """Seller confirms or rejects an order item."""
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
        SET SellerStatus = :status,
            RejectionReason = :reason,
            EstimatedDeliveryDate = :edd,
            UpdatedAt = GETDATE()
        WHERE OrderItemID = :oiid
    """), {
        "status": req.SellerStatus,
        "reason": req.RejectionReason,
        "edd":    req.EstimatedDeliveryDate,
        "oiid":   order_item_id,
    })

    # If rejected, restore inventory
    if req.SellerStatus == "rejected":
        db.execute(text("""
            UPDATE MarketplaceListings
            SET QuantityAvailable = QuantityAvailable + :qty, UpdatedAt = GETDATE()
            WHERE ListingID = :lid
        """), {"qty": item.Quantity, "lid": item.ListingID})

    db.commit()

    # Check if all items in this order have been actioned
    pending = db.execute(text("""
        SELECT COUNT(*) FROM MarketplaceOrderItems
        WHERE OrderID = :oid AND SellerStatus = 'pending'
    """), {"oid": item.OrderID}).scalar()

    if pending == 0:
        # Update overall order status
        confirmed = db.execute(text("""
            SELECT COUNT(*) FROM MarketplaceOrderItems
            WHERE OrderID = :oid AND SellerStatus = 'confirmed'
        """), {"oid": item.OrderID}).scalar()

        rejected = db.execute(text("""
            SELECT COUNT(*) FROM MarketplaceOrderItems
            WHERE OrderID = :oid AND SellerStatus = 'rejected'
        """), {"oid": item.OrderID}).scalar()

        if confirmed == 0:
            new_status = "cancelled"
        elif rejected > 0:
            new_status = "partially_confirmed"
        else:
            new_status = "confirmed"

        db.execute(text("""
            UPDATE MarketplaceOrders SET OrderStatus = :status, UpdatedAt = GETDATE()
            WHERE OrderID = :oid
        """), {"status": new_status, "oid": item.OrderID})
        db.commit()

        # Notify buyer all sellers have responded
        try:
            from marketplace_emails import send_item_status_buyer, send_ready_for_payment
            send_item_status_buyer(item.OrderID, order_item_id, req.SellerStatus, db)
            if confirmed > 0:
                send_ready_for_payment(item.OrderID, db)
        except Exception as e:
            print(f"[marketplace] Email failed: {e}")
    else:
        # Notify buyer of this item's status
        try:
            from marketplace_emails import send_item_status_buyer
            send_item_status_buyer(item.OrderID, order_item_id, req.SellerStatus, db)
        except Exception as e:
            print(f"[marketplace] Email failed: {e}")

    return {"message": f"Item {req.SellerStatus}", "OrderID": item.OrderID}


@marketplace_router.post("/seller/orders/{order_item_id}/ship")
def ship_item(
    order_item_id: int,
    req: ShipItemRequest,
    db: Session = Depends(get_db),
):
    """Mark an item as shipped."""
    item = db.execute(text(
        "SELECT * FROM MarketplaceOrderItems WHERE OrderItemID = :oiid"
    ), {"oiid": order_item_id}).fetchone()

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

    try:
        from marketplace_emails import send_item_shipped
        send_item_shipped(item.OrderID, order_item_id, db)
    except Exception as e:
        print(f"[marketplace] Email failed: {e}")

    return {"message": "Item marked as shipped"}


@marketplace_router.post("/orders/{order_id}/deliver")
def confirm_delivery(
    order_id: int,
    order_item_id: int = Query(...),
    db: Session = Depends(get_db),
):
    """Buyer confirms delivery of an item."""
    db.execute(text("""
        UPDATE MarketplaceOrderItems
        SET SellerStatus = 'delivered', DeliveredAt = GETDATE(), UpdatedAt = GETDATE()
        WHERE OrderItemID = :oiid AND OrderID = :oid
    """), {"oiid": order_item_id, "oid": order_id})
    db.commit()

    try:
        from marketplace_emails import send_delivery_confirmed
        send_delivery_confirmed(order_id, order_item_id, db)
    except Exception as e:
        print(f"[marketplace] Email failed: {e}")

    return {"message": "Delivery confirmed"}


# ─────────────────────────────────────────────
# SELLER LISTINGS MANAGEMENT
# ─────────────────────────────────────────────

@marketplace_router.get("/seller/listings")
def get_seller_listings(business_id: int, db: Session = Depends(get_db)):
    """All listings for a seller."""
    rows = db.execute(text("""
        SELECT * FROM MarketplaceListings
        WHERE BusinessID = :bid
        ORDER BY IsFeatured DESC, ListingID DESC
    """), {"bid": business_id}).fetchall()

    result = []
    for r in rows:
        row = dict(r._mapping)
        for f in ["UnitPrice", "WholesalePrice", "QuantityAvailable", "MinOrderQuantity", "MaxOrderQuantity"]:
            if row.get(f) is not None:
                row[f] = float(row[f])
        row["IsOrganic"]  = bool(row.get("IsOrganic"))
        row["IsLocal"]    = bool(row.get("IsLocal"))
        row["IsActive"]   = bool(row.get("IsActive"))
        row["IsFeatured"] = bool(row.get("IsFeatured"))
        result.append(row)
    return result


class CreateListingRequest(BaseModel):
    BusinessID:        int
    ProductType:       str          # produce | meat | processed_food
    SourceID:          Optional[int] = None
    Title:             str
    Description:       Optional[str] = None
    CategoryName:      Optional[str] = None
    UnitPrice:         float
    WholesalePrice:    Optional[float] = None
    UnitLabel:         str           = "each"
    QuantityAvailable: float
    MinOrderQuantity:  Optional[float] = None
    MaxOrderQuantity:  Optional[float] = None
    ImageURL:          Optional[str] = None
    IsOrganic:         bool          = False
    IsLocal:           bool          = True
    AvailableDate:     Optional[date] = None
    ExpirationDate:    Optional[date] = None


@marketplace_router.post("/seller/listings")
def create_listing(req: CreateListingRequest, db: Session = Depends(get_db)):
    """Create a new marketplace listing."""
    db.execute(text("""
        INSERT INTO MarketplaceListings (
            BusinessID, ProductType, SourceID, Title, Description, CategoryName,
            UnitPrice, WholesalePrice, UnitLabel,
            QuantityAvailable, MinOrderQuantity, MaxOrderQuantity,
            ImageURL, IsOrganic, IsLocal, AvailableDate, ExpirationDate,
            IsActive, IsFeatured
        ) VALUES (
            :bid, :ptype, :source_id, :title, :desc, :category,
            :price, :ws_price, :unit_label,
            :qty, :min_qty, :max_qty,
            :image_url, :is_organic, :is_local, :avail_date, :exp_date,
            1, 0
        )
    """), {
        "bid":        req.BusinessID,
        "ptype":      req.ProductType,
        "source_id":  req.SourceID,
        "title":      req.Title,
        "desc":       req.Description,
        "category":   req.CategoryName,
        "price":      req.UnitPrice,
        "ws_price":   req.WholesalePrice,
        "unit_label": req.UnitLabel,
        "qty":        req.QuantityAvailable,
        "min_qty":    req.MinOrderQuantity,
        "max_qty":    req.MaxOrderQuantity,
        "image_url":  req.ImageURL,
        "is_organic": 1 if req.IsOrganic else 0,
        "is_local":   1 if req.IsLocal   else 0,
        "avail_date": req.AvailableDate,
        "exp_date":   req.ExpirationDate,
    })
    listing_id = db.execute(text("SELECT SCOPE_IDENTITY()")).scalar()
    db.commit()
    return {"ListingID": listing_id, "message": "Listing created"}


@marketplace_router.patch("/seller/listings/{listing_id}/toggle")
def toggle_listing(listing_id: int, db: Session = Depends(get_db)):
    """Activate or deactivate a listing."""
    db.execute(text("""
        UPDATE MarketplaceListings
        SET IsActive = 1 - IsActive, UpdatedAt = GETDATE()
        WHERE ListingID = :lid
    """), {"lid": listing_id})
    db.commit()
    active = db.execute(text("SELECT IsActive FROM MarketplaceListings WHERE ListingID = :lid"), {"lid": listing_id}).scalar()
    return {"ListingID": listing_id, "IsActive": bool(active)}


@marketplace_router.delete("/seller/listings/{listing_id}")
def delete_listing(listing_id: int, db: Session = Depends(get_db)):
    """Soft-delete (deactivate) a listing."""
    db.execute(text("""
        UPDATE MarketplaceListings SET IsActive = 0, UpdatedAt = GETDATE()
        WHERE ListingID = :lid
    """), {"lid": listing_id})
    db.commit()
    return {"message": "Listing deactivated"}


# ─────────────────────────────────────────────
# REVIEWS
# ─────────────────────────────────────────────

class ReviewRequest(BaseModel):
    ListingID:        int
    ReviewerPeopleID: int
    OrderID:          int
    Rating:           int   # 1–5
    ReviewText:       Optional[str] = None


@marketplace_router.post("/reviews")
def submit_review(req: ReviewRequest, db: Session = Depends(get_db)):
    if not 1 <= req.Rating <= 5:
        raise HTTPException(400, "Rating must be between 1 and 5")

    # Check for duplicate review on this order+listing
    existing = db.execute(text("""
        SELECT ReviewID FROM MarketplaceReviews
        WHERE ListingID = :lid AND ReviewerPeopleID = :pid AND OrderID = :oid
    """), {"lid": req.ListingID, "pid": req.ReviewerPeopleID, "oid": req.OrderID}).fetchone()

    if existing:
        raise HTTPException(400, "You have already reviewed this item for this order")

    db.execute(text("""
        INSERT INTO MarketplaceReviews (ListingID, ReviewerPeopleID, OrderID, Rating, ReviewText, CreatedAt)
        VALUES (:lid, :pid, :oid, :rating, :text, GETDATE())
    """), {
        "lid":    req.ListingID,
        "pid":    req.ReviewerPeopleID,
        "oid":    req.OrderID,
        "rating": req.Rating,
        "text":   req.ReviewText,
    })
    db.commit()
    return {"message": "Review submitted"}


# ─────────────────────────────────────────────
# CHECKOUT ALIAS
# Accepts the same payload as /orders but also
# handles the legacy frontend cart-sync flow
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
    """
    Checkout using server-side CartItems table.
    Frontend syncs localStorage cart to CartItems first,
    then calls this endpoint.
    """
    rows = db.execute(text("""
        SELECT ci.ListingID, ci.Quantity, ci.UnitPrice,
               ml.Title, ml.ProductType, ml.QuantityAvailable,
               ml.BusinessID AS SellerBusinessID,
               b.BusinessName AS SellerName,
               p.PeopleEmail AS SellerEmail
        FROM CartItems ci
        JOIN MarketplaceListings ml ON ci.ListingID = ml.ListingID
        JOIN Business b ON ml.BusinessID = b.BusinessID
        JOIN People p ON b.PeopleID = p.PeopleID
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

    # Clear server cart
    db.execute(text("DELETE FROM CartItems WHERE BuyerPeopleID = :pid"), {"pid": req.BuyerPeopleID})
    db.commit()

    return result


# ─────────────────────────────────────────────
# SERVER-SIDE CART (for checkout flow)
# ─────────────────────────────────────────────

class CartItemAdd(BaseModel):
    BuyerPeopleID:   int
    BuyerBusinessID: Optional[int] = None
    ListingID:       int
    Quantity:        float
    Notes:           Optional[str] = None


@marketplace_router.post("/cart")
def add_to_cart(data: CartItemAdd, db: Session = Depends(get_db)):
    """Sync a localStorage cart item to the server CartItems table."""
    listing = db.execute(text(
        "SELECT BusinessID, UnitPrice, QuantityAvailable FROM MarketplaceListings WHERE ListingID = :lid AND IsActive = 1"
    ), {"lid": data.ListingID}).fetchone()

    if not listing:
        raise HTTPException(404, "Listing not found or inactive")

    seller_bid, unit_price, qty_available = listing[0], listing[1], listing[2]

    if float(data.Quantity) > float(qty_available):
        raise HTTPException(400, f"Only {qty_available} available")

    existing = db.execute(text(
        "SELECT CartItemID, Quantity FROM CartItems WHERE BuyerPeopleID = :pid AND ListingID = :lid"
    ), {"pid": data.BuyerPeopleID, "lid": data.ListingID}).fetchone()

    if existing:
        db.execute(text(
            "UPDATE CartItems SET Quantity = :qty, UpdatedAt = GETDATE() WHERE CartItemID = :cid"
        ), {"qty": data.Quantity, "cid": existing[0]})
    else:
        db.execute(text("""
            INSERT INTO CartItems (BuyerPeopleID, BuyerBusinessID, ListingID, SellerBusinessID, Quantity, UnitPrice, Notes)
            VALUES (:pid, :bid, :lid, :sbid, :qty, :price, :notes)
        """), {
            "pid":   data.BuyerPeopleID,
            "bid":   data.BuyerBusinessID,
            "lid":   data.ListingID,
            "sbid":  seller_bid,
            "qty":   data.Quantity,
            "price": float(unit_price),
            "notes": data.Notes,
        })

    db.commit()
    return {"message": "Added to cart"}