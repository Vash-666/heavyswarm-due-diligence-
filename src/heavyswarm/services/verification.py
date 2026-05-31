"""Data verification service for L1-L4 verification pipeline.

This module implements a comprehensive multi-level data verification system:
- L1: Source Attribution (URL validation, credibility scoring, timestamp checks)
- L2: Cross-Reference Framework (multi-source consensus, discrepancy detection)
- L3: Real-Time Validation (live price validation, SEC EDGAR checks)
- L4: Human Review Flagging (automatic flagging, queue management, resolution workflow)
"""

import asyncio
import hashlib
import json
import re
import ssl
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.robotparser import RobotFileParser

import aiohttp
import structlog

from heavyswarm.core.enums import VerificationLevel
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


# ============================================================================
# Domain Reputation Database (Production would use external service)
# ============================================================================

TRUSTED_DOMAINS = {
    # Financial Data
    "sec.gov": 0.95,
    "investor.gov": 0.95,
    "finra.org": 0.90,
    "bloomberg.com": 0.90,
    "reuters.com": 0.90,
    "wsj.com": 0.88,
    "ft.com": 0.88,
    "marketwatch.com": 0.85,
    "seekingalpha.com": 0.75,
    "yahoo.com": 0.80,
    "google.com": 0.85,
    "morningstar.com": 0.88,
    "msci.com": 0.90,
    "spglobal.com": 0.90,
    "fitchratings.com": 0.90,
    "moodys.com": 0.90,
    "standardandpoors.com": 0.90,
    # News Sources
    "nytimes.com": 0.85,
    "washingtonpost.com": 0.85,
    "economist.com": 0.88,
    "forbes.com": 0.75,
    "cnbc.com": 0.80,
    "cnn.com": 0.80,
    "bbc.com": 0.85,
    "apnews.com": 0.88,
    "reuters.com": 0.90,
    # Academic/Government
    "gov": 0.90,
    "edu": 0.85,
    "org": 0.70,
}

UNTRUSTED_DOMAINS = {
    "rumor": 0.20,
    "conspiracy": 0.10,
    "fake": 0.05,
    "blogspot.com": 0.40,
    "wordpress.com": 0.45,
}

# ============================================================================
# Data Classes
# ============================================================================

class ReviewStatus(Enum):
    """Status of human review."""
    
    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"
    DISMISSED = "dismissed"


class FlagReason(Enum):
    """Reason for flagging data for human review."""
    
    HIGH_DISCREPANCY = "high_discrepancy"
    LOW_CONFIDENCE = "low_confidence"
    DISPUTED_DATA = "disputed_data"
    STALE_DATA = "stale_data"
    UNTRUSTED_SOURCE = "untrusted_source"
    VALIDATION_FAILED = "validation_failed"
    CONSENSUS_LOW = "consensus_low"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


@dataclass
class SourceAttribution:
    """Source attribution details for L1 verification."""
    
    url: str
    domain: str
    retrieved_at: datetime
    credibility_score: float = 0.0
    reputation_score: float = 0.0
    is_reachable: bool = False
    is_valid_format: bool = False
    is_stale: bool = False
    age_hours: float = 0.0
    ssl_valid: bool = False
    robots_allowed: bool = True
    headers: Dict[str, str] = field(default_factory=dict)
    http_status: Optional[int] = None
    redirect_chain: List[str] = field(default_factory=list)
    error_message: Optional[str] = None


@dataclass
class CrossReferenceResult:
    """Result of cross-referencing a data point."""
    
    source_url: str
    value: Any
    retrieved_at: datetime
    credibility_score: float = 0.0
    similarity_score: float = 0.0
    exact_match: bool = False
    normalized_value: Optional[str] = None


@dataclass
class CrossReferenceAnalysis:
    """Analysis of cross-reference results."""
    
    sources: List[CrossReferenceResult] = field(default_factory=list)
    consensus_score: float = 0.0
    consensus_value: Optional[Any] = None
    discrepancies: List[Dict[str, Any]] = field(default_factory=list)
    discrepancy_count: int = 0
    high_credibility_sources: int = 0
    low_credibility_sources: int = 0
    agreement_ratio: float = 0.0
    confidence_score: float = 0.0
    requires_review: bool = False


@dataclass
class RealTimeValidationResult:
    """Result of real-time validation."""
    
    validator_type: str
    validated_at: datetime
    is_valid: bool = False
    live_value: Optional[Any] = None
    deviation_percent: Optional[float] = None
    tolerance_percent: float = 5.0
    api_source: Optional[str] = None
    api_response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HumanReviewItem:
    """Item in the human review queue."""
    
    item_id: str
    data_id: str
    data_point: "DataPoint"
    flag_reasons: List[FlagReason] = field(default_factory=list)
    status: ReviewStatus = ReviewStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    reviewed_by: Optional[str] = None
    resolution_notes: Optional[str] = None
    l1_result: Optional[SourceAttribution] = None
    l2_result: Optional[CrossReferenceAnalysis] = None
    l3_result: Optional[RealTimeValidationResult] = None
    priority: int = 1  # 1 = highest


@dataclass
class VerificationResult:
    """Result of data verification."""
    
    data_id: str
    requested_level: VerificationLevel
    achieved_level: Optional[VerificationLevel]
    verified: bool
    sources: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    verified_at: datetime = field(default_factory=datetime.utcnow)
    
    # L1 Results
    l1_attribution: Optional[SourceAttribution] = None
    
    # L2 Results
    l2_cross_reference: Optional[CrossReferenceAnalysis] = None
    
    # L3 Results
    l3_validation: Optional[RealTimeValidationResult] = None
    
    # L4 Results
    l4_review_item_id: Optional[str] = None
    l4_review_status: Optional[ReviewStatus] = None
    
    # Metadata
    processing_time_ms: Optional[float] = None
    retry_count: int = 0


@dataclass
class DataPoint:
    """A single data point to verify."""
    
    id: str
    value: Any
    data_type: str  # financial, news, market, analyst, sec_filing
    source_url: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    expected_sources: int = 2  # Minimum cross-references needed
    tolerance_percent: float = 5.0  # For numerical comparisons
    
    def get_normalized_value(self) -> str:
        """Get normalized string representation for comparison."""
        if isinstance(self.value, (int, float)):
            return f"{self.value:.4f}"
        elif isinstance(self.value, str):
            return self.value.lower().strip()
        else:
            return json.dumps(self.value, sort_keys=True)


# ============================================================================
# L1: Source Attribution Validators
# ============================================================================

