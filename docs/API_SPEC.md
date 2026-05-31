# API Specification
## HeavySwarm Investment Due Diligence Engine v1.0.0

**Version:** 1.0.0  
**Date:** 2026-05-30  
**Base URL:** `https://api.heavyswarm.io/v1`  
**Protocol:** REST + WebSocket (for real-time updates)

---

## 1. Authentication

All API requests require authentication via Bearer token.

```http
Authorization: Bearer <jwt_token>
```

### 1.1 Token Acquisition

```http
POST /auth/token
Content-Type: application/json

{
  "client_id": "string",
  "client_secret": "string",
  "scope": "diligence:read diligence:write"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "diligence:read diligence:write"
}
```

---

## 2. Core Endpoints

### 2.1 Create Diligence

Initiate a new investment due diligence analysis.

```http
POST /diligence
Content-Type: application/json

{
  "ticker": "AAPL",
  "thesis": "Apple's AI integration in iOS 18 will drive services revenue growth",
  "time_horizon": "medium_term",
  "risk_tolerance": "moderate",
  "position_size": 0.05,
  "priority": "high",
  "deadline": "2026-06-02T23:59:59Z",
  "metadata": {
    "portfolio_id": "tech-growth-001",
    "analyst_notes": "Focus on services segment"
  }
}
```

**Response (202 Accepted):**
```json
{
  "diligence_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "estimated_completion": "2026-05-31T00:05:00Z",
  "webhook_url": "https://api.heavyswarm.io/v1/webhook/550e8400-e29b-41d4-a716-446655440000",
  "polling_url": "https://api.heavyswarm.io/v1/diligence/550e8400-e29b-41d4-a716-446655440000"
}
```

**Status Codes:**
| Code | Meaning |
|------|---------|
| 202 | Accepted - Diligence queued |
| 400 | Bad Request - Invalid input |
| 401 | Unauthorized - Invalid token |
| 429 | Rate Limited - Too many requests |

---

### 2.2 Get Diligence Status

Retrieve current status and progress of a diligence.

```http
GET /diligence/{diligence_id}
```

**Response:**
```json
{
  "diligence_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "in_progress",
  "ticker": "AAPL",
  "created_at": "2026-05-31T00:00:00Z",
  "updated_at": "2026-05-31T00:02:30Z",
  "progress": {
    "current_phase": "researcher",
    "completed_phases": ["question_generator"],
    "percent_complete": 15
  },
  "metrics": {
    "data_points_collected": 47,
    "verification_rate": 0.94,
    "current_confidence": 0.82
  },
  "estimated_completion": "2026-05-31T00:05:00Z"
}
```

**Status Values:**
- `pending` - Queued for processing
- `in_progress` - Active analysis
- `verifying` - In verification phase
- `quality_gate` - Under quality review
- `completed` - Analysis complete
- `failed` - Processing failed

---

### 2.3 Get Investment Memo

Retrieve the final investment memo (available after completion).

```http
GET /diligence/{diligence_id}/memo
Accept: application/json
# or
Accept: application/pdf
```

**JSON Response:**
```json
{
  "memo": {
    "metadata": {
      "ticker": "AAPL",
      "date": "2026-05-31T00:05:00Z",
      "version": "1.0.0",
      "confidence_score": 0.87,
      "diligence_id": "550e8400-e29b-41d4-a716-446655440000"
    },
    "executive_summary": {
      "recommendation": "buy",
      "position_size": "4-5% of portfolio",
      "time_horizon": "12-18 months",
      "key_thesis": "AI integration driving services growth with expanding margins",
      "risk_rating": "medium"
    },
    "investment_thesis": "# Investment Thesis\n\n## Core Argument...",
    "valuation_analysis": "# Valuation Analysis\n\n## DCF Model...",
    "risk_assessment": "# Risk Assessment\n\n## Market Risks...",
    "scenarios": "# Scenario Analysis\n\n## Bull Case...",
    "catalysts": [
      "iOS 18 AI features launch (Q3 2026)",
      "Services revenue acceleration",
      "China market stabilization"
    ],
    "appendices": {
      "data_sources": ["SEC EDGAR", "Bloomberg", "Company Filings"],
      "model_assumptions": ["WACC: 8.5%", "Terminal Growth: 3%"],
      "disclaimer": "This memo is for informational purposes..."
    }
  }
}
```

---

### 2.4 Get Trading Signal

Retrieve structured trading signal for system integration.

```http
GET /diligence/{diligence_id}/signal
```

