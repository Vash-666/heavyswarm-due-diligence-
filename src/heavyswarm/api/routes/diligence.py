"""Diligence API endpoints with full database integration."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status, Depends
from pydantic import BaseModel, Field, field_validator

from heavyswarm.core.enums import (
    DiligenceStatus,
    Priority,
    Recommendation,
    RiskTolerance,
    TimeHorizon,
)
from heavyswarm.core.state import DiligenceState, InvestmentThesis
from heavyswarm.services.database import DatabaseService, db_service
from heavyswarm.services.background_tasks import (
    BackgroundTaskManager,
    TaskStatus,
    get_task_manager,
)
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class CreateDiligenceRequest(BaseModel):
    """Request to create a new diligence."""
    
    ticker: str = Field(..., min_length=1, max_length=10, description="Stock ticker symbol")
    thesis: str = Field(..., min_length=10, description="Investment thesis statement")
    time_horizon: TimeHorizon = Field(default=TimeHorizon.MEDIUM_TERM)
    risk_tolerance: RiskTolerance = Field(default=RiskTolerance.MODERATE)
    position_size: float = Field(default=0.05, ge=0, le=1)
    priority: Priority = Field(default=Priority.MEDIUM)
    deadline: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        """Validate ticker format."""
        return v.upper().strip()


class CreateDiligenceResponse(BaseModel):
    """Response from creating a diligence."""
    
    diligence_id: str
    status: str
    estimated_completion: str
    polling_url: str


class ProgressInfo(BaseModel):
    """Progress information for a diligence."""
    
    current_phase: Optional[str] = None
    completed_phases: List[str] = []
    percent_complete: float = 0.0


class DiligenceStatusResponse(BaseModel):
    """Diligence status response."""
    
    diligence_id: str
    status: str
    ticker: str
    created_at: str
    updated_at: str
    progress: ProgressInfo
    metrics: Dict[str, Any]
    estimated_completion: Optional[str] = None


class TradingSignalResponse(BaseModel):
    """Trading signal response."""
    
    signal_id: str
    timestamp: str
    ticker: str
    action: str
    confidence: float
    urgency: str
    position_sizing: Dict[str, Any]
    price_targets: Dict[str, Any]
    risk_metrics: Dict[str, Any]
    execution: Dict[str, Any]
    monitoring: Dict[str, Any]
    audit: Dict[str, Any]


class InvestmentMemoResponse(BaseModel):
    """Investment memo response."""
    
    memo: Dict[str, Any]


class DiligenceListItem(BaseModel):
    """Single item in diligence list."""
    
    diligence_id: str
    ticker: str
    status: str
    priority: str
    created_at: str
    confidence_score: Optional[float] = None
    recommendation: Optional[str] = None


class DiligenceListResponse(BaseModel):
    """Diligence list response."""
    
    total: int
    limit: int
    offset: int
    diligences: List[DiligenceListItem]


class AuditTrailResponse(BaseModel):
    """Audit trail response."""
    
    diligence_id: str
    events: List[Dict[str, Any]]


class CancelResponse(BaseModel):
    """Cancellation response."""
    
    diligence_id: str
    status: str
    cancelled_at: str


# =============================================================================
# Dependencies
# =============================================================================

async def get_db() -> DatabaseService:
    """Get database service."""
    return db_service


def get_task_manager_dep() -> Optional[BackgroundTaskManager]:
    """Get task manager dependency."""
    return get_task_manager()


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/diligence",
    response_model=CreateDiligenceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_diligence(
    request: CreateDiligenceRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseService = Depends(get_db),
    task_manager: Optional[BackgroundTaskManager] = Depends(get_task_manager_dep),
) -> Dict[str, Any]:
    """Create a new investment due diligence analysis.
    
    This endpoint initiates the 6-phase HeavySwarm analysis workflow:
    1. Question Generation
    2. Research (parallel data gathering)
    3. Financial & Risk Analysis (parallel)
    4. Strategy & Scenarios
    5. Verification
    6. Memo Writing
    + Quality Guardian (conditional)
    
    Args:
        request: Diligence creation request
        background_tasks: FastAPI background tasks
        db: Database service
        task_manager: Background task manager
        
    Returns:
        Diligence ID and polling information
    """
    diligence_id = str(uuid4())
    
    # Create investment thesis
    thesis = InvestmentThesis(
        ticker=request.ticker,
        thesis=request.thesis,
        time_horizon=request.time_horizon,
        risk_tolerance=request.risk_tolerance,
        position_size=request.position_size,
        priority=request.priority,
        deadline=datetime.fromisoformat(request.deadline) if request.deadline else None,
        metadata=request.metadata or {},
    )
    
    # Create initial state
    state = DiligenceState(
        thesis=thesis,
        status=DiligenceStatus.PENDING,
    )
    
    # Persist to database
    try:
        await db.create_diligence(
            diligence_id=diligence_id,
            ticker=request.ticker,
            thesis=request.thesis,
            time_horizon=request.time_horizon.value,
            risk_tolerance=request.risk_tolerance.value,
            position_size=request.position_size,
            priority=request.priority.value,
            status=DiligenceStatus.PENDING.value,
            state_data=state.to_full_dict(),
        )
        
        logger.info(
            "Diligence created in database",
            extra={
                "diligence_id": diligence_id,
                "ticker": request.ticker,
            },
        )
    except Exception as e:
        logger.error(
            "Failed to create diligence in database",
            extra={
                "diligence_id": diligence_id,
                "error": str(e),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create diligence: {str(e)}",
        )
    
    # Start background workflow if task manager is available
    if task_manager:
        try:
            await task_manager.start_diligence(
                diligence_id=diligence_id,
                thesis=thesis,
            )
            
            # Update status to in_progress
            await db.update_diligence_status(
                diligence_id=diligence_id,
                status=DiligenceStatus.IN_PROGRESS.value,
            )
            
            logger.info(
                "Diligence workflow started in background",
                extra={"diligence_id": diligence_id},
            )
        except Exception as e:
            logger.error(
                "Failed to start diligence workflow",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
            )
            # Don't fail the request - the diligence exists and can be started manually
    else:
        logger.warning(
            "Task manager not available - diligence created but not started",
            extra={"diligence_id": diligence_id},
        )
    
    return {
        "diligence_id": diligence_id,
        "status": "pending" if not task_manager else "in_progress",
        "estimated_completion": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
        "polling_url": f"/api/v1/diligence/{diligence_id}",
    }


@router.get("/diligence/{diligence_id}", response_model=DiligenceStatusResponse)
async def get_diligence_status(
    diligence_id: str,
    db: DatabaseService = Depends(get_db),
    task_manager: Optional[BackgroundTaskManager] = Depends(get_task_manager_dep),
) -> Dict[str, Any]:
    """Get the current status of a diligence analysis.
    
    Args:
        diligence_id: The diligence ID
        db: Database service
        task_manager: Background task manager
        
    Returns:
        Current status and progress information
    """
    # Get from database
    diligence = await db.get_diligence(diligence_id)
    
    if not diligence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diligence {diligence_id} not found",
        )
    
    state = diligence.get('state', {})
    
    # Get progress from task manager if available
    progress = ProgressInfo(
        current_phase=state.get('current_phase'),
        completed_phases=state.get('completed_phases', []),
        percent_complete=0.0,
    )
    
    if task_manager:
        task_info = task_manager.get_task_info(diligence_id)
        if task_info:
            progress.percent_complete = task_info.progress_percent
            if task_info.current_phase:
                progress.current_phase = task_info.current_phase
    
    # Calculate progress from completed phases if not from task manager
    if progress.percent_complete == 0.0 and progress.completed_phases:
        phase_weights = {
            "QUESTION_GENERATOR": 0.10,
            "RESEARCHER": 0.25,
            "FINANCIAL_ANALYST": 0.15,
            "RISK_ANALYST": 0.15,
            "STRATEGIST": 0.15,
            "VERIFIER": 0.10,
            "WRITER": 0.10,
        }
        total_weight = sum(phase_weights.values())
        completed_weight = sum(
            phase_weights.get(phase, 0)
            for phase in progress.completed_phases
        )
        progress.percent_complete = (completed_weight / total_weight) * 100
    
    # Build metrics
    metrics = {
        "overall_confidence": float(state.get('overall_confidence', 0)),
        "verification_rate": float(state.get('verification_rate', 0)),
        "total_data_points": state.get('total_data_points', 0),
        "verified_data_points": state.get('verified_data_points', 0),
        "quality_gate_triggered": state.get('quality_gate_triggered', False),
    }
    
    return {
        "diligence_id": diligence_id,
        "status": diligence['status'],
        "ticker": diligence.get('ticker', 'UNKNOWN'),
        "created_at": diligence['created_at'],
        "updated_at": diligence['updated_at'],
        "progress": progress,
        "metrics": metrics,
        "estimated_completion": (datetime.fromisoformat(diligence['created_at']) + timedelta(minutes=5)).isoformat()
        if diligence['status'] in ['pending', 'in_progress'] else None,
    }


@router.get("/diligence/{diligence_id}/memo", response_model=InvestmentMemoResponse)
async def get_investment_memo(
    diligence_id: str,
    db: DatabaseService = Depends(get_db),
) -> Dict[str, Any]:
    """Get the investment memo for a completed diligence.
    
    Args:
        diligence_id: The diligence ID
        db: Database service
        
    Returns:
        Investment memo with analysis and recommendation
    """
    # Check if diligence exists
    diligence = await db.get_diligence(diligence_id)
    
    if not diligence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diligence {diligence_id} not found",
        )
    
    # Get memo
    memo = await db.get_diligence_memo(diligence_id)
    
    if not memo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memo not yet available for diligence {diligence_id}",
        )
    
    return {"memo": memo}


@router.get("/diligence/{diligence_id}/signal", response_model=TradingSignalResponse)
async def get_trading_signal(
    diligence_id: str,
    db: DatabaseService = Depends(get_db),
) -> Dict[str, Any]:
    """Get the trading signal for a completed diligence.
    
    Args:
        diligence_id: The diligence ID
        db: Database service
        
    Returns:
        Trading signal with action, confidence, and risk metrics
    """
    # Check if diligence exists
    diligence = await db.get_diligence(diligence_id)
    
    if not diligence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diligence {diligence_id} not found",
        )
    
    # Get trading signal
    signal = await db.get_trading_signal(diligence_id)
    
    if not signal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trading signal not yet available for diligence {diligence_id}",
        )
    
    return signal


@router.get("/diligence/{diligence_id}/audit")
async def get_audit_trail(
    diligence_id: str,
    db: DatabaseService = Depends(get_db),
) -> Dict[str, Any]:
    """Get the complete audit trail for a diligence.
    
    Args:
        diligence_id: The diligence ID
        db: Database service
        
    Returns:
        Complete audit trail with all events and data provenance
    """
    # Check if diligence exists
    diligence = await db.get_diligence(diligence_id)
    
    if not diligence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diligence {diligence_id} not found",
        )
    
    # Get audit trail
    events = await db.get_audit_trail(diligence_id)
    
    return {
        "diligence_id": diligence_id,
        "events": events,
    }


@router.delete("/diligence/{diligence_id}", response_model=CancelResponse)
async def cancel_diligence(
    diligence_id: str,
    db: DatabaseService = Depends(get_db),
    task_manager: Optional[BackgroundTaskManager] = Depends(get_task_manager_dep),
) -> Dict[str, Any]:
    """Cancel an in-progress diligence.
    
    Args:
        diligence_id: The diligence ID
        db: Database service
        task_manager: Background task manager
        
    Returns:
        Cancellation confirmation
    """
    # Check if diligence exists
    diligence = await db.get_diligence(diligence_id)
    
    if not diligence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Diligence {diligence_id} not found",
        )
    
    # Check if already in terminal state
    if diligence['status'] in ['completed', 'failed', 'cancelled']:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Diligence {diligence_id} is already {diligence['status']}",
        )
    
    # Cancel background task if running
    if task_manager:
        cancelled = await task_manager.cancel_diligence(diligence_id)
        if cancelled:
            logger.info(
                "Diligence cancelled via task manager",
                extra={"diligence_id": diligence_id},
            )
    
    # Update database status
    await db.update_diligence_status(
        diligence_id=diligence_id,
        status=DiligenceStatus.CANCELLED.value,
    )
    
    return {
        "diligence_id": diligence_id,
        "status": "cancelled",
        "cancelled_at": datetime.utcnow().isoformat(),
    }


@router.get("/diligence", response_model=DiligenceListResponse)
async def list_diligences(
    status: Optional[str] = Query(None, description="Filter by status"),
    ticker: Optional[str] = Query(None, description="Filter by ticker"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: DatabaseService = Depends(get_db),
) -> Dict[str, Any]:
    """List all diligences with filtering and pagination.
    
    Args:
        status: Filter by status
        ticker: Filter by ticker symbol
        priority: Filter by priority
        limit: Maximum results per page
        offset: Pagination offset
        db: Database service
        
    Returns:
        Paginated list of diligences
    """
    diligences, total = await db.list_diligences(
        status=status,
        ticker=ticker.upper() if ticker else None,
        priority=priority,
        limit=limit,
        offset=offset,
    )
    
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "diligences": [
            DiligenceListItem(
                diligence_id=d['diligence_id'],
                ticker=d.get('ticker', 'UNKNOWN'),
                status=d['status'],
                priority=d.get('priority', 'medium'),
                created_at=d['created_at'],
                confidence_score=d.get('confidence'),
                recommendation=d.get('recommendation'),
            )
            for d in diligences
        ],
    }
