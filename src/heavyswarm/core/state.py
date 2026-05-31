"""State management for HeavySwarm diligence workflows."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from heavyswarm.core.enums import (
    AgentPhase,
    DiligenceStatus,
    Priority,
    RiskTolerance,
    TimeHorizon,
    VerificationLevel,
)


@dataclass
class InvestmentThesis:
    """Investment thesis input data."""
    
    ticker: str
    thesis: str
    time_horizon: TimeHorizon = TimeHorizon.MEDIUM_TERM
    risk_tolerance: RiskTolerance = RiskTolerance.MODERATE
    position_size: float = 0.05
    priority: Priority = Priority.MEDIUM
    deadline: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Validate inputs after initialization."""
        if not self.ticker or not isinstance(self.ticker, str):
            raise ValueError("Ticker must be a non-empty string")
        if not self.thesis or len(self.thesis) < 10:
            raise ValueError("Thesis must be at least 10 characters")
        if not 0 < self.position_size <= 1:
            raise ValueError("Position size must be between 0 and 1")


@dataclass
class DataProvenance:
    """Data provenance tracking for audit trail."""
    
    data_id: str
    value: Any
    source_url: str
    retrieved_at: datetime
    verified_by: str
    verification_level: VerificationLevel = VerificationLevel.L1
    confidence: float = 1.0
    chain_of_custody: List[str] = field(default_factory=list)
    cross_references: List[Dict[str, Any]] = field(default_factory=list)
    expires_at: Optional[datetime] = None
    
    def __post_init__(self) -> None:
        """Validate confidence score."""
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")


