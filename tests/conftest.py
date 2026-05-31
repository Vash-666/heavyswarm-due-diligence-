"""Test configuration and fixtures."""

import pytest
from datetime import datetime
from uuid import uuid4

from heavyswarm.core.enums import TimeHorizon, RiskTolerance, Priority
from heavyswarm.core.state import InvestmentThesis


@pytest.fixture
def sample_thesis():
    """Create sample investment thesis for testing."""
    return InvestmentThesis(
        ticker="AAPL",
        thesis="Apple Inc. continues to demonstrate strong ecosystem lock-in with recurring revenue streams from Services. The transition to AI-powered features and Vision Pro represent significant growth catalysts. Trading at reasonable valuation relative to historical multiples.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
        risk_tolerance=RiskTolerance.MODERATE,
        position_size=0.05,
        priority=Priority.MEDIUM,
    )


@pytest.fixture
def mock_db_service():
    """Create mock database service."""
    from unittest.mock import AsyncMock, MagicMock
    
    db = MagicMock()
    
    # Mock data storage
    db._diligences = {}
    db._audit_events = {}
    
    async def mock_create_diligence(**kwargs):
        diligence_id = kwargs.get('diligence_id', str(uuid4()))
        db._diligences[diligence_id] = {
            'diligence_id': diligence_id,
            'ticker': kwargs.get('ticker'),
            'status': kwargs.get('status'),
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat(),
            'state': kwargs.get('state_data', {}),
        }
        return db._diligences[diligence_id]
    
    async def mock_get_diligence(diligence_id):
        return db._diligences.get(diligence_id)
    
    async def mock_update_diligence_status(diligence_id, status, progress=None):
        if diligence_id in db._diligences:
            db._diligences[diligence_id]['status'] = status
            db._diligences[diligence_id]['updated_at'] = datetime.utcnow().isoformat()
            return db._diligences[diligence_id]
        return None
    
    async def mock_delete_diligence(diligence_id, hard_delete=False):
        if diligence_id in db._diligences:
            if hard_delete:
                del db._diligences[diligence_id]
            else:
                db._diligences[diligence_id]['archived'] = True
            return True
        return False
    
    async def mock_list_diligences(status=None, ticker=None, priority=None, limit=10, offset=0):
        results = list(db._diligences.values())
        if status:
            results = [d for d in results if d.get('status') == status]
        if ticker:
            results = [d for d in results if d.get('ticker') == ticker]
        return results[offset:offset+limit], len(results)
    
    async def mock_get_diligence_memo(diligence_id):
        diligence = db._diligences.get(diligence_id)
        if diligence:
            state = diligence.get('state', {})
            return state.get('memo')
        return None
    
    async def mock_get_trading_signal(diligence_id):
        diligence = db._diligences.get(diligence_id)
        if diligence:
            state = diligence.get('state', {})
            return state.get('trading_signal')
        return None
    
    async def mock_get_audit_trail(diligence_id):
        return db._audit_events.get(diligence_id, [])
    
    async def mock_add_audit_event(diligence_id, event_type, agent_id, details=None):
        if diligence_id not in db._audit_events:
            db._audit_events[diligence_id] = []
        db._audit_events[diligence_id].append({
            'event_type': event_type,
            'agent_id': agent_id,
            'details': details or {},
            'timestamp': datetime.utcnow().isoformat(),
        })
    
    db.create_diligence = mock_create_diligence
    db.get_diligence = mock_get_diligence
    db.update_diligence_status = mock_update_diligence_status
    db.delete_diligence = mock_delete_diligence
    db.list_diligences = mock_list_diligences
    db.get_diligence_memo = mock_get_diligence_memo
    db.get_trading_signal = mock_get_trading_signal
    db.get_audit_trail = mock_get_audit_trail
    db.add_audit_event = mock_add_audit_event
    
    return db
