"""API endpoints for Stripe integration."""

from fastapi import APIRouter, Depends, HTTPException, Request, status, Response
from loguru import logger
from typing import Dict, Any, Optional
from uuid import UUID
import stripe
from datetime import datetime, timezone

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.services.deps import get_stripe_service
from langflow.services.database.models.user import User
from langflow.services.database.models.billing.models import StripeEvent, Invoice, SubscriptionPlan, BillingPeriod
from sqlmodel import select


router = APIRouter(tags=["Stripe"], prefix="/stripe")


@router.post("/webhook", status_code=200)
async def stripe_webhook(request: Request, response: Response, session: DbSession):
    """Handle incoming Stripe webhook events.
    
    This endpoint receives webhook events from Stripe to keep our
    billing system in sync with Stripe payments, subscriptions, etc.
    """
    try:
        # Get Stripe service
        stripe_service = get_stripe_service()
        
        # Get the request body for verification
        payload = await request.body()
        sig_header = request.headers.get("stripe-signature")
        
        if not sig_header:
            logger.warning("No Stripe signature header in webhook request")
            response.status_code = status.HTTP_400_BAD_REQUEST
            return {"status": "error", "message": "No Stripe signature header"}
        
        # Verify webhook event
        event = await stripe_service.verify_webhook_signature(payload, sig_header)
        
        if not event:
            logger.warning("Invalid Stripe webhook signature")
            response.status_code = status.HTTP_400_BAD_REQUEST
            return {"status": "error", "message": "Invalid signature"}
        
        # Save event to database for processing and audit
        stripe_event = StripeEvent(
            stripe_event_id=event.id,
            type=event.type,
            api_version=event.api_version,
            data=event.data,
            status="received"
        )
        
        session.add(stripe_event)
        await session.commit()
        await session.refresh(stripe_event)
        
        # Process common event types immediately
        # For complex event processing, we should use a background task or job queue
        
        if event.type == "customer.subscription.created":
            await process_subscription_created(event.data.object, session)
        elif event.type == "customer.subscription.updated":
            await process_subscription_updated(event.data.object, session)
        elif event.type == "customer.subscription.deleted":
            await process_subscription_deleted(event.data.object, session)
        elif event.type == "invoice.paid":
            await process_invoice_paid(event.data.object, session)
        elif event.type == "invoice.payment_failed":
            await process_invoice_payment_failed(event.data.object, session)
        elif event.type == "checkout.session.completed":
            await process_checkout_completed(event.data.object, session)
            
        # Update event status
        stripe_event.status = "processed"
        session.add(stripe_event)
        await session.commit()
        
        return {"status": "success", "event_id": stripe_event.id}
    
    except Exception as e:
        logger.error(f"Error processing Stripe webhook: {str(e)}")
        
        # Try to save the error if we can
        try:
            if 'stripe_event' in locals():
                stripe_event.status = "failed"  # type: ignore
                stripe_event.error_message = str(e)  # type: ignore
                session.add(stripe_event)  # type: ignore
                await session.commit()
        except Exception:
            pass
            
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        return {"status": "error", "message": "Internal server error"}


@router.post("/setup-intent", status_code=200)
async def create_setup_intent(user: CurrentActiveUser, session: DbSession):
    """Create a Stripe SetupIntent for adding a payment method."""
    try:
        stripe_service = get_stripe_service()
        
        # Ensure user has a Stripe customer ID
        if not user.stripe_customer_id:
            customer_id = await stripe_service.create_customer(user)
            if customer_id:
                user.stripe_customer_id = customer_id
                session.add(user)
                await session.commit()
                await session.refresh(user)
            else:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create Stripe customer"
                )
        
        # Create a SetupIntent
        setup_intent = await stripe_service._make_request(
            stripe.SetupIntent.create,
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
        )
        
        return {
            "client_secret": setup_intent.client_secret,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Error creating SetupIntent: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating payment setup: {str(e)}"
        )


@router.get("/payment-methods", status_code=200)
async def get_payment_methods(user: CurrentActiveUser):
    """Retrieve a user's saved payment methods."""
    try:
        stripe_service = get_stripe_service()
        
        if not user.stripe_customer_id:
            return {"payment_methods": []}
        
        # Get payment methods for customer
        payment_methods = await stripe_service._make_request(
            stripe.PaymentMethod.list,
            customer=user.stripe_customer_id,
            type="card"
        )
        
        # Format response
        result = []
        for method in payment_methods.data:
            card = method.card
            result.append({
                "id": method.id,
                "brand": card.brand,
                "last4": card.last4,
                "exp_month": card.exp_month,
                "exp_year": card.exp_year,
                "is_default": user.stripe_default_payment_method_id == method.id
            })
            
        return {"payment_methods": result}
        
    except Exception as e:
        logger.error(f"Error retrieving payment methods: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving payment methods"
        )


