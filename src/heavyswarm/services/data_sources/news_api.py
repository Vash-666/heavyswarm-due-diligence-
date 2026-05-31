"""News API client for news and sentiment data."""

from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

import aiohttp

from heavyswarm.services.data_sources.base import BaseDataSource, DataSourceConfig, DataSourceResponse
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class NewsAPIClient(BaseDataSource):
    """Client for news APIs (NewsAPI.org and backup sources).
    
    Provides:
    - News article search
    - Sentiment analysis
    - Source aggregation
    """
    
    def __init__(self, api_key: str):
        """Initialize News API client.
        
        Args:
            api_key: NewsAPI.org API key
        """
        config = DataSourceConfig(
            api_key=api_key,
            base_url="https://newsapi.org/v2",
            timeout_seconds=30,
            retry_attempts=3,
            rate_limit_per_minute=100,  # Developer plan limit
            cache_ttl_minutes=30,  # News gets stale
        )
        super().__init__(config)
    
    async def _fetch(self, endpoint: str, params: Dict[str, Any]) -> Any:
        """Fetch data from News API.
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            
        Returns:
            Response data
        """
        params["apiKey"] = self.config.api_key
        url = f"{self.config.base_url}/{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                # Check for API errors
                if data.get("status") == "error":
                    raise ValueError(f"NewsAPI error: {data.get('message', 'Unknown error')}")
                
                return data
    
    async def health_check(self) -> bool:
        """Check if News API is accessible.
        
        Returns:
            True if healthy
        """
        try:
            response = await self.search_news("stock market", page_size=1)
            return response.error is None
        except Exception as e:
            logger.error(f"NewsAPI health check failed: {e}")
            return False
    
    async def search_news(
        self,
        query: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        language: str = "en",
        sort_by: str = "publishedAt",
        page_size: int = 20,
        page: int = 1,
    ) -> DataSourceResponse:
        """Search for news articles.
        
        Args:
            query: Search query
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            language: Language code
            sort_by: Sort by "relevancy", "popularity", or "publishedAt"
            page_size: Results per page (max 100)
            page: Page number
            
        Returns:
            News articles
        """
        params = {
            "q": query,
            "language": language,
            "sortBy": sort_by,
            "pageSize": min(page_size, 100),
            "page": page,
        }
        
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        
        return await self._make_request("everything", params)
    
    async def get_top_headlines(
        self,
        query: Optional[str] = None,
        category: Optional[str] = None,
        country: str = "us",
        page_size: int = 20,
        page: int = 1,
    ) -> DataSourceResponse:
        """Get top headlines.
        
        Args:
            query: Search query
            category: Category (business, entertainment, general, health, science, sports, technology)
            country: Country code
            page_size: Results per page (max 100)
            page: Page number
            
        Returns:
            Top headlines
        """
        params = {
            "country": country,
            "pageSize": min(page_size, 100),
            "page": page,
        }
        
        if query:
            params["q"] = query
        if category:
            params["category"] = category
        
        return await self._make_request("top-headlines", params)
    
    async def get_company_news(
        self,
        ticker: str,
        company_name: Optional[str] = None,
        days_back: int = 30,
        page_size: int = 50,
    ) -> DataSourceResponse:
        """Get news for a specific company.
        
        Args:
            ticker: Stock ticker
            company_name: Company name for better search
            days_back: Number of days to look back
            page_size: Maximum articles to return
            
        Returns:
            Company news articles
        """
        # Build search query
        query = f"{ticker}"
        if company_name:
            query = f"({ticker} OR \"{company_name}\")"
        
        # Calculate date range
        to_date = datetime.utcnow()
        from_date = to_date - timedelta(days=days_back)
        
        response = await self.search_news(
            query=query,
            from_date=from_date.strftime("%Y-%m-%d"),
            to_date=to_date.strftime("%Y-%m-%d"),
            sort_by="publishedAt",
            page_size=page_size,
        )
        
        if response.error:
            return response
        
        # Process and enrich articles
        articles = response.data.get("articles", [])
        processed_articles = []
        
        for article in articles:
            processed_articles.append({
                "title": article.get("title"),
                "description": article.get("description"),
                "content": article.get("content"),
                "url": article.get("url"),
                "source": article.get("source", {}).get("name"),
                "published_at": article.get("publishedAt"),
                "author": article.get("author"),
            })
        
        return DataSourceResponse(
            data={
                "ticker": ticker,
                "total_results": response.data.get("totalResults", 0),
                "articles": processed_articles,
            },
            source="NewsAPIClient",
            retrieved_at=datetime.utcnow(),
            cached=response.cached,
        )
    
    async def get_market_news(
        self,
        category: str = "business",
        page_size: int = 20,
    ) -> DataSourceResponse:
        """Get general market news.
        
        Args:
            category: News category
            page_size: Number of articles
            
        Returns:
            Market news
        """
        return await self.get_top_headlines(
            category=category,
            page_size=page_size,
        )
    
    async def analyze_sentiment(
        self,
        ticker: str,
        days_back: int = 30,
    ) -> DataSourceResponse:
        """Analyze sentiment for a company based on news.
        
        Note: This is a basic implementation. For production,
        consider using a dedicated sentiment analysis service.
        
        Args:
            ticker: Stock ticker
            days_back: Days to analyze
            
        Returns:
            Sentiment analysis
        """
        news_response = await self.get_company_news(ticker, days_back=days_back)
        
        if news_response.error:
            return news_response
        
        articles = news_response.data.get("articles", [])
        
        # Simple keyword-based sentiment analysis
        # In production, use a proper NLP model
        positive_keywords = [
            "beat", "beats", "beaten", "outperform", "strong", "growth",
            "profit", "profits", "profitable", "gain", "gains", "surge",
            "surges", "rally", "rallies", "bullish", "upgrade", "upgrades",
            "positive", "optimistic", "success", "successful", "breakthrough",
        ]
        
        negative_keywords = [
            "miss", "misses", "missed", "underperform", "weak", "decline",
            "loss", "losses", "lose", "loses", "lost", "fall", "falls",
            "drop", "drops", "plunge", "plunges", "bearish", "downgrade",
            "downgrades", "negative", "pessimistic", "fail", "failed",
            "failure", "concern", "concerns", "worry", "worries", "risk",
        ]
        
        sentiment_scores = []
        
        for article in articles:
            text = f"{article.get('title', '')} {article.get('description', '')}".lower()
            
            positive_count = sum(1 for word in positive_keywords if word in text)
            negative_count = sum(1 for word in negative_keywords if word in text)
            
            if positive_count + negative_count > 0:
                score = (positive_count - negative_count) / (positive_count + negative_count)
            else:
                score = 0  # Neutral
            
            sentiment_scores.append({
                "title": article.get("title"),
                "published_at": article.get("published_at"),
                "sentiment_score": score,
                "positive_words": positive_count,
                "negative_words": negative_count,
            })
        
        # Calculate aggregate sentiment
        if sentiment_scores:
            avg_sentiment = sum(s["sentiment_score"] for s in sentiment_scores) / len(sentiment_scores)
            positive_articles = sum(1 for s in sentiment_scores if s["sentiment_score"] > 0.1)
            negative_articles = sum(1 for s in sentiment_scores if s["sentiment_score"] < -0.1)
            neutral_articles = len(sentiment_scores) - positive_articles - negative_articles
        else:
            avg_sentiment = 0
            positive_articles = negative_articles = neutral_articles = 0
        
        # Determine sentiment label
        if avg_sentiment > 0.2:
            sentiment_label = "positive"
        elif avg_sentiment < -0.2:
            sentiment_label = "negative"
        else:
            sentiment_label = "neutral"
        
        return DataSourceResponse(
            data={
                "ticker": ticker,
                "period_days": days_back,
                "aggregate_sentiment": avg_sentiment,
                "sentiment_label": sentiment_label,
                "article_counts": {
                    "total": len(articles),
                    "positive": positive_articles,
                    "negative": negative_articles,
                    "neutral": neutral_articles,
                },
                "article_sentiments": sentiment_scores[:20],  # Top 20
            },
            source="NewsAPIClient",
            retrieved_at=datetime.utcnow(),
            cached=news_response.cached,
        )