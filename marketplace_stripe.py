# marketplace_stripe.py
# Stripe Connect payment processing for the Farm2Restaurant Marketplace
# Mount: app.include_router(stripe_router, prefix="/api/marketplace/payments")

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import os
import json

stripe_router = APIRouter()

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
PLATFORM_FEE_PERCENT = 2.5
OFN_BASE_URL = os.getenv("OFN_BASE_URL", "https://oatmealfarmnetwork.com")

from database import get_db_cursor

# ============================================================
# 1. CREATE PAYMENT INTENT (after sellers confirm)
# ============================================================

@stripe_router.post("/create-intent/{order_id}")
async def create_payment_intent(order_id: int):
    """
    Creates a Stripe PaymentIntent for confirmed order items.
    Uses Stripe Connect with transfer_group for multi-seller split.
    Only charges for confirmed items (rejected items excluded).
    """
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    cursor = get_db_cursor()

    # Get order
    cursor.execute("SELECT * FROM MarketplaceOrders WHERE OrderID = ?", [order_id])
    columns = [desc[0] for desc in cursor.description]
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Order not found")
    order = dict(zip(columns, row))

    if order["PaymentStatus"] == "paid":
        raise HTTPException(400, "Order already paid")

    # Get confirmed items only
    cursor.execute("""
        SELECT oi.*, sa.StripeConnectAccountID
        FROM MarketplaceOrderItems oi
        LEFT JOIN StripeAccounts sa ON oi.SellerBusinessID = sa.BusinessID
        WHERE oi.OrderID = ? AND oi.SellerStatus = 'confirmed'
    """, [order_id])
    cols2 = [desc[0] for desc in cursor.description]
    confirmed_items = [dict(zip(cols2, r)) for r in cursor.fetchall()]

    if not confirmed_items:
        raise HTTPException(400, "No confirmed items to charge")

    # Calculate amount (only confirmed items)
    subtotal = sum(float(i["LineTotal"]) for i in confirmed_items)
    platform_fee = round(subtotal * PLATFORM_FEE_PERCENT / 100, 2)
    total_cents = int(round((subtotal + platform_fee) * 100))

    transfer_group = f"order_{order_id}"

    # Build transfer data for each seller
    transfers = []
    for item in confirmed_items:
        if item.get("StripeConnectAccountID"):
            payout_cents = int(round(float(item["SellerPayout"]) * 100))
            transfers.append({
                "seller_account": item["StripeConnectAccountID"],
                "amount": payout_cents,
                "order_item_id": item["OrderItemID"],
                "seller_business_id": item["SellerBusinessID"],
            })

    try:
        # Create PaymentIntent
        intent = stripe.PaymentIntent.create(
            amount=total_cents,
            currency="usd",
            transfer_group=transfer_group,
            metadata={
                "order_id": str(order_id),
                "order_number": order["OrderNumber"],
                "buyer_people_id": str(order["BuyerPeopleID"]),
            },
            description=f"Order {order['OrderNumber']} - Oatmeal Farm Network",
        )

        # Save to order
        cursor.execute("""
            UPDATE MarketplaceOrders
            SET StripePaymentIntentID = ?, PaymentStatus = 'authorized',
                Subtotal = ?, PlatformFee = ?, TotalAmount = ?, UpdatedAt = GETDATE()
            WHERE OrderID = ?
        """, [intent.id, subtotal, platform_fee, subtotal + platform_fee, order_id])

        cursor.connection.commit()

        return {
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id,
            "amount": total_cents,
            "transfer_group": transfer_group,
            "transfers_pending": len(transfers),
        }
    except stripe.error.StripeError as e:
        raise HTTPException(400, str(e))


# ============================================================
# 2. CONFIRM PAYMENT (after buyer pays via Stripe Elements)
# ============================================================

