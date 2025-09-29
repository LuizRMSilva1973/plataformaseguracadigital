import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
import os

from .database import SessionLocal
from .models import Subscription, Tenant, Plan
from .auth import require_tenant

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_API_KEY")
webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/billing/webhook/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        # Invalid payload
        raise HTTPException(status_code=400, detail="Invalid payload") from e
    except stripe.error.SignatureVerificationError as e:
        # Invalid signature
        raise HTTPException(status_code=400, detail="Invalid signature") from e

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        # ... handle checkout session completed event ...
    elif event['type'] == 'invoice.paid':
        # ... handle invoice paid event ...
        pass
    elif event['type'] == 'invoice.payment_failed':
        # ... handle invoice payment failed event ...
        pass
    elif event['type'] == 'customer.subscription.deleted':
        # ... handle subscription deleted event ...
        pass
    elif event['type'] == 'customer.subscription.updated':
        # ... handle subscription updated event ...
        pass

    return {"status": "success"}

@router.post("/billing/create-checkout-session")
async def create_checkout_session(plan_id: int, tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    plan = db.query(Plan).filter(Plan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")

    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    'price': plan.stripe_price_id,
                    'quantity': 1,
                },
            ],
            mode='subscription',
            success_url="http://localhost:5500/billing?success=true",
            cancel_url="http://localhost:5500/billing?canceled=true",
            customer_email=tenant.users[0].email,
            client_reference_id=tenant.id,
        )
        return {"checkout_url": checkout_session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/billing/create-portal-session")
async def create_portal_session(tenant: Tenant = Depends(require_tenant), db: Session = Depends(get_db)):
    subscription = db.query(Subscription).filter(Subscription.tenant_id == tenant.id).first()
    if not subscription or not subscription.stripe_customer_id:
        raise HTTPException(status_code=404, detail="Subscription not found")

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=subscription.stripe_customer_id,
            return_url="http://localhost:5500/billing",
        )
        return {"portal_url": portal_session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