@dataclass
class PhaseResult:
    """Result from a single agent phase execution."""
    
    phase: AgentPhase
    output: Dict[str, Any]
    confidence: float
    processing_time_ms: int
    completed_at: datetime
    agent_id: str
    error: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Validate confidence score."""
        if not 0 <= self.confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")


@dataclass
class AuditEvent:
    """Single audit event for compliance tracking."""
    
    timestamp: datetime
    event_type: str
    agent_id: str
    details: Dict[str, Any]
    event_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class CheckpointMetadata:
    """Metadata for a state checkpoint.
    
    Tracks checkpoint information including when it was created,
    what phase the diligence was in, and why it was created.
    """
    
    checkpoint_id: str = field(default_factory=lambda: str(uuid4()))
    diligence_id: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = "system"  # agent_id or user_id
    phase: Optional[AgentPhase] = None
    status: DiligenceStatus = DiligenceStatus.PENDING
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    parent_checkpoint_id: Optional[str] = None  # For checkpoint chains
    
    # Metrics at checkpoint time
    overall_confidence: float = 0.0
    verification_rate: float = 0.0
    completed_phases_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert checkpoint metadata to dictionary."""
        return {
            "checkpoint_id": self.checkpoint_id,
            "diligence_id": self.diligence_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
            "phase": self.phase.name if self.phase else None,
            "status": self.status.value if self.status else None,
            "description": self.description,
            "tags": self.tags,
            "parent_checkpoint_id": self.parent_checkpoint_id,
            "overall_confidence": self.overall_confidence,
            "verification_rate": self.verification_rate,
            "completed_phases_count": self.completed_phases_count,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CheckpointMetadata":
        """Create CheckpointMetadata from dictionary."""
        from heavyswarm.core.enums import DiligenceStatus, AgentPhase
        
        metadata = cls(
            checkpoint_id=data.get("checkpoint_id", str(uuid4())),
            diligence_id=data.get("diligence_id", ""),
            created_by=data.get("created_by", "system"),
            description=data.get("description"),
            tags=data.get("tags", []),
            parent_checkpoint_id=data.get("parent_checkpoint_id"),
            overall_confidence=data.get("overall_confidence", 0.0),
            verification_rate=data.get("verification_rate", 0.0),
            completed_phases_count=data.get("completed_phases_count", 0),
        )
        
        # Parse datetime
        if data.get("created_at"):
            if isinstance(data["created_at"], str):
                metadata.created_at = datetime.fromisoformat(data["created_at"])
            else:
                metadata.created_at = data["created_at"]
        
        # Parse phase
        if data.get("phase"):
            metadata.phase = AgentPhase[data["phase"]]
        
        # Parse status
        if data.get("status"):
            if isinstance(data["status"], str):
                metadata.status = DiligenceStatus(data["status"])
            else:
                metadata.status = data["status"]
        
        return metadata


@dataclass
class StateCheckpoint:
    """Complete checkpoint of a diligence state.
    
    Contains both the full state data and checkpoint metadata
    for restore operations.
    """
    
    metadata: CheckpointMetadata = field(default_factory=CheckpointMetadata)
    state_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert checkpoint to dictionary."""
        return {
            "metadata": self.metadata.to_dict(),
            "state_data": self.state_data,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StateCheckpoint":
        """Create StateCheckpoint from dictionary."""
        return cls(
            metadata=CheckpointMetadata.from_dict(data.get("metadata", {})),
            state_data=data.get("state_data", {}),
        )


@dataclass
class DiligenceState:
    """Central state object shared across all agents in a diligence workflow.
    
    This is the core data structure that maintains the complete state of an
    investment due diligence analysis from start to finish.
    """
    
    # =========================================================================
    # Identity & Timing
    # =========================================================================
    diligence_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # =========================================================================
    # Input
    # =========================================================================
    thesis: Optional[InvestmentThesis] = None
    
    # =========================================================================
    # Progress Tracking
    # =========================================================================
    status: DiligenceStatus = DiligenceStatus.PENDING
    current_phase: Optional[AgentPhase] = None
    completed_phases: List[AgentPhase] = field(default_factory=list)
    
    # =========================================================================
    # Phase Results
    # =========================================================================
    phase_results: Dict[AgentPhase, PhaseResult] = field(default_factory=dict)
    data_provenance: Dict[str, DataProvenance] = field(default_factory=dict)
    
    # =========================================================================
    # Aggregated Metrics
    # =========================================================================
    overall_confidence: float = 0.0
    verification_rate: float = 0.0
    total_data_points: int = 0
    verified_data_points: int = 0
    
    # =========================================================================
    # Quality Gate
    # =========================================================================
    quality_gate_triggered: bool = False
    quality_gate_result: Optional[Dict[str, Any]] = None
    
    # =========================================================================
    # Final Output
    # =========================================================================
    memo: Optional[Dict[str, Any]] = None
    trading_signal: Optional[Dict[str, Any]] = None
    
    # =========================================================================
    # Audit Trail
    # =========================================================================
    events: List[AuditEvent] = field(default_factory=list)
    
    # =========================================================================
    # Checkpoint Tracking
    # =========================================================================
    checkpoint_history: List[str] = field(default_factory=list)  # List of checkpoint_ids
    restored_from_checkpoint: Optional[str] = None  # checkpoint_id if restored
    
    def add_event(
        self,
        event_type: str,
        agent_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEvent:
        """Add an immutable audit event.
        
        Args:
            event_type: Type of event (e.g., 'phase_started', 'phase_completed')
            agent_id: ID of the agent that triggered the event
            details: Additional event details
            
        Returns:
            The created audit event
        """
        event = AuditEvent(
            timestamp=datetime.utcnow(),
            event_type=event_type,
            agent_id=agent_id,
            details=details or {},
        )
        self.events.append(event)
        self.updated_at = datetime.utcnow()
        return event
    
    def add_phase_result(self, result: PhaseResult) -> None:
        """Add a phase result and update progress.
        
        Args:
            result: The phase execution result
        """
        self.phase_results[result.phase] = result
        if result.phase not in self.completed_phases:
            self.completed_phases.append(result.phase)
        self.updated_at = datetime.utcnow()
    
    def add_data_provenance(self, provenance: DataProvenance) -> None:
        """Add data provenance entry.
        
        Args:
            provenance: Data provenance record
        """
        self.data_provenance[provenance.data_id] = provenance
        self.total_data_points += 1
        if provenance.verification_level in [
            VerificationLevel.L2,
            VerificationLevel.L3,
            VerificationLevel.L4,
        ]:
            self.verified_data_points += 1
        self.verification_rate = (
            self.verified_data_points / self.total_data_points
            if self.total_data_points > 0
            else 0.0
        )
        self.updated_at = datetime.utcnow()
    
    def get_context_for_phase(self, phase: AgentPhase) -> Dict[str, Any]:
        """Get relevant context for a specific phase.
        
        This method compiles all relevant information from previous phases
        that should be passed to the specified phase.
        
        Args:
            phase: The target phase
            
        Returns:
            Context dictionary with thesis and previous phase outputs
        """
        context: Dict[str, Any] = {
            "thesis": self.thesis,
            "diligence_id": self.diligence_id,
            "previous_phases": {},
        }
        
        # Include outputs from all previous phases
        for p in AgentPhase:
            if p.value < phase.value and p in self.phase_results:
                context["previous_phases"][p.name] = self.phase_results[p].output
        
        return context
    
    def should_trigger_quality_gate(self, settings: Any) -> bool:
        """Determine if quality gate should be triggered.
        
        Args:
            settings: Application settings with thresholds
            
        Returns:
            True if quality gate should be triggered
        """
        if not settings.quality_gate_enabled:
            return False
            
        # Check confidence threshold
        if self.overall_confidence < settings.confidence_threshold:
            return True
            
        # Check position size threshold
        if self.thesis and self.thesis.position_size > settings.max_position_size_pct:
            return True
            
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization.
        
        Returns:
            Dictionary representation of the state
        """
        return {
            "diligence_id": self.diligence_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status.value,
            "current_phase": self.current_phase.name if self.current_phase else None,
            "completed_phases": [p.name for p in self.completed_phases],
            "overall_confidence": self.overall_confidence,
            "verification_rate": self.verification_rate,
            "total_data_points": self.total_data_points,
            "verified_data_points": self.verified_data_points,
            "quality_gate_triggered": self.quality_gate_triggered,
            "thesis": {
                "ticker": self.thesis.ticker if self.thesis else None,
                "time_horizon": self.thesis.time_horizon.value if self.thesis else None,
                "risk_tolerance": self.thesis.risk_tolerance.value if self.thesis else None,
                "position_size": self.thesis.position_size if self.thesis else None,
            } if self.thesis else None,
            "checkpoint_history": self.checkpoint_history,
            "restored_from_checkpoint": self.restored_from_checkpoint,
        }
    
    def to_full_dict(self) -> Dict[str, Any]:
        """Convert complete state to dictionary including all nested objects.
        
        Returns:
            Complete dictionary representation suitable for checkpointing
        """
        base = self.to_dict()
        
        # Add full phase results
        base["phase_results"] = {
            phase.name: {
                "phase": result.phase.name,
                "output": result.output,
                "confidence": result.confidence,
                "processing_time_ms": result.processing_time_ms,
                "completed_at": result.completed_at.isoformat() if result.completed_at else None,
                "agent_id": result.agent_id,
                "error": result.error,
            }
            for phase, result in self.phase_results.items()
        }
        
        # Add full data provenance
        base["data_provenance"] = {
            data_id: {
                "data_id": prov.data_id,
                "value": prov.value,
                "source_url": prov.source_url,
                "retrieved_at": prov.retrieved_at.isoformat() if prov.retrieved_at else None,
                "verified_by": prov.verified_by,
                "verification_level": prov.verification_level.value,
                "confidence": prov.confidence,
                "chain_of_custody": prov.chain_of_custody,
                "cross_references": prov.cross_references,
                "expires_at": prov.expires_at.isoformat() if prov.expires_at else None,
            }
            for data_id, prov in self.data_provenance.items()
        }
        
        # Add full events
        base["events"] = [
            {
                "event_id": event.event_id,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                "event_type": event.event_type,
                "agent_id": event.agent_id,
                "details": event.details,
            }
            for event in self.events
        ]
        
        # Add memo and trading signal
        base["memo"] = self.memo
        base["trading_signal"] = self.trading_signal
        base["quality_gate_result"] = self.quality_gate_result
        
        return base
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiligenceState":
        """Create DiligenceState from dictionary.
        
        Args:
            data: Dictionary containing state data
            
        Returns:
            Reconstructed DiligenceState
        """
        from heavyswarm.core.enums import DiligenceStatus, AgentPhase
        
        state = cls(
            diligence_id=data.get("diligence_id", str(uuid4())),
        )
        
        # Parse timestamps
        if data.get("created_at"):
            state.created_at = datetime.fromisoformat(data["created_at"]) if isinstance(data["created_at"], str) else data["created_at"]
        if data.get("updated_at"):
            state.updated_at = datetime.fromisoformat(data["updated_at"]) if isinstance(data["updated_at"], str) else data["updated_at"]
        if data.get("completed_at"):
            state.completed_at = datetime.fromisoformat(data["completed_at"]) if isinstance(data["completed_at"], str) else data["completed_at"]
        
        # Parse status
        if data.get("status"):
            state.status = DiligenceStatus(data["status"]) if isinstance(data["status"], str) else data["status"]
        
        # Parse current phase
        if data.get("current_phase"):
            state.current_phase = AgentPhase[data["current_phase"]]
        
        # Parse completed phases
        if data.get("completed_phases"):
            state.completed_phases = [
                AgentPhase[p] if isinstance(p, str) else p
                for p in data["completed_phases"]
            ]
        
        # Parse metrics
        state.overall_confidence = data.get("overall_confidence", 0.0)
        state.verification_rate = data.get("verification_rate", 0.0)
        state.total_data_points = data.get("total_data_points", 0)
        state.verified_data_points = data.get("verified_data_points", 0)
        state.quality_gate_triggered = data.get("quality_gate_triggered", False)
        
        # Parse checkpoint tracking
        state.checkpoint_history = data.get("checkpoint_history", [])
        state.restored_from_checkpoint = data.get("restored_from_checkpoint")
        
        # Parse thesis (simplified - full reconstruction would need more logic)
        if data.get("thesis"):
            thesis_data = data["thesis"]
            if isinstance(thesis_data, dict) and thesis_data.get("ticker"):
                state.thesis = InvestmentThesis(
                    ticker=thesis_data["ticker"],
                    thesis=thesis_data.get("thesis", ""),
                    time_horizon=TimeHorizon(thesis_data.get("time_horizon", "medium_term")),
                    risk_tolerance=RiskTolerance(thesis_data.get("risk_tolerance", "moderate")),
                    position_size=thesis_data.get("position_size", 0.05),
                )
        
        # Parse phase results (simplified)
        if data.get("phase_results"):
            for phase_name, result_data in data["phase_results"].items():
                if isinstance(result_data, dict):
                    phase = AgentPhase[result_data.get("phase", phase_name)]
                    state.phase_results[phase] = PhaseResult(
                        phase=phase,
                        output=result_data.get("output", {}),
                        confidence=result_data.get("confidence", 0.0),
                        processing_time_ms=result_data.get("processing_time_ms", 0),
                        completed_at=datetime.fromisoformat(result_data["completed_at"]) if result_data.get("completed_at") else datetime.utcnow(),
                        agent_id=result_data.get("agent_id", "unknown"),
                        error=result_data.get("error"),
                    )
        
        # Parse memo and trading signal
        state.memo = data.get("memo")
        state.trading_signal = data.get("trading_signal")
        state.quality_gate_result = data.get("quality_gate_result")
        
        return state
    
    def create_checkpoint_metadata(
        self,
        created_by: str = "system",
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        parent_checkpoint_id: Optional[str] = None,
    ) -> CheckpointMetadata:
        """Create checkpoint metadata from current state.
        
        Args:
            created_by: ID of entity creating the checkpoint
            description: Optional description
            tags: Optional tags
            parent_checkpoint_id: Optional parent checkpoint for chains
            
        Returns:
            CheckpointMetadata instance
        """
        return CheckpointMetadata(
            diligence_id=self.diligence_id,
            created_by=created_by,
            phase=self.current_phase,
            status=self.status,
            description=description,
            tags=tags or [],
            parent_checkpoint_id=parent_checkpoint_id,
            overall_confidence=self.overall_confidence,
            verification_rate=self.verification_rate,
            completed_phases_count=len(self.completed_phases),
        )
    
    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate the duration of the diligence in seconds.
        
        Returns:
            Duration in seconds, or None if not completed
        """
        if self.completed_at and self.created_at:
            return (self.completed_at - self.created_at).total_seconds()
        return None
    
    @property
    def is_complete(self) -> bool:
        """Check if diligence is complete.
        
        Returns:
            True if status is COMPLETED
        """
        return self.status == DiligenceStatus.COMPLETED
    
    @property
    def has_failed(self) -> bool:
        """Check if diligence has failed.
        
        Returns:
            True if status is FAILED
        """
        return self.status == DiligenceStatus.FAILED
    
    @property
    def is_active(self) -> bool:
        """Check if diligence is currently active.
        
        Returns:
            True if status indicates active processing
        """
        return self.status in [
            DiligenceStatus.PENDING,
            DiligenceStatus.IN_PROGRESS,
            DiligenceStatus.VERIFYING,
            DiligenceStatus.QUALITY_GATE,
        ]
