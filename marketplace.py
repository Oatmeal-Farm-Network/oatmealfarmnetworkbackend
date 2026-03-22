# marketplace.py
# FastAPI routes for the Farm2Restaurant Marketplace
# Mount in your main.py: from marketplace import marketplace_router
#                         app.include_router(marketplace_router, prefix="/api/marketplace")

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
import os
import json

marketplace_router = APIRouter()

# --- Database helper (adapt to your existing db connection) ---
# Assumes you have a get_db_connection() that returns a pyodbc or aioodbc connection
# Replace with your actual database helper import
from main import get_db_cursor  # Adjust this import to match your setup

PLATFORM_FEE_PERCENT = 2.5
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_CONNECT_CLIENT_ID = os.getenv("STRIPE_CONNECT_CLIENT_ID", "")
OFN_BASE_URL = os.getenv("OFN_BASE_URL", "https://oatmealfarmnetwork.com")

# ============================================================
# MODELS
# ============================================================

class ListingCreate(BaseModel):
    BusinessID: int
    ProductType: str  # produce, meat, processed_food
    SourceID: int
    Title: str
    Description: Optional[str] = None
    CategoryName: Optional[str] = None
    UnitPrice: float
    WholesalePrice: Optional[float] = None
    UnitLabel: Optional[str] = 'each'
    QuantityAvailable: float = 0
    MinOrderQuantity: float = 1
    MaxOrderQuantity: Optional[float] = None
    ImageURL: Optional[str] = None
    IsOrganic: bool = False
    Weight: Optional[float] = None
    WeightUnit: Optional[str] = None
    Tags: Optional[str] = None
    DeliveryOptions: Optional[str] = 'pickup'
    AvailableDate: Optional[str] = None

class CartItemAdd(BaseModel):
    BuyerPeopleID: int
    BuyerBusinessID: Optional[int] = None
    ListingID: int
    Quantity: float
    Notes: Optional[str] = None

class CartItemUpdate(BaseModel):
    Quantity: float
    Notes: Optional[str] = None

class CheckoutRequest(BaseModel):
    BuyerPeopleID: int
    BuyerBusinessID: Optional[int] = None
    DeliveryMethod: str = 'pickup'
    DeliveryAddressID: Optional[int] = None
    DeliveryAddress: Optional[str] = None
    DeliveryNotes: Optional[str] = None
    RequestedDeliveryDate: Optional[str] = None

class SellerConfirmation(BaseModel):
    OrderItemID: int
    Status: str  # confirmed, rejected
    RejectionReason: Optional[str] = None
    EstimatedDeliveryDate: Optional[str] = None

class ShipmentUpdate(BaseModel):
    OrderItemID: int
    TrackingNumber: Optional[str] = None

# ============================================================
# 1. PRODUCT CATALOG - PUBLIC (no auth required)
# ============================================================