@router.post("/sync-products", status_code=200)
async def sync_stripe_products(user: CurrentActiveUser, session: DbSession):
    """Sync Stripe products with local subscription plans based on matching names."""
    if not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can sync Stripe products"
        )
    
    try:
        stripe_service = get_stripe_service()
        
        # Get all Stripe products
        products = await stripe_service._make_request(
            stripe.Product.list,
            active=True
        )
        
        # Get all local subscription plans
        plans_query = select(SubscriptionPlan).where(SubscriptionPlan.is_active == True)
        plans = (await session.exec(plans_query)).all()
        
        # Map of plan names to plans
        plans_by_name = {plan.name.lower(): plan for plan in plans}
        
        results = {
            "success": True,
            "matched": 0,
            "skipped": 0,
            "details": []
        }
        
        # For each Stripe product, try to find matching plan
        for product in products.data:
            product_name = product.name.lower()
            
            # Get default price for this product
            prices = await stripe_service._make_request(
                stripe.Price.list,
                product=product.id,
                active=True
            )
            
            if not prices.data:
                results["details"].append({
                    "product_id": product.id,
                    "name": product.name,
                    "status": "skipped",
                    "reason": "No active prices found"
                })
                results["skipped"] += 1
                continue
            
            # Find matching plan
            matching_plan = None
            for plan_name, plan in plans_by_name.items():
                # Try exact match first
                if product_name == plan_name:
                    matching_plan = plan
                    break
                
                # Try partial match (e.g. "Lite Plan" matches "Lite")
                if product_name in plan_name or plan_name in product_name:
                    matching_plan = plan
                    break
            
            if matching_plan:
                # Update plan with Stripe IDs
                matching_plan.stripe_product_id = product.id
                matching_plan.stripe_default_price_id = prices.data[0].id
                session.add(matching_plan)
                
                results["matched"] += 1
                results["details"].append({
                    "product_id": product.id,
                    "name": product.name,
                    "plan_id": str(matching_plan.id),
                    "plan_name": matching_plan.name,
                    "price_id": prices.data[0].id,
                    "price_amount": prices.data[0].unit_amount / 100,  # Convert from cents
                    "status": "matched"
                })
            else:
                results["skipped"] += 1
                results["details"].append({
                    "product_id": product.id,
                    "name": product.name,
                    "status": "skipped",
                    "reason": "No matching plan found"
                })
        
        await session.commit()
        return results
        
    except Exception as e:
        logger.error(f"Error syncing Stripe products: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error syncing Stripe products: {str(e)}"
        )


async def process_subscription_created(subscription_data: Dict[str, Any], session: DbSession) -> None:
    """Process a subscription.created event."""
    customer_id = subscription_data.get("customer")
    if not customer_id:
        logger.error("No customer ID in subscription data")
        return
        
    # Find user with this Stripe customer ID
    user_query = select(User).where(User.stripe_customer_id == customer_id)
    result = await session.exec(user_query)
    user = result.first()
    
    if not user:
        logger.error(f"No user found with Stripe customer ID: {customer_id}")
        return
        
    # Update user's subscription info
    user.stripe_subscription_id = subscription_data.get("id")
    user.subscription_status = subscription_data.get("status", "active")
    
    # Update other subscription details based on metadata or product info
    
    session.add(user)
    await session.commit()
    print(f"Updated subscription for user {user.id}")


