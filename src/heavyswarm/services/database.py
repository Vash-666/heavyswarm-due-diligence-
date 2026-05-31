"""Database service for PostgreSQL persistence with asyncpg."""

import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
from asyncpg import Pool, Connection

from heavyswarm.core.config import settings
from heavyswarm.utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseError(Exception):
    """Base database error."""
    pass


class DatabaseConnectionError(DatabaseError):
    """Database connection error."""
    pass


class DatabaseService:
    """PostgreSQL database service using asyncpg.
    
    Provides connection pooling, transaction management, and
    CRUD operations for diligence workflows.
    """
    
    def __init__(self):
        """Initialize database service."""
        self._pool: Optional[Pool] = None
        self._connection_string = self._build_connection_string()
    
    def _build_connection_string(self) -> str:
        """Build connection string from settings."""
        return (
            f"postgresql://{settings.db_user}:{settings.db_password}"
            f"@{settings.db_host}:{settings.db_port}/{settings.db_name}"
        )
    
    async def connect(self) -> None:
        """Initialize connection pool."""
        try:
            self._pool = await asyncpg.create_pool(
                self._connection_string,
                min_size=5,
                max_size=20,
                command_timeout=60,
                server_settings={
                    'jit': 'off',  # Disable JIT for short queries
                }
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to initialize database pool: {e}")
            raise DatabaseConnectionError(f"Database connection failed: {e}")
    
    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database connection pool closed")
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire connection from pool."""
        if not self._pool:
            await self.connect()
        
        async with self._pool.acquire() as connection:
            yield connection
    
    @asynccontextmanager
    async def transaction(self):
        """Execute operations in a transaction."""
        async with self.acquire() as conn:
            async with conn.transaction():
                yield conn
    
    # ========================================================================
    # Diligence CRUD Operations
    # ========================================================================
    
    async def create_diligence(
        self,
        diligence_id: str,
        ticker: str,
        thesis: str,
        time_horizon: str,
        risk_tolerance: str,
        position_size: float,
        priority: str,
        status: str,
        state_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a new diligence record.
        
        Args:
            diligence_id: Unique diligence ID
            ticker: Stock ticker symbol
            thesis: Investment thesis statement
            time_horizon: Investment time horizon
            risk_tolerance: Risk tolerance level
            position_size: Position size as decimal
            priority: Task priority
            status: Initial status
            state_data: Full state data as dictionary
            
        Returns:
            Created diligence record
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO diligence_states (
                    id, state, created_at, updated_at
                ) VALUES ($1, $2, NOW(), NOW())
                RETURNING 
                    id as diligence_id,
                    state->>'status' as status,
                    state->'thesis'->>'ticker' as ticker,
                    state->>'created_at' as created_at,
                    state->>'updated_at' as updated_at
                """,
                diligence_id,
                json.dumps(state_data),
            )
            
            return dict(row)
    
    async def get_diligence(self, diligence_id: str) -> Optional[Dict[str, Any]]:
        """Get diligence by ID.
        
        Args:
            diligence_id: Diligence ID
            
        Returns:
            Diligence record or None if not found
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    id as diligence_id,
                    state,
                    state->>'status' as status,
                    state->'thesis'->>'ticker' as ticker,
                    state->>'created_at' as created_at,
                    state->>'updated_at' as updated_at,
                    state->>'completed_at' as completed_at,
                    state->>'overall_confidence' as confidence,
                    state->>'current_phase' as current_phase,
                    archived,
                    archived_at
                FROM diligence_states
                WHERE id = $1 AND (archived = FALSE OR archived IS NULL)
                """,
                diligence_id,
            )
            
            if not row:
                return None
            
            result = dict(row)
            result['state'] = json.loads(result['state']) if result['state'] else {}
            return result
    
    async def update_diligence_state(
        self,
        diligence_id: str,
        state_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update diligence state.
        
        Args:
            diligence_id: Diligence ID
            state_data: Updated state data
            
        Returns:
            Updated diligence record or None if not found
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE diligence_states
                SET state = $2, updated_at = NOW()
                WHERE id = $1 AND (archived = FALSE OR archived IS NULL)
                RETURNING 
                    id as diligence_id,
                    state->>'status' as status,
                    state->'thesis'->>'ticker' as ticker,
                    state->>'created_at' as created_at,
                    state->>'updated_at' as updated_at
                """,
                diligence_id,
                json.dumps(state_data),
            )
            
            if not row:
                return None
            
            return dict(row)
    
    async def update_diligence_status(
        self,
        diligence_id: str,
        status: str,
        progress: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Update diligence status.
        
        Args:
            diligence_id: Diligence ID
            status: New status
            progress: Optional progress data
            
        Returns:
            Updated diligence record or None if not found
        """
        async with self.acquire() as conn:
            # Get current state
            current = await conn.fetchrow(
                "SELECT state FROM diligence_states WHERE id = $1",
                diligence_id,
            )
            
            if not current:
                return None
            
            state = json.loads(current['state'])
            state['status'] = status
            state['updated_at'] = datetime.utcnow().isoformat()
            
            if progress:
                state['progress'] = progress
            
            if status == 'completed':
                state['completed_at'] = datetime.utcnow().isoformat()
            
            row = await conn.fetchrow(
                """
                UPDATE diligence_states
                SET state = $2, updated_at = NOW()
                WHERE id = $1
                RETURNING 
                    id as diligence_id,
                    state->>'status' as status,
                    state->'thesis'->>'ticker' as ticker,
                    state->>'created_at' as created_at,
                    state->>'updated_at' as updated_at
                """,
                diligence_id,
                json.dumps(state),
            )
            
            return dict(row) if row else None
    
    async def delete_diligence(
        self,
        diligence_id: str,
        hard_delete: bool = False,
    ) -> bool:
        """Delete or archive a diligence.
        
        Args:
            diligence_id: Diligence ID
            hard_delete: If True, permanently delete
            
        Returns:
            True if deleted/archived
        """
        async with self.acquire() as conn:
            if hard_delete:
                result = await conn.execute(
                    "DELETE FROM diligence_states WHERE id = $1",
                    diligence_id,
                )
                return result != "DELETE 0"
            else:
                result = await conn.execute(
                    """
                    UPDATE diligence_states
                    SET archived = TRUE, archived_at = NOW()
                    WHERE id = $1 AND (archived = FALSE OR archived IS NULL)
                    """,
                    diligence_id,
                )
                return result != "UPDATE 0"
    
    async def list_diligences(
        self,
        status: Optional[str] = None,
        ticker: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """List diligences with filtering.
        
        Args:
            status: Filter by status
            ticker: Filter by ticker
            priority: Filter by priority
            limit: Maximum results
            offset: Pagination offset
            
        Returns:
            Tuple of (diligences list, total count)
        """
        async with self.acquire() as conn:
            # Build conditions
            conditions = ["(archived = FALSE OR archived IS NULL)"]
            params = []
            
            if status:
                conditions.append(f"state->>'status' = ${len(params) + 1}")
                params.append(status)
            
            if ticker:
                conditions.append(f"state->'thesis'->>'ticker' = ${len(params) + 1}")
                params.append(ticker.upper())
            
            if priority:
                conditions.append(f"state->'thesis'->>'priority' = ${len(params) + 1}")
                params.append(priority)
            
            where_clause = "WHERE " + " AND ".join(conditions)
            
            # Get total count
            count_query = f"SELECT COUNT(*) as total FROM diligence_states {where_clause}"
            count_row = await conn.fetchrow(count_query, *params)
            total = count_row['total'] if count_row else 0
            
            # Get results
            query = f"""
                SELECT 
                    id as diligence_id,
                    state->>'status' as status,
                    state->'thesis'->>'ticker' as ticker,
                    state->'thesis'->>'priority' as priority,
                    state->>'created_at' as created_at,
                    state->>'updated_at' as updated_at,
                    state->>'overall_confidence' as confidence,
                    state->'memo'->'executive_summary'->>'recommendation' as recommendation
                FROM diligence_states
                {where_clause}
                ORDER BY updated_at DESC
                LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
            """
            
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)
            
            diligences = []
            for row in rows:
                record = dict(row)
                if record.get('confidence'):
                    try:
                        record['confidence'] = float(record['confidence'])
                    except (ValueError, TypeError):
                        record['confidence'] = None
                diligences.append(record)
            
            return diligences, total
    
    async def get_diligence_memo(self, diligence_id: str) -> Optional[Dict[str, Any]]:
        """Get investment memo for a diligence.
        
        Args:
            diligence_id: Diligence ID
            
        Returns:
            Memo data or None
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT state->'memo' as memo
                FROM diligence_states
                WHERE id = $1 AND (archived = FALSE OR archived IS NULL)
                """,
                diligence_id,
            )
            
            if not row or not row['memo']:
                return None
            
            return json.loads(row['memo']) if isinstance(row['memo'], str) else row['memo']
    
    async def get_trading_signal(self, diligence_id: str) -> Optional[Dict[str, Any]]:
        """Get trading signal for a diligence.
        
        Args:
            diligence_id: Diligence ID
            
        Returns:
            Trading signal data or None
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT state->'trading_signal' as signal
                FROM diligence_states
                WHERE id = $1 AND (archived = FALSE OR archived IS NULL)
                """,
                diligence_id,
            )
            
            if not row or not row['signal']:
                return None
            
            return json.loads(row['signal']) if isinstance(row['signal'], str) else row['signal']
    
    async def get_audit_trail(self, diligence_id: str) -> List[Dict[str, Any]]:
        """Get audit trail for a diligence.
        
        Args:
            diligence_id: Diligence ID
            
        Returns:
            List of audit events
        """
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    event_type,
                    agent_id,
                    details,
                    timestamp
                FROM audit_events
                WHERE diligence_id = $1
                ORDER BY timestamp DESC
                """,
                diligence_id,
            )
            
            return [
                {
                    'event_type': row['event_type'],
                    'agent_id': row['agent_id'],
                    'details': json.loads(row['details']) if isinstance(row['details'], str) else row['details'],
                    'timestamp': row['timestamp'].isoformat() if row['timestamp'] else None,
                }
                for row in rows
            ]
    
    async def add_audit_event(
        self,
        diligence_id: str,
        event_type: str,
        agent_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add audit event.
        
        Args:
            diligence_id: Associated diligence ID
            event_type: Type of event
            agent_id: Agent that triggered event
            details: Additional details
        """
        from uuid import uuid4
        
        async with self.acquire() as conn:
            await conn.execute(
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


# Global database service instance
db_service = DatabaseService()


# Import at end to avoid circular imports
from datetime import datetime
