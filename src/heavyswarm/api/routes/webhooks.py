"""Webhook management endpoints with full CRUD, HMAC verification, and delivery tracking."""

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl, field_validator

from heavyswarm.core.config import get_settings
from heavyswarm.services.webhook_service import WebhookService, get_webhook_service
from heavyswarm.utils.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

# =============================================================================
# Valid Webhook Events
# =============================================================================

VALID_WEBHOOK_EVENTS = {
    "diligence.created",
    "diligence.completed",
    "diligence.failed",
    "diligence.quality_gate",
    "diligence.cancelled",
    "diligence.phase_start",
    "diligence.phase_complete",
    "webhook.test",
    "webhook.disabled",
    "webhook.enabled",
}


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateWebhookRequest(BaseModel):
    """Request to create a webhook."""
    
    url: HttpUrl = Field(..., description="Webhook URL")
    events: List[str] = Field(
        default=["diligence.completed"],
        description="Events to subscribe to",
    )
    secret: Optional[str] = Field(
        None,
        description="Secret for webhook signature verification (auto-generated if not provided)",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata",
    )
    
    @field_validator("events")
    @classmethod
    def validate_events(cls, v: List[str]) -> List[str]:
        """Validate that all events are valid webhook events."""
        invalid_events = set(v) - VALID_WEBHOOK_EVENTS
        if invalid_events:
            raise ValueError(f"Invalid event types: {', '.join(invalid_events)}")
        return v