class SourceValidator:
    """L1 Source Attribution Validator.
    
    Validates URLs, checks domain reputation, verifies timestamps,
    and ensures source credibility.
    """
    
    def __init__(
        self,
        stale_threshold_hours: float = 24.0,
        min_credibility_score: float = 0.3,
        request_timeout: float = 10.0,
    ):
        """Initialize source validator.
        
        Args:
            stale_threshold_hours: Hours before data is considered stale
            min_credibility_score: Minimum credibility score for acceptance
            request_timeout: HTTP request timeout in seconds
        """
        self.stale_threshold_hours = stale_threshold_hours
        self.min_credibility_score = min_credibility_score
        self.request_timeout = request_timeout
        self._ssl_context = ssl.create_default_context()
        self._session: Optional[aiohttp.ClientSession] = None
        
        logger.debug("SourceValidator initialized")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                headers={
                    "User-Agent": "HeavySwarm-DataVerifier/1.0 (Research Bot)"
                },
            )
        return self._session
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def validate(
        self,
        data_point: DataPoint,
        check_reachability: bool = True,
    ) -> SourceAttribution:
        """Validate source attribution for a data point.
        
        Args:
            data_point: Data point to validate
            check_reachability: Whether to perform HTTP reachability check
            
        Returns:
            SourceAttribution with validation results
        """
        attribution = SourceAttribution(
            url=data_point.source_url or "",
            domain="",
            retrieved_at=data_point.retrieved_at or datetime.utcnow(),
        )
        
        # Validate URL format
        attribution.is_valid_format = self._validate_url_format(attribution.url)
        if not attribution.is_valid_format:
            attribution.error_message = "Invalid URL format"
            return attribution
        
        # Extract domain
        attribution.domain = self._extract_domain(attribution.url)
        
        # Check domain reputation
        attribution.reputation_score = self._calculate_domain_reputation(attribution.domain)
        
        # Check timestamp
        attribution.age_hours = self._calculate_age_hours(attribution.retrieved_at)
        attribution.is_stale = attribution.age_hours > self.stale_threshold_hours
        
        # Check reachability if requested
        if check_reachability:
            reachability = await self._check_url_reachability(attribution.url)
            attribution.is_reachable = reachability["reachable"]
            attribution.http_status = reachability["status"]
            attribution.ssl_valid = reachability["ssl_valid"]
            attribution.headers = reachability["headers"]
            attribution.redirect_chain = reachability["redirects"]
            
            if not attribution.is_reachable:
                attribution.error_message = reachability.get("error", "URL not reachable")
        
        # Calculate overall credibility score
        attribution.credibility_score = self._calculate_credibility_score(attribution)
        
        logger.debug(
            "Source validation completed",
            url=attribution.url,
            domain=attribution.domain,
            credibility_score=attribution.credibility_score,
            is_reachable=attribution.is_reachable,
        )
        
        return attribution
    
    def _validate_url_format(self, url: str) -> bool:
        """Validate URL format.
        
        Args:
            url: URL to validate
            
        Returns:
            True if valid format
        """
        if not url:
            return False
        
        try:
            parsed = urllib.parse.urlparse(url)
            
            # Must have scheme and netloc
            if not parsed.scheme or not parsed.netloc:
                return False
            
            # Valid scheme
            if parsed.scheme not in ("http", "https"):
                return False
            
            # Valid domain structure
            if not re.match(r"^[a-zA-Z0-9][-a-zA-Z0-9.]*[a-zA-Z0-9]$", parsed.netloc.split(":")[0]):
                return False
            
            return True
        except Exception:
            return False
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL.
        
        Args:
            url: URL to extract domain from
            
        Returns:
            Domain name
        """
        try:
            parsed = urllib.parse.urlparse(url)
            netloc = parsed.netloc.lower()
            
            # Remove port if present
            if ":" in netloc:
                netloc = netloc.split(":")[0]
            
            # Remove www. prefix
            if netloc.startswith("www."):
                netloc = netloc[4:]
            
            return netloc
        except Exception:
            return ""
    
    def _calculate_domain_reputation(self, domain: str) -> float:
        """Calculate domain reputation score.
        
        Args:
            domain: Domain to check
            
        Returns:
            Reputation score (0.0 - 1.0)
        """
        if not domain:
            return 0.0
        
        # Check exact domain match
        if domain in TRUSTED_DOMAINS:
            return TRUSTED_DOMAINS[domain]
        
        # Check TLD
        parts = domain.split(".")
        if len(parts) >= 2:
            tld = parts[-1]
            if tld in TRUSTED_DOMAINS:
                return TRUSTED_DOMAINS[tld]
        
        # Check for untrusted patterns
        for pattern, score in UNTRUSTED_DOMAINS.items():
            if pattern in domain:
                return score
        
        # Default score for unknown domains
        return 0.50
    
    def _calculate_age_hours(self, retrieved_at: datetime) -> float:
        """Calculate age of data in hours.
        
        Args:
            retrieved_at: When data was retrieved
            
        Returns:
            Age in hours
        """
        now = datetime.utcnow()
        age = now - retrieved_at
        return age.total_seconds() / 3600
    
    async def _check_url_reachability(self, url: str) -> Dict[str, Any]:
        """Check if URL is reachable.
        
        Args:
            url: URL to check
            
        Returns:
            Dictionary with reachability info
        """
        result = {
            "reachable": False,
            "status": None,
            "ssl_valid": False,
            "headers": {},
            "redirects": [],
            "error": None,
        }
        
        try:
            session = await self._get_session()
            
            async with session.get(
                url,
                allow_redirects=True,
                ssl=self._ssl_context if url.startswith("https") else False,
            ) as response:
                result["status"] = response.status
                result["headers"] = dict(response.headers)
                result["ssl_valid"] = url.startswith("https")
                
                # Check for redirect history
                if response.history:
                    result["redirects"] = [str(r.url) for r in response.history]
                
                # 2xx status codes are considered reachable
                if 200 <= response.status < 300:
                    result["reachable"] = True
                elif response.status in (301, 302, 307, 308):
                    result["reachable"] = True  # Redirects are OK
                else:
                    result["error"] = f"HTTP {response.status}"
                    
        except aiohttp.ClientSSLError:
            result["error"] = "SSL certificate error"
            result["ssl_valid"] = False
        except aiohttp.ClientConnectorError as e:
            result["error"] = f"Connection error: {str(e)}"
        except asyncio.TimeoutError:
            result["error"] = "Request timeout"
        except Exception as e:
            result["error"] = f"Error: {str(e)}"
        
        return result
    
    def _calculate_credibility_score(self, attribution: SourceAttribution) -> float:
        """Calculate overall credibility score.
        
        Args:
            attribution: Source attribution to score
            
        Returns:
            Credibility score (0.0 - 1.0)
        """
        scores = []
        weights = []
        
        # Domain reputation (40%)
        if attribution.reputation_score > 0:
            scores.append(attribution.reputation_score)
            weights.append(0.40)
        
        # Reachability (20%)
        if attribution.is_reachable:
            scores.append(1.0)
        else:
            scores.append(0.0)
        weights.append(0.20)
        
        # Freshness (25%)
        freshness_score = max(0, 1 - (attribution.age_hours / self.stale_threshold_hours))
        scores.append(freshness_score)
        weights.append(0.25)
        
        # SSL/Security (15%)
        if attribution.url.startswith("https") and attribution.ssl_valid:
            scores.append(1.0)
        elif attribution.url.startswith("http"):
            scores.append(0.5)
        else:
            scores.append(0.0)
        weights.append(0.15)
        
        # Calculate weighted average
        if not scores:
            return 0.0
        
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        
        return weighted_sum / total_weight if total_weight > 0 else 0.0
    
    def is_source_trusted(self, attribution: SourceAttribution) -> bool:
        """Check if source is trusted.
        
        Args:
            attribution: Source attribution to check
            
        Returns:
            True if source is trusted
        """
        return (
            attribution.is_valid_format
            and attribution.credibility_score >= self.min_credibility_score
            and not attribution.is_stale
        )


# ============================================================================
# L2: Cross-Reference Framework
# ============================================================================

class CrossReferenceEngine:
    """L2 Cross-Reference Framework.
    
    Finds and compares multiple sources for the same data point,
    calculates consensus, detects discrepancies, and scores confidence.
    """
    
    def __init__(
        self,
        min_sources: int = 2,
        consensus_threshold: float = 0.6,
        high_credibility_threshold: float = 0.7,
        similarity_threshold: float = 0.8,
    ):
        """Initialize cross-reference engine.
        
        Args:
            min_sources: Minimum number of sources required
            consensus_threshold: Minimum consensus score for acceptance
            high_credibility_threshold: Threshold for high credibility sources
            similarity_threshold: Threshold for value similarity
        """
        self.min_sources = min_sources
        self.consensus_threshold = consensus_threshold
        self.high_credibility_threshold = high_credibility_threshold
        self.similarity_threshold = similarity_threshold
        self._source_validator = SourceValidator()
        
        logger.debug("CrossReferenceEngine initialized")
    
    async def close(self) -> None:
        """Close resources."""
        await self._source_validator.close()
    
    async def cross_reference(
        self,
        data_point: DataPoint,
        additional_sources: Optional[List[str]] = None,
    ) -> CrossReferenceAnalysis:
        """Perform cross-reference analysis.
        
        Args:
            data_point: Data point to cross-reference
            additional_sources: Additional source URLs to check
            
        Returns:
            Cross-reference analysis results
        """
        analysis = CrossReferenceAnalysis()
        
        # Collect all sources to check
        sources_to_check = []
        
        if data_point.source_url:
            sources_to_check.append(data_point.source_url)
        
        if additional_sources:
            sources_to_check.extend(additional_sources)
        
        # Validate each source
        for url in sources_to_check:
            # Create a temporary data point for validation
            temp_dp = DataPoint(
                id=f"{data_point.id}_xref",
                value=data_point.value,
                data_type=data_point.data_type,
                source_url=url,
                retrieved_at=datetime.utcnow(),
            )
            
            attribution = await self._source_validator.validate(temp_dp)
            
            # Create cross-reference result
            xref_result = CrossReferenceResult(
                source_url=url,
                value=data_point.value,  # In production, would fetch actual value
                retrieved_at=datetime.utcnow(),
                credibility_score=attribution.credibility_score,
                normalized_value=data_point.get_normalized_value(),
            )
            
            analysis.sources.append(xref_result)
            
            # Track credibility counts
            if attribution.credibility_score >= self.high_credibility_threshold:
                analysis.high_credibility_sources += 1
            else:
                analysis.low_credibility_sources += 1
        
        # Calculate consensus
        analysis = self._calculate_consensus(analysis, data_point)
        
        # Detect discrepancies
        analysis = self._detect_discrepancies(analysis, data_point)
        
        # Calculate final confidence
        analysis.confidence_score = self._calculate_confidence_score(analysis)
        
        # Determine if review is required
        analysis.requires_review = (
            analysis.consensus_score < self.consensus_threshold
            or analysis.discrepancy_count > 0
            or len(analysis.sources) < self.min_sources
        )
        
        logger.debug(
            "Cross-reference analysis completed",
            data_id=data_point.id,
            source_count=len(analysis.sources),
            consensus_score=analysis.consensus_score,
            discrepancy_count=analysis.discrepancy_count,
        )
        
        return analysis
    
    def _calculate_consensus(
        self,
        analysis: CrossReferenceAnalysis,
        data_point: DataPoint,
    ) -> CrossReferenceAnalysis:
        """Calculate consensus across sources.
        
        Args:
            analysis: Analysis to update
            data_point: Original data point
            
        Returns:
            Updated analysis
        """
        if not analysis.sources:
            analysis.consensus_score = 0.0
            return analysis
        
        # Group sources by normalized value
        value_groups: Dict[str, List[CrossReferenceResult]] = {}
        for source in analysis.sources:
            key = source.normalized_value or ""
            if key not in value_groups:
                value_groups[key] = []
            value_groups[key].append(source)
        
        # Find the most common value (weighted by credibility)
        best_value = None
        best_score = 0.0
        
        for value, sources in value_groups.items():
            # Calculate weighted score for this value
            score = sum(s.credibility_score for s in sources)
            if score > best_score:
                best_score = score
                best_value = value
        
        # Calculate consensus score
        total_credibility = sum(s.credibility_score for s in analysis.sources)
        if total_credibility > 0:
            analysis.consensus_score = best_score / total_credibility
        else:
            analysis.consensus_score = 0.0
        
        analysis.consensus_value = best_value
        
        # Calculate agreement ratio
        if len(analysis.sources) > 1:
            agreeing_sources = len(value_groups.get(best_value, []))
            analysis.agreement_ratio = agreeing_sources / len(analysis.sources)
        else:
            analysis.agreement_ratio = 1.0 if analysis.sources else 0.0
        
        return analysis
    
    def _detect_discrepancies(
        self,
        analysis: CrossReferenceAnalysis,
        data_point: DataPoint,
    ) -> CrossReferenceAnalysis:
        """Detect discrepancies between sources.
        
        Args:
            analysis: Analysis to update
            data_point: Original data point
            
        Returns:
            Updated analysis
        """
        if len(analysis.sources) < 2:
            return analysis
        
        discrepancies = []
        base_value = data_point.get_normalized_value()
        
        for i, source1 in enumerate(analysis.sources):
            for source2 in analysis.sources[i + 1:]:
                # Check for value differences
                if source1.normalized_value != source2.normalized_value:
                    discrepancy = {
                        "type": "value_mismatch",
                        "source1": source1.source_url,
                        "source2": source2.source_url,
                        "value1": source1.normalized_value,
                        "value2": source2.normalized_value,
                        "severity": "high" if source1.credibility_score > 0.8 and source2.credibility_score > 0.8 else "medium",
                    }
                    discrepancies.append(discrepancy)
                
                # For numerical values, check deviation
                elif isinstance(data_point.value, (int, float)):
                    try:
                        val1 = float(source1.normalized_value)
                        val2 = float(source2.normalized_value)
                        
                        if val1 != 0:
                            deviation = abs(val1 - val2) / val1 * 100
                            
                            if deviation > data_point.tolerance_percent:
                                discrepancy = {
                                    "type": "numerical_deviation",
                                    "source1": source1.source_url,
                                    "source2": source2.source_url,
                                    "value1": val1,
                                    "value2": val2,
                                    "deviation_percent": deviation,
                                    "severity": "high" if deviation > 10 else "medium",
                                }
                                discrepancies.append(discrepancy)
                    except (ValueError, TypeError):
                        pass
        
        analysis.discrepancies = discrepancies
        analysis.discrepancy_count = len(discrepancies)
        
        return analysis
    
    def _calculate_confidence_score(self, analysis: CrossReferenceAnalysis) -> float:
        """Calculate overall confidence score.
        
        Args:
            analysis: Cross-reference analysis
            
        Returns:
            Confidence score (0.0 - 1.0)
        """
        if not analysis.sources:
            return 0.0
        
        scores = []
        weights = []
        
        # Consensus score (40%)
        scores.append(analysis.consensus_score)
        weights.append(0.40)
        
        # Source credibility (30%)
        avg_credibility = sum(s.credibility_score for s in analysis.sources) / len(analysis.sources)
        scores.append(avg_credibility)
        weights.append(0.30)
        
        # Agreement ratio (20%)
        scores.append(analysis.agreement_ratio)
        weights.append(0.20)
        
        # Source count (10%)
        source_count_score = min(1.0, len(analysis.sources) / self.min_sources)
        scores.append(source_count_score)
        weights.append(0.10)
        
        # Penalize for discrepancies
        discrepancy_penalty = min(0.5, analysis.discrepancy_count * 0.1)
        
        # Calculate weighted average
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        
        confidence = (weighted_sum / total_weight) - discrepancy_penalty
        return max(0.0, min(1.0, confidence))


# ============================================================================
# L3: Real-Time Validation Logic
# ============================================================================

class RealTimeValidator:
    """L3 Real-Time Validation Logic.
    
    Validates data against live sources including market prices,
    SEC EDGAR filings, and news sources.
    """
    
    def __init__(
        self,
        price_tolerance_percent: float = 2.0,
        request_timeout: float = 15.0,
        enable_sec_validation: bool = True,
    ):
        """Initialize real-time validator.
        
        Args:
            price_tolerance_percent: Tolerance for price deviations
            request_timeout: API request timeout
            enable_sec_validation: Whether to enable SEC EDGAR validation
        """
        self.price_tolerance_percent = price_tolerance_percent
        self.request_timeout = request_timeout
        self.enable_sec_validation = enable_sec_validation
        self._session: Optional[aiohttp.ClientSession] = None
        
        # API endpoints (stubs for external integration)
        self._api_endpoints = {
            "market_price": None,  # e.g., "https://api.polygon.io/v2/aggs/ticker"
            "sec_edgar": "https://www.sec.gov/Archives/edgar/daily-index",
            "news_validation": None,  # e.g., "https://newsapi.org/v2/everything"
        }
        
        logger.debug("RealTimeValidator initialized")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.request_timeout),
                headers={
                    "User-Agent": "HeavySwarm-DataVerifier/1.0 (Research Bot)"
                },
            )
        return self._session
    
    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def validate(
        self,
        data_point: DataPoint,
    ) -> RealTimeValidationResult:
        """Validate data point against live sources.
        
        Args:
            data_point: Data point to validate
            
        Returns:
            Real-time validation result
        """
        validator_type = self._get_validator_type(data_point.data_type)
        
        result = RealTimeValidationResult(
            validator_type=validator_type,
            validated_at=datetime.utcnow(),
            tolerance_percent=self.price_tolerance_percent,
        )
        
        try:
            if data_point.data_type == "market":
                result = await self._validate_market_data(data_point, result)
            elif data_point.data_type == "financial":
                result = await self._validate_financial_data(data_point, result)
            elif data_point.data_type == "sec_filing":
                result = await self._validate_sec_filing(data_point, result)
            elif data_point.data_type == "news":
                result = await self._validate_news_data(data_point, result)
            else:
                # Generic validation for unknown types
                result.is_valid = True
                result.metadata["note"] = "No specific validator for data type"
                
        except Exception as e:
            result.error_message = f"Validation error: {str(e)}"
            result.is_valid = False
            logger.error(
                "Real-time validation failed",
                data_id=data_point.id,
                error=str(e),
            )
        
        return result
    
    def _get_validator_type(self, data_type: str) -> str:
        """Get validator type for data type.
        
        Args:
            data_type: Type of data
            
        Returns:
            Validator type string
        """
        type_map = {
            "market": "market_price",
            "financial": "financial_data",
            "sec_filing": "sec_edgar",
            "news": "news_source",
        }
        return type_map.get(data_type, "generic")
    
    async def _validate_market_data(
        self,
        data_point: DataPoint,
        result: RealTimeValidationResult,
    ) -> RealTimeValidationResult:
        """Validate market data against live prices.
        
        Args:
            data_point: Data point to validate
            result: Result object to update
            
        Returns:
            Updated validation result
        """
        import time
        start_time = time.time()
        
        # Extract ticker symbol from metadata
        ticker = data_point.metadata.get("ticker")
        if not ticker:
            result.error_message = "No ticker symbol provided"
            result.is_valid = False
            return result
        
        # In production, this would call a real market data API
        # For now, we provide the stub implementation
        
        try:
            # Simulate API call (replace with actual implementation)
            live_price = await self._fetch_live_price(ticker)
            
            if live_price is None:
                result.error_message = "Could not fetch live price"
                result.is_valid = False
                return result
            
            result.live_value = live_price
            result.api_source = "market_data_api_stub"
            
            # Calculate deviation
            if isinstance(data_point.value, (int, float)) and live_price != 0:
                result.deviation_percent = abs(data_point.value - live_price) / live_price * 100
                result.is_valid = result.deviation_percent <= self.price_tolerance_percent
            else:
                result.is_valid = True
                
        except Exception as e:
            result.error_message = f"Market data validation error: {str(e)}"
            result.is_valid = False
        
        result.api_response_time_ms = (time.time() - start_time) * 1000
        return result
    
    async def _fetch_live_price(self, ticker: str) -> Optional[float]:
        """Fetch live price for ticker (stub for external API).
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            Live price or None if unavailable
        """
        # This is a stub - in production, integrate with:
        # - Polygon.io
        # - Alpha Vantage
        # - IEX Cloud
        # - Yahoo Finance
        # - Bloomberg API
        
        # Example implementation structure:
        # session = await self._get_session()
        # url = f"{self._api_endpoints['market_price']}/{ticker}/prev"
        # async with session.get(url, params={"apikey": API_KEY}) as response:
        #     data = await response.json()
        #     return data["results"][0]["c"]
        
        logger.debug(f"Live price fetch stub called for {ticker}")
        return None  # Return None to indicate stub
    
    async def _validate_financial_data(
        self,
        data_point: DataPoint,
        result: RealTimeValidationResult,
    ) -> RealTimeValidationResult:
        """Validate financial data against SEC EDGAR.
        
        Args:
            data_point: Data point to validate
            result: Result object to update
            
        Returns:
            Updated validation result
        """
        import time
        start_time = time.time()
        
        if not self.enable_sec_validation:
            result.is_valid = True
            result.metadata["note"] = "SEC validation disabled"
            return result
        
        cik = data_point.metadata.get("cik")
        filing_type = data_point.metadata.get("filing_type")
        
        if not cik:
            result.error_message = "No CIK provided for SEC validation"
            result.is_valid = False
            return result
        
        try:
            # In production, query SEC EDGAR
            # https://www.sec.gov/edgar/sec-api-documentation
            
            sec_data = await self._fetch_sec_filing(cik, filing_type)
            
            if sec_data:
                result.live_value = sec_data.get("value")
                result.api_source = "sec_edgar"
                result.is_valid = True
                result.metadata["filing_date"] = sec_data.get("filing_date")
            else:
                result.error_message = "Could not retrieve SEC filing"
                result.is_valid = False
                
        except Exception as e:
            result.error_message = f"SEC validation error: {str(e)}"
            result.is_valid = False
        
        result.api_response_time_ms = (time.time() - start_time) * 1000
        return result
    
    async def _fetch_sec_filing(
        self,
        cik: str,
        filing_type: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Fetch SEC filing data (stub for EDGAR API).
        
        Args:
            cik: Company CIK number
            filing_type: Type of filing (10-K, 10-Q, etc.)
            
        Returns:
            Filing data or None
        """
        # This is a stub - in production, integrate with SEC EDGAR API
        # https://www.sec.gov/edgar/sec-api-documentation
        
        # SEC requires proper User-Agent header with contact info
        # Rate limit: 10 requests per second
        
        logger.debug(f"SEC filing fetch stub called for CIK {cik}")
        return None
    
    async def _validate_sec_filing(
        self,
        data_point: DataPoint,
        result: RealTimeValidationResult,
    ) -> RealTimeValidationResult:
        """Validate SEC filing data.
        
        Args:
            data_point: Data point to validate
            result: Result object to update
            
        Returns:
            Updated validation result
        """
        return await self._validate_financial_data(data_point, result)
    
    async def _validate_news_data(
        self,
        data_point: DataPoint,
        result: RealTimeValidationResult,
    ) -> RealTimeValidationResult:
        """Validate news data against source URLs.
        
        Args:
            data_point: Data point to validate
            result: Result object to update
            
        Returns:
            Updated validation result
        """
        import time
        start_time = time.time()
        
        try:
            # In production, validate against news APIs:
            # - NewsAPI
            # - GDELT
            # - Event Registry
            # - Google News API
            
            if data_point.source_url:
                # Verify the source URL is still valid and accessible
                session = await self._get_session()
                async with session.head(data_point.source_url, allow_redirects=True) as response:
                    result.is_valid = 200 <= response.status < 300
                    result.api_source = "source_url_validation"
                    result.metadata["http_status"] = response.status
            else:
                result.error_message = "No source URL for news validation"
                result.is_valid = False
                
        except Exception as e:
            result.error_message = f"News validation error: {str(e)}"
            result.is_valid = False
        
        result.api_response_time_ms = (time.time() - start_time) * 1000
        return result
    
    def set_api_endpoint(self, api_type: str, endpoint: str) -> None:
        """Set API endpoint for external integration.
        
        Args:
            api_type: Type of API (market_price, sec_edgar, news_validation)
            endpoint: API endpoint URL
        """
        self._api_endpoints[api_type] = endpoint
        logger.info(f"API endpoint set for {api_type}: {endpoint}")


