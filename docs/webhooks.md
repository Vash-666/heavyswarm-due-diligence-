# HeavySwarm Webhook Framework

A production-ready webhook system with delivery guarantees, HMAC verification, and automatic retry logic.

## Features

- **Full CRUD Operations**: Create, read, update, delete, and list webhooks
- **Event Filtering**: Subscribe to specific event types
- **HMAC Signature Verification**: Cryptographically secure payload signing
- **Exponential Backoff Retry**: 5 attempts with delays: immediate, 5min, 25min, 2hr, 8hr
- **Dead Letter Queue**: Failed deliveries after max retries are preserved
- **Circuit Breaker**: Webhooks auto-disable after 10 consecutive failures
- **Delivery Tracking**: Full visibility into delivery attempts and status
- **Async Delivery**: Non-blocking event delivery using Redis queues

## API Endpoints

### Webhook Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/webhooks` | Create a new webhook |
| GET | `/webhooks` | List all webhooks |
| GET | `/webhooks/{id}` | Get webhook details |
| PATCH | `/webhooks/{id}` | Update webhook |
| DELETE | `/webhooks/{id}` | Delete webhook |
| POST | `/webhooks/{id}/test` | Send test event |
| POST | `/webhooks/{id}/pause` | Pause deliveries |
| POST | `/webhooks/{id}/resume` | Resume deliveries |
| POST | `/webhooks/{id}/rotate-secret` | Rotate webhook secret |

### Delivery Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/webhooks/{id}/deliveries` | List delivery attempts |
| GET | `/webhooks/{id}/deliveries/{delivery_id}` | Get delivery details |
| POST | `/webhooks/{id}/deliveries/{delivery_id}/retry` | Manually retry delivery |

### Utilities

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/webhooks/events` | List available event types |
| POST | `/webhooks/verify-hmac` | Verify HMAC signature |
| POST | `/webhooks/receiver/test` | Test webhook receiver |

## Event Types

- `diligence.created` - Diligence analysis started
- `diligence.completed` - Diligence analysis completed
- `diligence.failed` - Diligence analysis failed
- `diligence.quality_gate` - Diligence entered quality gate review
- `diligence.cancelled` - Diligence was cancelled
- `diligence.phase_start` - Agent phase started
- `diligence.phase_complete` - Agent phase completed
- `webhook.test` - Test event
- `webhook.disabled` - Webhook auto-disabled
- `webhook.enabled` - Webhook re-enabled

## Creating a Webhook

```bash
curl -X POST http://localhost:8000/webhooks \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-app.com/webhooks/heavyswarm",
    "events": ["diligence.completed", "diligence.failed"],
    "metadata": {
      "team": "trading",
      "environment": "production"
    }
  }'
```

Response:
```json
{
  "webhook_id": "whk_a1b2c3d4e5f6...",
  "url": "https://your-app.com/webhooks/heavyswarm",
  "events": ["diligence.completed", "diligence.failed"],
  "status": "active",
  "metadata": {
    "team": "trading",
    "environment": "production"
  },
  "created_at": "2026-05-31T12:00:00+00:00",
  "updated_at": "2026-05-31T12:00:00+00:00",
  "last_delivered_at": null,
  "delivery_count": 0,
  "failure_count": 0
}
```

**Note:** The webhook secret is auto-generated and returned only on creation or secret rotation.

## Verifying Webhook Signatures

Webhooks are signed using HMAC-SHA256. Each request includes:

- `X-Webhook-Signature` - HMAC signature
- `X-Webhook-Timestamp` - Unix timestamp
- `X-Webhook-Event` - Event type
- `X-Webhook-ID` - Webhook ID

### Python Verification Example

```python
import hmac
import hashlib
import time