async def process_subscription_updated(subscription_data: Dict[str, Any], session: DbSession) -> None:
    """Process a subscription.updated event."""
    subscription_id = subscription_data.get("id")
    customer_id = subscription_data.get("customer")
    
    if not subscription_id:
        logger.error("No subscription ID in event data")
        return
        
    # Find user with this subscription ID
    user_query = select(User).where(User.stripe_subscription_id == subscription_id)
    result = await session.exec(user_query)
    user = result.first()
    
    # If not found by subscription ID, try to find by customer ID (race condition handling)
    if not user and customer_id:
        logger.warning(f"No user found with subscription ID: {subscription_id}, trying customer ID")
        user_query = select(User).where(User.stripe_customer_id == customer_id)
        result = await session.exec(user_query)
        user = result.first()
        
        if user:
            # Update the subscription ID since we found the user by customer ID
            user.stripe_subscription_id = subscription_id
            logger.info(f"Updated user {user.id} with subscription ID: {subscription_id}")
    
    if not user:
        logger.error(f"No user found with subscription ID: {subscription_id} or customer ID: {customer_id}")
        return
        
    # Get subscription details
    status = subscription_data.get("status", "active")
    items = subscription_data.get("items", {}).get("data", [])
    
    # Check for plan change by comparing price ID
    if items and len(items) > 0:
        price_id = items[0].get("price", {}).get("id")
        
        if price_id:
            # Find the plan that matches this price ID
            plan_query = select(SubscriptionPlan).where(SubscriptionPlan.stripe_default_price_id == price_id)
            result = await session.exec(plan_query)
            new_plan = result.first()
            
            # If we found a matching plan and it's different from current plan
            if new_plan and user.subscription_plan_id != new_plan.id:
                old_plan_id = user.subscription_plan_id
                
                # Update user's plan
                user.subscription_plan_id = new_plan.id
                
                # Get billing cycle manager to handle the plan change
                from langflow.services.billing.cycle_manager import get_billing_cycle_manager
                billing_cycle_manager = get_billing_cycle_manager()
                
                # Process the plan change
                await billing_cycle_manager.change_user_plan(user.id, new_plan.id)
                
                print(f"User {user.id} plan changed from {old_plan_id} to {new_plan.id}")
    
    # Update subscription status
    user.subscription_status = status
    session.add(user)
    await session.commit()
    print(f"Updated subscription status for user {user.id} to {status}")


async def process_subscription_deleted(subscription_data: Dict[str, Any], session: DbSession) -> None:
    """Process a subscription.deleted event."""
    subscription_id = subscription_data.get("id")
    if not subscription_id:
        logger.error("No subscription ID in event data")
        return
        
    # Find user with this subscription ID
    user_query = select(User).where(User.stripe_subscription_id == subscription_id)
    result = await session.exec(user_query)
    user = result.first()
    
    if not user:
        logger.error(f"No user found with subscription ID: {subscription_id}")
        return
        
    # Update user's subscription info
    user.subscription_status = "canceled"
    
    session.add(user)
    await session.commit()
    print(f"Marked subscription as canceled for user {user.id}")


async def process_invoice_paid(invoice_data: Dict[str, Any], session: DbSession) -> None:
    """Process an invoice.paid event."""
    invoice_id = invoice_data.get("id")
    customer_id = invoice_data.get("customer")
    
    if not invoice_id or not customer_id:
        logger.error("Missing invoice ID or customer ID in invoice data")
        return
    
    # Find the user with this Stripe customer ID
    user_query = select(User).where(User.stripe_customer_id == customer_id)
    result = await session.exec(user_query)
    user = result.first()
    
    if not user:
        logger.error(f"No user found with Stripe customer ID: {customer_id}")
        return
    
    # Find our internal invoice that matches this Stripe invoice
    invoice_query = select(Invoice).where(Invoice.stripe_invoice_id == invoice_id)
    result = await session.exec(invoice_query)
    invoice = result.first()
    
    if invoice:
        # Update our internal invoice record
        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)
        session.add(invoice)
        
        print(f"Marked invoice {invoice.id} as paid for user {user.id}")
    else:
        # This might be a subscription invoice not created by us
        print(f"Received payment for invoice {invoice_id} without local record")
        
        # If this is a subscription payment, we might want to update the user's subscription status
        if invoice_data.get("subscription"):
            user.subscription_status = "active"
            session.add(user)
            print(f"Updated user {user.id} subscription status to active")


async def process_invoice_payment_failed(invoice_data: Dict[str, Any], session: DbSession) -> None:
    """Process an invoice.payment_failed event."""
    invoice_id = invoice_data.get("id")
    customer_id = invoice_data.get("customer")
    
    if not invoice_id or not customer_id:
        logger.error("Missing invoice ID or customer ID in invoice data")
        return
    
    # Find the user with this Stripe customer ID
    user_query = select(User).where(User.stripe_customer_id == customer_id)
    result = await session.exec(user_query)
    user = result.first()
    
    if not user:
        logger.error(f"No user found with Stripe customer ID: {customer_id}")
        return
    
    # Find our internal invoice that matches this Stripe invoice
    invoice_query = select(Invoice).where(Invoice.stripe_invoice_id == invoice_id)
    result = await session.exec(invoice_query)
    invoice = result.first()
    
    if invoice:
        # Update our internal invoice record
        invoice.status = "failed"
        session.add(invoice)
        print(f"Marked invoice {invoice.id} as failed for user {user.id}")
    
    # Check if this is a subscription payment failure
    if invoice_data.get("subscription"):
        # Update user subscription status
        attempts = invoice_data.get("attempt_count", 0)
        
        # If this is a recurring failure, we might want to mark the subscription as past_due
        if attempts > 2:
            user.subscription_status = "past_due"
            session.add(user)
            logger.warning(f"Updated user {user.id} subscription status to past_due after {attempts} failed attempts")
            
            # You might want to notify the user here 


