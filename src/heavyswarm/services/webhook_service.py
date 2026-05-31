"""Webhook delivery service with Redis queue, retry logic, and event emitter integration."""

import asyncio
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import and_, desc, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from heavyswarm.core.config import get_settings
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)

# =============================================================================
# Constants
# =============================================================================

# Retry delays in seconds (exponential backoff: immediate, 5min, 25min, 2hr, 8hr)
RETRY_DELAYS = [0, 300, 1500, 7200, 28800]  # 0, 5min, 25min, 2hr, 8hr
MAX_RETRY_ATTEMPTS = 5

# Redis key prefixes
REDIS_PREFIX = "heavyswarm:webhooks"
REDIS_QUEUE_KEY = f"{REDIS_PREFIX}:queue"
REDIS_DLQ_KEY = f"{REDIS_PREFIX}:dlq"  # Dead letter queue
REDIS_RETRY_KEY = f"{REDIS_PREFIX}:retry"
REDIS_PROCESSING_KEY = f"{REDIS_PREFIX}:processing"

# Delivery statuses
DELIVERY_PENDING = "pending"
DELIVERY_DELIVERED = "delivered"
DELIVERY_FAILED = "failed"
DELIVERY_RETRYING = "retrying"
DELIVERY_DEAD_LETTER = "dead_letter"

# Webhook statuses
WEBHOOK_ACTIVE = "active"
WEBHOOK_PAUSED = "paused"
WEBHOOK_DISABLED = "disabled"

# Circuit breaker thresholds
FAILURE_THRESHOLD = 10  # Disable webhook after this many consecutive failures
FAILURE_WINDOW_MINUTES = 60  # Count failures within this window


# =============================================================================
# Webhook Service
# =============================================================================

