"""Tests for LLM client with circuit breaker, rate limiting, and retry logic."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from heavyswarm.services.llm_client import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenError,
    CircuitState,
    LLMClient,
    LLMRequest,
    LLMResponse,
    ModelPricing,
    MODEL_PRICING,
    RetryConfig,
    RetryableError,
    NonRetryableError,
    TokenBucket,
    ModelRateLimiter,
    TokenCounter,
)


class TestTokenBucket:
    """Tests for token bucket rate limiter."""
    
    @pytest.mark.asyncio
    async def test_token_bucket_initial_capacity(self):
        """Test that token bucket starts with full capacity."""
        bucket = TokenBucket(rate=1.0, capacity=10.0)
        assert bucket.tokens == 10.0
    
    @pytest.mark.asyncio
    async def test_token_bucket_acquire_available(self):
        """Test acquiring tokens when available."""
        bucket = TokenBucket(rate=1.0, capacity=10.0)
        wait_time = await bucket.acquire(5.0)
        assert wait_time == 0.0
        assert bucket.tokens == 5.0
    
    @pytest.mark.asyncio
    async def test_token_bucket_acquire_unavailable(self):
        """Test acquiring tokens when not enough available."""
        bucket = TokenBucket(rate=1.0, capacity=10.0)
        bucket.tokens = 2.0
        wait_time = await bucket.acquire(5.0)
        assert wait_time > 0.0
        assert bucket.tokens == 0.0
    
    @pytest.mark.asyncio
    async def test_token_bucket_refill(self):
        """Test token bucket refill over time."""
        bucket = TokenBucket(rate=10.0, capacity=10.0)
        bucket.tokens = 0.0
        bucket.last_update = asyncio.get_event_loop().time() - 1.0  # 1 second ago
        
        wait_time = await bucket.acquire(5.0)
        # Should have refilled 10 tokens over 1 second, but capped at capacity
        assert wait_time == 0.0
        assert bucket.tokens == 5.0


class TestModelRateLimiter:
    """Tests for model rate limiter."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_initialization(self):
        """Test rate limiter initialization."""
        from heavyswarm.services.llm_client import RateLimitConfig
        config = RateLimitConfig(
            requests_per_minute=60,
            tokens_per_minute=100000,
            burst_size=10,
        )
        limiter = ModelRateLimiter(config)
        assert limiter.config == config
    
    @pytest.mark.asyncio
    async def test_rate_limiter_acquire(self):
        """Test rate limiter acquire."""
        from heavyswarm.services.llm_client import RateLimitConfig
        config = RateLimitConfig(
            requests_per_minute=60,
            tokens_per_minute=100000,
            burst_size=10,
        )
        limiter = ModelRateLimiter(config)
        # Should not block on first acquire
        await limiter.acquire(estimated_tokens=100)


