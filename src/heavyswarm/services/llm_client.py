"""Production-ready LLM client with retry logic, circuit breaker, token counting, cost tracking, and rate limiting."""

import asyncio
import hashlib
import random
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, TypeVar

from heavyswarm.core.config import Settings
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = auto()  # Normal operation
    OPEN = auto()  # Failing, reject requests
    HALF_OPEN = auto()  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    success_threshold: int = 2


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    jitter_max: float = 1.0


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""

    requests_per_minute: int = 60
    tokens_per_minute: int = 100000
    burst_size: int = 10


@dataclass
class ModelPricing:
    """Pricing information for a model."""

    input_price_per_1k: float  # USD per 1K input tokens
    output_price_per_1k: float  # USD per 1K output tokens


# Model pricing data (USD per 1K tokens) - Updated 2024
MODEL_PRICING: Dict[str, ModelPricing] = {
    # OpenAI models
    "gpt-4o": ModelPricing(input_price_per_1k=0.005, output_price_per_1k=0.015),
    "gpt-4o-mini": ModelPricing(input_price_per_1k=0.00015, output_price_per_1k=0.0006),
    "gpt-4-turbo": ModelPricing(input_price_per_1k=0.01, output_price_per_1k=0.03),
    "gpt-4": ModelPricing(input_price_per_1k=0.03, output_price_per_1k=0.06),
    "gpt-3.5-turbo": ModelPricing(input_price_per_1k=0.0005, output_price_per_1k=0.0015),
    "o1-preview": ModelPricing(input_price_per_1k=0.015, output_price_per_1k=0.06),
    "o1-mini": ModelPricing(input_price_per_1k=0.003, output_price_per_1k=0.012),
    # Anthropic models
    "claude-3-5-sonnet-20241022": ModelPricing(
        input_price_per_1k=0.003, output_price_per_1k=0.015
    ),
    "claude-3-5-sonnet-20240620": ModelPricing(
        input_price_per_1k=0.003, output_price_per_1k=0.015
    ),
    "claude-3-opus-20240229": ModelPricing(input_price_per_1k=0.015, output_price_per_1k=0.075),
    "claude-3-sonnet-20240229": ModelPricing(
        input_price_per_1k=0.003, output_price_per_1k=0.015
    ),
    "claude-3-haiku-20240307": ModelPricing(
        input_price_per_1k=0.00025, output_price_per_1k=0.00125
    ),
    # xAI Grok models - Pricing as of 2025
    "grok-4.20-reasoning": ModelPricing(
        input_price_per_1k=0.015, output_price_per_1k=0.075
    ),
    "grok-4.3": ModelPricing(
        input_price_per_1k=0.005, output_price_per_1k=0.015
    ),
    "grok-2": ModelPricing(
        input_price_per_1k=0.002, output_price_per_1k=0.010
    ),
}

# Default rate limits per model
DEFAULT_RATE_LIMITS: Dict[str, RateLimitConfig] = {
    "gpt-4o": RateLimitConfig(requests_per_minute=500, tokens_per_minute=2000000),
    "gpt-4o-mini": RateLimitConfig(requests_per_minute=500, tokens_per_minute=2000000),
    "gpt-4-turbo": RateLimitConfig(requests_per_minute=500, tokens_per_minute=2000000),
    "gpt-4": RateLimitConfig(requests_per_minute=200, tokens_per_minute=400000),
    "gpt-3.5-turbo": RateLimitConfig(requests_per_minute=3500, tokens_per_minute=90000),
    "o1-preview": RateLimitConfig(requests_per_minute=500, tokens_per_minute=2000000),
    "o1-mini": RateLimitConfig(requests_per_minute=500, tokens_per_minute=2000000),
    "claude-3-5-sonnet-20241022": RateLimitConfig(
        requests_per_minute=4000, tokens_per_minute=4000000
    ),
    "claude-3-5-sonnet-20240620": RateLimitConfig(
        requests_per_minute=4000, tokens_per_minute=4000000
    ),
    "claude-3-opus-20240229": RateLimitConfig(
        requests_per_minute=4000, tokens_per_minute=4000000
    ),
    "claude-3-sonnet-20240229": RateLimitConfig(
        requests_per_minute=4000, tokens_per_minute=4000000
    ),
    "claude-3-haiku-20240307": RateLimitConfig(
        requests_per_minute=4000, tokens_per_minute=4000000
    ),
    # xAI Grok rate limits (conservative defaults)
    "grok-4.20-reasoning": RateLimitConfig(
        requests_per_minute=1000, tokens_per_minute=2000000
    ),
    "grok-4.3": RateLimitConfig(
        requests_per_minute=2000, tokens_per_minute=4000000
    ),
    "grok-2": RateLimitConfig(
        requests_per_minute=3000, tokens_per_minute=6000000
    ),
}


