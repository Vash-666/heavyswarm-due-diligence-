"""Tests for state management."""

import pytest

from heavyswarm.core.enums import (
    AgentPhase,
    DiligenceStatus,
    Priority,
    RiskTolerance,
    TimeHorizon,
    VerificationLevel,
)
from heavyswarm.core.state import (
    AuditEvent,
    DataProvenance,
    DiligenceState,
    InvestmentThesis,
    PhaseResult,
)


class TestInvestmentThesis:
    """Test cases for InvestmentThesis."""
    
    def test_valid_thesis(self):
        """Test creating a valid investment thesis."""
        thesis = InvestmentThesis(
            ticker="AAPL",
            thesis="Apple's AI integration will drive growth",
            time_horizon=TimeHorizon.MEDIUM_TERM,
            risk_tolerance=RiskTolerance.MODERATE,
            position_size=0.05,
            priority=Priority.HIGH,
        )
        
        assert thesis.ticker == "AAPL"
        assert thesis.position_size == 0.05
    
    def test_invalid_ticker(self):
        """Test validation of empty ticker."""
        with pytest.raises(ValueError):
            InvestmentThesis(
                ticker="",
                thesis="Valid thesis statement here",
                position_size=0.05,
            )
    
    def test_invalid_thesis_length(self):
        """Test validation of short thesis."""
        with pytest.raises(ValueError):
            InvestmentThesis(
                ticker="AAPL",
                thesis="Short",
                position_size=0.05,
            )


class TestDiligenceState:
    """Test cases for DiligenceState."""
    
    def test_initial_state(self, sample_thesis):
        """Test initial state creation."""
        state = DiligenceState(thesis=sample_thesis)
        
        assert state.status == DiligenceStatus.PENDING
        assert state.overall_confidence == 0.0
        assert state.diligence_id is not None
        assert len(state.events) == 0
    
    def test_add_event(self, sample_state):
        """Test adding audit events."""
        event = sample_state.add_event(
            "test_event",
            "test_agent",
            {"key": "value"},
        )
        
        assert len(sample_state.events) == 1
        assert event.event_type == "test_event"
        assert event.agent_id == "test_agent"
        assert event.details == {"key": "value"}
    
    def test_add_phase_result(self, sample_state):
        """Test adding phase results."""
        from datetime import datetime
        
        result = PhaseResult(
            phase=AgentPhase.QUESTION_GENERATOR,
            output={"test": "data"},
            confidence=0.9,
            processing_time_ms=1000,
            completed_at=datetime.utcnow(),
            agent_id="test_agent",
        )
        
        sample_state.add_phase_result(result)
        
        assert AgentPhase.QUESTION_GENERATOR in sample_state.phase_results
        assert len(sample_state.completed_phases) == 1
    
    def test_get_context_for_phase(self, sample_state):
        """Test getting context for a phase."""
        from datetime import datetime
        
        # Add a phase result
        result = PhaseResult(
            phase=AgentPhase.QUESTION_GENERATOR,
            output={"prompts": ["test"]},
            confidence=0.9,
            processing_time_ms=1000,
            completed_at=datetime.utcnow(),
            agent_id="test_agent",
        )
        sample_state.add_phase_result(result)
        
        # Get context for researcher phase
        context = sample_state.get_context_for_phase(AgentPhase.RESEARCHER)
        
        assert "thesis" in context
        assert "previous_phases" in context
        assert "QUESTION_GENERATOR" in context["previous_phases"]
    
    def test_should_trigger_quality_gate_low_confidence(self, sample_state):
        """Test quality gate trigger with low confidence."""
        from unittest.mock import MagicMock
        
        settings = MagicMock()
        settings.quality_gate_enabled = True
        settings.confidence_threshold = 0.85
        settings.max_position_size_pct = 0.05
        
        sample_state.overall_confidence = 0.80
        
        assert sample_state.should_trigger_quality_gate(settings) is True
    
    def test_should_trigger_quality_gate_high_position(self, sample_state):
        """Test quality gate trigger with large position."""
        from unittest.mock import MagicMock
        
        settings = MagicMock()
        settings.quality_gate_enabled = True
        settings.confidence_threshold = 0.85
        settings.max_position_size_pct = 0.05
        
        sample_state.thesis.position_size = 0.10
        sample_state.overall_confidence = 0.90
        
        assert sample_state.should_trigger_quality_gate(settings) is True


class TestDataProvenance:
    """Test cases for DataProvenance."""
    
    def test_valid_provenance(self):
        """Test creating valid data provenance."""
        from datetime import datetime
        
        provenance = DataProvenance(
            data_id="revenue_2025",
            value=1000000000,
            source_url="https://sec.gov/...",
            retrieved_at=datetime.utcnow(),
            verified_by="researcher",
            verification_level=VerificationLevel.L2,
            confidence=0.95,
        )
        
        assert provenance.data_id == "revenue_2025"
        assert provenance.confidence == 0.95
    
    def test_invalid_confidence(self):
        """Test validation of confidence score."""
        from datetime import datetime
        
        with pytest.raises(ValueError):
            DataProvenance(
                data_id="test",
                value=100,
                source_url="https://example.com",
                retrieved_at=datetime.utcnow(),
                verified_by="test",
                confidence=1.5,  # Invalid: > 1
            )