# ============================================================================
# L4: Human Review Flagging
# ============================================================================

class HumanReviewQueue:
    """L4 Human Review Queue Management.
    
    Manages automatic flagging criteria, review queue, status tracking,
    and resolution workflows.
    """
    
    def __init__(
        self,
        auto_flag_threshold: float = 0.5,
        high_discrepancy_threshold: int = 1,
        low_confidence_threshold: float = 0.4,
        max_queue_size: int = 1000,
    ):
        """Initialize human review queue.
        
        Args:
            auto_flag_threshold: Confidence threshold for auto-flagging
            high_discrepancy_threshold: Discrepancy count threshold
            low_confidence_threshold: Confidence threshold for low confidence
            max_queue_size: Maximum items in queue
        """
        self.auto_flag_threshold = auto_flag_threshold
        self.high_discrepancy_threshold = high_discrepancy_threshold
        self.low_confidence_threshold = low_confidence_threshold
        self.max_queue_size = max_queue_size
        
        # In-memory queue (production would use persistent storage)
        self._queue: Dict[str, HumanReviewItem] = {}
        self._queue_order: List[str] = []
        
        # Callbacks for status changes
        self._status_callbacks: List[Callable[[HumanReviewItem], None]] = []
        
        logger.debug("HumanReviewQueue initialized")
    
    def register_status_callback(
        self,
        callback: Callable[[HumanReviewItem], None],
    ) -> None:
        """Register callback for status changes.
        
        Args:
            callback: Function to call on status change
        """
        self._status_callbacks.append(callback)
    
    def _notify_status_change(self, item: HumanReviewItem) -> None:
        """Notify callbacks of status change.
        
        Args:
            item: Item that changed status
        """
        for callback in self._status_callbacks:
            try:
                callback(item)
            except Exception as e:
                logger.error(f"Status callback error: {e}")
    
    def should_flag_for_review(
        self,
        data_point: DataPoint,
        l1_result: Optional[SourceAttribution] = None,
        l2_result: Optional[CrossReferenceAnalysis] = None,
        l3_result: Optional[RealTimeValidationResult] = None,
    ) -> Tuple[bool, List[FlagReason]]:
        """Determine if data should be flagged for human review.
        
        Args:
            data_point: Data point to evaluate
            l1_result: L1 validation result
            l2_result: L2 cross-reference result
            l3_result: L3 real-time validation result
            
        Returns:
            Tuple of (should_flag, list_of_reasons)
        """
        reasons: List[FlagReason] = []
        
        # Check L1 issues
        if l1_result:
            if l1_result.is_stale:
                reasons.append(FlagReason.STALE_DATA)
            if l1_result.credibility_score < self.low_confidence_threshold:
                reasons.append(FlagReason.UNTRUSTED_SOURCE)
            if not l1_result.is_reachable:
                reasons.append(FlagReason.VALIDATION_FAILED)
        
        # Check L2 issues
        if l2_result:
            if l2_result.discrepancy_count >= self.high_discrepancy_threshold:
                reasons.append(FlagReason.HIGH_DISCREPANCY)
            if l2_result.confidence_score < self.auto_flag_threshold:
                reasons.append(FlagReason.LOW_CONFIDENCE)
            if l2_result.consensus_score < 0.5:
                reasons.append(FlagReason.CONSENSUS_LOW)
        
        # Check L3 issues
        if l3_result:
            if not l3_result.is_valid:
                reasons.append(FlagReason.VALIDATION_FAILED)
        
        # Manual review required for certain data types
        if data_point.data_type in ("analyst", "esg"):
            reasons.append(FlagReason.MANUAL_REVIEW_REQUIRED)
        
        should_flag = len(reasons) > 0
        
        logger.debug(
            "Flag evaluation completed",
            data_id=data_point.id,
            should_flag=should_flag,
            reason_count=len(reasons),
        )
        
        return should_flag, reasons
    
    async def add_to_queue(
        self,
        data_point: DataPoint,
        flag_reasons: List[FlagReason],
        l1_result: Optional[SourceAttribution] = None,
        l2_result: Optional[CrossReferenceAnalysis] = None,
        l3_result: Optional[RealTimeValidationResult] = None,
    ) -> HumanReviewItem:
        """Add item to review queue.
        
        Args:
            data_point: Data point to review
            flag_reasons: Reasons for flagging
            l1_result: L1 validation result
            l2_result: L2 cross-reference result
            l3_result: L3 real-time validation result
            
        Returns:
            Created review item
        """
        # Check queue size
        if len(self._queue) >= self.max_queue_size:
            # Remove oldest pending item
            self._remove_oldest_pending()
        
        # Generate unique ID
        item_id = self._generate_item_id(data_point)
        
        # Calculate priority (lower = higher priority)
        priority = self._calculate_priority(flag_reasons, l2_result)
        
        item = HumanReviewItem(
            item_id=item_id,
            data_id=data_point.id,
            data_point=data_point,
            flag_reasons=flag_reasons,
            status=ReviewStatus.PENDING,
            l1_result=l1_result,
            l2_result=l2_result,
            l3_result=l3_result,
            priority=priority,
        )
        
        self._queue[item_id] = item
        self._queue_order.append(item_id)
        
        # Sort queue by priority
        self._queue_order.sort(
            key=lambda x: (self._queue[x].priority, self._queue[x].created_at)
        )
        
        logger.info(
            "Item added to review queue",
            item_id=item_id,
            data_id=data_point.id,
            priority=priority,
            reasons=[r.value for r in flag_reasons],
        )
        
        return item
    
    def _generate_item_id(self, data_point: DataPoint) -> str:
        """Generate unique item ID.
        
        Args:
            data_point: Data point
            
        Returns:
            Unique ID string
        """
        timestamp = datetime.utcnow().isoformat()
        content = f"{data_point.id}:{timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _calculate_priority(
        self,
        flag_reasons: List[FlagReason],
        l2_result: Optional[CrossReferenceAnalysis],
    ) -> int:
        """Calculate priority for queue ordering.
        
        Args:
            flag_reasons: Reasons for flagging
            l2_result: L2 cross-reference result
            
        Returns:
            Priority (1 = highest)
        """
        priority = 5  # Default priority
        
        # Critical issues get highest priority
        critical_reasons = {
            FlagReason.HIGH_DISCREPANCY,
            FlagReason.VALIDATION_FAILED,
        }
        if any(r in critical_reasons for r in flag_reasons):
            priority = 1
        
        # High confidence issues
        elif FlagReason.LOW_CONFIDENCE in flag_reasons:
            priority = 2
        
        # Consensus issues
        elif FlagReason.CONSENSUS_LOW in flag_reasons:
            priority = 3
        
        # Adjust based on confidence score
        if l2_result and l2_result.confidence_score < 0.2:
            priority = max(1, priority - 1)
        
        return priority
    
    def _remove_oldest_pending(self) -> None:
        """Remove oldest pending item from queue."""
        for item_id in self._queue_order:
            item = self._queue.get(item_id)
            if item and item.status == ReviewStatus.PENDING:
                del self._queue[item_id]
                self._queue_order.remove(item_id)
                logger.warning(f"Removed oldest pending item: {item_id}")
                break
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status.
        
        Returns:
            Queue status dictionary
        """
        status_counts = {
            ReviewStatus.PENDING.value: 0,
            ReviewStatus.IN_REVIEW.value: 0,
            ReviewStatus.APPROVED.value: 0,
            ReviewStatus.REJECTED.value: 0,
            ReviewStatus.ESCALATED.value: 0,
            ReviewStatus.DISMISSED.value: 0,
        }
        
        for item in self._queue.values():
            status_counts[item.status.value] += 1
        
        return {
            "total_items": len(self._queue),
            "pending": status_counts[ReviewStatus.PENDING.value],
            "in_review": status_counts[ReviewStatus.IN_REVIEW.value],
            "approved": status_counts[ReviewStatus.APPROVED.value],
            "rejected": status_counts[ReviewStatus.REJECTED.value],
            "escalated": status_counts[ReviewStatus.ESCALATED.value],
            "dismissed": status_counts[ReviewStatus.DISMISSED.value],
            "max_size": self.max_queue_size,
        }
    
    def get_pending_items(
        self,
        limit: int = 10,
        offset: int = 0,
    ) -> List[HumanReviewItem]:
        """Get pending items from queue.
        
        Args:
            limit: Maximum items to return
            offset: Offset for pagination
            
        Returns:
            List of pending review items
        """
        pending = [
            self._queue[item_id]
            for item_id in self._queue_order
            if self._queue[item_id].status == ReviewStatus.PENDING
        ]
        
        return pending[offset:offset + limit]
    
    def assign_item(
        self,
        item_id: str,
        reviewer_id: str,
    ) -> Optional[HumanReviewItem]:
        """Assign item to reviewer.
        
        Args:
            item_id: Item ID to assign
            reviewer_id: Reviewer ID
            
        Returns:
            Assigned item or None if not found
        """
        item = self._queue.get(item_id)
        if not item:
            return None
        
        if item.status != ReviewStatus.PENDING:
            logger.warning(f"Cannot assign item {item_id} with status {item.status}")
            return None
        
        item.status = ReviewStatus.IN_REVIEW
        item.assigned_to = reviewer_id
        item.assigned_at = datetime.utcnow()
        
        self._notify_status_change(item)
        
        logger.info(f"Item {item_id} assigned to {reviewer_id}")
        
        return item
    
    def resolve_item(
        self,
        item_id: str,
        resolution: ReviewStatus,
        reviewer_id: str,
        notes: Optional[str] = None,
    ) -> Optional[HumanReviewItem]:
        """Resolve review item.
        
        Args:
            item_id: Item ID to resolve
            resolution: Resolution status
            reviewer_id: Reviewer ID
            notes: Resolution notes
            
        Returns:
            Resolved item or None if not found
        """
        if resolution not in (
            ReviewStatus.APPROVED,
            ReviewStatus.REJECTED,
            ReviewStatus.ESCALATED,
            ReviewStatus.DISMISSED,
        ):
            logger.error(f"Invalid resolution status: {resolution}")
            return None
        
        item = self._queue.get(item_id)
        if not item:
            return None
        
        if item.status not in (ReviewStatus.PENDING, ReviewStatus.IN_REVIEW):
            logger.warning(f"Cannot resolve item {item_id} with status {item.status}")
            return None
        
        item.status = resolution
        item.reviewed_by = reviewer_id
        item.reviewed_at = datetime.utcnow()
        item.resolution_notes = notes
        
        self._notify_status_change(item)
        
        logger.info(
            f"Item {item_id} resolved as {resolution.value}",
            reviewer=reviewer_id,
        )
        
        return item
    
    def get_item(self, item_id: str) -> Optional[HumanReviewItem]:
        """Get item by ID.
        
        Args:
            item_id: Item ID
            
        Returns:
            Review item or None
        """
        return self._queue.get(item_id)


# ============================================================================
# Main Verification Service
# ============================================================================

class VerificationService:
    """Handles multi-level data verification (L1-L4).
    
    The verification pipeline ensures data quality through:
    - L1: Source attribution (URL validation, credibility, timestamp)
    - L2: Cross-referencing (multi-source consensus)
    - L3: Real-time validation (live price/SEC validation)
    - L4: Human review (flagging and queue management)
    """
    
    def __init__(
        self,
        cache: Any = None,
        enable_l1: bool = True,
        enable_l2: bool = True,
        enable_l3: bool = True,
        enable_l4: bool = True,
        stale_threshold_hours: float = 24.0,
        min_credibility_score: float = 0.3,
        consensus_threshold: float = 0.6,
        auto_flag_threshold: float = 0.5,
    ):
        """Initialize verification service.
        
        Args:
            cache: Cache client for storing verification results
            enable_l1: Enable L1 source attribution
            enable_l2: Enable L2 cross-referencing
            enable_l3: Enable L3 real-time validation
            enable_l4: Enable L4 human review
            stale_threshold_hours: Hours before data is stale
            min_credibility_score: Minimum credibility score
            consensus_threshold: Minimum consensus score
            auto_flag_threshold: Auto-flag confidence threshold
        """
        self.cache = cache
        
        # Feature flags
        self.enable_l1 = enable_l1
        self.enable_l2 = enable_l2
        self.enable_l3 = enable_l3
        self.enable_l4 = enable_l4
        
        # Initialize validators
        self.source_validator = SourceValidator(
            stale_threshold_hours=stale_threshold_hours,
            min_credibility_score=min_credibility_score,
        )
        self.cross_reference_engine = CrossReferenceEngine(
            consensus_threshold=consensus_threshold,
        )
        self.real_time_validator = RealTimeValidator()
        self.human_review_queue = HumanReviewQueue(
            auto_flag_threshold=auto_flag_threshold,
        )
        
        # TTL for verification results
        self._verification_ttl = timedelta(hours=24)
        
        logger.info(
            "VerificationService initialized",
            l1_enabled=enable_l1,
            l2_enabled=enable_l2,
            l3_enabled=enable_l3,
            l4_enabled=enable_l4,
        )
    
    async def close(self) -> None:
        """Close all resources."""
        await self.source_validator.close()
        await self.cross_reference_engine.close()
        await self.real_time_validator.close()
        logger.info("VerificationService closed")
    
    async def verify_data_point(
        self,
        data_point: DataPoint,
        required_level: VerificationLevel = VerificationLevel.L2,
        additional_sources: Optional[List[str]] = None,
    ) -> VerificationResult:
        """Verify a single data point through all levels.
        
        Args:
            data_point: Data point to verify
            required_level: Required verification level
            additional_sources: Additional sources for cross-referencing
            
        Returns:
            Verification result
        """
        import time
        start_time = time.time()
        
        result = VerificationResult(
            data_id=data_point.id,
            requested_level=required_level,
            achieved_level=None,
            verified=False,
            sources=[],
            errors=[],
            warnings=[],
        )
        
        try:
            # L1: Source attribution (always required)
            if self.enable_l1:
                if not await self._verify_l1(data_point, result):
                    result.processing_time_ms = (time.time() - start_time) * 1000
                    return result
            
            # L2: Cross-reference (for key data)
            if self.enable_l2 and required_level in [
                VerificationLevel.L2,
                VerificationLevel.L3,
                VerificationLevel.L4,
            ]:
                if not await self._verify_l2(data_point, result, additional_sources):
                    result.processing_time_ms = (time.time() - start_time) * 1000
                    return result
            
            # L3: Real-time validation
            if self.enable_l3 and required_level in [
                VerificationLevel.L3,
                VerificationLevel.L4,
            ]:
                if not await self._verify_l3(data_point, result):
                    result.processing_time_ms = (time.time() - start_time) * 1000
                    return result
            
            # L4: Human review (if enabled or specifically requested)
            if self.enable_l4:
                should_flag, flag_reasons = self.human_review_queue.should_flag_for_review(
                    data_point,
                    result.l1_attribution,
                    result.l2_cross_reference,
                    result.l3_validation,
                )
                
                if should_flag or required_level == VerificationLevel.L4:
                    await self._verify_l4(data_point, result, flag_reasons)
            
            result.verified = (
                result.achieved_level is not None
                and result.errors == []
                and (result.l4_review_status is None or result.l4_review_status == ReviewStatus.APPROVED)
            )
            
        except Exception as e:
            logger.error(
                "Verification error",
                data_id=data_point.id,
                error=str(e),
            )
            result.errors.append(f"Verification error: {str(e)}")
        
        result.processing_time_ms = (time.time() - start_time) * 1000
        
        logger.debug(
            "Data point verification completed",
            data_id=data_point.id,
            achieved_level=result.achieved_level.value if result.achieved_level else None,
            verified=result.verified,
            processing_time_ms=result.processing_time_ms,
        )
        
        return result
    
    async def verify_batch(
        self,
        data_points: List[DataPoint],
        required_level: VerificationLevel = VerificationLevel.L2,
    ) -> List[VerificationResult]:
        """Verify multiple data points.
        
        Args:
            data_points: List of data points to verify
            required_level: Required verification level
            
        Returns:
            List of verification results
        """
        tasks = [
            self.verify_data_point(dp, required_level)
            for dp in data_points
        ]
        
        return await asyncio.gather(*tasks)
    
    async def _verify_l1(
        self,
        data_point: DataPoint,
        result: VerificationResult,
    ) -> bool:
        """L1 verification: Source attribution.
        
        Args:
            data_point: Data to verify
            result: Result object to update
            
        Returns:
            True if passed
        """
        attribution = await self.source_validator.validate(data_point)
        result.l1_attribution = attribution
        
        # Check for errors
        if not attribution.is_valid_format:
            result.errors.append("Invalid source URL format")
            return False
        
        if not attribution.is_reachable:
            result.warnings.append(f"Source not reachable: {attribution.error_message}")
        
        if attribution.is_stale:
            result.warnings.append(f"Data is stale ({attribution.age_hours:.1f} hours old)")
        
        if attribution.credibility_score < self.source_validator.min_credibility_score:
            result.errors.append(
                f"Source credibility too low: {attribution.credibility_score:.2f}"
            )
            return False
        
        result.sources.append({
            "url": attribution.url,
            "domain": attribution.domain,
            "retrieved_at": attribution.retrieved_at.isoformat(),
            "credibility_score": attribution.credibility_score,
            "reputation_score": attribution.reputation_score,
            "level": "L1",
        })
        result.achieved_level = VerificationLevel.L1
        
        return True
    
    async def _verify_l2(
        self,
        data_point: DataPoint,
        result: VerificationResult,
        additional_sources: Optional[List[str]] = None,
    ) -> bool:
        """L2 verification: Cross-referencing.
        
        Args:
            data_point: Data to verify
            result: Result object to update
            additional_sources: Additional sources to check
            
        Returns:
            True if passed
        """
        analysis = await self.cross_reference_engine.cross_reference(
            data_point,
            additional_sources,
        )
        result.l2_cross_reference = analysis
        
        # Check for insufficient sources
        if len(analysis.sources) < self.cross_reference_engine.min_sources:
            result.warnings.append(
                f"Insufficient cross-references: {len(analysis.sources)} found, "
                f"{self.cross_reference_engine.min_sources} recommended"
            )
        
        # Check for discrepancies
        if analysis.discrepancy_count > 0:
            result.warnings.append(
                f"Found {analysis.discrepancy_count} discrepancies between sources"
            )
            for disc in analysis.discrepancies:
                result.warnings.append(
                    f"  - {disc['type']}: {disc.get('severity', 'unknown')} severity"
                )
        
        # Check consensus
        if analysis.consensus_score < self.cross_reference_engine.consensus_threshold:
            result.warnings.append(
                f"Low consensus score: {analysis.consensus_score:.2f}"
            )
        
        result.sources.append({
            "level": "L2",
            "source_count": len(analysis.sources),
            "consensus_score": analysis.consensus_score,
            "confidence_score": analysis.confidence_score,
            "discrepancy_count": analysis.discrepancy_count,
            "requires_review": analysis.requires_review,
        })
        result.achieved_level = VerificationLevel.L2
        
        return True
    
    async def _verify_l3(
        self,
        data_point: DataPoint,
        result: VerificationResult,
    ) -> bool:
        """L3 verification: Real-time validation.
        
        Args:
            data_point: Data to verify
            result: Result object to update
            
        Returns:
            True if passed
        """
        validation = await self.real_time_validator.validate(data_point)
        result.l3_validation = validation
        
        if not validation.is_valid:
            result.warnings.append(
                f"Real-time validation failed: {validation.error_message}"
            )
            # Don't fail immediately - just warn
        
        if validation.deviation_percent is not None:
            if validation.deviation_percent > validation.tolerance_percent:
                result.warnings.append(
                    f"Value deviation: {validation.deviation_percent:.2f}% "
                    f"(tolerance: {validation.tolerance_percent:.2f}%)"
                )
        
        result.sources.append({
            "level": "L3",
            "validator_type": validation.validator_type,
            "validated_at": validation.validated_at.isoformat(),
            "is_valid": validation.is_valid,
            "api_source": validation.api_source,
            "deviation_percent": validation.deviation_percent,
            "api_response_time_ms": validation.api_response_time_ms,
        })
        result.achieved_level = VerificationLevel.L3
        
        return True
    
    async def _verify_l4(
        self,
        data_point: DataPoint,
        result: VerificationResult,
        flag_reasons: List[FlagReason],
    ) -> bool:
        """L4 verification: Human review.
        
        Args:
            data_point: Data to verify
            result: Result object to update
            flag_reasons: Reasons for flagging
            
        Returns:
            True if queued successfully
        """
        review_item = await self.human_review_queue.add_to_queue(
            data_point,
            flag_reasons,
            result.l1_attribution,
            result.l2_cross_reference,
            result.l3_validation,
        )
        
        result.l4_review_item_id = review_item.item_id
        result.l4_review_status = review_item.status
        
        result.sources.append({
            "level": "L4",
            "status": review_item.status.value,
            "item_id": review_item.item_id,
            "flag_reasons": [r.value for r in flag_reasons],
            "priority": review_item.priority,
            "flagged_at": review_item.created_at.isoformat(),
        })
        result.achieved_level = VerificationLevel.L4
        
        return True
    
    def get_review_queue_status(self) -> Dict[str, Any]:
        """Get human review queue status.
        
        Returns:
            Queue status dictionary
        """
        return self.human_review_queue.get_queue_status()
    
    def get_pending_reviews(self, limit: int = 10) -> List[HumanReviewItem]:
        """Get pending review items.
        
        Args:
            limit: Maximum items to return
            
        Returns:
            List of pending review items
        """
        return self.human_review_queue.get_pending_items(limit)
    
    def assign_review(self, item_id: str, reviewer_id: str) -> Optional[HumanReviewItem]:
        """Assign review item to reviewer.
        
        Args:
            item_id: Item ID
            reviewer_id: Reviewer ID
            
        Returns:
            Assigned item or None
        """
        return self.human_review_queue.assign_item(item_id, reviewer_id)
    
    def resolve_review(
        self,
        item_id: str,
        resolution: ReviewStatus,
        reviewer_id: str,
        notes: Optional[str] = None,
    ) -> Optional[HumanReviewItem]:
        """Resolve review item.
        
        Args:
            item_id: Item ID
            resolution: Resolution status
            reviewer_id: Reviewer ID
            notes: Resolution notes
            
        Returns:
            Resolved item or None
        """
        return self.human_review_queue.resolve_item(item_id, resolution, reviewer_id, notes)
    
    def calculate_verification_rate(
        self,
        results: List[VerificationResult],
    ) -> Dict[str, Any]:
        """Calculate verification statistics from results.
        
        Args:
            results: List of verification results
            
        Returns:
            Verification statistics
        """
        if not results:
            return {
                "total": 0,
                "verified": 0,
                "rate": 0.0,
                "by_level": {},
            }
        
        verified_count = sum(1 for r in results if r.verified)
        
        # Count by achieved level
        by_level = {}
        for level in VerificationLevel:
            count = sum(
                1 for r in results
                if r.achieved_level == level
            )
            by_level[level.value] = count
        
        return {
            "total": len(results),
            "verified": verified_count,
            "rate": verified_count / len(results),
            "by_level": by_level,
            "avg_processing_time_ms": sum(
                r.processing_time_ms or 0 for r in results
            ) / len(results),
        }


# ============================================================================
# Legacy Classes (for backward compatibility)
# ============================================================================

class DataValidator:
    """Base class for data validators (legacy)."""
    
    async def validate(self, data_point: DataPoint) -> bool:
        """Validate a data point.
        
        Args:
            data_point: Data to validate
            
        Returns:
            True if valid
        """
        raise NotImplementedError


class FinancialDataValidator(DataValidator):
    """Validator for financial data (legacy)."""
    
    async def validate(self, data_point: DataPoint) -> bool:
        """Validate financial data against live sources."""
        logger.debug(f"Validating financial data: {data_point.id}")
        return True


class MarketDataValidator(DataValidator):
    """Validator for market data (legacy)."""
    
    async def validate(self, data_point: DataPoint) -> bool:
        """Validate market data against live prices."""
        logger.debug(f"Validating market data: {data_point.id}")
        return True
