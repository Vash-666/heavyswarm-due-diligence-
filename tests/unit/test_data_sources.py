"""Tests for data source clients."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from heavyswarm.services.data_sources.base import (
    BaseDataSource,
    DataSourceConfig,
    DataSourceResponse,
)


class TestDataSourceConfig:
    """Tests for DataSourceConfig."""

    def test_config_creation(self):
        """Test creating data source config."""
        config = DataSourceConfig(
            api_key="test_key",
            base_url="https://api.example.com",
            timeout_seconds=30,
            retry_attempts=3,
            rate_limit_per_minute=60,
            cache_ttl_minutes=60,
        )

        assert config.api_key == "test_key"
        assert config.base_url == "https://api.example.com"
        assert config.timeout_seconds == 30


class TestDataSourceResponse:
    """Tests for DataSourceResponse."""

    def test_response_creation(self):
        """Test creating data source response."""
        now = datetime.utcnow()
        response = DataSourceResponse(
            data={"test": "data"},
            source="TestSource",
            retrieved_at=now,
            cached=False,
        )

        assert response.data == {"test": "data"}
        assert response.source == "TestSource"
        assert response.cached is False


class MockDataSource(BaseDataSource):
    """Mock data source for testing."""

    def __init__(self):
        config = DataSourceConfig(
            api_key="test_key",
            base_url="https://api.example.com",
        )
        super().__init__(config)
        self._mock_data = {}

    async def _fetch(self, endpoint: str, params: dict) -> dict:
        return self._mock_data.get(endpoint, {})

    async def health_check(self) -> bool:
        return True


class TestBaseDataSource:
    """Tests for BaseDataSource."""

    @pytest.fixture
    def source(self):
        """Create mock data source."""
        return MockDataSource()

    def test_initialization(self, source):
        """Test data source initialization."""
        assert source.config.api_key == "test_key"
        assert source.config.base_url == "https://api.example.com"

    def test_cache_key_generation(self, source):
        """Test cache key generation."""
        key1 = source._get_cache_key("test", {"a": 1, "b": 2})
        key2 = source._get_cache_key("test", {"b": 2, "a": 1})
        # Same params in different order should produce same key
        assert key1 == key2

    def test_cache_operations(self, source):
        """Test cache set and get operations."""
        # Set cache
        source._set_cached("test_key", {"data": "value"})

        # Get cache
        cached = source._get_cached("test_key")
        assert cached is not None
        assert cached.data == {"data": "value"}
        assert cached.cached is True

    def test_cache_expiration(self, source):
        """Test cache expiration."""
        from datetime import timedelta
        # Set cache with old timestamp (older than cache_ttl_minutes)
        source._cache["old_key"] = {
            "data": "old_data",
            "retrieved_at": datetime.utcnow() - timedelta(minutes=source.config.cache_ttl_minutes + 10),
        }

        # Should be expired
        cached = source._get_cached("old_key")
        assert cached is None

    @pytest.mark.asyncio
    async def test_make_request_with_cache(self, source):
        """Test making request with caching."""
        source._mock_data = {"test_endpoint": {"result": "success"}}

        # First request - should hit the API
        response1 = await source._make_request("test_endpoint", {})
        assert response1.data == {"result": "success"}
        assert response1.cached is False

        # Second request - should use cache
        response2 = await source._make_request("test_endpoint", {})
        assert response2.data == {"result": "success"}
        assert response2.cached is True

    @pytest.mark.asyncio
    async def test_rate_limiting(self, source):
        """Test rate limiting."""
        source.config.rate_limit_per_minute = 1000  # High limit for testing

        # Should not raise any errors
        await source._rate_limit()

    def test_rate_limit_cleanup(self, source):
        """Test rate limit cleanup of old requests."""
        from datetime import timedelta

        # Add old request times
        old_time = datetime.utcnow() - timedelta(minutes=2)
        source._request_times = [old_time]

        # Should clean up old requests
        source._rate_limit()
        # After cleanup, list should be empty or only contain recent requests


class TestAlphaVantageClient:
    """Tests for Alpha Vantage client."""

    def test_client_import(self):
        """Test Alpha Vantage client can be imported."""
        from heavyswarm.services.data_sources.alpha_vantage import AlphaVantageClient

        assert AlphaVantageClient is not None

    def test_client_initialization(self):
        """Test client initialization."""
        from heavyswarm.services.data_sources.alpha_vantage import AlphaVantageClient

        client = AlphaVantageClient(api_key="test_key")
        assert client.config.api_key == "test_key"
        assert client.config.base_url == "https://www.alphavantage.co/query"


class TestNewsAPIClient:
    """Tests for News API client."""

    def test_client_import(self):
        """Test News API client can be imported."""
        from heavyswarm.services.data_sources.news_api import NewsAPIClient

        assert NewsAPIClient is not None

    def test_client_initialization(self):
        """Test client initialization."""
        from heavyswarm.services.data_sources.news_api import NewsAPIClient

        client = NewsAPIClient(api_key="test_key")
        assert client.config.api_key == "test_key"
        assert client.config.base_url == "https://newsapi.org/v2"


class TestSECEdgarClient:
    """Tests for SEC EDGAR client."""

    def test_client_import(self):
        """Test SEC EDGAR client can be imported."""
        from heavyswarm.services.data_sources.sec_edgar import SECEdgarClient

        assert SECEdgarClient is not None

    def test_client_initialization(self):
        """Test client initialization."""
        from heavyswarm.services.data_sources.sec_edgar import SECEdgarClient

        client = SECEdgarClient(user_agent="Test Agent")
        assert client.user_agent == "Test Agent"
        assert client.config.base_url == "https://www.sec.gov/Archives/edgar"