class TokenBucket:
    """Token bucket for rate limiting."""

    def __init__(
        self,
        rate: float,  # tokens per second
        capacity: float,  # maximum burst
    ):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> float:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            Time to wait before proceeding (0 if tokens available immediately)
        """
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return 0.0
            else:
                deficit = tokens - self.tokens
                wait_time = deficit / self.rate
                self.tokens = 0
                return wait_time


class ModelRateLimiter:
    """Rate limiter for LLM models using token bucket algorithm."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        # Request rate limiter
        request_rate = config.requests_per_minute / 60.0
        self.request_bucket = TokenBucket(
            rate=request_rate,
            capacity=config.burst_size,
        )
        # Token rate limiter
        token_rate = config.tokens_per_minute / 60.0
        self.token_bucket = TokenBucket(
            rate=token_rate,
            capacity=config.tokens_per_minute,
        )

    async def acquire(self, estimated_tokens: int = 0) -> None:
        """Acquire rate limit permission.

        Args:
            estimated_tokens: Estimated tokens for the request
        """
        # Wait for request slot
        wait_time = await self.request_bucket.acquire(1.0)
        if wait_time > 0:
            logger.debug(f"Rate limit: waiting {wait_time:.2f}s for request slot")
            await asyncio.sleep(wait_time)

        # Wait for token budget if estimated
        if estimated_tokens > 0:
            token_wait = await self.token_bucket.acquire(float(estimated_tokens))
            if token_wait > 0:
                logger.debug(f"Rate limit: waiting {token_wait:.2f}s for token budget")
                await asyncio.sleep(token_wait)


class CircuitBreaker:
    """Circuit breaker pattern implementation."""

    def __init__(self, name: str, config: CircuitBreakerConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if self.state == CircuitState.OPEN:
                if time.monotonic() - (self.last_failure_time or 0) > self.config.recovery_timeout:
                    logger.info(f"Circuit {self.name}: transitioning to HALF_OPEN")
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    self.success_count = 0
                else:
                    raise CircuitBreakerOpenError(f"Circuit {self.name} is OPEN")

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"Circuit {self.name} HALF_OPEN max calls reached"
                    )
                self.half_open_calls += 1

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    logger.info(f"Circuit {self.name}: transitioning to CLOSED")
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.half_open_calls = 0
            elif self.state == CircuitState.CLOSED:
                self.failure_count = max(0, self.failure_count - 1)

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()

            if self.state == CircuitState.HALF_OPEN:
                logger.warning(f"Circuit {self.name}: failure in HALF_OPEN, transitioning to OPEN")
                self.state = CircuitState.OPEN
            elif self.state == CircuitState.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    logger.warning(
                        f"Circuit {self.name}: failure threshold reached, transitioning to OPEN"
                    )
                    self.state = CircuitState.OPEN

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self.state


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


class RetryableError(Exception):
    """Base class for retryable errors."""

    pass


class NonRetryableError(Exception):
    """Base class for non-retryable errors."""

    pass


@dataclass
class LLMResponse:
    """Response from LLM API."""

    content: str
    model: str
    usage: Dict[str, int]
    finish_reason: str
    response_time_ms: int
    cost_usd: float = 0.0


