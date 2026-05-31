"""SEC EDGAR API client for financial filings."""

from typing import Any, Dict, List, Optional

import aiohttp

from heavyswarm.services.data_sources.base import BaseDataSource, DataSourceConfig, DataSourceResponse
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class SECEdgarClient(BaseDataSource):
    """Client for SEC EDGAR API.
    
    EDGAR API provides access to SEC filings including:
    - 10-K (Annual reports)
    - 10-Q (Quarterly reports)
    - 8-K (Current reports)
    - Proxy statements
    - Ownership reports
    
    Note: SEC EDGAR API does not require an API key but has rate limits.
    """
    
    def __init__(self, user_agent: str = "HeavySwarm Engine contact@example.com"):
        """Initialize SEC EDGAR client.
        
        Args:
            user_agent: User agent string (required by SEC)
        """
        config = DataSourceConfig(
            api_key="",  # Not required but field must exist
            base_url="https://www.sec.gov/Archives/edgar",
            timeout_seconds=30,
            retry_attempts=3,
            rate_limit_per_minute=10,  # SEC rate limit
            cache_ttl_minutes=60,  # Filings don't change
        )
        super().__init__(config)
        self.user_agent = user_agent
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers required by SEC.
        
        Returns:
            Headers dictionary
        """
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }
    
    async def _fetch(self, endpoint: str, params: Dict[str, Any]) -> Any:
        """Fetch data from SEC EDGAR API.
        
        Args:
            endpoint: API endpoint
            params: Request parameters
            
        Returns:
            Response data
        """
        url = f"{self.config.base_url}/{endpoint}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                params=params,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get("Content-Type", "")
                
                if "application/json" in content_type:
                    return await response.json()
                else:
                    return await response.text()
    
    async def health_check(self) -> bool:
        """Check if SEC EDGAR API is accessible.
        
        Returns:
            True if healthy
        """
        try:
            # Try to get company data for Apple
            response = await self.get_company_concept("AAPL", "us-gaap", "Revenues")
            return response.error is None
        except Exception as e:
            logger.error(f"SEC EDGAR health check failed: {e}")
            return False
    
    async def get_company_tickers(self) -> DataSourceResponse:
        """Get list of all company tickers and CIK numbers.
        
        Returns:
            Company tickers data
        """
        # This endpoint is on a different base URL
        url = "https://www.sec.gov/files/company_tickers.json"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                return DataSourceResponse(
                    data=data,
                    source="SECEdgarClient",
                    retrieved_at=__import__('datetime').datetime.utcnow(),
                    cached=False,
                )
    
    def _get_cik_from_ticker(self, ticker: str, tickers_data: Dict) -> Optional[str]:
        """Get CIK number from ticker symbol.
        
        Args:
            ticker: Stock ticker
            tickers_data: Tickers data from get_company_tickers
            
        Returns:
            CIK number or None
        """
        ticker_upper = ticker.upper()
        
        for entry in tickers_data.values():
            if entry.get("ticker", "").upper() == ticker_upper:
                cik = entry.get("cik_str")
                return str(cik).zfill(10)  # CIK must be 10 digits
        
        return None
    
    async def get_submissions(self, ticker: str) -> DataSourceResponse:
        """Get recent submissions (filings) for a company.
        
        Args:
            ticker: Stock ticker
            
        Returns:
            Submissions data
        """
        # First get CIK
        tickers_response = await self.get_company_tickers()
        if tickers_response.error:
            return tickers_response
        
        cik = self._get_cik_from_ticker(ticker, tickers_response.data)
        if not cik:
            return DataSourceResponse(
                data=None,
                source="SECEdgarClient",
                retrieved_at=__import__('datetime').datetime.utcnow(),
                error=f"Could not find CIK for ticker {ticker}",
            )
        
        # Use the new SEC API endpoint
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                return DataSourceResponse(
                    data=data,
                    source="SECEdgarClient",
                    retrieved_at=__import__('datetime').datetime.utcnow(),
                    cached=False,
                )
    
    async def get_company_facts(self, ticker: str) -> DataSourceResponse:
        """Get all company facts (XBRL data).
        
        Args:
            ticker: Stock ticker
            
        Returns:
            Company facts data
        """
        # First get CIK
        tickers_response = await self.get_company_tickers()
        if tickers_response.error:
            return tickers_response
        
        cik = self._get_cik_from_ticker(ticker, tickers_response.data)
        if not cik:
            return DataSourceResponse(
                data=None,
                source="SECEdgarClient",
                retrieved_at=__import__('datetime').datetime.utcnow(),
                error=f"Could not find CIK for ticker {ticker}",
            )
        
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                return DataSourceResponse(
                    data=data,
                    source="SECEdgarClient",
                    retrieved_at=__import__('datetime').datetime.utcnow(),
                    cached=False,
                )
    
    async def get_company_concept(
        self,
        ticker: str,
        taxonomy: str,
        concept: str,
    ) -> DataSourceResponse:
        """Get a specific concept/fact for a company.
        
        Args:
            ticker: Stock ticker
            taxonomy: Taxonomy (e.g., "us-gaap")
            concept: Concept name (e.g., "Revenues")
            
        Returns:
            Concept data
        """
        # First get CIK
        tickers_response = await self.get_company_tickers()
        if tickers_response.error:
            return tickers_response
        
        cik = self._get_cik_from_ticker(ticker, tickers_response.data)
        if not cik:
            return DataSourceResponse(
                data=None,
                source="SECEdgarClient",
                retrieved_at=__import__('datetime').datetime.utcnow(),
                error=f"Could not find CIK for ticker {ticker}",
            )
        
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/{taxonomy}/{concept}.json"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                return DataSourceResponse(
                    data=data,
                    source="SECEdgarClient",
                    retrieved_at=__import__('datetime').datetime.utcnow(),
                    cached=False,
                )
    
    async def get_filing_content(self, accession_number: str, cik: str) -> DataSourceResponse:
        """Get the content of a specific filing.
        
        Args:
            accession_number: Filing accession number
            cik: Company CIK number
            
        Returns:
            Filing content
        """
        # Format accession number (remove dashes)
        acc_no = accession_number.replace("-", "")
        
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{accession_number}-index.html"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=self.config.timeout_seconds),
            ) as response:
                response.raise_for_status()
                data = await response.text()
                
                return DataSourceResponse(
                    data=data,
                    source="SECEdgarClient",
                    retrieved_at=__import__('datetime').datetime.utcnow(),
                    cached=False,
                )
    
    async def get_recent_filings(
        self,
        ticker: str,
        form_types: Optional[List[str]] = None,
        limit: int = 10,
    ) -> DataSourceResponse:
        """Get recent filings of specific types.
        
        Args:
            ticker: Stock ticker
            form_types: List of form types (e.g., ["10-K", "10-Q"])
            limit: Maximum number of filings to return
            
        Returns:
            Recent filings data
        """
        response = await self.get_submissions(ticker)
        
        if response.error:
            return response
        
        data = response.data
        recent_filings = data.get("filings", {}).get("recent", {})
        
        forms = recent_filings.get("form", [])
        dates = recent_filings.get("filingDate", [])
        accession_numbers = recent_filings.get("accessionNumber", [])
        primary_documents = recent_filings.get("primaryDocument", [])
        
        filings = []
        for i, form in enumerate(forms):
            if form_types and form not in form_types:
                continue
            
            filings.append({
                "form": form,
                "filing_date": dates[i] if i < len(dates) else None,
                "accession_number": accession_numbers[i] if i < len(accession_numbers) else None,
                "primary_document": primary_documents[i] if i < len(primary_documents) else None,
            })
            
            if len(filings) >= limit:
                break
        
        return DataSourceResponse(
            data={
                "ticker": ticker,
                "cik": data.get("cik"),
                "filings": filings,
            },
            source="SECEdgarClient",
            retrieved_at=__import__('datetime').datetime.utcnow(),
            cached=False,
        )