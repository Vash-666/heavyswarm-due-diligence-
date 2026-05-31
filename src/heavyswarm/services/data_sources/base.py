"""Base class for data source clients."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DataSourceConfig:
    """Configuration for a data source client."""
    
    api_key: str
    base_url: str
    timeout_seconds: int = 30
    retry_attempts: int = 3
    rate_limit_per_minute: int = 60
    cache_ttl_minutes: int = 60


@dataclass
class DataSourceResponse:
    """Response from a data source."""
    
    data: Any
    source: str
    retrieved_at: datetime
    cached: bool = False
    error: Optional[str] = None


class BaseDataSource(ABC):
    """Base class for all data source clients."""
    
    def __init__(self, config: DataSourceConfig):
        """Initialize the data source client.
        
        Args:
            config: Data source configuration
        """
        self.config = config
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._request_times: List[datetime] = []
        self._semaphore = asyncio.Semaphore(10)  # Limit concurrent requests
    
    async def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        now = datetime.utcnow()
        
        # Remove requests older than 1 minute
        cutoff = now - timedelta(minutes=1)
        self._request_times = [t for t in self._request_times if t > cutoff]
        
        # Check if we're at the limit
        if len(self._request_times) >= self.config.rate_limit_per_minute:
            # Wait until we can make another request
            sleep_time = 60 - (now - self._request_times[0]).total_seconds()
            if sleep_time > 0:
                logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
        
        self._request_times.append(datetime.utcnow())
    
    def _get_cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        """Generate cache key for a request.
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            
        Returns:
            Cache key string
        """
        import hashlib
        import json
        
        key_data = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _get_cached(self, cache_key: str) -> Optional[DataSourceResponse]:
        """Get cached response if available and not expired.
        
        Args:
            cache_key: Cache key
            
        Returns:
            Cached response or None
        """
        if cache_key not in self._cache:
            return None
        
        cached = self._cache[cache_key]
        age = datetime.utcnow() - cached["retrieved_at"]
        
        if age > timedelta(minutes=self.config.cache_ttl_minutes):
            del self._cache[cache_key]
            return None
        
        return DataSourceResponse(
            data=cached["data"],
            source=self.__class__.__name__,
            retrieved_at=cached["retrieved_at"],
            cached=True,
        )
    
    def _set_cached(self, cache_key: str, data: Any) -> None:
        """Cache a response.
        
        Args:
            cache_key: Cache key
            data: Response data
        """
        self._cache[cache_key] = {
            "data": data,
            "retrieved_at": datetime.utcnow(),
        }
    
    async def _make_request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_cache: bool = True,
    ) -> DataSourceResponse:
        """Make a rate-limited request with caching.
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            use_cache: Whether to use cache
            
        Returns:
            Data source response
        """
        params = params or {}
        cache_key = self._get_cache_key(endpoint, params)
        
        # Check cache
        if use_cache:
            cached = self._get_cached(cache_key)
            if cached:
                return cached
        
        # Rate limit
        await self._rate_limit()
        
        # Make request with semaphore
        async with self._semaphore:
            for attempt in range(self.config.retry_attempts):
                try:
                    data = await self._fetch(endpoint, params)
                    
                    # Cache successful response
                    self._set_cached(cache_key, data)
                    
                    return DataSourceResponse(
                        data=data,
                        source=self.__class__.__name__,
                        retrieved_at=datetime.utcnow(),
                        cached=False,
                    )
                    
                except Exception as e:
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.config.retry_attempts}): {e}"
                    )
                    
                    if attempt < self.config.retry_attempts - 1:
                        wait_time = 2 ** attempt  # Exponential backoff
                        await asyncio.sleep(wait_time)
                    else:
                        return DataSourceResponse(
                            data=None,
                            source=self.__class__.__name__,
                            retrieved_at=datetime.utcnow(),
                            error=str(e),
                        )
        
        return DataSourceResponse(
            data=None,
            source=self.__class__.__name__,
            retrieved_at=datetime.utcnow(),
            error="Request failed after all retries",
        )
    
    @abstractmethod
    async def _fetch(self, endpoint: str, params: Dict[str, Any]) -> Any:
        """Fetch data from the API.
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            
        Returns:
            Response data
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the data source is healthy.
        
        Returns:
            True if healthy
        """
        pass