def verify_webhook(payload: str, signature: str, secret: str, timestamp: str, max_age: int = 300) -> bool:
    # Check timestamp to prevent replay attacks
    now = int(time.time())
    if abs(now - int(timestamp)) > max_age:
        return False
    
    # Compute expected signature
    signed_content = f"{timestamp}.{payload}"
    expected = hmac.new(
        secret.encode('utf-8'),
        signed_content.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    # Constant-time comparison
    return hmac.compare_digest(signature, expected)
```

### Using the Verify Endpoint

```bash
curl -X POST http://localhost:8000/webhooks/verify-hmac \
  -H "Content-Type: application/json" \
  -d '{
    "payload": "{\"event\": \"test\"}",
    "signature": "abc123...",
    "secret": "your-webhook-secret",
    "timestamp": "1717152000",
    "max_age_seconds": 300
  }'
```

## Delivery Retry Schedule

| Attempt | Delay | Time (approx) |
|---------|-------|---------------|
| 1 | 0 | Immediate |
| 2 | 5 min | 5 minutes |
| 3 | 25 min | 30 minutes |
| 4 | 2 hr | 2.5 hours |
| 5 | 8 hr | 10.5 hours |

After 5 failed attempts, the delivery is moved to the dead letter queue.

## Webhook Statuses

- **active** - Deliveries are being processed normally
- **paused** - Deliveries are temporarily suspended (can be resumed)
- **disabled** - Webhook is disabled due to failures (requires manual re-enable)

## Circuit Breaker

A webhook is automatically disabled after 10 consecutive delivery failures within a 60-minute window. This prevents overwhelming failing endpoints.

## Dead Letter Queue

Failed deliveries after max retries are preserved in the dead letter queue for manual inspection and retry.

```bash
# List dead letter items (via service)
curl http://localhost:8000/webhooks/dead-letter

# Retry a dead letter item
curl -X POST http://localhost:8000/webhooks/{webhook_id}/deliveries/{delivery_id}/retry
```

## Event Emitter Integration

The webhook service integrates with the event emitter for programmatic use:

```python
from heavyswarm.services import get_webhook_service

service = get_webhook_service()

# Register event handler
service.on("diligence.completed", lambda payload: print(f"Completed: {payload}"))

# Emit event (queues to webhooks and calls handlers)
await service.emit("diligence.completed", {
    "diligence_id": "dlg_123",
    "ticker": "AAPL",
    "recommendation": "buy"
})
```

## Database Schema

### webhooks table
- `id` - Primary key
- `url` - Webhook URL
- `events` - Array of subscribed event types
- `secret` - HMAC secret
- `metadata` - JSON metadata
- `status` - active/paused/disabled
- `consecutive_failures` - Failure counter for circuit breaker
- `delivery_count` - Total successful deliveries
- `failure_count` - Total failed deliveries
- `last_delivered_at` - Last successful delivery timestamp
- `created_at`, `updated_at` - Timestamps

### webhook_deliveries table
- `id` - Primary key (delivery ID)
- `webhook_id` - Foreign key to webhooks
- `event_type` - Event type
- `payload` - JSON payload
- `status` - pending/delivered/failed/retrying/dead_letter
- `attempt_count` - Number of delivery attempts
- `next_retry_at` - Scheduled retry time
- `delivered_at` - Successful delivery time
- `http_status` - Last HTTP response code
- `error_message` - Error details
- `created_at`, `updated_at` - Timestamps

## Redis Keys

- `heavyswarm:webhooks` - Hash of webhook configurations
- `heavyswarm:webhooks:queue` - Delivery queue (list)
- `heavyswarm:webhooks:retry` - Scheduled retries (sorted set)
- `heavyswarm:webhooks:dlq` - Dead letter queue (list)
- `heavyswarm:webhooks:processing` - Currently processing (hash)

## Configuration

Environment variables:

```env
REDIS_URL=redis://localhost:6379/0
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db
```

## Testing

Run webhook tests:

```bash
pytest tests/unit/test_webhooks.py -v
```

Send a test event:

```bash
curl -X POST http://localhost:8000/webhooks/{webhook_id}/test
```
