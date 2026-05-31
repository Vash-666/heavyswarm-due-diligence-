"""Tests for webhook framework."""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import AsyncClient

from heavyswarm.api.routes.webhooks import (
    generate_signature,
    generate_webhook_secret,
    verify_signature,
)
from heavyswarm.services.webhook_service import (
    DELIVERY_DEAD_LETTER,
    DELIVERY_DELIVERED,
    DELIVERY_FAILED,
    DELIVERY_PENDING,
    DELIVERY_RETRYING,
    MAX_RETRY_ATTEMPTS,
    RETRY_DELAYS,
    WEBHOOK_ACTIVE,
    WEBHOOK_DISABLED,
    WEBHOOK_PAUSED,
    WebhookService,
)


class TestWebhookSecretGeneration:
    """Tests for webhook secret generation."""
    
    def test_generate_secret_length(self):
        """Generated secret should be 64 characters (32 bytes hex)."""
        secret = generate_webhook_secret()
        assert len(secret) == 64
        assert all(c in "0123456789abcdef" for c in secret)
    
    def test_generate_secret_unique(self):
        """Generated secrets should be unique."""
        secrets = [generate_webhook_secret() for _ in range(100)]
        assert len(set(secrets)) == 100


class TestHMACSignature:
    """Tests for HMAC signature generation and verification."""
    
    def test_generate_signature_with_timestamp(self):
        """Test signature generation with timestamp."""
        payload = '{"event": "test"}'
        secret = "test_secret"
        timestamp = "1234567890"
        
        signature = generate_signature(payload, secret, timestamp)
        
        # Verify format
        assert len(signature) == 64  # SHA-256 hex
        
        # Verify it's deterministic
        signature2 = generate_signature(payload, secret, timestamp)
        assert signature == signature2
    
    def test_generate_signature_without_timestamp(self):
        """Test signature generation without timestamp."""
        payload = '{"event": "test"}'
        secret = "test_secret"
        
        signature = generate_signature(payload, secret, None)
        
        assert len(signature) == 64
    
    def test_verify_signature_valid(self):
        """Test valid signature verification."""
        payload = '{"event": "test"}'
        secret = "test_secret"
        timestamp = str(int(time.time()))
        
        signature = generate_signature(payload, secret, timestamp)
        is_valid, message, ts_valid = verify_signature(payload, signature, secret, timestamp)
        
        assert is_valid is True
        assert message == "Signature valid"
        assert ts_valid is True
    
    def test_verify_signature_invalid(self):
        """Test invalid signature detection."""
        payload = '{"event": "test"}'
        secret = "test_secret"
        
        is_valid, message, _ = verify_signature(payload, "invalid_signature", secret)
        
        assert is_valid is False
        assert "Invalid signature" in message
    
    def test_verify_signature_wrong_secret(self):
        """Test signature verification with wrong secret."""
        payload = '{"event": "test"}'
        secret = "correct_secret"
        wrong_secret = "wrong_secret"
        
        signature = generate_signature(payload, secret)
        is_valid, message, _ = verify_signature(payload, signature, wrong_secret)
        
        assert is_valid is False
        assert "Invalid signature" in message
    
    def test_verify_signature_timestamp_too_old(self):
        """Test timestamp validation - too old."""
        payload = '{"event": "test"}'
        secret = "test_secret"
        old_timestamp = str(int(time.time()) - 1000)  # 1000 seconds ago
        
        signature = generate_signature(payload, secret, old_timestamp)
        is_valid, message, ts_valid = verify_signature(
            payload, signature, secret, old_timestamp, max_age_seconds=300
        )
        
        assert is_valid is False
        assert "too old" in message
        assert ts_valid is False
    
    def test_verify_signature_timestamp_future(self):
        """Test timestamp validation - future timestamp."""
        payload = '{"event": "test"}'
        secret = "test_secret"
        future_timestamp = str(int(time.time()) + 1000)  # 1000 seconds in future
        
        signature = generate_signature(payload, secret, future_timestamp)
        is_valid, message, ts_valid = verify_signature(
            payload, signature, secret, future_timestamp, max_age_seconds=300
        )
        
        assert is_valid is False
        assert "too old" in message  # Future timestamps are also rejected


class TestWebhookService:
    """Tests for WebhookService."""
    
    @pytest.fixture
    async def service(self):
        """Create a webhook service for testing."""
        mock_db = AsyncMock()
        mock_redis = AsyncMock()
        
        service = WebhookService(db_session=mock_db, redis_client=mock_redis)
        return service
    
    @pytest.mark.asyncio
    async def test_create_webhook(self, service):
        """Test webhook creation."""
        webhook = await service.create_webhook(
            url="https://example.com/webhook",
            events=["diligence.completed"],
            secret="test_secret",
            metadata={"team": "engineering"},
        )
        
        assert webhook["url"] == "https://example.com/webhook"
        assert webhook["events"] == ["diligence.completed"]
        assert webhook["status"] == WEBHOOK_ACTIVE
        assert webhook["metadata"] == {"team": "engineering"}
        assert webhook["webhook_id"].startswith("whk_")
        assert "created_at" in webhook
    
    @pytest.mark.asyncio
    async def test_generate_signature_format(self, service):
        """Test signature generation format."""
        signature = service._generate_signature(
            payload='{"test": true}',
            secret="test_secret",
            timestamp="1234567890",
        )
        
        assert len(signature) == 64
        assert all(c in "0123456789abcdef" for c in signature)
    
    @pytest.mark.asyncio
    async def test_retry_delays_configuration(self):
        """Test retry delays are correctly configured."""
        # immediate, 5min, 25min, 2hr, 8hr
        expected_delays = [0, 300, 1500, 7200, 28800]
        assert RETRY_DELAYS == expected_delays
    
    @pytest.mark.asyncio
    async def test_max_retry_attempts(self):
        """Test max retry attempts constant."""
        assert MAX_RETRY_ATTEMPTS == 5
    
    def test_webhook_status_constants(self):
        """Test webhook status constants."""
        assert WEBHOOK_ACTIVE == "active"
        assert WEBHOOK_PAUSED == "paused"
        assert WEBHOOK_DISABLED == "disabled"
    
    def test_delivery_status_constants(self):
        """Test delivery status constants."""
        assert DELIVERY_PENDING == "pending"
        assert DELIVERY_DELIVERED == "delivered"
        assert DELIVERY_FAILED == "failed"
        assert DELIVERY_RETRYING == "retrying"
        assert DELIVERY_DEAD_LETTER == "dead_letter"