@router.post("/create-checkout-session", status_code=200)
async def create_checkout_session(
    request: Request,
    user: CurrentActiveUser, 
    session: DbSession,
    plan_id: UUID = None,
    success_url: str = None,
    cancel_url: str = None,
    change_plan: bool = False
):
    """Create a Stripe Checkout session for subscribing to a plan."""
    try:
        stripe_service = get_stripe_service()
        
        # Ensure Stripe service is initialized
        if not getattr(stripe_service, "_initialized", False):
            print("Stripe service not initialized - initializing now")
            await stripe_service.initialize()
            
            if not getattr(stripe_service, "_initialized", False):
                # If still not initialized, check Stripe settings
                if not stripe_service._api_key:
                    raise HTTPException(
                        status_code=503,
                        detail="Stripe is not properly configured. Please contact the administrator."
                    )
        
        if not plan_id:
            raise HTTPException(
                status_code=400,
                detail="Plan ID is required"
            )
            
        # Get the subscription plan
        plan = await session.get(SubscriptionPlan, plan_id)
        if not plan:
            raise HTTPException(
                status_code=404,
                detail=f"Subscription plan {plan_id} not found"
            )
            
        if not plan.stripe_default_price_id:
            raise HTTPException(
                status_code=400,
                detail=f"Plan {plan.name} is not configured for Stripe checkout. Please contact support."
            )
        
        # Ensure user has a Stripe customer ID
        if not user.stripe_customer_id:
            print(f"Creating Stripe customer for user {user.id}")
            customer_id = await stripe_service.create_customer(user)
            if customer_id:
                user.stripe_customer_id = customer_id
                session.add(user)
                await session.commit()
                await session.refresh(user)
            else:
                # More detailed error for customer creation failure
                logger.error(f"Failed to create Stripe customer for user {user.id} - Check Stripe logs")
                raise HTTPException(
                    status_code=500,
                    detail="Failed to create Stripe customer profile. Please verify your account information is complete."
                )
        
        # Check if this is a plan change for an existing subscriber
        if change_plan and user.stripe_subscription_id:
            try:
                # Get the current subscription to check currency
                subscription = await stripe_service._make_request(
                    stripe.Subscription.retrieve,
                    user.stripe_subscription_id
                )
                
                # Try to update the subscription instead of creating a new one
                if subscription and subscription.status != "canceled":
                    # Create checkout session for updating existing subscription
                    checkout_session = await stripe_service._make_request(
                        stripe.checkout.Session.create,
                        customer=user.stripe_customer_id,
                        payment_method_types=["card"],
                        mode="subscription",
                        subscription_data={
                            "metadata": {
                                "user_id": str(user.id),
                                "plan_id": str(plan_id)
                            }
                        },
                        # Add metadata at the top level too for the webhook handler
                        metadata={
                            "user_id": str(user.id),
                            "plan_id": str(plan_id),
                            "is_plan_change": "true"
                        },
                        line_items=[
                            {
                                "price": plan.stripe_default_price_id,
                                "quantity": 1,
                            },
                        ],
                        success_url=success_url or f"{request.base_url}billing/success?session_id={{CHECKOUT_SESSION_ID}}",
                        cancel_url=cancel_url or f"{request.base_url}billing/cancel",
                    )
                    
                    return {
                        "checkout_url": checkout_session.url,
                        "session_id": checkout_session.id,
                        "is_plan_change": True
                    }
            except stripe.error.StripeError as se:
                # If we get a currency mismatch or other Stripe error, raise it
                logger.error(f"Stripe error during plan change: {str(se)}")
                raise HTTPException(
                    status_code=400,
                    detail=f"Stripe error: {str(se)}"
                )
        
        # Create checkout session (for new subscriptions)
        checkout_session = await stripe_service._make_request(
            stripe.checkout.Session.create,
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[
                {
                    "price": plan.stripe_default_price_id,
                    "quantity": 1,
                },
            ],
            mode="subscription",
            success_url=success_url or f"{request.base_url}billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=cancel_url or f"{request.base_url}billing/cancel",
            metadata={
                "user_id": str(user.id),
                "plan_id": str(plan_id)
            }
        )
        
        return {
            "checkout_url": checkout_session.url,
            "session_id": checkout_session.id
        }
        
    except stripe.error.StripeError as e:
        logger.error(f"Stripe API error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Stripe error: {str(e)}"
        )
    except HTTPException:
        # Pass through HTTP exceptions with their status codes
        raise
    except Exception as e:
        logger.error(f"Error creating checkout session: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating checkout session: {str(e)}"
        )