**Response:**
```json
{
  "signal_id": "sig-550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-05-31T00:05:00Z",
  "ticker": "AAPL",
  "signal": {
    "action": "buy",
    "confidence": 0.87,
    "urgency": "this_week",
    "position_size": {
      "recommended_pct": 0.045,
      "max_pct": 0.06,
      "rationale": "Optimal risk-adjusted position given portfolio constraints"
    }
  },
  "price_targets": {
    "entry": 195.5,
    "stop_loss": 175.0,
    "take_profit": [220.0, 245.0, 275.0],
    "time_horizon_days": 365
  },
  "risk_metrics": {
    "var_95": 0.12,
    "max_drawdown": 0.18,
    "sharpe_ratio": 1.4,
    "risk_rating": "medium"
  },
  "audit": {
    "memo_url": "https://api.heavyswarm.io/v1/diligence/550e8400-e29b-41d4-a716-446655440000/memo",
    "confidence_score": 0.87,
    "verification_rate": 0.94,
    "agents_involved": [
      "question_generator",
      "researcher",
      "financial_analyst",
      "risk_analyst",
      "strategist",
      "verifier",
      "writer"
    ],
    "processing_time_ms": 285000
  }
}
```

---

### 2.5 Get Audit Trail

Retrieve complete audit trail for compliance and debugging.

```http
GET /diligence/{diligence_id}/audit
```

**Response:**
```json
{
  "diligence_id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2026-05-31T00:00:00Z",
  "completed_at": "2026-05-31T00:05:00Z",
  "events": [
    {
      "timestamp": "2026-05-31T00:00:00Z",
      "event_type": "diligence_created",
      "agent_id": "api",
      "details": {"ticker": "AAPL", "priority": "high"}
    },
    {
      "timestamp": "2026-05-31T00:00:01Z",
      "event_type": "phase_started",
      "agent_id": "question_generator",
      "details": {"phase": "question_generator"}
    },
    {
      "timestamp": "2026-05-31T00:00:05Z",
      "event_type": "phase_completed",
      "agent_id": "question_generator",
      "details": {
        "phase": "question_generator",
        "confidence": 0.92,
        "processing_time_ms": 4200
      }
    },
    {
      "timestamp": "2026-05-31T00:00:06Z",
      "event_type": "phase_started",
      "agent_id": "researcher",
      "details": {"phase": "researcher"}
    }
    // ... more events
  ],
  "data_provenance": [
    {
      "data_id": "revenue_2025",
      "value": 385000000000,
      "source": {
        "primary": {
          "url": "https://www.sec.gov/Archives/edgar/data/...",
          "retrieved_at": "2026-05-31T00:00:30Z"
        },
        "cross_references": [
          {
            "url": "https://finance.yahoo.com/quote/AAPL/financials",
            "verified_at": "2026-05-31T00:00:45Z"
          }
        ]
      },
      "verification": {
        "level": "L2",
        "verified_by": "verifier",
        "verified_at": "2026-05-31T00:03:00Z",
        "expires_at": "2026-06-01T00:03:00Z"
      },
      "confidence": 0.99,
      "chain_of_custody": ["researcher", "verifier"]
    }
    // ... more data points
  ],
  "phase_results": {
    "question_generator": {
      "completed_at": "2026-05-31T00:00:05Z",
      "confidence": 0.92,
      "processing_time_ms": 4200
    },
    "researcher": {
      "completed_at": "2026-05-31T00:01:30Z",
      "confidence": 0.88,
      "processing_time_ms": 85000,
      "data_points": 47
    }
    // ... more phases
  }
}
```

---

### 2.6 List Diligences

List all diligences with filtering and pagination.

```http
GET /diligence?status=completed&ticker=AAPL&limit=10&offset=0
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `status` | string | Filter by status |
| `ticker` | string | Filter by ticker |
| `priority` | string | Filter by priority |
| `from_date` | ISO8601 | Start date filter |
| `to_date` | ISO8601 | End date filter |
| `limit` | integer | Results per page (max 100) |
| `offset` | integer | Pagination offset |

**Response:**
```json
{
  "total": 156,
  "limit": 10,
  "offset": 0,
  "diligences": [
    {
      "diligence_id": "550e8400-e29b-41d4-a716-446655440000",
      "ticker": "AAPL",
      "status": "completed",
      "priority": "high",
      "created_at": "2026-05-31T00:00:00Z",
      "confidence_score": 0.87,
      "recommendation": "buy"
    }
    // ... more items
  ]
}
```

---

### 2.7 Cancel Diligence

Cancel an in-progress diligence.

```http
DELETE /diligence/{diligence_id}
```

**Response (200 OK):**
```json
{
  "diligence_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "cancelled",
  "cancelled_at": "2026-05-31T00:01:00Z"
}
```

---

## 3. Webhook Integration

### 3.1 Register Webhook

Register a webhook to receive real-time updates.

```http
POST /webhooks
Content-Type: application/json

