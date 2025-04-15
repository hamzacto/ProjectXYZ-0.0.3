"""Stripe API client service for handling all interactions with Stripe."""

import asyncio
from typing import Dict, List, Optional, Any, Union, Tuple
from uuid import UUID
import stripe
from loguru import logger
from datetime import datetime, timezone

from langflow.services.base import Service
from langflow.services.deps import get_settings_service
from langflow.services.database.models.user import User
from langflow.services.database.models.billing.models import (
    SubscriptionPlan,
    BillingPeriod,
    Invoice,
    StripeEvent
)


class StripeService(Service):
    """Service for handling all Stripe API interactions."""
    name = "stripe_service"
    
    def __init__(self):
        """Initialize the Stripe API client."""
        super().__init__()
        self._api_key = None
        self._webhook_secret = None
        self._initialized = False
        self._retry_delay = 1  # Initial retry delay in seconds
        self._max_retries = 3  # Maximum number of retries
        self._logger = logger.bind(service="stripe")
    
    def _print(self, message: str) -> None:
        """Print a message to the console and log it at info level."""
        print(message)
        self._logger.info(message)
    
    async def initialize(self) -> None:
        """Initialize the Stripe API client with config from settings."""
        if self._initialized:
            return
            
        try:
            # Get API key and webhook secret from settings
            settings_service = get_settings_service()
            
            # Check if Stripe is enabled
            if not settings_service.settings.stripe_enabled:
                self._print("Stripe integration is disabled in settings")
                return
                
            self._api_key = settings_service.settings.stripe_api_key
            self._webhook_secret = settings_service.settings.stripe_webhook_secret
            
            if not self._api_key:
                self._logger.warning("Stripe API key not configured - Stripe integration disabled")
                return
                
            # Initialize Stripe client
            stripe.api_key = self._api_key
            stripe.api_version = "2022-11-15"  # Lock API version for stability
            
            # Test connection to Stripe API - verify configuration is working
            try:
                await self._make_request(stripe.Account.retrieve)
                self._initialized = True
                self._print("Stripe API client initialized successfully")
            except stripe.error.AuthenticationError:
                self._logger.error("Invalid Stripe API key - could not authenticate")
                return
            except Exception as e:
                self._logger.error(f"Failed to connect to Stripe API: {str(e)}")
                
                # For test mode, we'll continue even with connection issues
                if self._api_key and self._api_key.startswith("sk_test_"):
                    self._logger.warning("Test environment detected: Proceeding with Stripe initialization despite connection issues")
                    self._initialized = True
                return
                
        except Exception as e:
            self._logger.error(f"Failed to initialize Stripe API client: {str(e)}")
            # Don't raise - allow application to start without Stripe if not critical
    
    async def _make_request(self, func, *args, **kwargs) -> Any:
        """
        Make a request to the Stripe API with retry logic.
        
        Args:
            func: The Stripe API function to call
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            The result of the API call
            
        Raises:
            Exception: If the request fails after all retries
        """
        if not self._initialized and not self._api_key:
            raise ValueError("Stripe service not initialized or API key not configured")
            
        retries = 0
        last_error = None
        
        while retries <= self._max_retries:
            try:
                # Stripe SDK is synchronous, so run in thread pool
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
                
            except stripe.error.RateLimitError as e:
                retries += 1
                last_error = e
                if retries <= self._max_retries:
                    # Exponential backoff with jitter
                    delay = self._retry_delay * (2 ** (retries - 1))
                    self._logger.warning(f"Rate limited by Stripe, retrying in {delay}s... (attempt {retries}/{self._max_retries})")
                    await asyncio.sleep(delay)
                    
            except stripe.error.APIConnectionError as e:
                retries += 1
                last_error = e
                if retries <= self._max_retries:
                    delay = self._retry_delay * (2 ** (retries - 1))
                    self._logger.warning(f"Connection error to Stripe API, retrying in {delay}s... (attempt {retries}/{self._max_retries})")
                    await asyncio.sleep(delay)
                
            except stripe.error.StripeError as e:
                # Other Stripe errors are not retryable
                self._logger.error(f"Stripe API error: {str(e)}")
                raise
                
            except Exception as e:
                self._logger.error(f"Unexpected error in Stripe API call: {str(e)}")
                raise
        
        # If we get here, we've exhausted our retries
        self._logger.error(f"Failed to call Stripe API after {self._max_retries} retries: {str(last_error)}")
        raise last_error

    # Customer Management
    
    async def create_customer(self, user: User) -> Optional[str]:
        """
        Create a new customer in Stripe.
        
        Args:
            user: The user to create a customer for
            
        Returns:
            The Stripe customer ID or None if creation failed
        """
        # Ensure the service is initialized
        if not self._initialized:
            self._logger.warning("Stripe service not initialized - attempting automatic initialization")
            await self.initialize()
            
        # If still not initialized after attempt, cannot proceed
        if not self._initialized:
            self._logger.error("Stripe service initialization failed - cannot create customer")
            return None
            
        try:
            if user.stripe_customer_id:
                self._logger.info(f"User {user.id} already has Stripe customer: {user.stripe_customer_id}")
                return user.stripe_customer_id
            
            # Make sure we have an email
            if not user.email:
                self._logger.error(f"Cannot create Stripe customer - user {user.id} has no email")
                return None
            
            # If OAuth user with no username, use email as name
            name = user.username if user.username else user.email.split('@')[0]
            
            # Create with retry logic
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    customer = await self._make_request(
                        stripe.Customer.create,
                        email=user.email,
                        name=name,
                        metadata={
                            "user_id": str(user.id),
                            "username": name,
                            "oauth_provider": user.oauth_provider if hasattr(user, "oauth_provider") else None
                        }
                    )
                    
                    self._logger.info(f"Created Stripe customer for user {user.id}: {customer.id}")
                    return customer.id
                except stripe.error.StripeError as se:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise
                    self._logger.warning(f"Stripe API error on attempt {retry_count}, retrying: {str(se)}")
                    await asyncio.sleep(1)
            
        except Exception as e:
            self._logger.error(f"Failed to create Stripe customer for user {user.id}: {str(e)}")
            return None
    
    async def update_customer(self, user: User) -> bool:
        """
        Update customer information in Stripe.
        
        Args:
            user: The user with updated information
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized or not user.stripe_customer_id:
            return False
            
        try:
            customer = await self._make_request(
                stripe.Customer.modify,
                user.stripe_customer_id,
                email=user.email,
                name=user.username,
                metadata={
                    "user_id": str(user.id),
                    "username": user.username
                }
            )
            
            self._print(f"Updated Stripe customer {customer.id} for user {user.id}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to update Stripe customer for user {user.id}: {str(e)}")
            return False
    
    async def delete_customer(self, user: User) -> bool:
        """
        Delete a customer from Stripe.
        
        Args:
            user: The user to delete from Stripe
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized or not user.stripe_customer_id:
            return False
            
        try:
            await self._make_request(
                stripe.Customer.delete,
                user.stripe_customer_id
            )
            
            self._print(f"Deleted Stripe customer {user.stripe_customer_id} for user {user.id}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to delete Stripe customer for user {user.id}: {str(e)}")
            return False
    
    # Payment Methods
    
    async def add_payment_method(self, user: User, payment_method_id: str) -> Optional[str]:
        """
        Add a payment method to a customer.
        
        Args:
            user: The user to add the payment method to
            payment_method_id: The Stripe payment method ID
            
        Returns:
            The payment method ID if successful, None otherwise
        """
        if not self._initialized or not user.stripe_customer_id:
            return None
            
        try:
            # Attach payment method to customer
            await self._make_request(
                stripe.PaymentMethod.attach,
                payment_method_id,
                customer=user.stripe_customer_id
            )
            
            # Set as default payment method
            await self._make_request(
                stripe.Customer.modify,
                user.stripe_customer_id,
                invoice_settings={"default_payment_method": payment_method_id}
            )
            
            self._print(f"Added payment method {payment_method_id} for user {user.id}")
            return payment_method_id
            
        except Exception as e:
            self._logger.error(f"Failed to add payment method for user {user.id}: {str(e)}")
            return None
    
    async def delete_payment_method(self, payment_method_id: str) -> bool:
        """
        Delete a payment method.
        
        Args:
            payment_method_id: The Stripe payment method ID
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            return False
            
        try:
            await self._make_request(
                stripe.PaymentMethod.detach,
                payment_method_id
            )
            
            self._print(f"Deleted payment method {payment_method_id}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to delete payment method {payment_method_id}: {str(e)}")
            return False
    
    # Subscription Management
    
    async def create_subscription(self, user: User, plan: SubscriptionPlan) -> Optional[str]:
        """
        Create a subscription for a user.
        
        Args:
            user: The user to create a subscription for
            plan: The subscription plan to use
            
        Returns:
            The Stripe subscription ID if successful, None otherwise
        """
        if not self._initialized or not user.stripe_customer_id or not plan.stripe_default_price_id:
            return None
            
        try:
            # Create the subscription
            subscription = await self._make_request(
                stripe.Subscription.create,
                customer=user.stripe_customer_id,
                items=[
                    {"price": plan.stripe_default_price_id}
                ],
                metadata={
                    "user_id": str(user.id),
                    "plan_id": str(plan.id),
                    "plan_name": plan.name
                }
            )
            
            self._print(f"Created subscription {subscription.id} for user {user.id} on plan {plan.name}")
            return subscription.id
            
        except Exception as e:
            self._logger.error(f"Failed to create subscription for user {user.id}: {str(e)}")
            return None
    
    async def update_subscription(self, user: User, plan: SubscriptionPlan) -> bool:
        """
        Update a user's subscription to a new plan.
        
        Args:
            user: The user to update the subscription for
            plan: The new subscription plan
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized or not user.stripe_subscription_id or not plan.stripe_default_price_id:
            return False
            
        try:
            # Retrieve the subscription to get the current items
            subscription = await self._make_request(
                stripe.Subscription.retrieve,
                user.stripe_subscription_id
            )
            
            # Update the subscription items
            if subscription.items.data:
                subscription_item_id = subscription.items.data[0].id
                
                updated_subscription = await self._make_request(
                    stripe.Subscription.modify,
                    user.stripe_subscription_id,
                    items=[{
                        "id": subscription_item_id,
                        "price": plan.stripe_default_price_id
                    }],
                    metadata={
                        "user_id": str(user.id),
                        "plan_id": str(plan.id),
                        "plan_name": plan.name
                    }
                )
                
                self._print(f"Updated subscription {updated_subscription.id} for user {user.id} to plan {plan.name}")
                return True
            else:
                self._logger.error(f"No subscription items found for subscription {user.stripe_subscription_id}")
                return False
                
        except Exception as e:
            self._logger.error(f"Failed to update subscription for user {user.id}: {str(e)}")
            return False
    
    async def cancel_subscription(self, user: User) -> bool:
        """
        Cancel a user's subscription.
        
        Args:
            user: The user to cancel the subscription for
            
        Returns:
            True if successful, False otherwise
        """
        if not self._initialized or not user.stripe_subscription_id:
            return False
            
        try:
            await self._make_request(
                stripe.Subscription.delete,
                user.stripe_subscription_id
            )
            
            self._print(f"Cancelled subscription {user.stripe_subscription_id} for user {user.id}")
            return True
            
        except Exception as e:
            self._logger.error(f"Failed to cancel subscription for user {user.id}: {str(e)}")
            return False
    
    # Invoice Management
    
    async def create_invoice(self, user: User, billing_period: BillingPeriod) -> Optional[str]:
        """
        Create an invoice for a billing period.
        
        Args:
            user: The user to create an invoice for
            billing_period: The billing period to create an invoice for
            
        Returns:
            The Stripe invoice ID if successful, None otherwise
        """
        if not self._initialized or not user.stripe_customer_id:
            return None
            
        try:
            # Create an invoice item for the billing period
            invoice_item = await self._make_request(
                stripe.InvoiceItem.create,
                customer=user.stripe_customer_id,
                amount=int(billing_period.overage_cost * 100),  # Convert to cents
                currency="usd",
                description=f"Overage charges for billing period {billing_period.start_date.strftime('%Y-%m-%d')} to {billing_period.end_date.strftime('%Y-%m-%d')}",
                metadata={
                    "user_id": str(user.id),
                    "billing_period_id": str(billing_period.id),
                    "overage_credits": str(billing_period.overage_credits)
                }
            )
            
            # Create the invoice
            invoice = await self._make_request(
                stripe.Invoice.create,
                customer=user.stripe_customer_id,
                auto_advance=True,  # Automatically finalize the invoice
                metadata={
                    "user_id": str(user.id),
                    "billing_period_id": str(billing_period.id)
                }
            )
            
            self._print(f"Created invoice {invoice.id} for user {user.id} with amount {billing_period.overage_cost}")
            return invoice.id
            
        except Exception as e:
            self._logger.error(f"Failed to create invoice for user {user.id}: {str(e)}")
            return None
    
    # Webhook Handling
    
    async def verify_webhook_signature(self, payload: bytes, signature: str) -> Optional[Dict]:
        """
        Verify a webhook signature and construct the event.
        
        Args:
            payload: The raw webhook payload
            signature: The Stripe signature from headers
            
        Returns:
            The verified Stripe event or None if verification fails
        """
        if not self._initialized or not self._webhook_secret:
            return None
            
        try:
            event = stripe.Webhook.construct_event(
                payload.decode('utf-8'),
                signature,
                self._webhook_secret
            )
            
            self._print(f"Verified webhook event: {event.id}, type: {event.type}")
            return event
            
        except stripe.error.SignatureVerificationError as e:
            self._logger.warning(f"Invalid webhook signature: {str(e)}")
            return None
            
        except Exception as e:
            self._logger.error(f"Error verifying webhook: {str(e)}")
            return None
    
    # Utility Methods
    
    async def get_subscription_status(self, subscription_id: str) -> Optional[str]:
        """
        Get the status of a subscription.
        
        Args:
            subscription_id: The Stripe subscription ID
            
        Returns:
            The subscription status or None if retrieval fails
        """
        if not self._initialized:
            return None
            
        try:
            subscription = await self._make_request(
                stripe.Subscription.retrieve,
                subscription_id
            )
            
            return subscription.status
            
        except Exception as e:
            self._logger.error(f"Failed to get subscription status for {subscription_id}: {str(e)}")
            return None
            
    async def teardown(self) -> None:
        """Clean up resources when shutting down."""
        self._initialized = False
        self._print("Stripe service shut down")


# Global instance for singleton access
_stripe_service = None

def get_stripe_service() -> StripeService:
    """Get the global Stripe service instance."""
    global _stripe_service
    if _stripe_service is None:
        _stripe_service = StripeService()
    return _stripe_service 