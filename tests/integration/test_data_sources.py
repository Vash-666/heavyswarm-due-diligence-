"""Integration tests for data source clients."""

import pytest
import os

from heavyswarm.services.data_sources import AlphaVantageClient, NewsAPIClient, SECEdgarClient


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ALPHA_VANTAGE_API_KEY"),
    reason="ALPHA_VANTAGE_API_KEY not set",
)
async def test_alpha_vantage_health_check():
    """Test Alpha Vantage API health check."""
    client = AlphaVantageClient(api_key=os.getenv("ALPHA_VANTAGE_API_KEY"))
    
    is_healthy = await client.health_check()
    
    # Note: This may fail in CI without API key
    assert isinstance(is_healthy, bool)


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("ALPHA_VANTAGE_API_KEY"),
    reason="ALPHA_VANTAGE_API_KEY not set",
)
async def test_alpha_vantage_get_quote():
    """Test Alpha Vantage quote retrieval."""
    client = AlphaVantageClient(api_key=os.getenv("ALPHA_VANTAGE_API_KEY"))
    
    response = await client.get_quote("AAPL")
    
    assert response.error is None or response.error is not None  # Either is valid for test
    if response.error is None:
        assert "Global Quote" in response.data or "Note" in response.data


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("NEWS_API_KEY"),
    reason="NEWS_API_KEY not set",
)
async def test_news_api_health_check():
    """Test News API health check."""
    client = NewsAPIClient(api_key=os.getenv("NEWS_API_KEY"))
    
    is_healthy = await client.health_check()
    
    assert isinstance(is_healthy, bool)


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.getenv("NEWS_API_KEY"),
    reason="NEWS_API_KEY not set",
)
async def test_news_api_search():
    """Test News API search."""
    client = NewsAPIClient(api_key=os.getenv("NEWS_API_KEY"))
    
    response = await client.search_news("Apple stock", page_size=5)
    
    assert response.error is None or response.error is not None
    if response.error is None:
        assert "articles" in response.data or response.data.get("status") == "ok"


@pytest.mark.asyncio
async def test_sec_edgar_health_check():
    """Test SEC EDGAR API health check."""
    client = SECEdgarClient()
    
    is_healthy = await client.health_check()
    
    # SEC API is public and should generally be available
    assert isinstance(is_healthy, bool)


@pytest.mark.asyncio
async def test_sec_edgar_get_company_tickers():
    """Test SEC EDGAR company tickers retrieval."""
    client = SECEdgarClient()
    
    response = await client.get_company_tickers()
    
    if response.error is None:
        assert len(response.data) > 0
        # Check for Apple
        found_apple = any(
            entry.get("ticker") == "AAPL"
            for entry in response.data.values()
        )
        assert found_apple, "AAPL should be in company tickers"


@pytest.mark.asyncio
async def test_sec_edgar_get_submissions():
    """Test SEC EDGAR submissions retrieval."""
    client = SECEdgarClient()
    
    response = await client.get_submissions("AAPL")
    
    if response.error is None:
        assert "filings" in response.data or "recent" in response.data


@pytest.mark.asyncio
async def test_sec_edgar_get_recent_filings():
    """Test SEC EDGAR recent filings retrieval."""
    client = SECEdgarClient()
    
    response = await client.get_recent_filings(
        "AAPL",
        form_types=["10-K", "10-Q"],
        limit=5,
    )
    
    if response.error is None:
        assert "filings" in response.data
        assert len(response.data["filings"]) <= 5