{
  "url": "https://your-trading-system.com/webhooks/heavyswarm",
  "events": ["diligence.completed", "diligence.quality_gate"],
  "secret": "your_webhook_secret_for_signature",
  "metadata": {
    "portfolio_id": "tech-growth-001"
  }
}
```

**Response:**
```json
{
  "webhook_id": "whk-550e8400-e29b-41d4-a716-446655440000",
  "url": "https://your-trading-system.com/webhooks/heavyswarm",
  "events": ["diligence.completed", "diligence.quality_gate"],
  "status": "active",
  "created_at": "2026-05-31T00:00:00Z"
}
```

### 3.2 Webhook Payload

**Event: `diligence.completed`**
```json
{
  "event": "diligence.completed",
  "timestamp": "2026-05-31T00:05:00Z",
  "diligence_id": "550e8400-e29b-41d4-a716-446655440000",
  "ticker": "AAPL",
  "recommendation": "buy",
  "confidence": 0.87,
  "signal": {
    "action": "buy",
    "urgency": "this_week",
    "position_size": 0.045
  },
  "memo_url": "https://api.heavyswarm.io/v1/diligence/550e8400-e29b-41d4-a716-446655440000/memo",
  "signal_url": "https://api.heavyswarm.io/v1/diligence/550e8400-e29b-41d4-a716-446655440000/signal"
}
```

**Event: `diligence.quality_gate`**
```json
{
  "event": "diligence.quality_gate",
  "timestamp": "2026-05-31T00:04:00Z",
  "diligence_id": "550e8400-e29b-41d4-a716-446655440000",
  "ticker": "AAPL",
  "reason": "confidence_below_threshold",
  "confidence": 0.82,
  "threshold": 0.85,
  "status_url": "https://api.heavyswarm.io/v1/diligence/550e8400-e29b-41d4-a716-446655440000"
}
```

### 3.3 Webhook Signature Verification

Webhooks include a signature header for verification:

```http
X-Heavyswarm-Signature: sha256=<hex_signature>
```

**Verification (Python):**
```python
import hmac
import hashlib

def verify_webhook(payload: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

---

## 4. WebSocket API

For real-time updates, connect via WebSocket:

```
wss://api.heavyswarm.io/v1/stream?token=<jwt_token>
```

### 4.1 Subscribe to Diligence

```json
{
  "action": "subscribe",
  "diligence_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 4.2 Real-time Updates

```json
{
  "type": "phase_update",
  "diligence_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-05-31T00:01:30Z",
  "data": {
    "phase": "researcher",
    "status": "completed",
    "progress": 15
  }
}
```

---

## 5. Error Responses

### 5.1 Error Format

All errors follow this structure:

```json
{
  "error": {
    "code": "invalid_ticker",
    "message": "The provided ticker symbol is not valid",
    "details": {
      "ticker": "INVALID",
      "suggestion": "Did you mean: AAPL?"
    },
    "request_id": "req-550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-05-31T00:00:00Z"
  }
}
```

### 5.2 Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `invalid_ticker` | 400 | Ticker symbol not found |
| `invalid_thesis` | 400 | Thesis statement too short/vague |
| `diligence_not_found` | 404 | Diligence ID does not exist |
| `diligence_in_progress` | 409 | Cannot cancel completed diligence |
| `rate_limited` | 429 | Too many requests |
| `insufficient_confidence` | 422 | Could not reach confidence threshold |
| `service_unavailable` | 503 | Temporary service degradation |

---

## 6. Rate Limits

| Tier | Requests/Min | Concurrent Diligences |
|------|--------------|----------------------|
| Free | 10 | 1 |
| Pro | 100 | 5 |
| Enterprise | 1000 | 25 |

Rate limit headers included in all responses:

```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1622505600
```

---

## 7. SDK Examples

### 7.1 Python SDK

```python
from heavyswarm import DiligenceClient

client = DiligenceClient(api_key="your_api_key")

# Create diligence
diligence = client.diligence.create(
    ticker="AAPL",
    thesis="AI integration will drive services growth",
    time_horizon="medium_term",
    risk_tolerance="moderate",
    position_size=0.05
)

# Wait for completion
result = client.diligence.wait_for_completion(
    diligence.diligence_id,
    timeout=300
)

# Get trading signal
signal = client.diligence.get_signal(diligence.diligence_id)
print(f"Action: {signal.signal.action}")
print(f"Confidence: {signal.signal.confidence}")
```

### 7.2 JavaScript SDK

```javascript
import { DiligenceClient } from '@heavyswarm/sdk';

const client = new DiligenceClient({ apiKey: 'your_api_key' });

// Create diligence
const diligence = await client.diligence.create({
  ticker: 'AAPL',
  thesis: 'AI integration will drive services growth',
  time_horizon: 'medium_term',
  risk_tolerance: 'moderate',
  position_size: 0.05
});

// Poll for completion
const result = await client.diligence.pollUntilComplete(
  diligence.diligenceId,
  { interval: 5000, timeout: 300000 }
);

// Get trading signal
const signal = await client.diligence.getSignal(diligence.diligenceId);
console.log(`Action: ${signal.signal.action}`);
console.log(`Confidence: ${signal.signal.confidence}`);
```

---

## 8. OpenAPI Specification

Full OpenAPI 3.0 spec available at:

```
GET /openapi.json
```

---

**End of API Specification**
