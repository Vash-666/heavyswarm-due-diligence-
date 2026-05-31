"""Alpha Vantage API client for market data."""

from typing import Any, Dict, List, Optional

import aiohttp

from heavyswarm.services.data_sources.base import BaseDataSource, DataSourceConfig, DataSourceResponse
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class AlphaVantageClient(BaseDataSource):
    """Client for Alpha Vantage market data API."""
    
    def __init__(self, api_key: str):
        """Initialize Alpha Vantage client.
        
        Args:
            api_key: Alpha Vantage API key
        """
        config = DataSourceConfig(
            api_key=api_key,
            base_url="https://www.alphavantage.co/query",
            timeout_seconds=30,
            retry_attempts=3,
            rate_limit_per_minute=5,  # Free tier limit
            cache_ttl_minutes=15,  # Market data gets stale quickly
        )
        super().__init__(config)
    
    async def _fetch(self, endpoint: str, params: Dict[str, Any]) -> Any:
        """Fetch data from Alpha Vantage API.
        
        Args:
            endpoint: API function (Alpha Vantage uses function param)
            params: Request parameters
            
        Returns:
            Response data
        """
        params["apikey"] = self.config.api_key
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                self.config.base_url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Check for API errors
                if "Error Message" in data:
                    raise ValueError(f"Alpha Vantage API error: {data['Error Message']}")
                
                if "Note" in data:
                    raise ValueError(f"Alpha Vantage rate limit: {data['Note']}")
                
                return data
    
    async def health_check(self) -> bool:
        """Check if Alpha Vantage API is accessible.
        
        Returns:
            True if healthy
        """
        try:
            response = await self._make_request(
                "GLOBAL_QUOTE",
                {"function": "GLOBAL_QUOTE", "symbol": "IBM"},
                use_cache=False,
            )
            return response.error is None
        except Exception as e:
            logger.error(f"Alpha Vantage health check failed: {e}")
            return False
    
    async def get_quote(self, symbol: str) -> DataSourceResponse:
        """Get current quote for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Quote data
        """
        return await self._make_request(
            "GLOBAL_QUOTE",
            {"function": "GLOBAL_QUOTE", "symbol": symbol},
        )
    
    async def get_company_overview(self, symbol: str) -> DataSourceResponse:
        """Get company overview and key metrics.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Company overview data
        """
        return await self._make_request(
            "OVERVIEW",
            {"function": "OVERVIEW", "symbol": symbol},
        )
    
    async def get_income_statement(self, symbol: str) -> DataSourceResponse:
        """Get annual and quarterly income statements.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Income statement data
        """
        return await self._make_request(
            "INCOME_STATEMENT",
            {"function": "INCOME_STATEMENT", "symbol": symbol},
        )
    
    async def get_balance_sheet(self, symbol: str) -> DataSourceResponse:
        """Get annual and quarterly balance sheets.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Balance sheet data
        """
        return await self._make_request(
            "BALANCE_SHEET",
            {"function": "BALANCE_SHEET", "symbol": symbol},
        )
    
    async def get_cash_flow(self, symbol: str) -> DataSourceResponse:
        """Get annual and quarterly cash flow statements.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Cash flow data
        """
        return await self._make_request(
            "CASH_FLOW",
            {"function": "CASH_FLOW", "symbol": symbol},
        )
    
    async def get_daily_prices(self, symbol: str, output_size: str = "compact") -> DataSourceResponse:
        """Get daily price history.
        
        Args:
            symbol: Stock symbol
            output_size: "compact" (last 100) or "full" (20+ years)
            
        Returns:
            Daily price data
        """
        return await self._make_request(
            "TIME_SERIES_DAILY",
            {
                "function": "TIME_SERIES_DAILY",
                "symbol": symbol,
                "outputsize": output_size,
            },
        )
    
    async def get_earnings(self, symbol: str) -> DataSourceResponse:
        """Get earnings data.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Earnings data
        """
        return await self._make_request(
            "EARNINGS",
            {"function": "EARNINGS", "symbol": symbol},
        )
    
    async def get_insider_transactions(self, symbol: str) -> DataSourceResponse:
        """Get insider transactions.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Insider transaction data
        """
        return await self._make_request(
            "INSIDER_TRANSACTIONS",
            {"function": "INSIDER_TRANSACTIONS", "symbol": symbol},
        )
    
    async def get_comprehensive_data(self, symbol: str) -> Dict[str, DataSourceResponse]:
        """Get comprehensive data for a symbol.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary of all data types
        """
        import asyncio
        
        tasks = {
            "quote": self.get_quote(symbol),
            "overview": self.get_company_overview(symbol),
            "income": self.get_income_statement(symbol),
            "balance": self.get_balance_sheet(symbol),
            "cash_flow": self.get_cash_flow(symbol),
            "earnings": self.get_earnings(symbol),
        }
        
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        
        return {
            key: result if not isinstance(result, Exception) else None
            for key, result in zip(tasks.keys(), results)
        }