@dataclass
class LLMRequest:
    """Request to LLM API."""

    model: str
    messages: List[Dict[str, str]]
    temperature: float = 0.2
    max_tokens: int = 4000
    timeout_seconds: int = 60


@dataclass
class CostMetrics:
    """Cost tracking metrics for a model."""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    average_cost_per_call: float = 0.0


class TokenCounter:
    """Token counting for various LLM models."""

    def __init__(self):
        self._tiktoken_encoders: Dict[str, Any] = {}
        self._tiktoken_available = False
        try:
            import tiktoken

            self._tiktoken_available = True
            self._tiktoken = tiktoken
        except ImportError:
            logger.warning("tiktoken not available, using approximate token counting")

    def count_tokens_openai(self, text: str, model: str = "gpt-4") -> int:
        """Count tokens for OpenAI models using tiktoken."""
        if not self._tiktoken_available:
            return self._approximate_token_count(text)

        try:
            # Map model to encoding
            encoding_name = self._get_encoding_for_model(model)
            if encoding_name not in self._tiktoken_encoders:
                self._tiktoken_encoders[encoding_name] = self._tiktoken.get_encoding(encoding_name)
            encoder = self._tiktoken_encoders[encoding_name]
            return len(encoder.encode(text))
        except Exception as e:
            logger.warning(f"Failed to count tokens with tiktoken: {e}, using approximation")
            return self._approximate_token_count(text)

    def count_tokens_grok(self, text: str) -> int:
        """Count tokens for Grok models using approximation.
        
        Grok uses a similar tokenizer to other modern LLMs.
        We use the same approximation as Anthropic (~4 chars per token).
        """
        return self._approximate_token_count(text)

    def count_tokens_anthropic(self, text: str) -> int:
        """Count tokens for Anthropic models using approximation."""
        # Anthropic uses ~4 characters per token on average
        # This is a reasonable approximation
        return self._approximate_token_count(text)

    def count_message_tokens(
        self, messages: List[Dict[str, str]], model: str
    ) -> int:
        """Count tokens for a list of messages."""
        total = 0
        for message in messages:
            content = message.get("content", "")
            if self._is_openai_model(model):
                total += self.count_tokens_openai(content, model)
                # Add overhead for message format (role, etc.)
                total += 4
            elif self._is_grok_model(model):
                total += self.count_tokens_grok(content)
                # Add overhead for message format (role, etc.)
                total += 4
            else:
                total += self.count_tokens_anthropic(content)
                total += 4
        return total

    def _get_encoding_for_model(self, model: str) -> str:
        """Get the appropriate encoding for a model."""
        if model.startswith("gpt-4") or model.startswith("gpt-3.5-turbo"):
            return "cl100k_base"
        elif model.startswith("o1-"):
            return "cl100k_base"
        elif model.startswith("text-embedding-"):
            return "cl100k_base"
        elif model.startswith("gpt-3.5"):
            return "p50k_base"
        else:
            return "cl100k_base"  # Default to cl100k_base

    def _approximate_token_count(self, text: str) -> int:
        """Approximate token count based on character count."""
        # Roughly 4 characters per token for English text
        return len(text) // 4

    def _is_openai_model(self, model: str) -> bool:
        """Check if model is from OpenAI."""
        openai_prefixes = ("gpt-", "o1-", "text-")
        return any(model.startswith(prefix) for prefix in openai_prefixes)


