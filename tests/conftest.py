"""Pytest configuration and fixtures."""

import pytest
import pytest_asyncio

from heavyswarm.core.agent_base import AgentConfig
from heavyswarm.core.enums import AgentPhase, DiligenceStatus, TimeHorizon, RiskTolerance
from heavyswarm.core.state import DiligenceState, InvestmentThesis


@pytest.fixture
def sample_thesis():
    """Create a sample investment thesis."""
    return InvestmentThesis(
        ticker="AAPL",
        thesis="Apple's AI integration will drive services revenue growth",
        time_horizon=TimeHorizon.MEDIUM_TERM,
        risk_tolerance=RiskTolerance.MODERATE,
        position_size=0.05,
    )


@pytest.fixture
def sample_state(sample_thesis):
    """Create a sample diligence state."""
    return DiligenceState(thesis=sample_thesis)


@pytest.fixture
def agent_config():
    """Create a sample agent configuration."""
    return AgentConfig(
        model="gpt-4o",
        temperature=0.2,
        max_tokens=4000,
        timeout_seconds=60,
        retry_attempts=3,
    )


@pytest.fixture
def mock_llm_response():
    """Create a mock LLM response."""
    return {
        "content": '{"result": "test"}',
        "model": "gpt-4o",
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        "finish_reason": "stop",
        "response_time_ms": 1000,
    }
