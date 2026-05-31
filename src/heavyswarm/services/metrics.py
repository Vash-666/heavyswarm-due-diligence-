"""Prometheus metrics collection for HeavySwarm."""

from typing import Optional

from prometheus_client import Counter, Histogram, Gauge, Info, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily

from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)

# Create a custom registry
REGISTRY = CollectorRegistry()

# =============================================================================
# Diligence Metrics
# =============================================================================

DILIGENCE_DURATION = Histogram(
    "diligence_duration_seconds",
    "End-to-end diligence processing time",
    ["ticker", "status"],
    buckets=[30, 60, 120, 180, 240, 300, 600, 900, 1800],
    registry=REGISTRY,
)

DILIGENCE_CREATED = Counter(
    "diligence_created_total",
    "Total number of diligences created",
    ["ticker", "priority"],
    registry=REGISTRY,
)

DILIGENCE_COMPLETED = Counter(
    "diligence_completed_total",
    "Total number of diligences completed",
    ["ticker", "status", "recommendation"],
    registry=REGISTRY,
)

CONFIDENCE_SCORE = Gauge(
    "diligence_confidence_score",
    "Final confidence score of diligence",
    ["ticker", "diligence_id"],
    registry=REGISTRY,
)

# =============================================================================
# Phase Metrics
# =============================================================================

PHASE_DURATION = Histogram(
    "phase_duration_seconds",
    "Per-phase processing time",
    ["phase", "agent"],
    buckets=[5, 10, 20, 30, 45, 60, 90, 120, 180, 300],
    registry=REGISTRY,
)

PHASE_ERRORS = Counter(
    "phase_errors_total",
    "Total errors per phase",
    ["phase", "error_type"],
    registry=REGISTRY,
)

PHASE_RETRIES = Counter(
    "phase_retries_total",
    "Total retries per phase",
    ["phase"],
    registry=REGISTRY,
)

# =============================================================================
# LLM Metrics
# =============================================================================

LLM_REQUESTS = Counter(
    "llm_requests_total",
    "Total LLM requests",
    ["model", "provider"],
    registry=REGISTRY,
)

LLM_TOKENS = Counter(
    "llm_tokens_total",
    "Total tokens used",
    ["model", "token_type"],
    registry=REGISTRY,
)

LLM_COST = Counter(
    "llm_cost_usd",
    "Total LLM cost in USD",
    ["model"],
    registry=REGISTRY,
)

LLM_LATENCY = Histogram(
    "llm_latency_seconds",
    "LLM request latency",
    ["model"],
    buckets=[0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0, 60.0],
    registry=REGISTRY,
)

LLM_ERRORS = Counter(
    "llm_errors_total",
    "Total LLM errors",
    ["model", "error_type"],
    registry=REGISTRY,
)

CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["provider"],
    registry=REGISTRY,
)

# =============================================================================
# Data Source Metrics
# =============================================================================

DATA_SOURCE_REQUESTS = Counter(
    "data_source_requests_total",
    "Total data source requests",
    ["source", "endpoint"],
    registry=REGISTRY,
)