class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""
    
    @pytest.mark.asyncio
    async def test_circuit_starts_closed(self):
        """Test circuit starts in CLOSED state."""
        config = CircuitBreakerConfig()
        cb = CircuitBreaker("test", config)
        assert cb.get_state() == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_opens_after_failures(self):
        """Test circuit opens after threshold failures."""
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config)
        
        # Simulate failures
        for _ in range(3):
            try:
                await cb.call(self._failing_func)
            except ValueError:
                pass
        
        assert cb.get_state() == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_rejects_when_open(self):
        """Test circuit rejects calls when open."""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", config)
        
        # Trigger failure to open circuit
        try:
            await cb.call(self._failing_func)
        except ValueError:
            pass
        
        # Next call should raise CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call(self._success_func)
    
    @pytest.mark.asyncio
    async def test_circuit_closes_after_recovery(self):
        """Test circuit closes after successful recovery."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.1,
            success_threshold=1,
        )
        cb = CircuitBreaker("test", config)
        
        # Open the circuit
        try:
            await cb.call(self._failing_func)
        except ValueError:
            pass
        
        assert cb.get_state() == CircuitState.OPEN
        
        # Wait for recovery timeout
        await asyncio.sleep(0.15)
        
        # Circuit should be HALF_OPEN, successful call should close it
        result = await cb.call(self._success_func)
        assert result == "success"
        assert cb.get_state() == CircuitState.CLOSED
    
    async def _failing_func(self):
        raise ValueError("Test failure")
    
    async def _success_func(self):
        return "success"


class TestTokenCounter:
    """Tests for token counter."""
    
    def test_approximate_token_count(self):
        """Test approximate token counting."""
        counter = TokenCounter()
        # Roughly 4 characters per token
        text = "a" * 100
        tokens = counter._approximate_token_count(text)
        assert tokens == 25
    
    def test_count_message_tokens(self):
        """Test counting tokens for messages."""
        counter = TokenCounter()
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
        ]
        tokens = counter.count_message_tokens(messages, "gpt-4")
        assert tokens > 0
    
    def test_is_openai_model(self):
        """Test OpenAI model detection."""
        counter = TokenCounter()
        assert counter._is_openai_model("gpt-4") is True
        assert counter._is_openai_model("gpt-3.5-turbo") is True
        assert counter._is_openai_model("claude-3") is False


class TestLLMClientInitialization:
    """Tests for LLM client initialization."""
    
    def test_client_initialization(self):
        """Test LLM client initialization."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        mock_settings.llm_timeout_seconds = 60
        mock_settings.llm_retry_max_attempts = 3
        mock_settings.llm_retry_base_delay = 1.0
        mock_settings.llm_retry_max_delay = 60.0
        mock_settings.llm_circuit_failure_threshold = 5
        mock_settings.llm_circuit_recovery_timeout = 30.0
        
        client = LLMClient(mock_settings)
        assert client.settings == mock_settings
        assert client.token_counter is not None
    
    def test_model_pricing_exists(self):
        """Test that pricing data exists for supported models."""
        assert "gpt-4o" in MODEL_PRICING
        assert "claude-3-5-sonnet-20241022" in MODEL_PRICING
        assert "grok-4.20-reasoning" in MODEL_PRICING
        
        # Check pricing structure
        pricing = MODEL_PRICING["gpt-4o"]
        assert isinstance(pricing, ModelPricing)
        assert pricing.input_price_per_1k > 0
        assert pricing.output_price_per_1k > 0


class TestLLMClientRetryLogic:
    """Tests for retry logic."""
    
    def test_is_retryable_error(self):
        """Test retryable error detection."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        client = LLMClient(mock_settings)
        
        # Retryable errors
        assert client._is_retryable_error(Exception("rate limit exceeded")) is True
        assert client._is_retryable_error(Exception("timeout")) is True
        assert client._is_retryable_error(Exception("connection error")) is True
        assert client._is_retryable_error(Exception("503 service unavailable")) is True
        
        # Non-retryable errors
        assert client._is_retryable_error(Exception("invalid api key")) is False
        assert client._is_retryable_error(Exception("authentication failed")) is False
        assert client._is_retryable_error(Exception("bad request")) is False
    
    def test_calculate_retry_delay(self):
        """Test retry delay calculation."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        mock_settings.llm_retry_max_attempts = 3
        mock_settings.llm_retry_base_delay = 1.0
        mock_settings.llm_retry_max_delay = 60.0
        client = LLMClient(mock_settings)
        
        # Delay should increase with attempts
        delay1 = client._calculate_retry_delay(0)
        delay2 = client._calculate_retry_delay(1)
        delay3 = client._calculate_retry_delay(2)
        
        assert delay2 > delay1
        assert delay3 > delay2
    
    def test_get_fallback_model(self):
        """Test fallback model selection."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        mock_settings.fallback_model = "gpt-4o"
        client = LLMClient(mock_settings)
        
        # Test fallback chains
        assert client._get_fallback_model("gpt-4o") == "gpt-4-turbo"
        assert client._get_fallback_model("claude-3-opus-20240229") == "claude-3-5-sonnet-20241022"
        assert client._get_fallback_model("grok-4.20-reasoning") == "claude-3-5-sonnet-20241022"


class TestLLMClientCostCalculation:
    """Tests for cost calculation."""
    
    def test_calculate_cost(self):
        """Test cost calculation."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        client = LLMClient(mock_settings)
        
        usage = {
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500,
        }
        
        cost = client._calculate_cost("gpt-4o", usage)
        # gpt-4o: $0.005 per 1K input, $0.015 per 1K output
        expected_cost = (1000 / 1000) * 0.005 + (500 / 1000) * 0.015
        assert cost == round(expected_cost, 6)
    
    def test_calculate_cost_unknown_model(self):
        """Test cost calculation for unknown model."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        client = LLMClient(mock_settings)
        
        usage = {"prompt_tokens": 1000, "completion_tokens": 500}
        cost = client._calculate_cost("unknown-model", usage)
        assert cost == 0.0
    
    def test_get_estimated_cost(self):
        """Test estimated cost calculation."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        client = LLMClient(mock_settings)
        
        cost = client.get_estimated_cost("gpt-4o", 1000, 500)
        expected_cost = (1000 / 1000) * 0.005 + (500 / 1000) * 0.015
        assert cost == round(expected_cost, 6)