@marketplace_router.get("/catalog")
async def get_catalog(
    search: str = "",
    category: str = "",
    product_type: str = "",
    seller_id: Optional[int] = None,
    is_organic: Optional[bool] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    sort_by: str = "newest",  # newest, price_low, price_high, name
    page: int = 1,
    per_page: int = 24,
):
    """Public catalog - browse all active listings"""
    cursor = get_db_cursor()

    conditions = ["ml.IsActive = 1", "ml.QuantityAvailable > 0"]
    params = []

    if search:
        conditions.append("(ml.Title LIKE ? OR ml.Description LIKE ? OR ml.Tags LIKE ? OR ml.CategoryName LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term, term])

    if category:
        conditions.append("ml.CategoryName = ?")
        params.append(category)

    if product_type:
        conditions.append("ml.ProductType = ?")
        params.append(product_type)

    if seller_id:
        conditions.append("ml.BusinessID = ?")
        params.append(seller_id)

    if is_organic is not None:
        conditions.append("ml.IsOrganic = ?")
        params.append(1 if is_organic else 0)

    if min_price is not None:
        conditions.append("ml.UnitPrice >= ?")
        params.append(min_price)

    if max_price is not None:
        conditions.append("ml.UnitPrice <= ?")
        params.append(max_price)

    where_clause = " AND ".join(conditions)

    order_map = {
        "newest": "ml.CreatedAt DESC",
        "price_low": "ml.UnitPrice ASC",
        "price_high": "ml.UnitPrice DESC",
        "name": "ml.Title ASC",
    }
    order_by = order_map.get(sort_by, "ml.CreatedAt DESC")

    # Count total
    count_sql = f"SELECT COUNT(*) FROM MarketplaceListings ml WHERE {where_clause}"
    cursor.execute(count_sql, params)
    total = cursor.fetchone()[0]

    # Get page
    offset = (page - 1) * per_page
    sql = f"""
        SELECT ml.*, b.BusinessName AS SellerName, b.PickupAvailable, b.ShippingAvailable, b.DeliveryRadius,
               a.City AS SellerCity, a.State AS SellerState
        FROM MarketplaceListings ml
        JOIN Business b ON ml.BusinessID = b.BusinessID
        LEFT JOIN Address a ON b.AddressID = a.AddressID
        WHERE {where_clause}
        ORDER BY {order_by}
        OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
    """
    params.extend([offset, per_page])
    cursor.execute(sql, params)
    columns = [desc[0] for desc in cursor.description]
    listings = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # Get categories for filter sidebar
    cursor.execute("SELECT DISTINCT CategoryName FROM MarketplaceListings WHERE IsActive = 1 AND CategoryName IS NOT NULL ORDER BY CategoryName")
    categories = [row[0] for row in cursor.fetchall()]

    return {
        "listings": listings,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "categories": categories,
    }


@marketplace_router.get("/catalog/{listing_id}")
async def get_listing_detail(listing_id: int):
    """Public listing detail"""
    cursor = get_db_cursor()
    cursor.execute("""
        SELECT ml.*, b.BusinessName AS SellerName, b.PickupAvailable, b.ShippingAvailable, b.DeliveryRadius,
               a.City AS SellerCity, a.State AS SellerState, a.Zip AS SellerZip,
               p.PeopleFirstName AS SellerFirstName
        FROM MarketplaceListings ml
        JOIN Business b ON ml.BusinessID = b.BusinessID
        LEFT JOIN Address a ON b.AddressID = a.AddressID
        LEFT JOIN People p ON b.PeopleID = p.PeopleID
        WHERE ml.ListingID = ?
    """, [listing_id])
    columns = [desc[0] for desc in cursor.description]
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Listing not found")
    listing = dict(zip(columns, row))

    # Get other listings from same seller
    cursor.execute("""
        SELECT TOP 6 ListingID, Title, UnitPrice, UnitLabel, ImageURL, CategoryName
        FROM MarketplaceListings
        WHERE BusinessID = ? AND ListingID != ? AND IsActive = 1
        ORDER BY NEWID()
    """, [listing["BusinessID"], listing_id])
    cols2 = [desc[0] for desc in cursor.description]
    listing["relatedListings"] = [dict(zip(cols2, r)) for r in cursor.fetchall()]

    # Get reviews
    cursor.execute("""
        SELECT r.Rating, r.ReviewText, r.CreatedAt, p.PeopleFirstName AS ReviewerName
        FROM MarketplaceReviews r
        JOIN People p ON r.ReviewerPeopleID = p.PeopleID
        WHERE r.ListingID = ? AND r.IsPublic = 1
        ORDER BY r.CreatedAt DESC
    """, [listing_id])
    cols3 = [desc[0] for desc in cursor.description]
    listing["reviews"] = [dict(zip(cols3, r)) for r in cursor.fetchall()]

    return listing


@marketplace_router.get("/categories")
async def get_categories():
    """Get all product categories with counts"""
    cursor = get_db_cursor()
    cursor.execute("""
        SELECT CategoryName, ProductType, COUNT(*) AS Count
        FROM MarketplaceListings
        WHERE IsActive = 1 AND QuantityAvailable > 0
        GROUP BY CategoryName, ProductType
        ORDER BY CategoryName
    """)
    columns = [desc[0] for desc in cursor.description]
    return {"categories": [dict(zip(columns, row)) for row in cursor.fetchall()]}


@marketplace_router.get("/sellers")
async def get_sellers(search: str = ""):
    """List sellers with active listings"""
    cursor = get_db_cursor()
    conditions = ["ml.IsActive = 1"]
    params = []
    if search:
        conditions.append("(b.BusinessName LIKE ? OR a.City LIKE ? OR a.State LIKE ?)")
        term = f"%{search}%"
        params.extend([term, term, term])

    where_clause = " AND ".join(conditions)
    cursor.execute(f"""
        SELECT b.BusinessID, b.BusinessName, b.PickupAvailable, b.ShippingAvailable, b.DeliveryRadius,
               a.City, a.State,
               COUNT(DISTINCT ml.ListingID) AS ListingCount,
               AVG(CAST(mr.Rating AS FLOAT)) AS AvgRating,
               COUNT(DISTINCT mr.ReviewID) AS ReviewCount
        FROM Business b
        JOIN MarketplaceListings ml ON b.BusinessID = ml.BusinessID
        LEFT JOIN Address a ON b.AddressID = a.AddressID
        LEFT JOIN MarketplaceReviews mr ON b.BusinessID = mr.SellerBusinessID
        WHERE {where_clause}
        GROUP BY b.BusinessID, b.BusinessName, b.PickupAvailable, b.ShippingAvailable, b.DeliveryRadius, a.City, a.State
        ORDER BY ListingCount DESC
    """, params)
    columns = [desc[0] for desc in cursor.description]
    return {"sellers": [dict(zip(columns, row)) for row in cursor.fetchall()]}


# ============================================================
# 2. LISTING MANAGEMENT (sellers)
# ============================================================

@marketplace_router.post("/listings")
async def create_listing(data: ListingCreate):
    """Seller creates a marketplace listing"""
    cursor = get_db_cursor()
    cursor.execute("""
        INSERT INTO MarketplaceListings (BusinessID, ProductType, SourceID, Title, Description,
            CategoryName, UnitPrice, WholesalePrice, UnitLabel, QuantityAvailable,
            MinOrderQuantity, MaxOrderQuantity, ImageURL, IsOrganic, Weight, WeightUnit,
            Tags, DeliveryOptions, AvailableDate, IsActive)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, [
        data.BusinessID, data.ProductType, data.SourceID, data.Title, data.Description,
        data.CategoryName, data.UnitPrice, data.WholesalePrice, data.UnitLabel,
        data.QuantityAvailable, data.MinOrderQuantity, data.MaxOrderQuantity,
        data.ImageURL, 1 if data.IsOrganic else 0, data.Weight, data.WeightUnit,
        data.Tags, data.DeliveryOptions, data.AvailableDate
    ])
    cursor.execute("SELECT @@IDENTITY AS ListingID")
    listing_id = cursor.fetchone()[0]
    cursor.connection.commit()
    return {"ListingID": int(listing_id), "message": "Listing created."}


@marketplace_router.get("/listings/seller/{business_id}")
async def get_seller_listings(business_id: int):
    """Get all listings for a seller"""
    cursor = get_db_cursor()
    cursor.execute("""
        SELECT * FROM MarketplaceListings WHERE BusinessID = ? ORDER BY CreatedAt DESC
    """, [business_id])
    columns = [desc[0] for desc in cursor.description]
    return {"listings": [dict(zip(columns, row)) for row in cursor.fetchall()]}


@marketplace_router.put("/listings/{listing_id}")
async def update_listing(listing_id: int, data: dict):
    """Update a listing"""
    cursor = get_db_cursor()
    allowed = ['Title', 'Description', 'CategoryName', 'UnitPrice', 'WholesalePrice',
               'UnitLabel', 'QuantityAvailable', 'MinOrderQuantity', 'MaxOrderQuantity',
               'ImageURL', 'IsOrganic', 'Weight', 'WeightUnit', 'Tags', 'DeliveryOptions',
               'AvailableDate', 'IsActive', 'IsFeatured']
    sets = []
    params = []
    for key, val in data.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            params.append(val)
    if not sets:
        raise HTTPException(400, "No valid fields to update")
    sets.append("UpdatedAt = GETDATE()")
    params.append(listing_id)
    cursor.execute(f"UPDATE MarketplaceListings SET {', '.join(sets)} WHERE ListingID = ?", params)
    cursor.connection.commit()
    return {"message": "Listing updated."}


@marketplace_router.delete("/listings/{listing_id}")
async def delete_listing(listing_id: int):
    cursor = get_db_cursor()
    cursor.execute("UPDATE MarketplaceListings SET IsActive = 0 WHERE ListingID = ?", [listing_id])
    cursor.connection.commit()
    return {"message": "Listing deactivated."}


# ============================================================
# 3. SHOPPING CART (requires login)
# ============================================================

@marketplace_router.get("/cart/{people_id}")
async def get_cart(people_id: int):
    """Get all items in a buyer's cart, grouped by seller"""
    cursor = get_db_cursor()
    cursor.execute("""
        SELECT ci.*, ml.Title, ml.ProductType, ml.UnitLabel, ml.ImageURL, ml.QuantityAvailable,
               b.BusinessName AS SellerName, b.BusinessID AS SellerBusinessID
        FROM CartItems ci
        JOIN MarketplaceListings ml ON ci.ListingID = ml.ListingID
        JOIN Business b ON ci.SellerBusinessID = b.BusinessID
        WHERE ci.BuyerPeopleID = ?
        ORDER BY b.BusinessName, ci.AddedAt
    """, [people_id])
    columns = [desc[0] for desc in cursor.description]
    items = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # Group by seller
    sellers = {}
    for item in items:
        sid = item["SellerBusinessID"]
        if sid not in sellers:
            sellers[sid] = {"SellerBusinessID": sid, "SellerName": item["SellerName"], "items": [], "subtotal": 0}
        item["lineTotal"] = round(item["Quantity"] * item["UnitPrice"], 2)
        sellers[sid]["items"].append(item)
        sellers[sid]["subtotal"] += item["lineTotal"]

    seller_list = list(sellers.values())
    subtotal = sum(s["subtotal"] for s in seller_list)
    platform_fee = round(subtotal * PLATFORM_FEE_PERCENT / 100, 2)

    return {
        "sellers": seller_list,
        "itemCount": len(items),
        "subtotal": subtotal,
        "platformFee": platform_fee,
        "total": round(subtotal + platform_fee, 2),
    }


@marketplace_router.post("/cart")
async def add_to_cart(data: CartItemAdd):
    """Add item to cart"""
    cursor = get_db_cursor()

    # Get listing details
    cursor.execute("SELECT BusinessID, UnitPrice, QuantityAvailable FROM MarketplaceListings WHERE ListingID = ? AND IsActive = 1", [data.ListingID])
    listing = cursor.fetchone()
    if not listing:
        raise HTTPException(404, "Listing not found or inactive")

    seller_bid, unit_price, qty_available = listing
    if data.Quantity > qty_available:
        raise HTTPException(400, f"Only {qty_available} available")

    # Check if already in cart
    cursor.execute("SELECT CartItemID, Quantity FROM CartItems WHERE BuyerPeopleID = ? AND ListingID = ?", [data.BuyerPeopleID, data.ListingID])
    existing = cursor.fetchone()
    if existing:
        new_qty = existing[1] + data.Quantity
        if new_qty > qty_available:
            raise HTTPException(400, f"Only {qty_available} available (you already have {existing[1]} in cart)")
        cursor.execute("UPDATE CartItems SET Quantity = ?, UpdatedAt = GETDATE() WHERE CartItemID = ?", [new_qty, existing[0]])
    else:
        cursor.execute("""
            INSERT INTO CartItems (BuyerPeopleID, BuyerBusinessID, ListingID, SellerBusinessID, Quantity, UnitPrice, Notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [data.BuyerPeopleID, data.BuyerBusinessID, data.ListingID, seller_bid, data.Quantity, unit_price, data.Notes])

    cursor.connection.commit()
    return {"message": "Added to cart."}


@marketplace_router.put("/cart/{cart_item_id}")
async def update_cart_item(cart_item_id: int, data: CartItemUpdate):
    cursor = get_db_cursor()
    if data.Quantity <= 0:
        cursor.execute("DELETE FROM CartItems WHERE CartItemID = ?", [cart_item_id])
    else:
        cursor.execute("UPDATE CartItems SET Quantity = ?, Notes = ?, UpdatedAt = GETDATE() WHERE CartItemID = ?",
                        [data.Quantity, data.Notes, cart_item_id])
    cursor.connection.commit()
    return {"message": "Cart updated."}


@marketplace_router.delete("/cart/{cart_item_id}")
async def remove_from_cart(cart_item_id: int):
    cursor = get_db_cursor()
    cursor.execute("DELETE FROM CartItems WHERE CartItemID = ?", [cart_item_id])
    cursor.connection.commit()
    return {"message": "Removed from cart."}


@marketplace_router.delete("/cart/clear/{people_id}")
async def clear_cart(people_id: int):
    cursor = get_db_cursor()
    cursor.execute("DELETE FROM CartItems WHERE BuyerPeopleID = ?", [people_id])
    cursor.connection.commit()
    return {"message": "Cart cleared."}


# ============================================================
# 4. CHECKOUT & ORDERS
# ============================================================

def generate_order_number():
    """Generate unique order number: OFN-YYYYMMDD-XXX"""
    now = datetime.now()
    prefix = f"OFN-{now.strftime('%Y%m%d')}"
    cursor = get_db_cursor()
    cursor.execute("SELECT COUNT(*) FROM MarketplaceOrders WHERE OrderNumber LIKE ?", [f"{prefix}%"])
    count = cursor.fetchone()[0] + 1
    return f"{prefix}-{count:03d}"


@marketplace_router.post("/checkout")
async def checkout(data: CheckoutRequest):
    """Create order from cart items. Payment is NOT charged yet — only after seller confirms."""
    cursor = get_db_cursor()

    # Get cart items
    cursor.execute("""
        SELECT ci.*, ml.Title, ml.ProductType, ml.QuantityAvailable, b.BusinessName AS SellerName
        FROM CartItems ci
        JOIN MarketplaceListings ml ON ci.ListingID = ml.ListingID
        JOIN Business b ON ci.SellerBusinessID = b.BusinessID
        WHERE ci.BuyerPeopleID = ?
    """, [data.BuyerPeopleID])
    columns = [desc[0] for desc in cursor.description]
    cart_items = [dict(zip(columns, row)) for row in cursor.fetchall()]

    if not cart_items:
        raise HTTPException(400, "Cart is empty")

    # Validate quantities
    for item in cart_items:
        if item["Quantity"] > item["QuantityAvailable"]:
            raise HTTPException(400, f"'{item['Title']}' only has {item['QuantityAvailable']} available")

    # Get buyer info
    cursor.execute("SELECT PeopleFirstName, PeopleLastName, PeopleEmail, PeoplePhone FROM People WHERE PeopleID = ?", [data.BuyerPeopleID])
    buyer = cursor.fetchone()
    if not buyer:
        raise HTTPException(404, "Buyer not found")
    buyer_name = f"{buyer[0]} {buyer[1]}"
    buyer_email = buyer[2]
    buyer_phone = buyer[3]

    # Calculate totals
    subtotal = sum(round(i["Quantity"] * i["UnitPrice"], 2) for i in cart_items)
    platform_fee = round(subtotal * PLATFORM_FEE_PERCENT / 100, 2)
    total = round(subtotal + platform_fee, 2)
    order_number = generate_order_number()

    # Create order
    cursor.execute("""
        INSERT INTO MarketplaceOrders (OrderNumber, BuyerPeopleID, BuyerBusinessID, BuyerName, BuyerEmail, BuyerPhone,
            DeliveryMethod, DeliveryAddressID, DeliveryAddress, DeliveryNotes, RequestedDeliveryDate,
            Subtotal, PlatformFee, TotalAmount, PaymentStatus, OrderStatus)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'pending')
    """, [order_number, data.BuyerPeopleID, data.BuyerBusinessID, buyer_name, buyer_email, buyer_phone,
          data.DeliveryMethod, data.DeliveryAddressID, data.DeliveryAddress, data.DeliveryNotes,
          data.RequestedDeliveryDate, subtotal, platform_fee, total])

    cursor.execute("SELECT @@IDENTITY")
    order_id = int(cursor.fetchone()[0])

    # Create order items (one per cart item)
    for item in cart_items:
        line_total = round(item["Quantity"] * item["UnitPrice"], 2)
        item_fee = round(line_total * PLATFORM_FEE_PERCENT / 100, 2)
        seller_payout = round(line_total - item_fee, 2)

        cursor.execute("""
            INSERT INTO MarketplaceOrderItems (OrderID, ListingID, SellerBusinessID, SellerName,
                ProductTitle, ProductType, Quantity, UnitPrice, LineTotal, PlatformFee, SellerPayout,
                Notes, SellerStatus)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, [order_id, item["ListingID"], item["SellerBusinessID"], item["SellerName"],
              item["Title"], item["ProductType"], item["Quantity"], item["UnitPrice"],
              line_total, item_fee, seller_payout, item.get("Notes")])

        # Reduce available quantity
        cursor.execute("""
            UPDATE MarketplaceListings SET QuantityAvailable = QuantityAvailable - ? WHERE ListingID = ?
        """, [item["Quantity"], item["ListingID"]])

    # Record status history
    cursor.execute("""
        INSERT INTO OrderStatusHistory (OrderID, NewStatus, ChangedByPeopleID, ChangedByRole, Notes)
        VALUES (?, 'pending', ?, 'buyer', 'Order placed')
    """, [order_id, data.BuyerPeopleID])

    # Record platform fee
    cursor.execute("""
        INSERT INTO PlatformFees (OrderID, FeeAmount, FeePercent, Status)
        VALUES (?, ?, ?, 'pending')
    """, [order_id, platform_fee, PLATFORM_FEE_PERCENT])

    # Clear cart
    cursor.execute("DELETE FROM CartItems WHERE BuyerPeopleID = ?", [data.BuyerPeopleID])

    cursor.connection.commit()

    # TODO: Send emails to buyer and each seller (see email section below)
    # TODO: Create Stripe PaymentIntent with transfers

    return {
        "OrderID": order_id,
        "OrderNumber": order_number,
        "Total": total,
        "Subtotal": subtotal,
        "PlatformFee": platform_fee,
        "ItemCount": len(cart_items),
        "message": "Order placed successfully. Waiting for seller confirmation.",
    }


# ============================================================
# 5. SELLER ORDER MANAGEMENT
# ============================================================

@marketplace_router.get("/orders/seller/{business_id}")
async def get_seller_orders(business_id: int, status: str = ""):
    """Get all orders for a seller"""
    cursor = get_db_cursor()
    conditions = ["oi.SellerBusinessID = ?"]
    params = [business_id]
    if status:
        conditions.append("oi.SellerStatus = ?")
        params.append(status)

    where_clause = " AND ".join(conditions)
    cursor.execute(f"""
        SELECT oi.*, o.OrderNumber, o.BuyerName, o.BuyerEmail, o.BuyerPhone,
               o.DeliveryMethod, o.DeliveryAddress, o.RequestedDeliveryDate, o.OrderStatus
        FROM MarketplaceOrderItems oi
        JOIN MarketplaceOrders o ON oi.OrderID = o.OrderID
        WHERE {where_clause}
        ORDER BY oi.CreatedAt DESC
    """, params)
    columns = [desc[0] for desc in cursor.description]
    return {"orders": [dict(zip(columns, row)) for row in cursor.fetchall()]}


@marketplace_router.post("/orders/seller/confirm")
async def seller_confirm_order_item(data: SellerConfirmation):
    """Seller confirms or rejects an order item"""
    cursor = get_db_cursor()

    if data.Status == "confirmed":
        cursor.execute("""
            UPDATE MarketplaceOrderItems SET SellerStatus = 'confirmed', SellerConfirmedAt = GETDATE(),
                EstimatedDeliveryDate = ?
            WHERE OrderItemID = ?
        """, [data.EstimatedDeliveryDate, data.OrderItemID])
    elif data.Status == "rejected":
        cursor.execute("""
            UPDATE MarketplaceOrderItems SET SellerStatus = 'rejected', SellerRejectedAt = GETDATE(),
                RejectionReason = ?
            WHERE OrderItemID = ?
        """, [data.RejectionReason, data.OrderItemID])

        # Restore inventory
        cursor.execute("SELECT ListingID, Quantity FROM MarketplaceOrderItems WHERE OrderItemID = ?", [data.OrderItemID])
        item = cursor.fetchone()
        if item:
            cursor.execute("UPDATE MarketplaceListings SET QuantityAvailable = QuantityAvailable + ? WHERE ListingID = ?", [item[1], item[0]])

    # Check if all items are confirmed/rejected for this order
    cursor.execute("SELECT OrderID FROM MarketplaceOrderItems WHERE OrderItemID = ?", [data.OrderItemID])
    order_id = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) AS Total,
               SUM(CASE WHEN SellerStatus = 'confirmed' THEN 1 ELSE 0 END) AS Confirmed,
               SUM(CASE WHEN SellerStatus = 'rejected' THEN 1 ELSE 0 END) AS Rejected,
               SUM(CASE WHEN SellerStatus = 'pending' THEN 1 ELSE 0 END) AS Pending
        FROM MarketplaceOrderItems WHERE OrderID = ?
    """, [order_id])
    counts = cursor.fetchone()
    total, confirmed, rejected, pending = counts

    if pending == 0:
        if confirmed > 0 and rejected > 0:
            new_status = "partially_confirmed"
        elif confirmed > 0:
            new_status = "confirmed"
        else:
            new_status = "cancelled"
        cursor.execute("UPDATE MarketplaceOrders SET OrderStatus = ?, UpdatedAt = GETDATE() WHERE OrderID = ?", [new_status, order_id])

        # TODO: Trigger Stripe payment for confirmed items only
        # Recalculate total based on confirmed items
        if confirmed > 0:
            cursor.execute("""
                SELECT SUM(LineTotal) AS NewSubtotal, SUM(PlatformFee) AS NewFee
                FROM MarketplaceOrderItems WHERE OrderID = ? AND SellerStatus = 'confirmed'
            """, [order_id])
            new_totals = cursor.fetchone()
            new_subtotal = new_totals[0] or 0
            new_fee = new_totals[1] or 0
            new_total = round(new_subtotal + new_fee, 2)
            cursor.execute("""
                UPDATE MarketplaceOrders SET Subtotal = ?, PlatformFee = ?, TotalAmount = ?, PaymentStatus = 'authorized'
                WHERE OrderID = ?
            """, [new_subtotal, new_fee, new_total, order_id])

    # Record history
    cursor.execute("""
        INSERT INTO OrderStatusHistory (OrderID, OrderItemID, NewStatus, ChangedByRole, Notes)
        VALUES (?, ?, ?, 'seller', ?)
    """, [order_id, data.OrderItemID, data.Status, data.RejectionReason or f"Item {data.Status}"])

    cursor.connection.commit()

    # TODO: Send email notifications

    return {"message": f"Order item {data.Status}.", "OrderID": order_id}


@marketplace_router.post("/orders/seller/ship")
async def seller_ship_item(data: ShipmentUpdate):
    """Mark an order item as shipped"""
    cursor = get_db_cursor()
    cursor.execute("""
        UPDATE MarketplaceOrderItems SET SellerStatus = 'shipped', ShippedAt = GETDATE(),
            TrackingNumber = ?
        WHERE OrderItemID = ?
    """, [data.TrackingNumber, data.OrderItemID])

    cursor.execute("SELECT OrderID FROM MarketplaceOrderItems WHERE OrderItemID = ?", [data.OrderItemID])
    order_id = cursor.fetchone()[0]

    cursor.execute("""
        INSERT INTO OrderStatusHistory (OrderID, OrderItemID, NewStatus, ChangedByRole, Notes)
        VALUES (?, ?, 'shipped', 'seller', ?)
    """, [order_id, data.OrderItemID, f"Tracking: {data.TrackingNumber or 'N/A'}"])

    cursor.connection.commit()
    return {"message": "Item marked as shipped."}


# ============================================================
# 6. BUYER ORDER MANAGEMENT
# ============================================================

@marketplace_router.get("/orders/buyer/{people_id}")
async def get_buyer_orders(people_id: int, status: str = ""):
    """Get all orders for a buyer"""
    cursor = get_db_cursor()
    conditions = ["o.BuyerPeopleID = ?"]
    params = [people_id]
    if status:
        conditions.append("o.OrderStatus = ?")
        params.append(status)

    cursor.execute(f"""
        SELECT o.* FROM MarketplaceOrders o
        WHERE {' AND '.join(conditions)}
        ORDER BY o.CreatedAt DESC
    """, params)
    columns = [desc[0] for desc in cursor.description]
    orders = [dict(zip(columns, row)) for row in cursor.fetchall()]

    # Get items for each order
    for order in orders:
        cursor.execute("""
            SELECT oi.*, b.BusinessName AS SellerName
            FROM MarketplaceOrderItems oi
            JOIN Business b ON oi.SellerBusinessID = b.BusinessID
            WHERE oi.OrderID = ?
        """, [order["OrderID"]])
        cols2 = [desc[0] for desc in cursor.description]
        order["items"] = [dict(zip(cols2, r)) for r in cursor.fetchall()]

    return {"orders": orders}


@marketplace_router.get("/orders/{order_id}")
async def get_order_detail(order_id: int):
    """Get full order details"""
    cursor = get_db_cursor()
    cursor.execute("SELECT * FROM MarketplaceOrders WHERE OrderID = ?", [order_id])
    columns = [desc[0] for desc in cursor.description]
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Order not found")
    order = dict(zip(columns, row))

    cursor.execute("""
        SELECT oi.*, b.BusinessName
        FROM MarketplaceOrderItems oi
        JOIN Business b ON oi.SellerBusinessID = b.BusinessID
        WHERE oi.OrderID = ?
    """, [order_id])
    cols2 = [desc[0] for desc in cursor.description]
    order["items"] = [dict(zip(cols2, r)) for r in cursor.fetchall()]

    cursor.execute("SELECT * FROM OrderStatusHistory WHERE OrderID = ? ORDER BY CreatedAt DESC", [order_id])
    cols3 = [desc[0] for desc in cursor.description]
    order["history"] = [dict(zip(cols3, r)) for r in cursor.fetchall()]

    return order


@marketplace_router.post("/orders/{order_id}/deliver")
async def mark_delivered(order_id: int, order_item_id: int):
    """Buyer confirms delivery"""
    cursor = get_db_cursor()
    cursor.execute("""
        UPDATE MarketplaceOrderItems SET SellerStatus = 'delivered', DeliveredAt = GETDATE()
        WHERE OrderItemID = ? AND OrderID = ?
    """, [order_item_id, order_id])

    # Check if all items delivered
    cursor.execute("""
        SELECT COUNT(*) AS Total,
               SUM(CASE WHEN SellerStatus = 'delivered' THEN 1 ELSE 0 END) AS Delivered
        FROM MarketplaceOrderItems WHERE OrderID = ? AND SellerStatus != 'rejected'
    """, [order_id])
    counts = cursor.fetchone()
    if counts[0] > 0 and counts[0] == counts[1]:
        cursor.execute("UPDATE MarketplaceOrders SET OrderStatus = 'delivered', UpdatedAt = GETDATE() WHERE OrderID = ?", [order_id])

    cursor.connection.commit()

    # TODO: Trigger Stripe payout to seller

    return {"message": "Delivery confirmed."}


# ============================================================
# 7. STRIPE CONNECT (producer onboarding)
# ============================================================

@marketplace_router.post("/stripe/onboard/{business_id}")
async def stripe_onboard(business_id: int):
    """Create Stripe Connect account and return onboarding URL"""
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        # Create connected account
        account = stripe.Account.create(
            type="express",
            metadata={"business_id": str(business_id)},
        )

        # Save to DB
        cursor = get_db_cursor()
        cursor.execute("""
            INSERT INTO StripeAccounts (BusinessID, StripeConnectAccountID) VALUES (?, ?)
        """, [business_id, account.id])
        cursor.execute("UPDATE Business SET StripeConnectAccountID = ? WHERE BusinessID = ?", [account.id, business_id])
        cursor.connection.commit()

        # Create onboarding link
        link = stripe.AccountLink.create(
            account=account.id,
            refresh_url=f"{OFN_BASE_URL}/account?BusinessID={business_id}&stripe=retry",
            return_url=f"{OFN_BASE_URL}/account?BusinessID={business_id}&stripe=success",
            type="account_onboarding",
        )

        return {"url": link.url, "stripe_account_id": account.id}
    except Exception as e:
        raise HTTPException(500, str(e))


@marketplace_router.get("/stripe/status/{business_id}")
async def stripe_status(business_id: int):
    """Check Stripe Connect status"""
    cursor = get_db_cursor()
    cursor.execute("SELECT StripeConnectAccountID FROM StripeAccounts WHERE BusinessID = ?", [business_id])
    row = cursor.fetchone()
    if not row or not row[0]:
        return {"connected": False, "onboarding_complete": False}

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
        account = stripe.Account.retrieve(row[0])
        cursor.execute("""
            UPDATE StripeAccounts SET OnboardingComplete = ?, PayoutsEnabled = ?, ChargesEnabled = ?, UpdatedAt = GETDATE()
            WHERE BusinessID = ?
        """, [1 if account.details_submitted else 0,
              1 if account.payouts_enabled else 0,
              1 if account.charges_enabled else 0,
              business_id])
        cursor.connection.commit()
        return {
            "connected": True,
            "onboarding_complete": account.details_submitted,
            "payouts_enabled": account.payouts_enabled,
            "charges_enabled": account.charges_enabled,
            "stripe_account_id": row[0],
        }
    except Exception as e:
        return {"connected": False, "error": str(e)}