class TestWebhookAPI:
    """Tests for webhook API endpoints."""
    
    @pytest.mark.asyncio
    async def test_create_webhook_validation(self):
        """Test webhook creation with invalid events fails."""
        from heavyswarm.api.routes.webhooks import CreateWebhookRequest
        
        with pytest.raises(ValueError) as exc_info:
            CreateWebhookRequest(
                url="https://example.com/webhook",
                events=["invalid.event"],
            )
        
        assert "Invalid event types" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_webhook_valid_events(self):
        """Test webhook creation with valid events succeeds."""
        from heavyswarm.api.routes.webhooks import CreateWebhookRequest
        
        request = CreateWebhookRequest(
            url="https://example.com/webhook",
            events=["diligence.completed", "diligence.failed"],
        )
        
        assert request.events == ["diligence.completed", "diligence.failed"]
    
    @pytest.mark.asyncio
    async def test_update_webhook_status_validation(self):
        """Test webhook status validation."""
        from heavyswarm.api.routes.webhooks import UpdateWebhookRequest
        
        with pytest.raises(ValueError) as exc_info:
            UpdateWebhookRequest(status="invalid_status")
        
        assert "Invalid status" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_update_webhook_valid_status(self):
        """Test valid webhook status."""
        from heavyswarm.api.routes.webhooks import UpdateWebhookRequest
        
        for status in ["active", "paused", "disabled"]:
            request = UpdateWebhookRequest(status=status)
            assert request.status == status


class TestWebhookDelivery:
    """Tests for webhook delivery logic."""
    
    @pytest.mark.asyncio
    async def test_attempt_delivery_success(self):
        """Test successful delivery."""
        service = WebhookService()
        
        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        service.http.post = AsyncMock(return_value=mock_response)
        
        webhook = {
            "webhook_id": "whk_test",
            "url": "https://example.com/webhook",
            "secret": "test_secret",
        }
        
        success, status, error = await service._attempt_delivery(
            webhook=webhook,
            event_type="diligence.completed",
            payload={"test": True},
        )
        
        assert success is True
        assert status == 200
        assert error is None
    
    @pytest.mark.asyncio
    async def test_attempt_delivery_failure(self):
        """Test failed delivery."""
        service = WebhookService()
        
        # Mock failed HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 500
        service.http.post = AsyncMock(return_value=mock_response)
        
        webhook = {
            "webhook_id": "whk_test",
            "url": "https://example.com/webhook",
            "secret": "test_secret",
        }
        
        success, status, error = await service._attempt_delivery(
            webhook=webhook,
            event_type="diligence.completed",
            payload={"test": True},
        )
        
        assert success is False
        assert status == 500
        assert "HTTP 500" in error
    
    @pytest.mark.asyncio
    async def test_attempt_delivery_timeout(self):
        """Test delivery timeout handling."""
        import httpx
        
        service = WebhookService()
        service.http.post = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))
        
        webhook = {
            "webhook_id": "whk_test",
            "url": "https://example.com/webhook",
            "secret": "test_secret",
        }
        
        success, status, error = await service._attempt_delivery(
            webhook=webhook,
            event_type="diligence.completed",
            payload={"test": True},
        )
        
        assert success is False
        assert status is None
        assert "timeout" in error.lower()


class TestEventEmitter:
    """Tests for event emitter functionality."""
    
    @pytest.mark.asyncio
    async def test_event_handler_registration(self):
        """Test event handler registration."""
        service = WebhookService()
        
        handler_called = False
        
        def handler(payload):
            nonlocal handler_called
            handler_called = True
        
        service.on("test.event", handler)
        
        assert "test.event" in service._event_handlers
        assert handler in service._event_handlers["test.event"]
    
    @pytest.mark.asyncio
    async def test_event_handler_unregistration(self):
        """Test event handler unregistration."""
        service = WebhookService()
        
        def handler(payload):
            pass
        
        service.on("test.event", handler)
        service.off("test.event", handler)
        
        assert handler not in service._event_handlers.get("test.event", [])
    
    @pytest.mark.asyncio
    async def test_emit_calls_handlers(self):
        """Test that emit calls registered handlers."""
        service = WebhookService()
        
        handler_called = False
        received_payload = None
        
        def handler(payload):
            nonlocal handler_called, received_payload
            handler_called = True
            received_payload = payload
        
        service.on("test.event", handler)
        
        test_payload = {"message": "hello"}
        await service.emit("test.event", test_payload)
        
        assert handler_called is True
        assert received_payload == test_payload


class TestCircuitBreaker:
    """Tests for webhook circuit breaker functionality."""
    
    @pytest.mark.asyncio
    async def test_failure_threshold_constant(self):
        """Test failure threshold configuration."""
        from heavyswarm.services.webhook_service import FAILURE_THRESHOLD
        assert FAILURE_THRESHOLD == 10