class LLMClient:
    """Production-ready unified client for OpenAI and Anthropic LLM APIs.

    Features:
    - Retry logic with exponential backoff and jitter
    - Circuit breaker pattern for fault tolerance
    - Token counting (tiktoken for OpenAI, approximation for Anthropic)
    - Cost tracking per model with pricing data
    - Rate limiting per model using token bucket algorithm
    - Full error handling and logging
    """

    def __init__(self, settings: Settings):
        """Initialize LLM client.

        Args:
            settings: Application settings with API keys
        """
        self.settings = settings
        self._openai_client: Optional[Any] = None
        self._anthropic_client: Optional[Any] = None
        self._grok_client: Optional[Any] = None
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)

        # Initialize components
        self.token_counter = TokenCounter()
        self._usage_stats: Dict[str, Dict[str, Any]] = {}
        self._cost_metrics: Dict[str, CostMetrics] = {}
        self._rate_limiters: Dict[str, ModelRateLimiter] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

        # Retry configuration
        self.retry_config = RetryConfig(
            max_attempts=getattr(settings, "llm_retry_max_attempts", 3),
            base_delay=getattr(settings, "llm_retry_base_delay", 1.0),
            max_delay=getattr(settings, "llm_retry_max_delay", 60.0),
        )

        # Circuit breaker configuration
        self.circuit_config = CircuitBreakerConfig(
            failure_threshold=getattr(settings, "llm_circuit_failure_threshold", 5),
            recovery_timeout=getattr(settings, "llm_circuit_recovery_timeout", 30.0),
        )

        logger.info("LLMClient initialized with retry, circuit breaker, and rate limiting")

    @property
    def openai_client(self) -> Any:
        """Lazy initialization of OpenAI client."""
        if self._openai_client is None:
            from openai import AsyncOpenAI

            if not self.settings.openai_api_key:
                raise ValueError("OpenAI API key not configured")
            self._openai_client = AsyncOpenAI(
                api_key=self.settings.openai_api_key,
                timeout=self.settings.llm_timeout_seconds,
            )
        return self._openai_client

    @property
    def anthropic_client(self) -> Any:
        """Lazy initialization of Anthropic client."""
        if self._anthropic_client is None:
            from anthropic import AsyncAnthropic

            if not self.settings.anthropic_api_key:
                raise ValueError("Anthropic API key not configured")
            self._anthropic_client = AsyncAnthropic(
                api_key=self.settings.anthropic_api_key,
                timeout=self.settings.llm_timeout_seconds,
            )
        return self._anthropic_client

    @property
    def grok_client(self) -> Any:
        """Lazy initialization of xAI Grok client.
        
        Grok API is OpenAI-compatible, so we use the OpenAI client
        with a different base URL and API key.
        """
        if self._grok_client is None:
            from openai import AsyncOpenAI

            if not self.settings.xai_api_key:
                raise ValueError("xAI API key not configured")
            self._grok_client = AsyncOpenAI(
                api_key=self.settings.xai_api_key,
                base_url="https://api.x.ai/v1",
                timeout=self.settings.llm_timeout_seconds,
            )
        return self._grok_client

    def _get_rate_limiter(self, model: str) -> ModelRateLimiter:
        """Get or create rate limiter for a model."""
        if model not in self._rate_limiters:
            config = DEFAULT_RATE_LIMITS.get(model, RateLimitConfig())
            self._rate_limiters[model] = ModelRateLimiter(config)
        return self._rate_limiters[model]

    def _get_circuit_breaker(self, provider: str) -> CircuitBreaker:
        """Get or create circuit breaker for a provider."""
        if provider not in self._circuit_breakers:
            self._circuit_breakers[provider] = CircuitBreaker(
                name=f"llm_{provider}",
                config=self.circuit_config,
            )
        return self._circuit_breakers[provider]

    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate retry delay with exponential backoff and jitter."""
        delay = min(
            self.retry_config.base_delay * (self.retry_config.exponential_base ** attempt),
            self.retry_config.max_delay,
        )
        if self.retry_config.jitter:
            jitter = random.uniform(0, self.retry_config.jitter_max)
            delay += jitter
        return delay

    def _is_retryable_error(self, error: Exception) -> bool:
        """Determine if an error is retryable."""
        error_str = str(error).lower()
        retryable_patterns = [
            "rate limit",
            "timeout",
            "connection",
            "server error",
            "503",
            "502",
            "504",
            "429",
            "too many requests",
            "temporary",
            "unavailable",
        ]
        non_retryable_patterns = [
            "invalid api key",
            "authentication",
            "not found",
            "bad request",
            "invalid request",
            "content filter",
            "quota exceeded",
        ]

        # Check non-retryable first
        for pattern in non_retryable_patterns:
            if pattern in error_str:
                return False

        # Check retryable
        for pattern in retryable_patterns:
            if pattern in error_str:
                return True

        # Default: retry on generic errors
        return True

    async def _execute_with_retry(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Execute a function with retry logic."""
        last_error: Optional[Exception] = None

        for attempt in range(self.retry_config.max_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e

                if not self._is_retryable_error(e):
                    logger.warning(f"Non-retryable error: {e}")
                    raise

                if attempt < self.retry_config.max_attempts - 1:
                    delay = self._calculate_retry_delay(attempt)
                    logger.warning(
                        f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {self.retry_config.max_attempts} attempts failed")

        raise last_error or Exception("All retry attempts failed")

    def _calculate_cost(self, model: str, usage: Dict[str, int]) -> float:
        """Calculate cost in USD for a request."""
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            logger.warning(f"No pricing data for model: {model}")
            return 0.0

        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        input_cost = (input_tokens / 1000) * pricing.input_price_per_1k
        output_cost = (output_tokens / 1000) * pricing.output_price_per_1k

        return round(input_cost + output_cost, 6)

    def _update_cost_metrics(self, model: str, usage: Dict[str, int], cost: float) -> None:
        """Update cost tracking metrics."""
        if model not in self._cost_metrics:
            self._cost_metrics[model] = CostMetrics()

        metrics = self._cost_metrics[model]
        metrics.total_calls += 1
        metrics.total_input_tokens += usage.get("prompt_tokens", 0)
        metrics.total_output_tokens += usage.get("completion_tokens", 0)
        metrics.total_tokens += usage.get("total_tokens", 0)
        metrics.total_cost_usd += cost
        metrics.average_cost_per_call = metrics.total_cost_usd / metrics.total_calls

    async def complete(
        self,
        request: LLMRequest,
        use_fallback: bool = True,
    ) -> LLMResponse:
        """Get completion from LLM with full resilience patterns.

        Args:
            request: LLM request
            use_fallback: Whether to fallback to alternative model on failure

        Returns:
            LLM response
        """
        async with self._semaphore:
            start_time = time.monotonic()

            # Estimate tokens for rate limiting
            estimated_tokens = self.token_counter.count_message_tokens(
                request.messages, request.model
            )

            # Apply rate limiting
            rate_limiter = self._get_rate_limiter(request.model)
            await rate_limiter.acquire(estimated_tokens)

            try:
                if self._is_openai_model(request.model):
                    provider = "openai"
                    circuit_breaker = self._get_circuit_breaker(provider)
                    response = await circuit_breaker.call(
                        self._execute_with_retry,
                        self._call_openai,
                        request,
                    )
                elif self._is_anthropic_model(request.model):
                    provider = "anthropic"
                    circuit_breaker = self._get_circuit_breaker(provider)
                    response = await circuit_breaker.call(
                        self._execute_with_retry,
                        self._call_anthropic,
                        request,
                    )
                elif self._is_grok_model(request.model):
                    provider = "grok"
                    circuit_breaker = self._get_circuit_breaker(provider)
                    response = await circuit_breaker.call(
                        self._execute_with_retry,
                        self._call_grok,
                        request,
                    )
                else:
                    raise ValueError(f"Unsupported model: {request.model}")

                # Calculate cost
                cost = self._calculate_cost(request.model, response.usage)
                response.cost_usd = cost

                # Update metrics
                self._track_usage(request.model, response.usage)
                self._update_cost_metrics(request.model, response.usage, cost)

                response_time = int((time.monotonic() - start_time) * 1000)
                response.response_time_ms = response_time

                logger.debug(
                    "LLM call completed",
                    extra={
                        "model": request.model,
                        "response_time_ms": response_time,
                        "usage": response.usage,
                        "cost_usd": cost,
                        "circuit_state": circuit_breaker.get_state().name,
                    },
                )

                return response

            except CircuitBreakerOpenError:
                logger.error(f"Circuit breaker OPEN for {request.model}")
                if use_fallback:
                    return await self._try_fallback(request)
                raise
            except Exception as e:
                logger.error(
                    "LLM call failed",
                    extra={
                        "model": request.model,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

                if use_fallback:
                    return await self._try_fallback(request)
                raise

    async def _try_fallback(self, request: LLMRequest) -> LLMResponse:
        """Try fallback model."""
        fallback_model = self._get_fallback_model(request.model)
        if fallback_model != request.model:
            logger.info(
                "Falling back to alternative model",
                extra={
                    "original": request.model,
                    "fallback": fallback_model,
                },
            )
            request.model = fallback_model
            return await self.complete(request, use_fallback=False)
        raise NonRetryableError("No fallback model available")

    async def complete_stream(
        self,
        request: LLMRequest,
    ) -> AsyncGenerator[str, None]:
        """Stream completion from LLM with resilience patterns.

        Args:
            request: LLM request

        Yields:
            Chunks of the response
        """
        async with self._semaphore:
            # Apply rate limiting
            estimated_tokens = self.token_counter.count_message_tokens(
                request.messages, request.model
            )
            rate_limiter = self._get_rate_limiter(request.model)
            await rate_limiter.acquire(estimated_tokens)

            try:
                if self._is_openai_model(request.model):
                    provider = "openai"
                    circuit_breaker = self._get_circuit_breaker(provider)
                    async for chunk in await circuit_breaker.call(
                        self._execute_with_retry,
                        self._stream_openai,
                        request,
                    ):
                        yield chunk
                elif self._is_anthropic_model(request.model):
                    provider = "anthropic"
                    circuit_breaker = self._get_circuit_breaker(provider)
                    async for chunk in await circuit_breaker.call(
                        self._execute_with_retry,
                        self._stream_anthropic,
                        request,
                    ):
                        yield chunk
                elif self._is_grok_model(request.model):
                    provider = "grok"
                    circuit_breaker = self._get_circuit_breaker(provider)
                    async for chunk in await circuit_breaker.call(
                        self._execute_with_retry,
                        self._stream_grok,
                        request,
                    ):
                        yield chunk
                else:
                    raise ValueError(f"Unsupported model: {request.model}")

            except CircuitBreakerOpenError:
                logger.error(f"Circuit breaker OPEN for streaming {request.model}")
                raise
            except Exception as e:
                logger.error(f"Streaming failed for {request.model}: {e}")
                raise

    async def _call_openai(self, request: LLMRequest) -> LLMResponse:
        """Call OpenAI API."""
        response = await self.openai_client.chat.completions.create(
            model=request.model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            finish_reason=response.choices[0].finish_reason or "",
            response_time_ms=0,
        )

    async def _call_anthropic(self, request: LLMRequest) -> LLMResponse:
        """Call Anthropic API."""
        # Convert messages to Anthropic format
        system_message = ""
        messages = []

        for msg in request.messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                messages.append(msg)

        response = await self.anthropic_client.messages.create(
            model=request.model,
            messages=messages,
            system=system_message,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            model=response.model,
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            },
            finish_reason=response.stop_reason or "",
            response_time_ms=0,
        )

    async def _stream_openai(
        self,
        request: LLMRequest,
    ) -> AsyncGenerator[str, None]:
        """Stream from OpenAI API."""
        stream = await self.openai_client.chat.completions.create(
            model=request.model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _stream_anthropic(
        self,
        request: LLMRequest,
    ) -> AsyncGenerator[str, None]:
        """Stream from Anthropic API."""
        system_message = ""
        messages = []

        for msg in request.messages:
            if msg["role"] == "system":
                system_message = msg["content"]
            else:
                messages.append(msg)

        async with self.anthropic_client.messages.stream(
            model=request.model,
            messages=messages,
            system=system_message,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def _call_grok(self, request: LLMRequest) -> LLMResponse:
        """Call xAI Grok API.
        
        Grok API is OpenAI-compatible, so we use the same interface
        but with the Grok-specific client configuration.
        """
        response = await self.grok_client.chat.completions.create(
            model=request.model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            finish_reason=response.choices[0].finish_reason or "",
            response_time_ms=0,
        )

    async def _stream_grok(
        self,
        request: LLMRequest,
    ) -> AsyncGenerator[str, None]:
        """Stream from xAI Grok API."""
        stream = await self.grok_client.chat.completions.create(
            model=request.model,
            messages=request.messages,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    def _is_openai_model(self, model: str) -> bool:
        """Check if model is from OpenAI."""
        openai_prefixes = ("gpt-", "o1-", "text-")
        return any(model.startswith(prefix) for prefix in openai_prefixes)

    def _is_anthropic_model(self, model: str) -> bool:
        """Check if model is from Anthropic."""
        return model.startswith("claude-")

    def _is_grok_model(self, model: str) -> bool:
        """Check if model is from xAI Grok."""
        return model.startswith("grok-")

    def _get_fallback_model(self, model: str) -> str:
        """Get fallback model for a given model."""
        # Define fallback chains
        fallback_chains = {
            # OpenAI fallbacks
            "gpt-4o": "gpt-4-turbo",
            "gpt-4-turbo": "gpt-4",
            "gpt-4": "gpt-3.5-turbo",
            "o1-preview": "o1-mini",
            "o1-mini": "gpt-4o",
            # Anthropic fallbacks
            "claude-3-opus-20240229": "claude-3-5-sonnet-20241022",
            "claude-3-5-sonnet-20241022": "claude-3-5-sonnet-20240620",
            "claude-3-5-sonnet-20240620": "claude-3-sonnet-20240229",
            "claude-3-sonnet-20240229": "claude-3-haiku-20240307",
            # Grok fallbacks - prefer reasoning model for complex tasks
            "grok-4.20-reasoning": "claude-3-5-sonnet-20241022",
            "grok-4.3": "grok-2",
            "grok-2": "gpt-4o",
        }

        if model in fallback_chains:
            return fallback_chains[model]

        # Default fallbacks by provider
        if self._is_openai_model(model):
            return getattr(self.settings, "fallback_model", "gpt-3.5-turbo")
        elif self._is_grok_model(model):
            # Grok models fall back to Claude for reasoning tasks
            return getattr(self.settings, "fallback_model", "claude-3-5-sonnet-20241022")
        else:
            return getattr(self.settings, "default_model", "claude-3-haiku-20240307")

    def _track_usage(self, model: str, usage: Dict[str, int]) -> None:
        """Track API usage statistics."""
        if model not in self._usage_stats:
            self._usage_stats[model] = {
                "calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            }

        stats = self._usage_stats[model]
        stats["calls"] += 1
        stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
        stats["completion_tokens"] += usage.get("completion_tokens", 0)
        stats["total_tokens"] += usage.get("total_tokens", 0)

    def get_usage_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get usage statistics."""
        return self._usage_stats.copy()

    def get_cost_metrics(self) -> Dict[str, CostMetrics]:
        """Get cost metrics for all models."""
        return self._cost_metrics.copy()

    def get_circuit_states(self) -> Dict[str, CircuitState]:
        """Get current circuit breaker states."""
        return {name: cb.get_state() for name, cb in self._circuit_breakers.items()}

    def reset_usage_stats(self) -> None:
        """Reset usage statistics."""
        self._usage_stats.clear()
        self._cost_metrics.clear()

    def get_estimated_cost(
        self, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """Estimate cost for a hypothetical request.

        Args:
            model: Model name
            input_tokens: Expected input tokens
            output_tokens: Expected output tokens

        Returns:
            Estimated cost in USD
        """
        pricing = MODEL_PRICING.get(model)
        if not pricing:
            return 0.0

        input_cost = (input_tokens / 1000) * pricing.input_price_per_1k
        output_cost = (output_tokens / 1000) * pricing.output_price_per_1k
        return round(input_cost + output_cost, 6)