@stripe_router.post("/confirm-payment/{order_id}")
async def confirm_payment(order_id: int, payment_intent_id: str = ""):
    """Called after frontend confirms payment via Stripe Elements"""
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    cursor = get_db_cursor()

    cursor.execute("SELECT StripePaymentIntentID FROM MarketplaceOrders WHERE OrderID = ?", [order_id])
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Order not found")

    pi_id = payment_intent_id or row[0]
    if not pi_id:
        raise HTTPException(400, "No payment intent found")

    try:
        intent = stripe.PaymentIntent.retrieve(pi_id)

        if intent.status == "succeeded":
            # Update order
            cursor.execute("""
                UPDATE MarketplaceOrders SET PaymentStatus = 'paid', PaidAt = GETDATE(),
                    OrderStatus = 'processing', UpdatedAt = GETDATE()
                WHERE OrderID = ?
            """, [order_id])

            # Record status
            cursor.execute("""
                INSERT INTO OrderStatusHistory (OrderID, NewStatus, ChangedByRole, Notes)
                VALUES (?, 'paid', 'system', 'Payment confirmed via Stripe')
            """, [order_id])

            # Update platform fee
            cursor.execute("""
                UPDATE PlatformFees SET Status = 'collected', CollectedAt = GETDATE(),
                    StripeChargeID = ?
                WHERE OrderID = ?
            """, [pi_id, order_id])

            # Create transfers to sellers
            cursor.execute("""
                SELECT oi.OrderItemID, oi.SellerBusinessID, oi.SellerPayout, sa.StripeConnectAccountID
                FROM MarketplaceOrderItems oi
                LEFT JOIN StripeAccounts sa ON oi.SellerBusinessID = sa.BusinessID
                WHERE oi.OrderID = ? AND oi.SellerStatus = 'confirmed' AND sa.StripeConnectAccountID IS NOT NULL
            """, [order_id])
            items_to_transfer = cursor.fetchall()

            transfer_group = f"order_{order_id}"
            for item in items_to_transfer:
                item_id, seller_bid, payout, connect_id = item
                payout_cents = int(round(float(payout) * 100))
                try:
                    transfer = stripe.Transfer.create(
                        amount=payout_cents,
                        currency="usd",
                        destination=connect_id,
                        transfer_group=transfer_group,
                        metadata={"order_item_id": str(item_id), "order_id": str(order_id)},
                    )
                    cursor.execute("""
                        UPDATE MarketplaceOrderItems SET StripeTransferID = ?, TransferStatus = 'paid'
                        WHERE OrderItemID = ?
                    """, [transfer.id, item_id])
                except stripe.error.StripeError as e:
                    print(f"[stripe] Transfer failed for item {item_id}: {e}")
                    cursor.execute("""
                        UPDATE MarketplaceOrderItems SET TransferStatus = 'failed'
                        WHERE OrderItemID = ?
                    """, [item_id])

            cursor.connection.commit()
            return {"status": "paid", "message": "Payment confirmed and transfers initiated."}

        elif intent.status == "requires_action":
            return {"status": "requires_action", "client_secret": intent.client_secret}
        else:
            return {"status": intent.status, "message": f"Payment status: {intent.status}"}

    except stripe.error.StripeError as e:
        raise HTTPException(400, str(e))


# ============================================================
# 3. STRIPE WEBHOOK (for async payment events)
# ============================================================

@stripe_router.post("/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events"""
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        else:
            event = json.loads(payload)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(400, "Invalid webhook signature")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    cursor = get_db_cursor()

    if event_type == "payment_intent.succeeded":
        pi_id = data.get("id")
        order_id = data.get("metadata", {}).get("order_id")
        if order_id:
            cursor.execute("""
                UPDATE MarketplaceOrders SET PaymentStatus = 'paid', PaidAt = GETDATE(), UpdatedAt = GETDATE()
                WHERE OrderID = ? AND PaymentStatus != 'paid'
            """, [int(order_id)])
            cursor.connection.commit()

    elif event_type == "payment_intent.payment_failed":
        order_id = data.get("metadata", {}).get("order_id")
        if order_id:
            cursor.execute("""
                UPDATE MarketplaceOrders SET PaymentStatus = 'failed', UpdatedAt = GETDATE()
                WHERE OrderID = ?
            """, [int(order_id)])
            cursor.connection.commit()

    elif event_type == "account.updated":
        # Stripe Connect account updated
        account_id = data.get("id")
        cursor.execute("""
            UPDATE StripeAccounts SET
                OnboardingComplete = ?, PayoutsEnabled = ?, ChargesEnabled = ?, UpdatedAt = GETDATE()
            WHERE StripeConnectAccountID = ?
        """, [
            1 if data.get("details_submitted") else 0,
            1 if data.get("payouts_enabled") else 0,
            1 if data.get("charges_enabled") else 0,
            account_id
        ])
        cursor.connection.commit()

    return {"received": True}


# ============================================================
# 4. REFUND
# ============================================================

@stripe_router.post("/refund/{order_item_id}")
async def refund_order_item(order_item_id: int):
    """Refund a specific order item (e.g., seller rejected after payment)"""
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

    cursor = get_db_cursor()

    cursor.execute("""
        SELECT oi.LineTotal, oi.StripeTransferID, o.StripePaymentIntentID
        FROM MarketplaceOrderItems oi
        JOIN MarketplaceOrders o ON oi.OrderID = o.OrderID
        WHERE oi.OrderItemID = ?
    """, [order_item_id])
    row = cursor.fetchone()
    if not row:
        raise HTTPException(404, "Order item not found")

    line_total, transfer_id, pi_id = row
    refund_cents = int(round(float(line_total) * 100))

    try:
        # Reverse the transfer to seller if it was made
        if transfer_id:
            stripe.Transfer.create_reversal(transfer_id, amount=refund_cents)

        # Partial refund on the PaymentIntent
        if pi_id:
            stripe.Refund.create(payment_intent=pi_id, amount=refund_cents)

        cursor.execute("""
            UPDATE MarketplaceOrderItems SET TransferStatus = 'refunded' WHERE OrderItemID = ?
        """, [order_item_id])

        cursor.execute("""
            INSERT INTO OrderStatusHistory (OrderID, OrderItemID, NewStatus, ChangedByRole, Notes)
            SELECT OrderID, ?, 'refunded', 'system', 'Item refunded via Stripe'
            FROM MarketplaceOrderItems WHERE OrderItemID = ?
        """, [order_item_id, order_item_id])

        cursor.connection.commit()
        return {"message": "Refund processed.", "amount": refund_cents / 100}

    except stripe.error.StripeError as e:
        raise HTTPException(400, str(e))
