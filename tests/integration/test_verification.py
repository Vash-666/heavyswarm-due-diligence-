"""Integration tests for verification pipeline."""

import pytest
from datetime import datetime

from heavyswarm.services.verification import (
    VerificationService,
    DataPoint,
    VerificationLevel,
    VerificationResult,
)


@pytest.fixture
def verification_service():
    """Create verification service fixture."""
    # Mock cache
    cache = {}
    return VerificationService(cache)


@pytest.mark.asyncio
async def test_verify_l1_source_attribution(verification_service):
    """Test L1 verification - source attribution."""
    data_point = DataPoint(
        id="test-1",
        value=100,
        data_type="financial",
        source_url="https://example.com/data",
        retrieved_at=datetime.utcnow(),
    )
    
    result = await verification_service.verify_data_point(
        data_point,
        required_level=VerificationLevel.L1,
    )
    
    assert result.verified is True
    assert result.achieved_level == VerificationLevel.L1
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_verify_l1_missing_source(verification_service):
    """Test L1 verification fails without source."""
    data_point = DataPoint(
        id="test-2",
        value=100,
        data_type="financial",
        source_url=None,
    )
    
    result = await verification_service.verify_data_point(
        data_point,
        required_level=VerificationLevel.L1,
    )
    
    assert result.verified is False
    assert result.achieved_level is None
    assert len(result.errors) > 0


@pytest.mark.asyncio
async def test_verify_l1_stale_data(verification_service):
    """Test L1 verification fails with stale data."""
    from datetime import timedelta
    
    data_point = DataPoint(
        id="test-3",
        value=100,
        data_type="financial",
        source_url="https://example.com/data",
        retrieved_at=datetime.utcnow() - timedelta(days=2),
    )
    
    result = await verification_service.verify_data_point(
        data_point,
        required_level=VerificationLevel.L1,
    )
    
    assert result.verified is False
    assert "stale" in str(result.errors).lower()


@pytest.mark.asyncio
async def test_verify_batch(verification_service):
    """Test batch verification."""
    data_points = [
        DataPoint(
            id=f"test-{i}",
            value=i * 10,
            data_type="financial",
            source_url=f"https://example.com/data{i}",
            retrieved_at=datetime.utcnow(),
        )
        for i in range(5)
    ]
    
    results = await verification_service.verify_batch(
        data_points,
        required_level=VerificationLevel.L1,
    )
    
    assert len(results) == 5
    assert all(r.verified for r in results)


def test_calculate_verification_rate(verification_service):
    """Test verification rate calculation."""
    results = [
        VerificationResult(
            data_id="1",
            requested_level=VerificationLevel.L1,
            achieved_level=VerificationLevel.L1,
            verified=True,
            sources=[],
            errors=[],
        ),
        VerificationResult(
            data_id="2",
            requested_level=VerificationLevel.L1,
            achieved_level=VerificationLevel.L1,
            verified=True,
            sources=[],
            errors=[],
        ),
        VerificationResult(
            data_id="3",
            requested_level=VerificationLevel.L1,
            achieved_level=None,
            verified=False,
            sources=[],
            errors=["Error"],
        ),
    ]
    
    rate = verification_service.calculate_verification_rate(results)
    
    assert rate == 2 / 3


def test_calculate_verification_rate_empty(verification_service):
    """Test verification rate with empty results."""
    rate = verification_service.calculate_verification_rate([])
    
    assert rate == 0.0
