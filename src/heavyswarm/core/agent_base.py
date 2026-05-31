"""Base agent class for HeavySwarm agents."""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from heavyswarm.core.enums import AgentPhase
from heavyswarm.core.state import DiligenceState, InvestmentThesis


@dataclass
class AgentConfig:
    """Configuration for an agent."""
    
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: int = 60
    retry_attempts: int = 3
    
    def __post_init__(self) -> None:
        """Validate configuration."""
        if not 0 <= self.temperature <= 2:
            raise ValueError("Temperature must be between 0 and 2")
        if self.max_tokens < 1:
            raise ValueError("Max tokens must be positive")
        if self.retry_attempts < 0:
            raise ValueError("Retry attempts must be non-negative")


@dataclass
class AgentInput:
    """Input data for an agent execution."""
    
    thesis: Optional[InvestmentThesis]
    context: Dict[str, Any] = field(default_factory=dict)
    previous_outputs: Dict[AgentPhase, Any] = field(default_factory=dict)
    state: Optional[DiligenceState] = None


@dataclass
class AgentOutput:
    """Output data from an agent execution."""
    
    phase: AgentPhase
    data: Dict[str, Any]
    confidence: float
    provenance: List[Dict[str, Any]] = field(default_factory=list)
    processing_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Validate confidence score."""
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")


class BaseAgent(ABC):
    """Base class for all HeavySwarm agents.
    
    All agents in the HeavySwarm system must inherit from this base class
    and implement the execute() and validate_output() methods.
    """
    
    def __init__(self, config: AgentConfig):
        """Initialize the agent.
        
        Args:
            config: Agent configuration
        """
        self.config = config
        self.phase: Optional[AgentPhase] = None
        self._execution_count = 0
        self._error_count = 0
    
    @abstractmethod
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute the agent's specific task.
        
        This method must be implemented by all concrete agent classes.
        It contains the core logic for the agent's analysis.
        
        Args:
            input_data: Input data including thesis and context
            
        Returns:
            Agent output with results and confidence score
        """
        pass
    
    @abstractmethod
    def validate_output(self, output: AgentOutput) -> bool:
        """Validate that output meets contract requirements.
        
        This method must be implemented by all concrete agent classes
        to ensure the output conforms to the expected schema.
        
        Args:
            output: The agent output to validate
            
        Returns:
            True if output is valid, False otherwise
        """
        pass
    
    async def run_with_retry(self, input_data: AgentInput) -> AgentOutput:
        """Execute with retry logic and exponential backoff.
        
        Args:
            input_data: Input data for the agent
            
        Returns:
            Agent output
            
        Raises:
            Exception: If all retry attempts fail
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(self.config.retry_attempts + 1):
            try:
                self._execution_count += 1
                output = await self.execute(input_data)
                
                # Validate output
                if not self.validate_output(output):
                    raise ValueError(f"Agent {self.phase} produced invalid output")
                
                return output
                
            except Exception as e:
                self._error_count += 1
                last_error = e
                
                if attempt < self.config.retry_attempts:
                    # Exponential backoff: 2^attempt seconds
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    # All retries exhausted
                    break
        
        # If we get here, all retries failed
        raise last_error or Exception(f"Agent {self.phase} failed after {self.config.retry_attempts} retries")
    
    async def run_with_timeout(self, input_data: AgentInput) -> AgentOutput:
        """Execute with timeout protection.
        
        Args:
            input_data: Input data for the agent
            
        Returns:
            Agent output
            
        Raises:
            asyncio.TimeoutError: If execution exceeds timeout
        """
        return await asyncio.wait_for(
            self.run_with_retry(input_data),
            timeout=self.config.timeout_seconds,
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get agent execution statistics.
        
        Returns:
            Dictionary with execution statistics
        """
        return {
            "phase": self.phase.name if self.phase else None,
            "execution_count": self._execution_count,
            "error_count": self._error_count,
            "error_rate": (
                self._error_count / self._execution_count
                if self._execution_count > 0
                else 0.0
            ),
            "config": {
                "model": self.config.model,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            },
        }
    
    def reset_stats(self) -> None:
        """Reset execution statistics."""
        self._execution_count = 0
        self._error_count = 0


class ParallelAgent(BaseAgent):
    """Base class for agents that execute parallel sub-tasks.
    
    This is used for agents like the researcher that spawn multiple
    parallel sub-agents for different research vectors.
    """
    
    def __init__(self, config: AgentConfig, max_parallel: int = 4):
        """Initialize parallel agent.
        
        Args:
            config: Agent configuration
            max_parallel: Maximum number of parallel sub-tasks
        """
        super().__init__(config)
        self.max_parallel = max_parallel
    
    @abstractmethod
    async def execute_sub_task(
        self,
        sub_task_id: str,
        sub_task_input: Dict[str, Any],
        input_data: AgentInput,
    ) -> Dict[str, Any]:
        """Execute a single sub-task.
        
        Args:
            sub_task_id: Identifier for the sub-task
            sub_task_input: Input specific to this sub-task
            input_data: Original agent input for context
            
        Returns:
            Sub-task results
        """
        pass
    
    async def execute_parallel(
        self,
        sub_tasks: Dict[str, Dict[str, Any]],
        input_data: AgentInput,
    ) -> Dict[str, Any]:
        """Execute multiple sub-tasks in parallel.
        
        Args:
            sub_tasks: Dictionary mapping sub-task IDs to their inputs
            input_data: Original agent input for context
            
        Returns:
            Combined results from all sub-tasks
        """
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(self.max_parallel)
        
        async def run_with_semaphore(
            task_id: str,
            task_input: Dict[str, Any],
        ) -> tuple[str, Dict[str, Any]]:
            async with semaphore:
                result = await self.execute_sub_task(task_id, task_input, input_data)
                return task_id, result
        
        # Execute all sub-tasks
        tasks = [
            run_with_semaphore(task_id, task_input)
            for task_id, task_input in sub_tasks.items()
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Combine results
        combined: Dict[str, Any] = {}
        for result in results:
            if isinstance(result, Exception):
                # Handle error - could log and continue or raise
                raise result
            task_id, task_result = result
            combined[task_id] = task_result
        
        return combined