class UpdateWebhookRequest(BaseModel):
    """Request to update a webhook."""
    
    url: Optional[HttpUrl] = Field(None, description="Webhook URL")
    events: Optional[List[str]] = Field(None, description="Events to subscribe to")
    secret: Optional[str] = Field(None, description="Secret for webhook signature verification")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")
    status: Optional[str] = Field(None, description="Webhook status (active/paused/disabled)")
    
    @field_validator("events")
    @classmethod
    def validate_events(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Validate that all events are valid webhook events."""
        if v is None:
            return v
        invalid_events = set(v) - VALID_WEBHOOK_EVENTS
        if invalid_events:
            raise ValueError(f"Invalid event types: {', '.join(invalid_events)}")
        return v
    
    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        """Validate webhook status."""
        if v is None:
            return v
        valid_statuses = {"active", "paused", "disabled"}
        if v not in valid_statuses:
            raise ValueError(f"Invalid status: {v}. Must be one of: {', '.join(valid_statuses)}")
        return v


class WebhookResponse(BaseModel):
    """Webhook response."""
    
    webhook_id: str
    url: str
    events: List[str]
    status: str
    metadata: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: str
    last_delivered_at: Optional[str] = None
    delivery_count: int = 0
    failure_count: int = 0


class WebhookListResponse(BaseModel):
    """Webhook list response."""
    
    webhooks: List[WebhookResponse]
    total: int


class WebhookDeliveryResponse(BaseModel):
    """Webhook delivery response."""
    
    delivery_id: str
    webhook_id: str
    event_type: str
    status: str  # pending, delivered, failed, retrying
    attempt_count: int
    next_retry_at: Optional[str] = None
    delivered_at: Optional[str] = None
    http_status: Optional[int] = None
    error_message: Optional[str] = None
    created_at: str


class WebhookDeliveryListResponse(BaseModel):
    """Webhook delivery list response."""
    
    deliveries: List[WebhookDeliveryResponse]
    total: int


class WebhookTestResponse(BaseModel):
    """Webhook test response."""
    
    webhook_id: str
    test_sent: bool
    delivery_id: str
    message: str


class HMACVerifyRequest(BaseModel):
    """Request to verify HMAC signature."""
    
    payload: str = Field(..., description="The webhook payload body")
    signature: str = Field(..., description="The X-Webhook-Signature header value")
    secret: str = Field(..., description="The webhook secret")
    timestamp: Optional[str] = Field(None, description="The X-Webhook-Timestamp header value")
    max_age_seconds: int = Field(default=300, description="Maximum age of timestamp to accept (default 5 minutes)")


class HMACVerifyResponse(BaseModel):
    """HMAC verification response."""
    
    valid: bool
    message: str
    timestamp_valid: Optional[bool] = None


# =============================================================================
# HMAC Utilities
# =============================================================================

def generate_webhook_secret() -> str:
    """Generate a cryptographically secure webhook secret.
    
    Returns:
        A 64-character hexadecimal secret
    """
    return secrets.token_hex(32)


def generate_signature(payload: str, secret: str, timestamp: Optional[str] = None) -> str:
    """Generate HMAC-SHA256 signature for webhook payload.
    
    Args:
        payload: The webhook payload body
        secret: The webhook secret
        timestamp: Optional timestamp to include in signature
        
    Returns:
        Hex-encoded HMAC signature
    """
    # Create the signed content: timestamp.payload
    if timestamp:
        signed_content = f"{timestamp}.{payload}"
    else:
        signed_content = payload
    
    signature = hmac.new(
        secret.encode("utf-8"),
        signed_content.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    return signature


def verify_signature(
    payload: str,
    signature: str,
    secret: str,
    timestamp: Optional[str] = None,
    max_age_seconds: int = 300
) -> tuple[bool, str, bool]:
    """Verify HMAC-SHA256 signature for webhook payload.
    
    Args:
        payload: The webhook payload body
        signature: The provided signature (hex string)
        secret: The webhook secret
        timestamp: Optional timestamp from the request
        max_age_seconds: Maximum age of timestamp to accept
        
    Returns:
        Tuple of (is_valid, message, timestamp_valid)
    """
    # Verify timestamp if provided (prevent replay attacks)
    timestamp_valid = True
    if timestamp:
        try:
            ts = int(timestamp)
            now = int(time.time())
            age = abs(now - ts)
            if age > max_age_seconds:
                return False, f"Timestamp too old: {age}s (max: {max_age_seconds}s)", False
            timestamp_valid = True
        except ValueError:
            return False, "Invalid timestamp format", False
    
    # Compute expected signature
    expected_signature = generate_signature(payload, secret, timestamp)
    
    # Use constant-time comparison to prevent timing attacks
    is_valid = hmac.compare_digest(signature, expected_signature)
    
    if not is_valid:
        return False, "Invalid signature", timestamp_valid
    
    return True, "Signature valid", timestamp_valid


# =============================================================================
# Dependencies
# =============================================================================

async def get_webhook_or_404(
    webhook_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """Get webhook or raise 404."""
    webhook = await service.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )
    return webhook


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/webhooks",
    response_model=WebhookResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook(
    request: CreateWebhookRequest,
    background_tasks: BackgroundTasks,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """Register a new webhook for receiving diligence events.
    
    Available events:
    - `diligence.created`: Diligence analysis started
    - `diligence.completed`: Diligence analysis completed
    - `diligence.failed`: Diligence analysis failed
    - `diligence.quality_gate`: Diligence entered quality gate review
    - `diligence.cancelled`: Diligence was cancelled
    - `diligence.phase_start`: Agent phase started
    - `diligence.phase_complete`: Agent phase completed
    - `webhook.test`: Test event
    - `webhook.disabled`: Webhook was disabled due to failures
    - `webhook.enabled`: Webhook was re-enabled
    
    Args:
        request: Webhook creation request
        
    Returns:
        Created webhook information
    """
    # Generate secret if not provided
    secret = request.secret
    if not secret:
        secret = generate_webhook_secret()
    
    webhook = await service.create_webhook(
        url=str(request.url),
        events=request.events,
        secret=secret,
        metadata=request.metadata or {},
    )
    
    logger.info(
        "webhook.created",
        webhook_id=webhook["webhook_id"],
        url=str(request.url),
        events=request.events,
    )
    
    return webhook


@router.get("/webhooks", response_model=WebhookListResponse)
async def list_webhooks(
    status: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """List all registered webhooks with optional filtering.
    
    Args:
        status: Filter by webhook status (active/paused/disabled)
        event_type: Filter by event type subscription
        limit: Maximum number of results
        offset: Pagination offset
        
    Returns:
        List of registered webhooks
    """
    webhooks, total = await service.list_webhooks(
        status=status,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    
    return {"webhooks": webhooks, "total": total}


@router.get("/webhooks/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(
    webhook: Dict[str, Any] = Depends(get_webhook_or_404),
) -> Dict[str, Any]:
    """Get a specific webhook.
    
    Args:
        webhook_id: The webhook ID
        
    Returns:
        Webhook information
    """
    return webhook


@router.patch("/webhooks/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    request: UpdateWebhookRequest,
    webhook_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """Update a webhook.
    
    Args:
        webhook_id: The webhook ID to update
        request: Update request
        
    Returns:
        Updated webhook information
    """
    # Check if webhook exists
    existing = await service.get_webhook(webhook_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )
    
    # Build update data
    update_data: Dict[str, Any] = {}
    if request.url is not None:
        update_data["url"] = str(request.url)
    if request.events is not None:
        update_data["events"] = request.events
    if request.secret is not None:
        update_data["secret"] = request.secret
    if request.metadata is not None:
        update_data["metadata"] = request.metadata
    if request.status is not None:
        update_data["status"] = request.status
    
    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    
    updated = await service.update_webhook(webhook_id, update_data)
    
    logger.info(
        "webhook.updated",
        webhook_id=webhook_id,
        updated_fields=list(update_data.keys()),
    )
    
    return updated


@router.delete("/webhooks/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> None:
    """Delete a webhook.
    
    Args:
        webhook_id: The webhook ID to delete
    """
    # Check if webhook exists
    existing = await service.get_webhook(webhook_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )
    
    await service.delete_webhook(webhook_id)
    
    logger.info("webhook.deleted", webhook_id=webhook_id)


@router.post("/webhooks/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: str,
    background_tasks: BackgroundTasks,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """Send a test event to a webhook.
    
    Args:
        webhook_id: The webhook ID to test
        
    Returns:
        Test result with delivery ID
    """
    # Check if webhook exists
    webhook = await service.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )
    
    # Queue test event
    delivery_id = await service.queue_event(
        webhook_id=webhook_id,
        event_type="webhook.test",
        payload={
            "message": "This is a test event from HeavySwarm",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "webhook_id": webhook_id,
        },
    )
    
    logger.info(
        "webhook.test_sent",
        webhook_id=webhook_id,
        delivery_id=delivery_id,
    )
    
    return {
        "webhook_id": webhook_id,
        "test_sent": True,
        "delivery_id": delivery_id,
        "message": "Test event queued for delivery",
    }


@router.post("/webhooks/{webhook_id}/pause", response_model=WebhookResponse)
async def pause_webhook(
    webhook_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """Pause a webhook (temporarily stop deliveries).
    
    Args:
        webhook_id: The webhook ID to pause
        
    Returns:
        Updated webhook information
    """
    webhook = await service.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )
    
    if webhook["status"] == "disabled":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot pause a disabled webhook. Enable it first.",
        )
    
    updated = await service.update_webhook(webhook_id, {"status": "paused"})
    
    logger.info("webhook.paused", webhook_id=webhook_id)
    
    return updated


@router.post("/webhooks/{webhook_id}/resume", response_model=WebhookResponse)
async def resume_webhook(
    webhook_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """Resume a paused webhook.
    
    Args:
        webhook_id: The webhook ID to resume
        
    Returns:
        Updated webhook information
    """
    webhook = await service.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )
    
    if webhook["status"] != "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Webhook is not paused (current status: {webhook['status']})",
        )
    
    updated = await service.update_webhook(webhook_id, {"status": "active"})
    
    logger.info("webhook.resumed", webhook_id=webhook_id)
    
    return updated


@router.post("/webhooks/{webhook_id}/rotate-secret", response_model=WebhookResponse)
async def rotate_webhook_secret(
    webhook_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """Rotate the secret for a webhook.
    
    Args:
        webhook_id: The webhook ID
        
    Returns:
        Updated webhook information (includes new secret - only time it's exposed)
    """
    webhook = await service.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )
    
    new_secret = generate_webhook_secret()
    updated = await service.update_webhook(webhook_id, {"secret": new_secret})
    
    # Include the new secret in the response (only time it's exposed)
    updated["secret"] = new_secret
    
    logger.info("webhook.secret_rotated", webhook_id=webhook_id)
    
    return updated


# =============================================================================
# Delivery Management Endpoints
# =============================================================================

@router.get("/webhooks/{webhook_id}/deliveries", response_model=WebhookDeliveryListResponse)
async def list_webhook_deliveries(
    webhook_id: str,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """List delivery attempts for a webhook.
    
    Args:
        webhook_id: The webhook ID
        status: Filter by delivery status
        limit: Maximum number of results
        offset: Pagination offset
        
    Returns:
        List of delivery attempts
    """
    # Check if webhook exists
    webhook = await service.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Webhook {webhook_id} not found",
        )
    
    deliveries, total = await service.list_deliveries(
        webhook_id=webhook_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    
    return {"deliveries": deliveries, "total": total}


@router.get("/webhooks/{webhook_id}/deliveries/{delivery_id}", response_model=WebhookDeliveryResponse)
async def get_delivery(
    webhook_id: str,
    delivery_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """Get a specific delivery attempt.
    
    Args:
        webhook_id: The webhook ID
        delivery_id: The delivery ID
        
    Returns:
        Delivery information
    """
    delivery = await service.get_delivery(delivery_id)
    if not delivery or delivery["webhook_id"] != webhook_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Delivery {delivery_id} not found",
        )
    
    return delivery


@router.post("/webhooks/{webhook_id}/deliveries/{delivery_id}/retry")
async def retry_delivery(
    webhook_id: str,
    delivery_id: str,
    service: WebhookService = Depends(get_webhook_service),
) -> Dict[str, Any]:
    """Manually retry a failed delivery.
    
    Args:
        webhook_id: The webhook ID
        delivery_id: The delivery ID to retry
        
    Returns:
        Retry result
    """
    delivery = await service.get_delivery(delivery_id)
    if not delivery or delivery["webhook_id"] != webhook_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Delivery {delivery_id} not found",
        )
    
    if delivery["status"] not in ("failed", "dead_letter"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot retry delivery with status: {delivery['status']}",
        )
    
    # Reset delivery for retry
    await service.retry_delivery(delivery_id)
    
    logger.info(
        "webhook.delivery_retry_requested",
        webhook_id=webhook_id,
        delivery_id=delivery_id,
    )
    
    return {
        "delivery_id": delivery_id,
        "webhook_id": webhook_id,
        "retry_queued": True,
        "message": "Delivery queued for retry",
    }


# =============================================================================
# HMAC Verification Endpoint
# =============================================================================

@router.post("/webhooks/verify-hmac", response_model=HMACVerifyResponse)
async def verify_hmac(request: HMACVerifyRequest) -> Dict[str, Any]:
    """Verify an HMAC signature for a webhook payload.
    
    This endpoint allows clients to verify webhook signatures
    they receive from HeavySwarm.
    
    Args:
        request: Verification request with payload and signature
        
    Returns:
        Verification result
    """
    is_valid, message, timestamp_valid = verify_signature(
        payload=request.payload,
        signature=request.signature,
        secret=request.secret,
        timestamp=request.timestamp,
        max_age_seconds=request.max_age_seconds,
    )
    
    return {
        "valid": is_valid,
        "message": message,
        "timestamp_valid": timestamp_valid,
    }


# =============================================================================
# Webhook Receiver (for testing/validation)
# =============================================================================

@router.post("/webhooks/receiver/test")
async def webhook_receiver_test(
    request: Request,
    x_webhook_signature: Optional[str] = Header(None),
    x_webhook_timestamp: Optional[str] = Header(None),
    x_webhook_event: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Test endpoint that receives webhooks and validates signatures.
    
    This is useful for testing webhook delivery from HeavySwarm.
    
    Headers:
        X-Webhook-Signature: HMAC-SHA256 signature
        X-Webhook-Timestamp: Unix timestamp
        X-Webhook-Event: Event type
        
    Returns:
        Received webhook information
    """
    body = await request.body()
    payload = body.decode("utf-8")
    
    return {
        "received": True,
        "event": x_webhook_event,
        "timestamp": x_webhook_timestamp,
        "signature_present": x_webhook_signature is not None,
        "payload_length": len(payload),
        "headers": {
            "X-Webhook-Signature": x_webhook_signature,
            "X-Webhook-Timestamp": x_webhook_timestamp,
            "X-Webhook-Event": x_webhook_event,
        },
    }


# =============================================================================
# Event Type Management
# =============================================================================

@router.get("/webhooks/events")
async def list_event_types() -> Dict[str, Any]:
    """List all available webhook event types.
    
    Returns:
        List of event types with descriptions
    """
    event_descriptions = {
        "diligence.created": "Diligence analysis started",
        "diligence.completed": "Diligence analysis completed successfully",
        "diligence.failed": "Diligence analysis failed",
        "diligence.quality_gate": "Diligence entered quality gate review",
        "diligence.cancelled": "Diligence was cancelled",
        "diligence.phase_start": "An agent phase has started",
        "diligence.phase_complete": "An agent phase has completed",
        "webhook.test": "Test event for webhook validation",
        "webhook.disabled": "Webhook was automatically disabled due to failures",
        "webhook.enabled": "Webhook was re-enabled",
    }
    
    events = [
        {"type": event, "description": desc}
        for event, desc in event_descriptions.items()
    ]
    
    return {"events": events}