DATA_SOURCE_LATENCY = Histogram(
    "data_source_latency_seconds",
    "Data source request latency",
    ["source", "endpoint"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
    registry=REGISTRY,
)

DATA_SOURCE_ERRORS = Counter(
    "data_source_errors_total",
    "Total data source errors",
    ["source", "error_type"],
    registry=REGISTRY,
)

VERIFICATION_RATE = Gauge(
    "verification_rate",
    "Data verification rate",
    ["diligence_id"],
    registry=REGISTRY,
)

# =============================================================================
# Webhook Metrics
# =============================================================================

WEBHOOK_DELIVERIES = Counter(
    "webhook_deliveries_total",
    "Total webhook deliveries",
    ["status"],
    registry=REGISTRY,
)

WEBHOOK_LATENCY = Histogram(
    "webhook_latency_seconds",
    "Webhook delivery latency",
    ["webhook_id"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0],
    registry=REGISTRY,
)

WEBHOOK_QUEUE_SIZE = Gauge(
    "webhook_queue_size",
    "Current webhook queue size",
    registry=REGISTRY,
)

# =============================================================================
# System Metrics
# =============================================================================

ACTIVE_DILIGENCES = Gauge(
    "active_diligences",
    "Number of currently running diligences",
    registry=REGISTRY,
)

QUEUE_SIZE = Gauge(
    "diligence_queue_size",
    "Number of diligences waiting in queue",
    registry=REGISTRY,
)

CACHE_HIT_RATE = Gauge(
    "cache_hit_rate",
    "Cache hit rate percentage",
    ["cache_type"],
    registry=REGISTRY,
)

# =============================================================================
# Application Info
# =============================================================================

APP_INFO = Info(
    "heavyswarm",
    "HeavySwarm application information",
    registry=REGISTRY,
)


def set_app_info(version: str, environment: str) -> None:
    """Set application information.
    
    Args:
        version: Application version
        environment: Deployment environment
    """
    APP_INFO.info({
        "version": version,
        "environment": environment,
    })


def record_diligence_created(ticker: str, priority: str) -> None:
    """Record a new diligence creation.
    
    Args:
        ticker: Stock ticker
        priority: Diligence priority
    """
    DILIGENCE_CREATED.labels(ticker=ticker, priority=priority).inc()


def record_diligence_completed(
    ticker: str,
    status: str,
    recommendation: str,
    duration_seconds: float,
) -> None:
    """Record a completed diligence.
    
    Args:
        ticker: Stock ticker
        status: Completion status
        recommendation: Final recommendation
        duration_seconds: Processing duration
    """
    DILIGENCE_COMPLETED.labels(
        ticker=ticker,
        status=status,
        recommendation=recommendation,
    ).inc()
    DILIGENCE_DURATION.labels(ticker=ticker, status=status).observe(duration_seconds)


def record_phase_duration(phase: str, agent: str, duration_seconds: float) -> None:
    """Record phase processing time.
    
    Args:
        phase: Phase name
        agent: Agent name
        duration_seconds: Processing duration
    """
    PHASE_DURATION.labels(phase=phase, agent=agent).observe(duration_seconds)


def record_phase_error(phase: str, error_type: str) -> None:
    """Record a phase error.
    
    Args:
        phase: Phase name
        error_type: Type of error
    """
    PHASE_ERRORS.labels(phase=phase, error_type=error_type).inc()


def record_llm_request(
    model: str,
    provider: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    latency_seconds: float,
) -> None:
    """Record LLM request metrics.
    
    Args:
        model: Model name
        provider: Provider name
        prompt_tokens: Number of prompt tokens
        completion_tokens: Number of completion tokens
        cost_usd: Cost in USD
        latency_seconds: Request latency
    """
    LLM_REQUESTS.labels(model=model, provider=provider).inc()
    LLM_TOKENS.labels(model=model, token_type="prompt").inc(prompt_tokens)
    LLM_TOKENS.labels(model=model, token_type="completion").inc(completion_tokens)
    LLM_COST.labels(model=model).inc(cost_usd)
    LLM_LATENCY.labels(model=model).observe(latency_seconds)


def record_llm_error(model: str, error_type: str) -> None:
    """Record an LLM error.
    
    Args:
        model: Model name
        error_type: Type of error
    """
    LLM_ERRORS.labels(model=model, error_type=error_type).inc()


def set_circuit_breaker_state(provider: str, state: str) -> None:
    """Set circuit breaker state.
    
    Args:
        provider: Provider name
        state: Circuit state (closed, open, half_open)
    """
    state_map = {"closed": 0, "open": 1, "half_open": 2}
    CIRCUIT_BREAKER_STATE.labels(provider=provider).set(state_map.get(state, 0))


def record_data_source_request(source: str, endpoint: str, latency_seconds: float) -> None:
    """Record data source request.
    
    Args:
        source: Data source name
        endpoint: API endpoint
        latency_seconds: Request latency
    """
    DATA_SOURCE_REQUESTS.labels(source=source, endpoint=endpoint).inc()
    DATA_SOURCE_LATENCY.labels(source=source, endpoint=endpoint).observe(latency_seconds)


def record_data_source_error(source: str, error_type: str) -> None:
    """Record data source error.
    
    Args:
        source: Data source name
        error_type: Type of error
    """
    DATA_SOURCE_ERRORS.labels(source=source, error_type=error_type).inc()


def record_webhook_delivery(status: str, latency_seconds: float) -> None:
    """Record webhook delivery.
    
    Args:
        status: Delivery status
        latency_seconds: Delivery latency
    """
    WEBHOOK_DELIVERIES.labels(status=status).inc()
    WEBHOOK_LATENCY.observe(latency_seconds)


def set_active_diligences(count: int) -> None:
    """Set active diligences count.
    
    Args:
        count: Number of active diligences
    """
    ACTIVE_DILIGENCES.set(count)


def set_queue_size(count: int) -> None:
    """Set queue size.
    
    Args:
        count: Number of items in queue
    """
    QUEUE_SIZE.set(count)


def get_metrics() -> bytes:
    """Get Prometheus metrics in text format.
    
    Returns:
        Metrics as bytes
    """
    return generate_latest(REGISTRY)
