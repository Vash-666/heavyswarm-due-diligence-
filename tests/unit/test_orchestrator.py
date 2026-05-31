"""Tests for orchestrator."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from heavyswarm.core.agent_base import AgentConfig, AgentOutput
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
    def mock_agents(self):
        """Create mock agents for all phases."""
        agents = {}
        for phase in AgentPhase:
            mock_agent = MagicMock()
            mock_agent.phase = phase
            mock_agent.run_with_timeout = AsyncMock(return_value=AgentOutput(
                phase=phase,
                data={"test": f"data for {phase.name}"},
                confidence=0.9,
                processing_time_ms=100,
            ))
            agents[phase] = mock_agent
        return agents
    
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
    def orchestrator(self, mock_agents, mock_state_manager):
        """Create orchestrator fixture."""
        return HeavySwarmOrchestrator(
            agents=mock_agents,
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
        from heavyswarm.core.state import DiligenceState
        
        state = DiligenceState(thesis=sample_thesis)
        
        await orchestrator._execute_phase(state, AgentPhase.QUESTION_GENERATOR)
        
        assert AgentPhase.QUESTION_GENERATOR in state.phase_results
        assert state.phase_results[AgentPhase.QUESTION_GENERATOR].confidence == 0.9
        
        # Verify agent was called
        orchestrator.agents[AgentPhase.QUESTION_GENERATOR].run_with_timeout.assert_called_once()
    
    def test_get_stats(self, orchestrator):
        """Test getting orchestrator stats."""
        stats = orchestrator.get_stats()
        
        assert "max_concurrent" in stats
        assert stats["max_concurrent"] == 10
        assert "running_diligences" in stats
        assert stats["running_diligences"] == 0
        assert "agents" in stats
        assert len(stats["agents"]) == 8
    
    @pytest.mark.asyncio
    async def test_execute_parallel_phases(self, orchestrator, sample_thesis):
        """Test executing parallel phases."""
        from heavyswarm.core.state import DiligenceState
        
        state = DiligenceState(thesis=sample_thesis)
        
        phases = [AgentPhase.FINANCIAL_ANALYST, AgentPhase.RISK_ANALYST]
        await orchestrator._execute_parallel_phases(state, phases)
        
        # Both phases should have results
        assert AgentPhase.FINANCIAL_ANALYST in state.phase_results
        assert AgentPhase.RISK_ANALYST in state.phase_results
        
        # Both agents should have been called
        orchestrator.agents[AgentPhase.FINANCIAL_ANALYST].run_with_timeout.assert_called_once()
        orchestrator.agents[AgentPhase.RISK_ANALYST].run_with_timeout.assert_called_once()
    
    def test_get_running_count(self, orchestrator):
        """Test getting running count."""
        # Initially no running diligences
        assert orchestrator.get_running_count() == 0
    
    def test_semaphore_initialization(self, orchestrator):
        """Test that semaphore is initialized with correct value."""
        # The semaphore should be initialized with max_concurrent
        assert orchestrator._semaphore._value == 10
