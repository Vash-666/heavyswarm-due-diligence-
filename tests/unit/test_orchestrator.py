"""Tests for orchestrator."""

import pytest

from heavyswarm.agents import (
    FinancialAnalystAgent,
    QualityGuardianAgent,
    QuestionGeneratorAgent,
    ResearcherAgent,
    RiskAnalystAgent,
    StrategistAgent,
    VerifierAgent,
    WriterAgent,
)
from heavyswarm.core.agent_base import AgentConfig
from heavyswarm.core.enums import AgentPhase
from heavyswarm.core.orchestrator import HeavySwarmOrchestrator


class TestHeavySwarmOrchestrator:
    """Test cases for HeavySwarmOrchestrator."""
    
    @pytest.fixture
    def agent_config(self):
        """Create agent configuration."""
        return AgentConfig(
            model="gpt-4o",
            temperature=0.2,
            max_tokens=4000,
        )
    
    @pytest.fixture
    def agents(self, agent_config):
        """Create all agents."""
        return {
            AgentPhase.QUESTION_GENERATOR: QuestionGeneratorAgent(agent_config),
            AgentPhase.RESEARCHER: ResearcherAgent(agent_config),
            AgentPhase.FINANCIAL_ANALYST: FinancialAnalystAgent(agent_config),
            AgentPhase.RISK_ANALYST: RiskAnalystAgent(agent_config),
            AgentPhase.STRATEGIST: StrategistAgent(agent_config),
            AgentPhase.VERIFIER: VerifierAgent(agent_config),
            AgentPhase.WRITER: WriterAgent(agent_config),
            AgentPhase.QUALITY_GUARDIAN: QualityGuardianAgent(agent_config),
        }
    
    @pytest.fixture
    def mock_state_manager(self):
        """Create mock state manager."""
        from unittest.mock import AsyncMock, MagicMock
        
        manager = MagicMock()
        manager.save_state = AsyncMock()
        manager.load_state = AsyncMock(return_value=None)
        manager.settings = MagicMock()
        manager.settings.quality_gate_enabled = True
        manager.settings.confidence_threshold = 0.85
        manager.settings.max_position_size_pct = 0.05
        
        return manager
    
    @pytest.fixture
    def orchestrator(self, agents, mock_state_manager):
        """Create orchestrator fixture."""
        return HeavySwarmOrchestrator(
            agents=agents,
            state_manager=mock_state_manager,
            max_concurrent=10,
        )
    
    def test_phase_order(self):
        """Test phase execution order."""
        expected_order = [
            AgentPhase.QUESTION_GENERATOR,
            AgentPhase.RESEARCHER,
            AgentPhase.FINANCIAL_ANALYST,
            AgentPhase.RISK_ANALYST,
            AgentPhase.STRATEGIST,
            AgentPhase.VERIFIER,
            AgentPhase.WRITER,
            AgentPhase.QUALITY_GUARDIAN,
        ]
        
        assert HeavySwarmOrchestrator.PHASE_ORDER == expected_order
    
    def test_parallel_phases(self):
        """Test parallel phase configuration."""
        expected_parallel = [
            [AgentPhase.FINANCIAL_ANALYST, AgentPhase.RISK_ANALYST],
        ]
        
        assert HeavySwarmOrchestrator.PARALLEL_PHASES == expected_parallel
    
    @pytest.mark.asyncio
    async def test_execute_phase(self, orchestrator, sample_thesis):
        """Test single phase execution."""
        from datetime import datetime
        
        state = sample_thesis  # This is actually a thesis, need to fix
        # Actually sample_thesis is an InvestmentThesis, we need DiligenceState
        from heavyswarm.core.state import DiligenceState
        
        state = DiligenceState(thesis=sample_thesis)
        
        await orchestrator._execute_phase(state, AgentPhase.QUESTION_GENERATOR)
        
        assert AgentPhase.QUESTION_GENERATOR in state.phase_results
        assert state.phase_results[AgentPhase.QUESTION_GENERATOR].confidence > 0
    
    def test_get_stats(self, orchestrator):
        """Test getting orchestrator stats."""
        stats = orchestrator.get_stats()
        
        assert "max_concurrent" in stats
        assert "running_diligences" in stats
        assert "agents" in stats
        assert len(stats["agents"]) == 8