class TestLLMClientModelDetection:
    """Tests for model provider detection."""
    
    def test_is_openai_model(self):
        """Test OpenAI model detection."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        client = LLMClient(mock_settings)
        
        assert client._is_openai_model("gpt-4o") is True
        assert client._is_openai_model("gpt-3.5-turbo") is True
        assert client._is_openai_model("o1-preview") is True
        assert client._is_openai_model("claude-3") is False
        assert client._is_openai_model("grok-2") is False
    
    def test_is_anthropic_model(self):
        """Test Anthropic model detection."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        client = LLMClient(mock_settings)
        
        assert client._is_anthropic_model("claude-3-5-sonnet") is True
        assert client._is_anthropic_model("claude-3-opus") is True
        assert client._is_openai_model("gpt-4o") is True
        assert client._is_anthropic_model("grok-2") is False
    
    def test_is_grok_model(self):
        """Test Grok model detection."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        client = LLMClient(mock_settings)
        
        assert client._is_grok_model("grok-2") is True
        assert client._is_grok_model("grok-4.3") is True
        assert client._is_grok_model("grok-4.20-reasoning") is True
        assert client._is_grok_model("gpt-4o") is False
        assert client._is_grok_model("claude-3") is False


class TestLLMClientUsageTracking:
    """Tests for usage tracking."""
    
    def test_track_usage(self):
        """Test usage tracking."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        client = LLMClient(mock_settings)
        
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }
        
        client._track_usage("gpt-4o", usage)
        stats = client.get_usage_stats()
        
        assert "gpt-4o" in stats
        assert stats["gpt-4o"]["calls"] == 1
        assert stats["gpt-4o"]["prompt_tokens"] == 100
        assert stats["gpt-4o"]["completion_tokens"] == 50
    
    def test_reset_usage_stats(self):
        """Test resetting usage stats."""
        mock_settings = MagicMock()
        mock_settings.max_concurrent_llm_calls = 10
        client = LLMClient(mock_settings)
        
        client._track_usage("gpt-4o", {"prompt_tokens": 100, "completion_tokens": 50})
        client.reset_usage_stats()
        
        stats = client.get_usage_stats()
        assert stats == {}


class TestLLMRequestResponse:
    """Tests for LLM request/response dataclasses."""
    
    def test_llm_request_creation(self):
        """Test LLM request creation."""
        request = LLMRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.5,
            max_tokens=1000,
        )
        
        assert request.model == "gpt-4o"
        assert request.temperature == 0.5
        assert request.max_tokens == 1000
    
    def test_llm_response_creation(self):
        """Test LLM response creation."""
        response = LLMResponse(
            content="Hello!",
            model="gpt-4o",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            finish_reason="stop",
            response_time_ms=1000,
            cost_usd=0.001,
        )
        
        assert response.content == "Hello!"
        assert response.cost_usd == 0.001
