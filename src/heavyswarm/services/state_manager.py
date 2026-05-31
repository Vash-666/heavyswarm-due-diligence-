"""State management service for persistence, caching, and checkpointing."""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from heavyswarm.core.config import Settings
from heavyswarm.core.enums import AgentPhase, DiligenceStatus
from heavyswarm.core.state import (
    CheckpointMetadata,
    DiligenceState,
    StateCheckpoint,
)
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class DiligenceStateEncoder(json.JSONEncoder):
    """Custom JSON encoder for DiligenceState."""
    
    def default(self, obj: Any) -> Any:
        """Handle custom types."""
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if hasattr(obj, "value"):
            return obj.value
        if hasattr(obj, "__dataclass_fields__"):
            return obj.__dict__
        return super().default(obj)


class StateTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""
    pass


class CheckpointError(Exception):
    """Raised when checkpoint operation fails."""
    pass


class StateNotFoundError(Exception):
    """Raised when a requested state is not found."""
    pass


class StateManager:
    """Manages persistence, retrieval, and checkpointing of diligence states.
    
    This service handles:
    - Hot caching (Redis) for fast access
    - Persistent storage (PostgreSQL) for durability
    - Checkpoint/restore functionality for state management
    - State transition validation
    - State comparison and diff operations
    - Archival of old states
    """
    
    # Valid state transitions matrix
    # From Status -> Set of valid To Statuses
    VALID_TRANSITIONS: Dict[DiligenceStatus, Set[DiligenceStatus]] = {
        DiligenceStatus.PENDING: {
            DiligenceStatus.IN_PROGRESS,
            DiligenceStatus.CANCELLED,
        },
        DiligenceStatus.IN_PROGRESS: {
            DiligenceStatus.VERIFYING,
            DiligenceStatus.QUALITY_GATE,
            DiligenceStatus.COMPLETED,
            DiligenceStatus.FAILED,
            DiligenceStatus.CANCELLED,
        },
        DiligenceStatus.VERIFYING: {
            DiligenceStatus.IN_PROGRESS,
            DiligenceStatus.QUALITY_GATE,
            DiligenceStatus.COMPLETED,
            DiligenceStatus.FAILED,
            DiligenceStatus.CANCELLED,
        },
        DiligenceStatus.QUALITY_GATE: {
            DiligenceStatus.IN_PROGRESS,
            DiligenceStatus.COMPLETED,
            DiligenceStatus.FAILED,
            DiligenceStatus.CANCELLED,
        },
        DiligenceStatus.COMPLETED: set(),  # Terminal state
        DiligenceStatus.FAILED: set(),  # Terminal state
        DiligenceStatus.CANCELLED: set(),  # Terminal state
    }
    
    def __init__(
        self,
        redis_client: Any,
        db_client: Any,
        settings: Settings,
    ):
        """Initialize state manager.
        
        Args:
            redis_client: Redis client for hot cache
            db_client: Database client for persistent storage
            settings: Application settings
        """
        self.redis = redis_client
        self.db = db_client
        self.settings = settings
        self._cache_ttl = settings.cache_ttl_medium  # 1 hour default
        
        logger.info("StateManager initialized")
    
    # =========================================================================
    # CRUD Operations
    # =========================================================================
    
    async def create_state(
        self,
        state: DiligenceState,
        skip_cache: bool = False,
    ) -> DiligenceState:
        """Create a new diligence state.
        
        Args:
            state: Diligence state to create
            skip_cache: If True, don't cache the state
            
        Returns:
            The created state
            
        Raises:
            ValueError: If state with same ID already exists
        """
        try:
            # Check if state already exists
            existing = await self.load_state(state.diligence_id, use_cache=False)
            if existing:
                raise ValueError(
                    f"State with diligence_id {state.diligence_id} already exists"
                )
            
            # Ensure timestamps are set
            now = datetime.utcnow()
            if not state.created_at:
                state.created_at = now
            state.updated_at = now
            
            # Serialize state
            state_json = json.dumps(state.to_full_dict(), cls=DiligenceStateEncoder)
            
            # Save to database
            await self.db.execute(
                """
                INSERT INTO diligence_states (id, state, updated_at)
                VALUES ($1, $2, NOW())
                """,
                state.diligence_id,
                state_json,
            )
            
            # Save to cache
            if self.settings.enable_cache and not skip_cache:
                await self.redis.setex(
                    f"diligence:{state.diligence_id}",
                    self._cache_ttl,
                    state_json,
                )
            
            logger.info(
                "State created",
                extra={
                    "diligence_id": state.diligence_id,
                    "status": state.status.value,
                },
            )
            
            return state
            
        except Exception as e:
            logger.error(
                "Failed to create state",
                extra={
                    "diligence_id": state.diligence_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
    
    async def get_state(
        self,
        diligence_id: str,
        use_cache: bool = True,
    ) -> DiligenceState:
        """Get a diligence state by ID.
        
        Args:
            diligence_id: ID of diligence to retrieve
            use_cache: Whether to use cache
            
        Returns:
            DiligenceState instance
            
        Raises:
            StateNotFoundError: If state not found
        """
        state = await self.load_state(diligence_id, use_cache=use_cache)
        if state is None:
            raise StateNotFoundError(f"State not found for diligence_id: {diligence_id}")
        return state
    
    async def load_state(
        self,
        diligence_id: str,
        use_cache: bool = True,
    ) -> Optional[DiligenceState]:
        """Load state from cache or database.
        
        Args:
            diligence_id: ID of diligence to load
            use_cache: Whether to check cache first
            
        Returns:
            DiligenceState if found, None otherwise
        """
        try:
            # Try cache first
            if use_cache and self.settings.enable_cache:
                cached = await self.redis.get(f"diligence:{diligence_id}")
                if cached:
                    logger.debug(
                        "State loaded from cache",
                        extra={"diligence_id": diligence_id},
                    )
                    return self._deserialize_state(cached)
            
            # Fall back to database
            row = await self.db.fetchrow(
                "SELECT state FROM diligence_states WHERE id = $1 AND archived = FALSE",
                diligence_id,
            )
            
            if row:
                logger.debug(
                    "State loaded from database",
                    extra={"diligence_id": diligence_id},
                )
                state = self._deserialize_state(row["state"])
                
                # Populate cache
                if self.settings.enable_cache:
                    await self.redis.setex(
                        f"diligence:{diligence_id}",
                        self._cache_ttl,
                        row["state"],
                    )
                
                return state
            
            return None
            
        except Exception as e:
            logger.error(
                "Failed to load state",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
    
    async def update_state(
        self,
        state: DiligenceState,
        agent_id: str = "system",
        skip_cache: bool = False,
    ) -> DiligenceState:
        """Update an existing diligence state.
        
        Args:
            state: Updated state
            agent_id: ID of agent making the update
            skip_cache: If True, don't update cache
            
        Returns:
            The updated state
            
        Raises:
            StateNotFoundError: If state doesn't exist
        """
        try:
            # Verify state exists
            existing = await self.load_state(state.diligence_id, use_cache=False)
            if existing is None:
                raise StateNotFoundError(
                    f"Cannot update: State not found for diligence_id: {state.diligence_id}"
                )
            
            # Update timestamp
            state.updated_at = datetime.utcnow()
            
            # Serialize state
            state_json = json.dumps(state.to_full_dict(), cls=DiligenceStateEncoder)
            
            # Update database
            await self.db.execute(
                """
                UPDATE diligence_states 
                SET state = $2, updated_at = NOW()
                WHERE id = $1
                """,
                state.diligence_id,
                state_json,
            )
            
            # Update cache
            if self.settings.enable_cache and not skip_cache:
                await self.redis.setex(
                    f"diligence:{state.diligence_id}",
                    self._cache_ttl,
                    state_json,
                )
            
            # Add audit event
            await self.add_audit_event(
                diligence_id=state.diligence_id,
                event_type="state_updated",
                agent_id=agent_id,
                details={"status": state.status.value},
            )
            
            logger.debug(
                "State updated",
                extra={
                    "diligence_id": state.diligence_id,
                    "status": state.status.value,
                },
            )
            
            return state
            
        except Exception as e:
            logger.error(
                "Failed to update state",
                extra={
                    "diligence_id": state.diligence_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
    
    async def delete_state(
        self,
        diligence_id: str,
        hard_delete: bool = False,
    ) -> bool:
        """Delete state from cache and database.
        
        Args:
            diligence_id: ID of diligence to delete
            hard_delete: If True, permanently delete; otherwise archive
            
        Returns:
            True if deleted/archived, False if not found
        """
        try:
            # Delete from cache
            if self.settings.enable_cache:
                await self.redis.delete(f"diligence:{diligence_id}")
            
            if hard_delete:
                # Permanently delete from database
                result = await self.db.execute(
                    "DELETE FROM diligence_states WHERE id = $1",
                    diligence_id,
                )
                deleted = result != "DELETE 0"
                action = "deleted"
            else:
                # Soft delete (archive)
                result = await self.db.execute(
                    """
                    UPDATE diligence_states 
                    SET archived = TRUE, archived_at = NOW()
                    WHERE id = $1 AND archived = FALSE
                    """,
                    diligence_id,
                )
                deleted = result != "UPDATE 0"
                action = "archived"
            
            logger.info(
                f"State {action}",
                extra={
                    "diligence_id": diligence_id,
                    "deleted": deleted,
                    "hard_delete": hard_delete,
                },
            )
            
            return deleted
            
        except Exception as e:
            logger.error(
                "Failed to delete state",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
    
    async def list_states(
        self,
        status: Optional[str] = None,
        ticker: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List diligence states with filtering.
        
        Args:
            status: Filter by status
            ticker: Filter by ticker
            include_archived: Include archived states
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of state summaries
        """
        try:
            # Build query
            conditions = ["1=1"]
            params = []
            
            if status:
                conditions.append(f"state->>'status' = ${len(params) + 1}")
                params.append(status)
            
            if ticker:
                conditions.append(f"state->'thesis'->>'ticker' = ${len(params) + 1}")
                params.append(ticker)
            
            if not include_archived:
                conditions.append("(archived = FALSE OR archived IS NULL)")
            
            where_clause = "WHERE " + " AND ".join(conditions)
            
            query = f"""
                SELECT 
                    id,
                    state->>'status' as status,
                    state->'thesis'->>'ticker' as ticker,
                    state->>'created_at' as created_at,
                    state->>'updated_at' as updated_at,
                    state->>'overall_confidence' as confidence,
                    archived,
                    archived_at
                FROM diligence_states
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """
            
            params.extend([limit, offset])
            
            rows = await self.db.fetch(query, *params)
            
            return [
                {
                    "diligence_id": row["id"],
                    "status": row["status"],
                    "ticker": row["ticker"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "confidence": float(row["confidence"]) if row["confidence"] else None,
                    "archived": row["archived"] or False,
                    "archived_at": row["archived_at"].isoformat() if row["archived_at"] else None,
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(
                "Failed to list states",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise
    
    # =========================================================================
    # State Transition Validation
    # =========================================================================
    
    def validate_transition(
        self,
        current_status: DiligenceStatus,
        new_status: DiligenceStatus,
    ) -> bool:
        """Validate if a state transition is allowed.
        
        Args:
            current_status: Current status
            new_status: Desired new status
            
        Returns:
            True if transition is valid
            
        Raises:
            StateTransitionError: If transition is invalid
        """
        # Same status is always valid (no-op)
        if current_status == new_status:
            return True
        
        # Check if transition is valid
        valid_next = self.VALID_TRANSITIONS.get(current_status, set())
        if new_status not in valid_next:
            raise StateTransitionError(
                f"Invalid state transition from {current_status.value} to {new_status.value}. "
                f"Valid transitions: {[s.value for s in valid_next]}"
            )
        
        return True
    
    async def transition_state(
        self,
        diligence_id: str,
        new_status: DiligenceStatus,
        agent_id: str = "system",
        validate: bool = True,
    ) -> DiligenceState:
        """Transition a state to a new status with validation.
        
        Args:
            diligence_id: ID of diligence
            new_status: New status to transition to
            agent_id: ID of agent performing transition
            validate: Whether to validate the transition
            
        Returns:
            Updated state
            
        Raises:
            StateNotFoundError: If state not found
            StateTransitionError: If transition is invalid
        """
        # Load current state
        state = await self.get_state(diligence_id)
        
        # Validate transition
        if validate:
            self.validate_transition(state.status, new_status)
        
        # Perform transition
        old_status = state.status
        state.status = new_status
        
        # Handle terminal states
        if new_status in [DiligenceStatus.COMPLETED, DiligenceStatus.FAILED]:
            state.completed_at = datetime.utcnow()
        
        # Update state
        await self.update_state(state, agent_id=agent_id)
        
        # Add audit event
        await self.add_audit_event(
            diligence_id=diligence_id,
            event_type="status_transition",
            agent_id=agent_id,
            details={
                "from_status": old_status.value,
                "to_status": new_status.value,
            },
        )
        
        logger.info(
            "State transitioned",
            extra={
                "diligence_id": diligence_id,
                "from_status": old_status.value,
                "to_status": new_status.value,
            },
        )
        
        return state
    
    # =========================================================================
    # Checkpoint Operations
    # =========================================================================
    
    async def create_checkpoint(
        self,
        diligence_id: str,
        created_by: str = "system",
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        parent_checkpoint_id: Optional[str] = None,
    ) -> StateCheckpoint:
        """Create a checkpoint of the current state.
        
        Args:
            diligence_id: ID of diligence to checkpoint
            created_by: ID of entity creating the checkpoint
            description: Optional description
            tags: Optional tags for the checkpoint
            parent_checkpoint_id: Optional parent checkpoint for chains
            
        Returns:
            StateCheckpoint instance
            
        Raises:
            StateNotFoundError: If state not found
            CheckpointError: If checkpoint creation fails
        """
        try:
            # Load current state
            state = await self.get_state(diligence_id)
            
            # Create checkpoint metadata
            metadata = state.create_checkpoint_metadata(
                created_by=created_by,
                description=description,
                tags=tags or [],
                parent_checkpoint_id=parent_checkpoint_id,
            )
            
            # Create checkpoint
            checkpoint = StateCheckpoint(
                metadata=metadata,
                state_data=state.to_full_dict(),
            )
            
            # Serialize checkpoint
            checkpoint_json = json.dumps(checkpoint.to_dict(), cls=DiligenceStateEncoder)
            
            # Save checkpoint to database
            await self.db.execute(
                """
                INSERT INTO diligence_checkpoints (
                    id, diligence_id, checkpoint_data, created_at, created_by,
                    phase, status, description, tags, parent_checkpoint_id
                )
                VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9)
                """,
                metadata.checkpoint_id,
                diligence_id,
                checkpoint_json,
                created_by,
                metadata.phase.value if metadata.phase else None,
                metadata.status.value if metadata.status else None,
                description,
                tags or [],
                parent_checkpoint_id,
            )
            
            # Update state's checkpoint history
            state.checkpoint_history.append(metadata.checkpoint_id)
            await self.update_state(state, agent_id=created_by)
            
            logger.info(
                "Checkpoint created",
                extra={
                    "checkpoint_id": metadata.checkpoint_id,
                    "diligence_id": diligence_id,
                    "phase": metadata.phase.value if metadata.phase else None,
                },
            )
            
            return checkpoint
            
        except StateNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to create checkpoint",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise CheckpointError(f"Failed to create checkpoint: {e}")
    
    async def restore_checkpoint(
        self,
        checkpoint_id: str,
        restored_by: str = "system",
        validate: bool = True,
    ) -> DiligenceState:
        """Restore state from a checkpoint.
        
        Args:
            checkpoint_id: ID of checkpoint to restore
            restored_by: ID of entity performing restore
            validate: Whether to validate restore operation
            
        Returns:
            Restored DiligenceState
            
        Raises:
            CheckpointError: If checkpoint not found or restore fails
        """
        try:
            # Load checkpoint
            row = await self.db.fetchrow(
                """
                SELECT checkpoint_data, diligence_id 
                FROM diligence_checkpoints 
                WHERE id = $1
                """,
                checkpoint_id,
            )
            
            if not row:
                raise CheckpointError(f"Checkpoint not found: {checkpoint_id}")
            
            # Deserialize checkpoint
            checkpoint_data = json.loads(row["checkpoint_data"])
            checkpoint = StateCheckpoint.from_dict(checkpoint_data)
            
            # Restore state
            restored_state = DiligenceState.from_dict(checkpoint.state_data)
            
            # Track restoration
            restored_state.restored_from_checkpoint = checkpoint_id
            restored_state.updated_at = datetime.utcnow()
            
            # Validate if requested
            if validate:
                # Ensure we're not restoring to a terminal state
                if restored_state.status in [
                    DiligenceStatus.COMPLETED,
                    DiligenceStatus.FAILED,
                    DiligenceStatus.CANCELLED,
                ]:
                    logger.warning(
                        "Restoring to terminal state",
                        extra={
                            "checkpoint_id": checkpoint_id,
                            "status": restored_state.status.value,
                        },
                    )
            
            # Save restored state
            await self.update_state(restored_state, agent_id=restored_by)
            
            # Add audit event
            await self.add_audit_event(
                diligence_id=restored_state.diligence_id,
                event_type="checkpoint_restored",
                agent_id=restored_by,
                details={
                    "checkpoint_id": checkpoint_id,
                    "previous_status": checkpoint.metadata.status.value if checkpoint.metadata.status else None,
                },
            )
            
            logger.info(
                "Checkpoint restored",
                extra={
                    "checkpoint_id": checkpoint_id,
                    "diligence_id": restored_state.diligence_id,
                    "restored_by": restored_by,
                },
            )
            
            return restored_state
            
        except CheckpointError:
            raise
        except Exception as e:
            logger.error(
                "Failed to restore checkpoint",
                extra={
                    "checkpoint_id": checkpoint_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise CheckpointError(f"Failed to restore checkpoint: {e}")
    
    async def list_checkpoints(
        self,
        diligence_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List all checkpoints for a diligence.
        
        Args:
            diligence_id: ID of diligence
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of checkpoint summaries
        """
        try:
            rows = await self.db.fetch(
                """
                SELECT 
                    id,
                    created_at,
                    created_by,
                    phase,
                    status,
                    description,
                    tags,
                    parent_checkpoint_id
                FROM diligence_checkpoints
                WHERE diligence_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                diligence_id,
                limit,
                offset,
            )
            
            return [
                {
                    "checkpoint_id": row["id"],
                    "diligence_id": diligence_id,
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                    "created_by": row["created_by"],
                    "phase": row["phase"],
                    "status": row["status"],
                    "description": row["description"],
                    "tags": row["tags"] or [],
                    "parent_checkpoint_id": row["parent_checkpoint_id"],
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(
                "Failed to list checkpoints",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
    
    async def get_checkpoint(
        self,
        checkpoint_id: str,
    ) -> StateCheckpoint:
        """Get a specific checkpoint by ID.
        
        Args:
            checkpoint_id: ID of checkpoint
            
        Returns:
            StateCheckpoint instance
            
        Raises:
            CheckpointError: If checkpoint not found
        """
        try:
            row = await self.db.fetchrow(
                "SELECT checkpoint_data FROM diligence_checkpoints WHERE id = $1",
                checkpoint_id,
            )
            
            if not row:
                raise CheckpointError(f"Checkpoint not found: {checkpoint_id}")
            
            checkpoint_data = json.loads(row["checkpoint_data"])
            return StateCheckpoint.from_dict(checkpoint_data)
            
        except CheckpointError:
            raise
        except Exception as e:
            logger.error(
                "Failed to get checkpoint",
                extra={
                    "checkpoint_id": checkpoint_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise CheckpointError(f"Failed to get checkpoint: {e}")
    
    async def delete_checkpoint(
        self,
        checkpoint_id: str,
        hard_delete: bool = False,
    ) -> bool:
        """Delete a checkpoint.
        
        Args:
            checkpoint_id: ID of checkpoint to delete
            hard_delete: If True, permanently delete; otherwise soft delete
            
        Returns:
            True if deleted, False if not found
        """
        try:
            if hard_delete:
                result = await self.db.execute(
                    "DELETE FROM diligence_checkpoints WHERE id = $1",
                    checkpoint_id,
                )
                deleted = result != "DELETE 0"
            else:
                result = await self.db.execute(
                    """
                    UPDATE diligence_checkpoints 
                    SET deleted = TRUE, deleted_at = NOW()
                    WHERE id = $1 AND (deleted = FALSE OR deleted IS NULL)
                    """,
                    checkpoint_id,
                )
                deleted = result != "UPDATE 0"
            
            logger.info(
                "Checkpoint deleted",
                extra={
                    "checkpoint_id": checkpoint_id,
                    "deleted": deleted,
                    "hard_delete": hard_delete,
                },
            )
            
            return deleted
            
        except Exception as e:
            logger.error(
                "Failed to delete checkpoint",
                extra={
                    "checkpoint_id": checkpoint_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
    
    # =========================================================================
    # State Diff/Compare Functionality
    # =========================================================================
    
    async def compare_states(
        self,
        state_id_a: str,
        state_id_b: str,
    ) -> Dict[str, Any]:
        """Compare two states and return differences.
        
        Args:
            state_id_a: First state ID (or checkpoint ID)
            state_id_b: Second state ID (or checkpoint ID)
            
        Returns:
            Dictionary containing differences
        """
        try:
            # Load both states
            state_a = await self._load_state_or_checkpoint(state_id_a)
            state_b = await self._load_state_or_checkpoint(state_id_b)
            
            # Compare
            diff = self._compute_diff(state_a, state_b)
            
            return {
                "state_a_id": state_id_a,
                "state_b_id": state_id_b,
                "differences": diff,
                "summary": {
                    "total_changes": len(diff),
                    "status_changed": state_a.status != state_b.status,
                    "confidence_changed": state_a.overall_confidence != state_b.overall_confidence,
                    "phases_changed": state_a.completed_phases != state_b.completed_phases,
                },
            }
            
        except Exception as e:
            logger.error(
                "Failed to compare states",
                extra={
                    "state_a_id": state_id_a,
                    "state_b_id": state_id_b,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
    
    async def compare_with_checkpoint(
        self,
        diligence_id: str,
        checkpoint_id: str,
    ) -> Dict[str, Any]:
        """Compare current state with a checkpoint.
        
        Args:
            diligence_id: Current diligence ID
            checkpoint_id: Checkpoint ID to compare against
            
        Returns:
            Dictionary containing differences
        """
        return await self.compare_states(diligence_id, checkpoint_id)
    
    def _compute_diff(
        self,
        state_a: DiligenceState,
        state_b: DiligenceState,
    ) -> List[Dict[str, Any]]:
        """Compute detailed differences between two states.
        
        Args:
            state_a: First state
            state_b: Second state
            
        Returns:
            List of difference records
        """
        differences = []
        
        # Compare status
        if state_a.status != state_b.status:
            differences.append({
                "field": "status",
                "old_value": state_a.status.value,
                "new_value": state_b.status.value,
            })
        
        # Compare current phase
        if state_a.current_phase != state_b.current_phase:
            differences.append({
                "field": "current_phase",
                "old_value": state_a.current_phase.name if state_a.current_phase else None,
                "new_value": state_b.current_phase.name if state_b.current_phase else None,
            })
        
        # Compare confidence
        if abs(state_a.overall_confidence - state_b.overall_confidence) > 0.001:
            differences.append({
                "field": "overall_confidence",
                "old_value": state_a.overall_confidence,
                "new_value": state_b.overall_confidence,
                "delta": state_b.overall_confidence - state_a.overall_confidence,
            })
        
        # Compare verification rate
        if abs(state_a.verification_rate - state_b.verification_rate) > 0.001:
            differences.append({
                "field": "verification_rate",
                "old_value": state_a.verification_rate,
                "new_value": state_b.verification_rate,
                "delta": state_b.verification_rate - state_a.verification_rate,
            })
        
        # Compare data points
        if state_a.total_data_points != state_b.total_data_points:
            differences.append({
                "field": "total_data_points",
                "old_value": state_a.total_data_points,
                "new_value": state_b.total_data_points,
                "delta": state_b.total_data_points - state_a.total_data_points,
            })
        
        # Compare completed phases
        phases_a = set(p.name for p in state_a.completed_phases)
        phases_b = set(p.name for p in state_b.completed_phases)
        if phases_a != phases_b:
            differences.append({
                "field": "completed_phases",
                "added": list(phases_b - phases_a),
                "removed": list(phases_a - phases_b),
            })
        
        # Compare quality gate
        if state_a.quality_gate_triggered != state_b.quality_gate_triggered:
            differences.append({
                "field": "quality_gate_triggered",
                "old_value": state_a.quality_gate_triggered,
                "new_value": state_b.quality_gate_triggered,
            })
        
        # Compare memo
        if state_a.memo != state_b.memo:
            differences.append({
                "field": "memo",
                "changed": True,
            })
        
        # Compare trading signal
        if state_a.trading_signal != state_b.trading_signal:
            differences.append({
                "field": "trading_signal",
                "changed": True,
            })
        
        return differences
    
    async def _load_state_or_checkpoint(
        self,
        state_or_checkpoint_id: str,
    ) -> DiligenceState:
        """Load either a current state or a checkpoint.
        
        Args:
            state_or_checkpoint_id: ID of state or checkpoint
            
        Returns:
            DiligenceState
        """
        # Try loading as current state first
        state = await self.load_state(state_or_checkpoint_id, use_cache=False)
        if state:
            return state
        
        # Try loading as checkpoint
        try:
            checkpoint = await self.get_checkpoint(state_or_checkpoint_id)
            return DiligenceState.from_dict(checkpoint.state_data)
        except CheckpointError:
            pass
        
        raise StateNotFoundError(
            f"Neither state nor checkpoint found for ID: {state_or_checkpoint_id}"
        )
    
    # =========================================================================
    # Archive Operations
    # =========================================================================
    
    async def archive_old_states(
        self,
        older_than_days: int = 90,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Archive states that haven't been updated in a specified period.
        
        Args:
            older_than_days: Archive states older than this many days
            dry_run: If True, only count what would be archived
            
        Returns:
            Summary of archival operation
        """
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
            
            # Count states to archive
            count_row = await self.db.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM diligence_states
                WHERE updated_at < $1 AND (archived = FALSE OR archived IS NULL)
                """,
                cutoff_date,
            )
            
            count = count_row["count"] if count_row else 0
            
            if dry_run:
                return {
                    "dry_run": True,
                    "would_archive": count,
                    "older_than_days": older_than_days,
                    "cutoff_date": cutoff_date.isoformat(),
                }
            
            # Perform archival
            if count > 0:
                result = await self.db.execute(
                    """
                    UPDATE diligence_states
                    SET archived = TRUE, archived_at = NOW()
                    WHERE updated_at < $1 AND (archived = FALSE OR archived IS NULL)
                    """,
                    cutoff_date,
                )
                
                # Clear cache for archived states
                if self.settings.enable_cache:
                    # Get IDs of archived states
                    rows = await self.db.fetch(
                        """
                        SELECT id FROM diligence_states
                        WHERE updated_at < $1 AND archived = TRUE
                        """,
                        cutoff_date,
                    )
                    for row in rows:
                        await self.redis.delete(f"diligence:{row['id']}")
            
            logger.info(
                "Archived old states",
                extra={
                    "archived_count": count,
                    "older_than_days": older_than_days,
                },
            )
            
            return {
                "dry_run": False,
                "archived_count": count,
                "older_than_days": older_than_days,
                "cutoff_date": cutoff_date.isoformat(),
            }
            
        except Exception as e:
            logger.error(
                "Failed to archive old states",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise
    
    async def list_archived_states(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List archived states.
        
        Args:
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            List of archived state summaries
        """
        try:
            rows = await self.db.fetch(
                """
                SELECT 
                    id,
                    state->>'status' as status,
                    state->'thesis'->>'ticker' as ticker,
                    state->>'created_at' as created_at,
                    state->>'updated_at' as updated_at,
                    archived_at
                FROM diligence_states
                WHERE archived = TRUE
                ORDER BY archived_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit,
                offset,
            )
            
            return [
                {
                    "diligence_id": row["id"],
                    "status": row["status"],
                    "ticker": row["ticker"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "archived_at": row["archived_at"].isoformat() if row["archived_at"] else None,
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(
                "Failed to list archived states",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise
    
    async def restore_archived_state(
        self,
        diligence_id: str,
        restored_by: str = "system",
    ) -> DiligenceState:
        """Restore an archived state to active status.
        
        Args:
            diligence_id: ID of archived state
            restored_by: ID of entity performing restore
            
        Returns:
            Restored DiligenceState
            
        Raises:
            StateNotFoundError: If archived state not found
        """
        try:
            # Check if state exists and is archived
            row = await self.db.fetchrow(
                """
                SELECT state FROM diligence_states
                WHERE id = $1 AND archived = TRUE
                """,
                diligence_id,
            )
            
            if not row:
                raise StateNotFoundError(
                    f"Archived state not found for diligence_id: {diligence_id}"
                )
            
            # Restore state
            await self.db.execute(
                """
                UPDATE diligence_states
                SET archived = FALSE, archived_at = NULL, updated_at = NOW()
                WHERE id = $1
                """,
                diligence_id,
            )
            
            # Deserialize and return
            state = self._deserialize_state(row["state"])
            
            # Add audit event
            await self.add_audit_event(
                diligence_id=diligence_id,
                event_type="archived_state_restored",
                agent_id=restored_by,
                details={"previous_status": state.status.value},
            )
            
            logger.info(
                "Archived state restored",
                extra={
                    "diligence_id": diligence_id,
                    "restored_by": restored_by,
                },
            )
            
            return state
            
        except StateNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "Failed to restore archived state",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _deserialize_state(self, data: str) -> DiligenceState:
        """Deserialize state from JSON.
        
        Args:
            data: JSON string
            
        Returns:
            DiligenceState instance
        """
        parsed = json.loads(data)
        return DiligenceState.from_dict(parsed)
    
    async def add_audit_event(
        self,
        diligence_id: str,
        event_type: str,
        agent_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add an audit event.
        
        Args:
            diligence_id: Associated diligence ID
            event_type: Type of event
            agent_id: Agent that triggered the event
            details: Additional details
        """
        try:
            await self.db.execute(
                """
                INSERT INTO audit_events (id, diligence_id, event_type, agent_id, details, timestamp)
                VALUES ($1, $2, $3, $4, $5, NOW())
                """,
                str(uuid4()),
                diligence_id,
                event_type,
                agent_id,
                json.dumps(details or {}),
            )
            
        except Exception as e:
            logger.error(
                "Failed to add audit event",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            # Don't raise - audit failures shouldn't break operations
    
    async def get_state_history(
        self,
        diligence_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit history for a diligence state.
        
        Args:
            diligence_id: ID of diligence
            limit: Maximum events to return
            
        Returns:
            List of audit events
        """
        try:
            rows = await self.db.fetch(
                """
                SELECT 
                    event_type,
                    agent_id,
                    details,
                    timestamp
                FROM audit_events
                WHERE diligence_id = $1
                ORDER BY timestamp DESC
                LIMIT $2
                """,
                diligence_id,
                limit,
            )
            
            return [
                {
                    "event_type": row["event_type"],
                    "agent_id": row["agent_id"],
                    "details": json.loads(row["details"]) if row["details"] else {},
                    "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(
                "Failed to get state history",
                extra={
                    "diligence_id": diligence_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise
