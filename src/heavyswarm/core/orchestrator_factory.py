"""Factory for creating orchestrator instances with all dependencies."""

from typing import Dict

from heavyswarm.core.agent_base import AgentConfig
from heavyswarm.core.enums import AgentPhase
from heavyswarm.core.orchestrator import HeavySwarmOrchestrator
from heavyswarm.services.database import DatabaseService
from heavyswarm.services.llm_client import LLMClient
from heavyswarm.agents import (
    QuestionGeneratorAgent,
    ResearcherAgent,
    FinancialAnalystAgent,
    RiskAnalystAgent,
    StrategistAgent,
    VerifierAgent,
    WriterAgent,
    QualityGuardianAgent,
)
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class OrchestratorFactory:
    """Factory for creating fully configured orchestrators."""
    
    def __init__(
        self,
        db_service: DatabaseService,
        llm_client: LLMClient,
        max_concurrent: int = 10,
    ):
        """Initialize the factory.
        
        Args:
            db_service: Database service for persistence
            llm_client: LLM client for agent operations
            max_concurrent: Maximum concurrent diligences
        """
        self.db_service = db_service
        self.llm_client = llm_client
        self.max_concurrent = max_concurrent
    
    def create_orchestrator(self) -> HeavySwarmOrchestrator:
        """Create a fully configured orchestrator.
        
        Returns:
            Configured HeavySwarmOrchestrator instance
        """
        # Create agent configurations
        default_config = AgentConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.3,
            max_tokens=4000,
            timeout_seconds=60,
            retry_attempts=3,
        )
        
        fast_config = AgentConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.2,
            max_tokens=2000,
            timeout_seconds=30,
            retry_attempts=2,
        )
        
        deep_config = AgentConfig(
            model="claude-3-5-sonnet-20241022",
            temperature=0.3,
            max_tokens=8000,
            timeout_seconds=120,
            retry_attempts=3,
        )
        
        # Create all agents
        agents: Dict[AgentPhase, any] = {
            AgentPhase.QUESTION_GENERATOR: QuestionGeneratorAgent(
                config=fast_config,
                llm_client=self.llm_client,
            ),
            AgentPhase.RESEARCHER: ResearcherAgent(
                config=default_config,
                llm_client=self.llm_client,
            ),
            AgentPhase.FINANCIAL_ANALYST: FinancialAnalystAgent(
                config=default_config,
                llm_client=self.llm_client,
            ),
            AgentPhase.RISK_ANALYST: RiskAnalystAgent(
                config=default_config,
                llm_client=self.llm_client,
            ),
            AgentPhase.STRATEGIST: StrategistAgent(
                config=deep_config,
                llm_client=self.llm_client,
            ),
            AgentPhase.VERIFIER: VerifierAgent(
                config=default_config,
                llm_client=self.llm_client,
            ),
            AgentPhase.WRITER: WriterAgent(
                config=deep_config,
                llm_client=self.llm_client,
            ),
            AgentPhase.QUALITY_GUARDIAN: QualityGuardianAgent(
                config=deep_config,
                llm_client=self.llm_client,
            ),
        }
        
        # Create state manager (simplified for now - uses database directly)
        from heavyswarm.services.state_manager import StateManager
        
        # Create a mock redis client (can be replaced with actual redis)
        class MockRedis:
            async def get(self, key: str) -> None:
                return None
            
            async def setex(self, key: str, ttl: int, value: str) -> None:
                pass
            
            async def delete(self, key: str) -> None:
                pass
        
        from heavyswarm.core.config import Settings
        state_manager = StateManager(
            redis_client=MockRedis(),
            db_client=self.db_service,
            settings=Settings(),
        )
        
        # Create and return orchestrator
        orchestrator = HeavySwarmOrchestrator(
            agents=agents,
            state_manager=state_manager,
            max_concurrent=self.max_concurrent,
        )
        
        logger.debug("Created new orchestrator instance")
        
        return orchestrator


def create_orchestrator_factory(
    db_service: DatabaseService,
    llm_client: LLMClient,
    max_concurrent: int = 10,
) -> OrchestratorFactory:
    """Create an orchestrator factory.
    
    Args:
        db_service: Database service
        llm_client: LLM client
        max_concurrent: Maximum concurrent diligences
        
    Returns:
        Orchestrator factory
    """
    return OrchestratorFactory(
        db_service=db_service,
        llm_client=llm_client,
        max_concurrent=max_concurrent,
    )