async def process_checkout_completed(checkout_data: Dict[str, Any], session: DbSession) -> None:
    """Process a checkout.session.completed event."""
    # Extract metadata
    metadata = checkout_data.get("metadata", {})
    user_id = metadata.get("user_id")
    plan_id = metadata.get("plan_id")
    
    if not user_id or not plan_id:
        logger.error("Missing user_id or plan_id in checkout metadata")
        return
    
    try:
        # Find the user
        user = await session.get(User, UUID(user_id))
        if not user:
            logger.error(f"User {user_id} not found for checkout completion")
            return
            
        # Find the plan
        plan = await session.get(SubscriptionPlan, UUID(plan_id))
        if not plan:
            logger.error(f"Plan {plan_id} not found for checkout completion")
            return
            
        # Get subscription ID from checkout session
        subscription_id = checkout_data.get("subscription")
        if not subscription_id:
            logger.error(f"No subscription ID in checkout data")
            return
            
        # Store the old plan ID before updating the user
        old_plan_id = user.subscription_plan_id
            
        # Update user with subscription information
        user.stripe_subscription_id = subscription_id
        user.subscription_status = "active"
        user.subscription_plan_id = UUID(plan_id)
        user.subscription_start_date = datetime.now(timezone.utc)
        
        # If coming from trial, mark as converted
        if user.trial_end_date:
            # Ensure both datetimes are timezone-aware for comparison
            trial_end = user.trial_end_date
            if trial_end.tzinfo is None:
                # Convert naive datetime to UTC
                trial_end = trial_end.replace(tzinfo=timezone.utc)
                
            if trial_end > datetime.now(timezone.utc):
                user.trial_converted = True
            
        session.add(user)
        
        # Create billing period for the new subscription
        from langflow.services.billing.cycle_manager import get_billing_cycle_manager
        billing_manager = get_billing_cycle_manager()
        
        # Check if there's an existing active period
        active_period_query = select(BillingPeriod).where(
            BillingPeriod.user_id == UUID(user_id),
            BillingPeriod.status == "active"
        )
        active_period = (await session.exec(active_period_query)).first()
        
        if active_period:
            # End the current period
            active_period.status = "inactive"
            active_period.is_plan_change = True
            # Don't set previous_plan_id on the old period as it's not changing from anything
            session.add(active_period)
        
        # Create a new billing period
        await billing_manager.create_new_billing_period(
            session=session,
            user=user,
            plan=plan,
            previous_period=active_period if active_period else None,
            previous_plan_id=old_plan_id  # Pass the old plan ID to set on the new period
        )
        
        await session.commit()
        print(f"Successfully processed checkout completion for user {user_id}, plan {plan.name}")
            
    except Exception as e:
        logger.error(f"Error processing checkout completion: {str(e)}")
        # Don't re-raise to avoid webhook failure 


@router.post("/init-test-data", status_code=200)
async def init_stripe_test_data(
    user: CurrentActiveUser,
    session: DbSession
):
    """
    Initialize Stripe test data for the current environment.
    Creates test products and prices in Stripe for subscription plans.
    Only works in test mode.
    """
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
        
    try:
        # Get Stripe service
        stripe_service = get_stripe_service()
        
        # Check if we're in test mode
        if not stripe_service._api_key or not stripe_service._api_key.startswith("sk_test_"):
            return {
                "success": False,
                "message": "Not in test mode. This endpoint only works with test API keys."
            }
            
        # Make sure Stripe is initialized
        if not stripe_service._initialized:
            await stripe_service.initialize()
            
        # Create Stripe customer for the user if not exists
        if not user.stripe_customer_id:
            customer_id = await stripe_service.create_customer(user)
            if customer_id:
                user.stripe_customer_id = customer_id
                session.add(user)
                await session.commit()
                
        # Initialize test prices for all subscription plans
        from langflow.services.database.models.billing.models import SubscriptionPlan
        price_mapping = await SubscriptionPlan.ensure_stripe_price_ids(session)
        
        if not price_mapping:
            return {
                "success": False,
                "message": "Failed to create Stripe test prices. Check logs for details."
            }
            
        return {
            "success": True,
            "message": f"Successfully created {len(price_mapping)} Stripe test prices",
            "price_ids": price_mapping
        }
        
    except Exception as e:
        logger.error(f"Error initializing Stripe test data: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error initializing Stripe test data: {str(e)}"
        ) 