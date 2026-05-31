"""HeavySwarm orchestrator for managing the 6-phase + quality gate workflow."""

import asyncio
import time
from typing import Any, Dict, List, Optional

from heavyswarm.core.agent_base import BaseAgent, AgentInput
from heavyswarm.core.enums import AgentPhase, DiligenceStatus
from heavyswarm.core.state import DiligenceState, InvestmentThesis, PhaseResult
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class HeavySwarmOrchestrator:
    """Orchestrates the 6-phase + quality gate HeavySwarm workflow.
    
    The orchestrator manages the execution sequence of all agents,
    handles state transitions, and coordinates parallel execution
    where specified in the architecture.
    """
    
    # Define the standard phase execution order
    PHASE_ORDER: List[AgentPhase] = [
        AgentPhase.QUESTION_GENERATOR,
        AgentPhase.RESEARCHER,
        AgentPhase.FINANCIAL_ANALYST,
        AgentPhase.RISK_ANALYST,
        AgentPhase.STRATEGIST,
        AgentPhase.VERIFIER,
        AgentPhase.WRITER,
        AgentPhase.QUALITY_GUARDIAN,
    ]
    
    # Phases that can run in parallel
    PARALLEL_PHASES: List[List[AgentPhase]] = [
        [AgentPhase.FINANCIAL_ANALYST, AgentPhase.RISK_ANALYST],
    ]
    
    def __init__(
        self,
        agents: Dict[AgentPhase, BaseAgent],
        state_manager: Any,  # StateManager type (avoid circular import)
        max_concurrent: int = 10,
    ):
        """Initialize the orchestrator.
        
        Args:
            agents: Dictionary mapping phases to agent instances
            state_manager: State manager for persistence
            max_concurrent: Maximum concurrent diligences
        """
        self.agents = agents
        self.state_manager = state_manager
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running_diligences: Dict[str, asyncio.Task] = {}
        
        logger.info(
            "Orchestrator initialized",
            extra={
                "agents": [p.name for p in agents.keys()],
                "max_concurrent": max_concurrent,
            },
        )
    
    async def run_diligence(
        self,
        thesis: InvestmentThesis,
        diligence_id: Optional[str] = None,
    ) -> DiligenceState:
        """Execute the full diligence workflow.
        
        This is the main entry point for running a complete due diligence
        analysis through all phases of the HeavySwarm pattern.
        
        Args:
            thesis: The investment thesis to analyze
            diligence_id: Optional existing diligence ID (for resuming)
            
        Returns:
            Final diligence state with all results
        """
        async with self._semaphore:
            # Initialize or load state
            if diligence_id:
                state = await self.state_manager.load_state(diligence_id)
                if not state:
                    raise ValueError(f"Diligence {diligence_id} not found")
            else:
                state = DiligenceState(thesis=thesis)
            
            state.status = DiligenceStatus.IN_PROGRESS
            await self.state_manager.save_state(state)
            
            logger.info(
                "Starting diligence workflow",
                extra={
                    "diligence_id": state.diligence_id,
                    "ticker": thesis.ticker if thesis else None,
                },
            )
            
            try:
                # Phase 0: Question Generation
                await self._execute_phase(state, AgentPhase.QUESTION_GENERATOR)
                
                # Phase 1: Research
                await self._execute_phase(state, AgentPhase.RESEARCHER)
                
                # Phase 2: Analysis (Parallel - Financial & Risk)
                await self._execute_parallel_phases(
                    state,
                    [AgentPhase.FINANCIAL_ANALYST, AgentPhase.RISK_ANALYST],
                )
                
                # Phase 3: Strategy
                await self._execute_phase(state, AgentPhase.STRATEGIST)
                
                # Phase 4: Verification
                await self._execute_phase(state, AgentPhase.VERIFIER)
                
                # Check if quality gate should be triggered
                if state.should_trigger_quality_gate(self.state_manager.settings):
                    state.quality_gate_triggered = True
                    state.status = DiligenceStatus.QUALITY_GATE
                    await self.state_manager.save_state(state)
                    logger.info(
                        "Quality gate triggered",
                        extra={
                            "diligence_id": state.diligence_id,
                            "confidence": state.overall_confidence,
                        },
                    )
                
                # Phase 5: Writing
                await self._execute_phase(state, AgentPhase.WRITER)
                
                # Quality Gate (conditional)
                if state.quality_gate_triggered:
                    await self._execute_phase(state, AgentPhase.QUALITY_GUARDIAN)
                
                # Mark as completed
                state.status = DiligenceStatus.COMPLETED
                state.completed_at = datetime.utcnow()
                
                logger.info(
                    "Diligence completed successfully",
                    extra={
                        "diligence_id": state.diligence_id,
                        "duration_seconds": state.duration_seconds,
                        "confidence": state.overall_confidence,
                    },
                )
                
            except Exception as e:
                state.status = DiligenceStatus.FAILED
                state.add_event(
                    "error",
                    "orchestrator",
                    {"error": str(e), "error_type": type(e).__name__},
                )
                logger.error(
                    "Diligence failed",
                    extra={
                        "diligence_id": state.diligence_id,
                        "error": str(e),
                    },
                    exc_info=True,
                )
                raise
            
            finally:
                await self.state_manager.save_state(state)
                if state.diligence_id in self._running_diligences:
                    del self._running_diligences[state.diligence_id]
            
            return state
    
    async def _execute_phase(
        self,
        state: DiligenceState,
        phase: AgentPhase,
    ) -> None:
        """Execute a single phase.
        
        Args:
            state: Current diligence state
            phase: Phase to execute
        """
        agent = self.agents.get(phase)
        if not agent:
            raise ValueError(f"No agent configured for phase {phase}")
        
        state.current_phase = phase
        state.add_event("phase_started", phase.name, {})
        
        logger.info(
            "Starting phase",
            extra={
                "diligence_id": state.diligence_id,
                "phase": phase.name,
            },
        )
        
        # Prepare input
        context = state.get_context_for_phase(phase)
        input_data = AgentInput(
            thesis=state.thesis,
            context=context,
            previous_outputs={
                p: r.output for p, r in state.phase_results.items()
            },
            state=state,
        )
        
        # Execute with timing
        start_time = time.time()
        try:
            output = await agent.run_with_timeout(input_data)
            processing_time = int((time.time() - start_time) * 1000)
            
            # Store result
            phase_result = PhaseResult(
                phase=phase,
                output=output.data,
                confidence=output.confidence,
                processing_time_ms=processing_time,
                completed_at=datetime.utcnow(),
                agent_id=phase.name,
            )
            state.add_phase_result(phase_result)
            
            # Update overall confidence from verifier
            if phase == AgentPhase.VERIFIER:
                state.overall_confidence = output.confidence
            
            state.add_event(
                "phase_completed",
                phase.name,
                {
                    "confidence": output.confidence,
                    "processing_time_ms": processing_time,
                },
            )
            
            logger.info(
                "Phase completed",
                extra={
                    "diligence_id": state.diligence_id,
                    "phase": phase.name,
                    "confidence": output.confidence,
                    "processing_time_ms": processing_time,
                },
            )
            
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            phase_result = PhaseResult(
                phase=phase,
                output={},
                confidence=0.0,
                processing_time_ms=processing_time,
                completed_at=datetime.utcnow(),
                agent_id=phase.name,
                error=str(e),
            )
            state.add_phase_result(phase_result)
            raise
        
        finally:
            await self.state_manager.save_state(state)
    
    async def _execute_parallel_phases(
        self,
        state: DiligenceState,
        phases: List[AgentPhase],
    ) -> None:
        """Execute multiple phases in parallel.
        
        Args:
            state: Current diligence state
            phases: List of phases to execute in parallel
        """
        logger.info(
            "Starting parallel phases",
            extra={
                "diligence_id": state.diligence_id,
                "phases": [p.name for p in phases],
            },
        )
        
        # Create tasks for each phase
        tasks = [
            self._execute_phase(state, phase)
            for phase in phases
        ]
        
        # Execute all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check for errors
        errors = [r for r in results if isinstance(r, Exception)]
        if errors:
            raise errors[0]
        
        logger.info(
            "Parallel phases completed",
            extra={
                "diligence_id": state.diligence_id,
                "phases": [p.name for p in phases],
            },
        )
    
    async def cancel_diligence(self, diligence_id: str) -> bool:
        """Cancel a running diligence.
        
        Args:
            diligence_id: ID of diligence to cancel
            
        Returns:
            True if cancelled, False if not found or already complete
        """
        if diligence_id not in self._running_diligences:
            return False
        
        task = self._running_diligences[diligence_id]
        task.cancel()
        
        try:
            await task
        except asyncio.CancelledError:
            pass
        
        # Update state
        state = await self.state_manager.load_state(diligence_id)
        if state:
            state.status = DiligenceStatus.CANCELLED
            await self.state_manager.save_state(state)
        
        del self._running_diligences[diligence_id]
        
        logger.info(
            "Diligence cancelled",
            extra={"diligence_id": diligence_id},
        )
        
        return True
    
    def get_running_count(self) -> int:
        """Get number of currently running diligences.
        
        Returns:
            Count of active diligences
        """
        return len(self._running_diligences)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics.
        
        Returns:
            Dictionary with orchestrator statistics
        """
        return {
            "max_concurrent": self.max_concurrent,
            "running_diligences": len(self._running_diligences),
            "available_slots": self.max_concurrent - len(self._running_diligences),
            "agents": [p.name for p in self.agents.keys()],
        }


# Import at end to avoid circular import
from datetime import datetime