class WebhookService:
    """Service for managing webhooks and delivering events."""
    
    def __init__(
        self,
        db_session: Optional[AsyncSession] = None,
        redis_client: Optional[Any] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        """Initialize the webhook service.
        
        Args:
            db_session: Database session for persistence
            redis_client: Redis client for queue management
            http_client: HTTP client for webhook delivery
        """
        self.db = db_session
        self.redis = redis_client
        self.http = http_client or httpx.AsyncClient(
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        self._settings = get_settings()
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._delivery_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def initialize(self) -> None:
        """Initialize the service and start background delivery processor."""
        self._running = True
        self._delivery_task = asyncio.create_task(self._delivery_processor())
        logger.info("webhook_service.initialized")
    
    async def shutdown(self) -> None:
        """Shutdown the service gracefully."""
        self._running = False
        if self._delivery_task:
            self._delivery_task.cancel()
            try:
                await self._delivery_task
            except asyncio.CancelledError:
                pass
        await self.http.aclose()
        logger.info("webhook_service.shutdown")
    
    # =====================================================================
    # Webhook CRUD Operations
    # =====================================================================
    
    async def create_webhook(
        self,
        url: str,
        events: List[str],
        secret: str,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a new webhook.
        
        Args:
            url: Webhook URL
            events: List of event types to subscribe to
            secret: Secret for HMAC signature
            metadata: Additional metadata
            
        Returns:
            Created webhook data
        """
        webhook_id = f"whk_{uuid.uuid4().hex[:24]}"
        now = datetime.now(timezone.utc)
        
        webhook_data = {
            "id": webhook_id,
            "url": url,
            "events": events,
            "secret": secret,
            "metadata": metadata,
            "status": WEBHOOK_ACTIVE,
            "created_at": now,
            "updated_at": now,
            "last_delivered_at": None,
            "delivery_count": 0,
            "failure_count": 0,
            "consecutive_failures": 0,
        }
        
        if self.db:
            from heavyswarm.services.state_manager import StateManager
            # Store in database
            await self.db.execute(
                insert("webhooks").values(**webhook_data)
            )
            await self.db.commit()
        
        # Also store in Redis for quick access
        if self.redis:
            await self.redis.hset(
                f"{REDIS_PREFIX}:webhooks",
                webhook_id,
                json.dumps(webhook_data, default=str),
            )
        
        # Format response
        return {
            "webhook_id": webhook_id,
            "url": url,
            "events": events,
            "status": WEBHOOK_ACTIVE,
            "metadata": metadata,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_delivered_at": None,
            "delivery_count": 0,
            "failure_count": 0,
        }
    
    async def get_webhook(self, webhook_id: str) -> Optional[Dict[str, Any]]:
        """Get a webhook by ID.
        
        Args:
            webhook_id: The webhook ID
            
        Returns:
            Webhook data or None if not found
        """
        # Try Redis first
        if self.redis:
            data = await self.redis.hget(f"{REDIS_PREFIX}:webhooks", webhook_id)
            if data:
                webhook = json.loads(data)
                return self._format_webhook_response(webhook)
        
        # Fall back to database
        if self.db:
            result = await self.db.execute(
                select("webhooks").where("webhooks.c.id" == webhook_id)
            )
            webhook = result.scalar_one_or_none()
            if webhook:
                return self._format_webhook_response(webhook.__dict__)
        
        return None
    
    async def update_webhook(
        self,
        webhook_id: str,
        update_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Update a webhook.
        
        Args:
            webhook_id: The webhook ID
            update_data: Fields to update
            
        Returns:
            Updated webhook data
        """
        update_data["updated_at"] = datetime.now(timezone.utc)
        
        if self.db:
            await self.db.execute(
                update("webhooks")
                .where("webhooks.c.id" == webhook_id)
                .values(**update_data)
            )
            await self.db.commit()
        
        # Update Redis cache
        if self.redis:
            cached = await self.redis.hget(f"{REDIS_PREFIX}:webhooks", webhook_id)
            if cached:
                webhook = json.loads(cached)
                webhook.update(update_data)
                await self.redis.hset(
                    f"{REDIS_PREFIX}:webhooks",
                    webhook_id,
                    json.dumps(webhook, default=str),
                )
        
        return await self.get_webhook(webhook_id)
    
    async def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook.
        
        Args:
            webhook_id: The webhook ID
            
        Returns:
            True if deleted, False if not found
        """
        if self.db:
            result = await self.db.execute(
                "webhooks".delete().where("webhooks.c.id" == webhook_id)
            )
            await self.db.commit()
            if result.rowcount == 0:
                return False
        
        # Remove from Redis
        if self.redis:
            await self.redis.hdel(f"{REDIS_PREFIX}:webhooks", webhook_id)
        
        return True
    
    async def list_webhooks(
        self,
        status: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List webhooks with optional filtering.
        
        Args:
            status: Filter by status
            event_type: Filter by event type
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            Tuple of (webhooks list, total count)
        """
        webhooks = []
        
        if self.db:
            query = select("webhooks")
            
            if status:
                query = query.where("webhooks.c.status" == status)
            
            if event_type:
                query = query.where("webhooks.c.events".contains([event_type]))
            
            # Get total count
            count_query = select("func.count()").select_from("webhooks")
            if status:
                count_query = count_query.where("webhooks.c.status" == status)
            if event_type:
                count_query = count_query.where("webhooks.c.events".contains([event_type]))
            
            total_result = await self.db.execute(count_query)
            total = total_result.scalar()
            
            # Get paginated results
            query = query.order_by(desc("webhooks.c.created_at")).limit(limit).offset(offset)
            result = await self.db.execute(query)
            
            for row in result.scalars():
                webhooks.append(self._format_webhook_response(row.__dict__))
        else:
            # Fallback to Redis
            if self.redis:
                all_webhooks = await self.redis.hgetall(f"{REDIS_PREFIX}:webhooks")
                for webhook_id, data in all_webhooks.items():
                    webhook = json.loads(data)
                    if status and webhook.get("status") != status:
                        continue
                    if event_type and event_type not in webhook.get("events", []):
                        continue
                    webhooks.append(self._format_webhook_response(webhook))
            total = len(webhooks)
        
        return webhooks, total
    
    def _format_webhook_response(self, webhook: Dict[str, Any]) -> Dict[str, Any]:
        """Format webhook data for API response."""
        return {
            "webhook_id": webhook.get("id") or webhook.get("webhook_id"),
            "url": webhook.get("url"),
            "events": webhook.get("events", []),
            "status": webhook.get("status", WEBHOOK_ACTIVE),
            "metadata": webhook.get("metadata", {}),
            "created_at": self._format_datetime(webhook.get("created_at")),
            "updated_at": self._format_datetime(webhook.get("updated_at")),
            "last_delivered_at": self._format_datetime(webhook.get("last_delivered_at")),
            "delivery_count": webhook.get("delivery_count", 0),
            "failure_count": webhook.get("failure_count", 0),
        }
    
    def _format_datetime(self, dt: Any) -> Optional[str]:
        """Format datetime for API response."""
        if dt is None:
            return None
        if isinstance(dt, str):
            return dt
        if isinstance(dt, datetime):
            return dt.isoformat()
        return str(dt)
    
    # =====================================================================
    # Event Queue Management
    # =====================================================================
    
    async def queue_event(
        self,
        webhook_id: str,
        event_type: str,
        payload: Dict[str, Any],
    ) -> str:
        """Queue an event for delivery to a webhook.
        
        Args:
            webhook_id: Target webhook ID
            event_type: Type of event
            payload: Event payload
            
        Returns:
            Delivery ID
        """
        delivery_id = f"dlv_{uuid.uuid4().hex[:24]}"
        now = datetime.now(timezone.utc)
        
        delivery_data = {
            "delivery_id": delivery_id,
            "webhook_id": webhook_id,
            "event_type": event_type,
            "payload": payload,
            "status": DELIVERY_PENDING,
            "attempt_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "next_retry_at": None,
            "delivered_at": None,
            "http_status": None,
            "error_message": None,
        }
        
        # Store delivery record
        if self.db:
            await self.db.execute(
                insert("webhook_deliveries").values(
                    id=delivery_id,
                    webhook_id=webhook_id,
                    event_type=event_type,
                    payload=payload,
                    status=DELIVERY_PENDING,
                    attempt_count=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            await self.db.commit()
        
        # Add to Redis queue
        if self.redis:
            await self.redis.lpush(
                REDIS_QUEUE_KEY,
                json.dumps(delivery_data),
            )
        
        logger.info(
            "webhook.event_queued",
            delivery_id=delivery_id,
            webhook_id=webhook_id,
            event_type=event_type,
        )
        
        return delivery_id
    
    async def queue_event_to_all(
        self,
        event_type: str,
        payload: Dict[str, Any],
    ) -> List[str]:
        """Queue an event to all webhooks subscribed to the event type.
        
        Args:
            event_type: Type of event
            payload: Event payload
            
        Returns:
            List of delivery IDs
        """
        # Get all active webhooks subscribed to this event
        webhooks, _ = await self.list_webhooks(
            status=WEBHOOK_ACTIVE,
            event_type=event_type,
            limit=1000,
        )
        
        delivery_ids = []
        for webhook in webhooks:
            delivery_id = await self.queue_event(
                webhook_id=webhook["webhook_id"],
                event_type=event_type,
                payload=payload,
            )
            delivery_ids.append(delivery_id)
        
        logger.info(
            "webhook.event_broadcast",
            event_type=event_type,
            webhook_count=len(webhooks),
            delivery_count=len(delivery_ids),
        )
        
        return delivery_ids
    
    async def get_delivery(self, delivery_id: str) -> Optional[Dict[str, Any]]:
        """Get a delivery by ID.
        
        Args:
            delivery_id: The delivery ID
            
        Returns:
            Delivery data or None
        """
        if self.db:
            result = await self.db.execute(
                select("webhook_deliveries").where("webhook_deliveries.c.id" == delivery_id)
            )
            row = result.scalar_one_or_none()
            if row:
                return self._format_delivery_response(row.__dict__)
        
        return None
    
    async def list_deliveries(
        self,
        webhook_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List delivery attempts.
        
        Args:
            webhook_id: Filter by webhook
            status: Filter by status
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            Tuple of (deliveries list, total count)
        """
        if not self.db:
            return [], 0
        
        query = select("webhook_deliveries")
        
        if webhook_id:
            query = query.where("webhook_deliveries.c.webhook_id" == webhook_id)
        if status:
            query = query.where("webhook_deliveries.c.status" == status)
        
        # Get total
        count_query = select("func.count()").select_from("webhook_deliveries")
        if webhook_id:
            count_query = count_query.where("webhook_deliveries.c.webhook_id" == webhook_id)
        if status:
            count_query = count_query.where("webhook_deliveries.c.status" == status)
        
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Get results
        query = query.order_by(desc("webhook_deliveries.c.created_at")).limit(limit).offset(offset)
        result = await self.db.execute(query)
        
        deliveries = []
        for row in result.scalars():
            deliveries.append(self._format_delivery_response(row.__dict__))
        
        return deliveries, total
    
    def _format_delivery_response(self, delivery: Dict[str, Any]) -> Dict[str, Any]:
        """Format delivery data for API response."""
        return {
            "delivery_id": delivery.get("id") or delivery.get("delivery_id"),
            "webhook_id": delivery.get("webhook_id"),
            "event_type": delivery.get("event_type"),
            "status": delivery.get("status", DELIVERY_PENDING),
            "attempt_count": delivery.get("attempt_count", 0),
            "next_retry_at": self._format_datetime(delivery.get("next_retry_at")),
            "delivered_at": self._format_datetime(delivery.get("delivered_at")),
            "http_status": delivery.get("http_status"),
            "error_message": delivery.get("error_message"),
            "created_at": self._format_datetime(delivery.get("created_at")),
        }
    
    async def retry_delivery(self, delivery_id: str) -> bool:
        """Manually retry a failed delivery.
        
        Args:
            delivery_id: The delivery ID
            
        Returns:
            True if queued for retry
        """
        delivery = await self.get_delivery(delivery_id)
        if not delivery:
            return False
        
        # Reset delivery status
        if self.db:
            await self.db.execute(
                update("webhook_deliveries")
                .where("webhook_deliveries.c.id" == delivery_id)
                .values(
                    status=DELIVERY_PENDING,
                    attempt_count=0,
                    next_retry_at=None,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await self.db.commit()
        
        # Re-queue in Redis
        if self.redis:
            delivery_data = {
                "delivery_id": delivery_id,
                "webhook_id": delivery["webhook_id"],
                "event_type": delivery["event_type"],
                "payload": {},  # Will be fetched from DB
                "status": DELIVERY_PENDING,
                "attempt_count": 0,
                "created_at": delivery["created_at"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            await self.redis.lpush(REDIS_QUEUE_KEY, json.dumps(delivery_data))
        
        return True
    
    # =====================================================================
    # Delivery Processor
    # =====================================================================
    
    async def _delivery_processor(self) -> None:
        """Background task that processes the delivery queue."""
        logger.info("webhook.delivery_processor_started")
        
        while self._running:
            try:
                if self.redis:
                    # Try to get an item from the queue (blocking with timeout)
                    result = await self.redis.brpop(REDIS_QUEUE_KEY, timeout=5)
                    if result:
                        _, delivery_json = result
                        delivery = json.loads(delivery_json)
                        await self._process_delivery(delivery)
                else:
                    # Without Redis, just sleep
                    await asyncio.sleep(5)
                
                # Process scheduled retries
                await self._process_scheduled_retries()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("webhook.delivery_processor_error", error=str(e))
                await asyncio.sleep(5)
        
        logger.info("webhook.delivery_processor_stopped")
    
    async def _process_delivery(self, delivery: Dict[str, Any]) -> None:
        """Process a single delivery.
        
        Args:
            delivery: Delivery data
        """
        delivery_id = delivery["delivery_id"]
        webhook_id = delivery["webhook_id"]
        
        # Get webhook details
        webhook = await self.get_webhook(webhook_id)
        if not webhook:
            logger.warning(
                "webhook.not_found_for_delivery",
                delivery_id=delivery_id,
                webhook_id=webhook_id,
            )
            await self._update_delivery_status(
                delivery_id,
                DELIVERY_FAILED,
                error_message="Webhook not found",
            )
            return
        
        # Check webhook status
        if webhook["status"] == WEBHOOK_DISABLED:
            logger.warning(
                "webhook.disabled_skipping_delivery",
                delivery_id=delivery_id,
                webhook_id=webhook_id,
            )
            await self._update_delivery_status(
                delivery_id,
                DELIVERY_FAILED,
                error_message="Webhook is disabled",
            )
            return
        
        if webhook["status"] == WEBHOOK_PAUSED:
            # Re-queue for later
            logger.info(
                "webhook.paused_requeueing",
                delivery_id=delivery_id,
                webhook_id=webhook_id,
            )
            await asyncio.sleep(60)  # Wait a minute before retry
            if self.redis:
                await self.redis.lpush(REDIS_QUEUE_KEY, json.dumps(delivery))
            return
        
        # Get full delivery data with payload
        full_delivery = await self.get_delivery(delivery_id)
        if not full_delivery:
            full_delivery = delivery
        
        # Attempt delivery
        attempt_count = delivery.get("attempt_count", 0) + 1
        success, http_status, error_message = await self._attempt_delivery(
            webhook=webhook,
            event_type=full_delivery.get("event_type", "unknown"),
            payload=full_delivery.get("payload", {}),
        )
        
        if success:
            # Delivery successful
            await self._update_delivery_status(
                delivery_id,
                DELIVERY_DELIVERED,
                http_status=http_status,
                attempt_count=attempt_count,
            )
            await self._record_webhook_success(webhook_id)
            
            logger.info(
                "webhook.delivery_success",
                delivery_id=delivery_id,
                webhook_id=webhook_id,
                http_status=http_status,
                attempt_count=attempt_count,
            )
        else:
            # Delivery failed - schedule retry or dead letter
            if attempt_count >= MAX_RETRY_ATTEMPTS:
                # Max retries reached - send to dead letter queue
                await self._update_delivery_status(
                    delivery_id,
                    DELIVERY_DEAD_LETTER,
                    http_status=http_status,
                    error_message=error_message,
                    attempt_count=attempt_count,
                )
                await self._send_to_dead_letter_queue(delivery, error_message)
                await self._record_webhook_failure(webhook_id)
                
                logger.warning(
                    "webhook.delivery_dead_letter",
                    delivery_id=delivery_id,
                    webhook_id=webhook_id,
                    attempt_count=attempt_count,
                    error=error_message,
                )
            else:
                # Schedule retry
                retry_delay = RETRY_DELAYS[min(attempt_count, len(RETRY_DELAYS) - 1)]
                next_retry = datetime.now(timezone.utc) + timedelta(seconds=retry_delay)
                
                await self._update_delivery_status(
                    delivery_id,
                    DELIVERY_RETRYING,
                    http_status=http_status,
                    error_message=error_message,
                    attempt_count=attempt_count,
                    next_retry_at=next_retry,
                )
                
                # Schedule for retry
                delivery["attempt_count"] = attempt_count
                delivery["next_retry_at"] = next_retry.isoformat()
                
                retry_score = int(next_retry.timestamp())
                if self.redis:
                    await self.redis.zadd(
                        REDIS_RETRY_KEY,
                        {json.dumps(delivery): retry_score},
                    )
                
                logger.info(
                    "webhook.delivery_retry_scheduled",
                    delivery_id=delivery_id,
                    webhook_id=webhook_id,
                    attempt_count=attempt_count,
                    next_retry=next_retry.isoformat(),
                )
    
    async def _attempt_delivery(
        self,
        webhook: Dict[str, Any],
        event_type: str,
        payload: Dict[str, Any],
    ) -> Tuple[bool, Optional[int], Optional[str]]:
        """Attempt to deliver a webhook.
        
        Args:
            webhook: Webhook configuration
            event_type: Event type
            payload: Event payload
            
        Returns:
            Tuple of (success, http_status, error_message)
        """
        url = webhook["url"]
        secret = webhook.get("secret", "")
        
        # Prepare payload
        timestamp = str(int(time.time()))
        payload_json = json.dumps(payload, separators=(",", ":"))
        
        # Generate signature
        signature = self._generate_signature(payload_json, secret, timestamp)
        
        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Event": event_type,
            "X-Webhook-ID": webhook["webhook_id"],
            "User-Agent": "HeavySwarm-Webhook/1.0",
        }
        
        try:
            response = await self.http.post(
                url,
                content=payload_json,
                headers=headers,
            )
            
            # Consider 2xx status codes as success
            if 200 <= response.status_code < 300:
                return True, response.status_code, None
            else:
                return False, response.status_code, f"HTTP {response.status_code}"
                
        except httpx.TimeoutException:
            return False, None, "Request timeout"
        except httpx.ConnectError as e:
            return False, None, f"Connection error: {str(e)}"
        except httpx.HTTPStatusError as e:
            return False, e.response.status_code, f"HTTP error: {e.response.status_code}"
        except Exception as e:
            return False, None, f"Delivery error: {str(e)}"
    
    def _generate_signature(
        self,
        payload: str,
        secret: str,
        timestamp: str,
    ) -> str:
        """Generate HMAC-SHA256 signature.
        
        Args:
            payload: JSON payload
            secret: Webhook secret
            timestamp: Unix timestamp
            
        Returns:
            Hex-encoded signature
        """
        signed_content = f"{timestamp}.{payload}"
        
        signature = hmac.new(
            secret.encode("utf-8"),
            signed_content.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        
        return signature
    
    async def _process_scheduled_retries(self) -> None:
        """Process deliveries scheduled for retry."""
        if not self.redis:
            return
        
        now = int(time.time())
        
        # Get deliveries that are due for retry
        deliveries = await self.redis.zrangebyscore(
            REDIS_RETRY_KEY,
            0,
            now,
        )
        
        for delivery_json in deliveries:
            # Remove from retry set
            await self.redis.zrem(REDIS_RETRY_KEY, delivery_json)
            
            # Add back to main queue
            await self.redis.lpush(REDIS_QUEUE_KEY, delivery_json)
            
            delivery = json.loads(delivery_json)
            logger.info(
                "webhook.retry_moved_to_queue",
                delivery_id=delivery.get("delivery_id"),
            )
    
    async def _update_delivery_status(
        self,
        delivery_id: str,
        status: str,
        http_status: Optional[int] = None,
        error_message: Optional[str] = None,
        attempt_count: Optional[int] = None,
        next_retry_at: Optional[datetime] = None,
    ) -> None:
        """Update delivery status in database.
        
        Args:
            delivery_id: Delivery ID
            status: New status
            http_status: HTTP response status
            error_message: Error message if failed
            attempt_count: Number of attempts
            next_retry_at: Next retry timestamp
        """
        if not self.db:
            return
        
        update_values = {
            "status": status,
            "updated_at": datetime.now(timezone.utc),
        }
        
        if http_status is not None:
            update_values["http_status"] = http_status
        if error_message is not None:
            update_values["error_message"] = error_message
        if attempt_count is not None:
            update_values["attempt_count"] = attempt_count
        if next_retry_at is not None:
            update_values["next_retry_at"] = next_retry_at
        if status == DELIVERY_DELIVERED:
            update_values["delivered_at"] = datetime.now(timezone.utc)
        
        await self.db.execute(
            update("webhook_deliveries")
            .where("webhook_deliveries.c.id" == delivery_id)
            .values(**update_values)
        )
        await self.db.commit()
    
    async def _record_webhook_success(self, webhook_id: str) -> None:
        """Record a successful delivery for a webhook.
        
        Args:
            webhook_id: Webhook ID
        """
        if not self.db:
            return
        
        await self.db.execute(
            update("webhooks")
            .where("webhooks.c.id" == webhook_id)
            .values(
                last_delivered_at=datetime.now(timezone.utc),
                delivery_count="webhooks.c.delivery_count + 1",
                consecutive_failures=0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.db.commit()
    
    async def _record_webhook_failure(self, webhook_id: str) -> None:
        """Record a failed delivery and check for circuit breaker.
        
        Args:
            webhook_id: Webhook ID
        """
        if not self.db:
            return
        
        # Increment failure count
        await self.db.execute(
            update("webhooks")
            .where("webhooks.c.id" == webhook_id)
            .values(
                failure_count="webhooks.c.failure_count + 1",
                consecutive_failures="webhooks.c.consecutive_failures + 1",
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.db.commit()
        
        # Check if we should disable the webhook
        result = await self.db.execute(
            select("webhooks.c.consecutive_failures").where("webhooks.c.id" == webhook_id)
        )
        consecutive_failures = result.scalar() or 0
        
        if consecutive_failures >= FAILURE_THRESHOLD:
            await self._disable_webhook(webhook_id, f"Too many consecutive failures ({consecutive_failures})")
    
    async def _disable_webhook(self, webhook_id: str, reason: str) -> None:
        """Disable a webhook due to failures.
        
        Args:
            webhook_id: Webhook ID
            reason: Reason for disabling
        """
        await self.update_webhook(webhook_id, {"status": WEBHOOK_DISABLED})
        
        # Notify about disabled webhook
        await self.queue_event(
            webhook_id=webhook_id,
            event_type="webhook.disabled",
            payload={
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "webhook_id": webhook_id,
            },
        )
        
        logger.warning(
            "webhook.auto_disabled",
            webhook_id=webhook_id,
            reason=reason,
        )
    
    async def _send_to_dead_letter_queue(
        self,
        delivery: Dict[str, Any],
        error_message: str,
    ) -> None:
        """Send a failed delivery to the dead letter queue.
        
        Args:
            delivery: Delivery data
            error_message: Final error message
        """
        dlq_entry = {
            "delivery_id": delivery["delivery_id"],
            "webhook_id": delivery["webhook_id"],
            "event_type": delivery.get("event_type", "unknown"),
            "payload": delivery.get("payload", {}),
            "final_error": error_message,
            "attempt_count": delivery.get("attempt_count", 0),
            "failed_at": datetime.now(timezone.utc).isoformat(),
        }
        
        if self.redis:
            await self.redis.lpush(REDIS_DLQ_KEY, json.dumps(dlq_entry))
        
        logger.warning(
            "webhook.dead_letter",
            delivery_id=delivery["delivery_id"],
            webhook_id=delivery["webhook_id"],
            error=error_message,
        )
    
    # =====================================================================
    # Event Emitter Integration
    # =====================================================================
    
    def on(self, event_type: str, handler: Callable) -> None:
        """Register an event handler.
        
        Args:
            event_type: Event type to listen for
            handler: Handler function
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    def off(self, event_type: str, handler: Callable) -> None:
        """Unregister an event handler.
        
        Args:
            event_type: Event type
            handler: Handler function to remove
        """
        if event_type in self._event_handlers:
            self._event_handlers[event_type] = [
                h for h in self._event_handlers[event_type] if h != handler
            ]
    
    async def emit(self, event_type: str, payload: Dict[str, Any]) -> None:
        """Emit an event to registered handlers and webhooks.
        
        Args:
            event_type: Event type
            payload: Event payload
        """
        # Call registered handlers
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(payload)
                else:
                    handler(payload)
            except Exception as e:
                logger.error(
                    "webhook.handler_error",
                    event_type=event_type,
                    error=str(e),
                )
        
        # Queue to webhooks
        await self.queue_event_to_all(event_type, payload)
    
    # =====================================================================
    # Dead Letter Queue Management
    # =====================================================================
    
    async def list_dead_letter(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List items in the dead letter queue.
        
        Args:
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            Tuple of (items, total)
        """
        if not self.redis:
            return [], 0
        
        # Get all items (this is a simplified implementation)
        all_items = await self.redis.lrange(REDIS_DLQ_KEY, 0, -1)
        total = len(all_items)
        
        items = []
        for item_json in all_items[offset:offset + limit]:
            items.append(json.loads(item_json))
        
        return items, total
    
    async def retry_dead_letter(self, delivery_id: str) -> bool:
        """Retry a dead letter item.
        
        Args:
            delivery_id: Delivery ID
            
        Returns:
            True if queued for retry
        """
        if not self.redis:
            return False
        
        # Find the item in DLQ
        all_items = await self.redis.lrange(REDIS_DLQ_KEY, 0, -1)
        for item_json in all_items:
            item = json.loads(item_json)
            if item.get("delivery_id") == delivery_id:
                # Remove from DLQ
                await self.redis.lrem(REDIS_DLQ_KEY, 0, item_json)
                
                # Reset and re-queue
                item["status"] = DELIVERY_PENDING
                item["attempt_count"] = 0
                item["next_retry_at"] = None
                item["error_message"] = None
                
                await self.redis.lpush(REDIS_QUEUE_KEY, json.dumps(item))
                
                logger.info(
                    "webhook.dead_letter_retry",
                    delivery_id=delivery_id,
                )
                return True
        
        return False


# =============================================================================
# Singleton Instance
# =============================================================================

_webhook_service: Optional[WebhookService] = None


def get_webhook_service() -> WebhookService:
    """Get the singleton webhook service instance.
    
    Returns:
        WebhookService instance
    """
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = WebhookService()
    return _webhook_service


def set_webhook_service(service: WebhookService) -> None:
    """Set the webhook service singleton (for testing/dependency injection).
    
    Args:
        service: WebhookService instance
    """
    global _webhook_service
    _webhook_service = service
