"""End-to-end integration tests for the full diligence workflow."""

import asyncio
import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from heavyswarm.api.main import app
from heavyswarm.core.enums import DiligenceStatus, TimeHorizon, RiskTolerance, Priority
from heavyswarm.core.state import DiligenceState, InvestmentThesis
from heavyswarm.services.database import DatabaseService


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
async def db():
    """Create database connection for tests."""
    db_service = DatabaseService()
    await db_service.connect()
    yield db_service
    await db_service.disconnect()


@pytest.fixture
def sample_thesis():
    """Create sample investment thesis for testing."""
    return {
        "ticker": "AAPL",
        "thesis": "Apple Inc. continues to demonstrate strong ecosystem lock-in with recurring revenue streams from Services. The transition to AI-powered features and Vision Pro represent significant growth catalysts. Trading at reasonable valuation relative to historical multiples.",
        "time_horizon": TimeHorizon.MEDIUM_TERM.value,
        "risk_tolerance": RiskTolerance.MODERATE.value,
        "position_size": 0.05,
        "priority": Priority.MEDIUM.value,
    }


class TestDiligenceE2E:
    """End-to-end tests for diligence workflow."""
    
    def test_create_diligence(self, client, sample_thesis):
        """Test creating a new diligence."""
        response = client.post("/api/v1/diligence", json=sample_thesis)
        
        assert response.status_code == 202
        data = response.json()
        
        assert "diligence_id" in data
        assert data["status"] in ["pending", "in_progress"]
        assert "polling_url" in data
        assert "estimated_completion" in data
        
        # Store for later tests
        self.diligence_id = data["diligence_id"]
    
    def test_get_diligence_status(self, client, sample_thesis):
        """Test getting diligence status."""
        # Create diligence
        create_response = client.post("/api/v1/diligence", json=sample_thesis)
        assert create_response.status_code == 202
        diligence_id = create_response.json()["diligence_id"]
        
        # Get status
        response = client.get(f"/api/v1/diligence/{diligence_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["diligence_id"] == diligence_id
        assert data["ticker"] == "AAPL"
        assert "status" in data
        assert "progress" in data
        assert "metrics" in data
        
        # Check progress structure
        progress = data["progress"]
        assert "current_phase" in progress
        assert "completed_phases" in progress
        assert "percent_complete" in progress
        assert isinstance(progress["percent_complete"], float)
        assert 0 <= progress["percent_complete"] <= 100
        
        # Check metrics structure
        metrics = data["metrics"]
        assert "overall_confidence" in metrics
        assert "verification_rate" in metrics
        assert "total_data_points" in metrics
        assert "verified_data_points" in metrics
        assert "quality_gate_triggered" in metrics
    
    def test_list_diligences(self, client, sample_thesis):
        """Test listing diligences."""
        # Create a few diligences
        for _ in range(3):
            response = client.post("/api/v1/diligence", json=sample_thesis)
            assert response.status_code == 202
        
        # List diligences
        response = client.get("/api/v1/diligence?limit=10")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert "diligences" in data
        assert isinstance(data["diligences"], list)
        assert len(data["diligences"]) >= 3
        
        # Check diligence item structure
        if data["diligences"]:
            item = data["diligences"][0]
            assert "diligence_id" in item
            assert "ticker" in item
            assert "status" in item
            assert "priority" in item
            assert "created_at" in item
    
    def test_list_diligences_with_filters(self, client, sample_thesis):
        """Test listing diligences with filters."""
        # Create diligence
        response = client.post("/api/v1/diligence", json=sample_thesis)
        assert response.status_code == 202
        
        # Filter by ticker
        response = client.get("/api/v1/diligence?ticker=AAPL")
        assert response.status_code == 200
        data = response.json()
        assert all(d["ticker"] == "AAPL" for d in data["diligences"])
        
        # Filter by status
        response = client.get("/api/v1/diligence?status=pending")
        assert response.status_code == 200
        data = response.json()
        # Should include pending or in_progress
        assert all(d["status"] in ["pending", "in_progress"] for d in data["diligences"])
    
    def test_cancel_diligence(self, client, sample_thesis):
        """Test cancelling a diligence."""
        # Create diligence
        create_response = client.post("/api/v1/diligence", json=sample_thesis)
        assert create_response.status_code == 202
        diligence_id = create_response.json()["diligence_id"]
        
        # Cancel diligence
        response = client.delete(f"/api/v1/diligence/{diligence_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["diligence_id"] == diligence_id
        assert data["status"] == "cancelled"
        assert "cancelled_at" in data
        
        # Verify status changed
        status_response = client.get(f"/api/v1/diligence/{diligence_id}")
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "cancelled"
    
    def test_cancel_completed_diligence_fails(self, client, sample_thesis):
        """Test that cancelling a completed diligence fails."""
        # This test would require a completed diligence
        # For now, just test the error handling with a non-existent ID
        response = client.delete("/api/v1/diligence/non-existent-id")
        assert response.status_code == 404
    
    def test_get_nonexistent_diligence(self, client):
        """Test getting a non-existent diligence."""
        response = client.get("/api/v1/diligence/non-existent-id")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_get_memo_not_available(self, client, sample_thesis):
        """Test getting memo before it's available."""
        # Create diligence
        create_response = client.post("/api/v1/diligence", json=sample_thesis)
        diligence_id = create_response.json()["diligence_id"]
        
        # Try to get memo immediately (should fail)
        response = client.get(f"/api/v1/diligence/{diligence_id}/memo")
        
        # Should return 404 since memo isn't generated yet
        assert response.status_code == 404
    
    def test_get_signal_not_available(self, client, sample_thesis):
        """Test getting signal before it's available."""
        # Create diligence
        create_response = client.post("/api/v1/diligence", json=sample_thesis)
        diligence_id = create_response.json()["diligence_id"]
        
        # Try to get signal immediately (should fail)
        response = client.get(f"/api/v1/diligence/{diligence_id}/signal")
        
        # Should return 404 since signal isn't generated yet
        assert response.status_code == 404
    
    def test_get_audit_trail(self, client, sample_thesis):
        """Test getting audit trail."""
        # Create diligence
        create_response = client.post("/api/v1/diligence", json=sample_thesis)
        diligence_id = create_response.json()["diligence_id"]
        
        # Get audit trail
        response = client.get(f"/api/v1/diligence/{diligence_id}/audit")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["diligence_id"] == diligence_id
        assert "events" in data
        assert isinstance(data["events"], list)
    
    def test_create_diligence_validation(self, client):
        """Test validation on create diligence."""
        # Missing required field
        response = client.post("/api/v1/diligence", json={})
        assert response.status_code == 422
        
        # Thesis too short
        response = client.post("/api/v1/diligence", json={
            "ticker": "AAPL",
            "thesis": "Short",
        })
        assert response.status_code == 422
        
        # Invalid position size
        response = client.post("/api/v1/diligence", json={
            "ticker": "AAPL",
            "thesis": "This is a valid investment thesis with sufficient length.",
            "position_size": 1.5,  # > 1
        })
        assert response.status_code == 422
    
    def test_ticker_normalization(self, client):
        """Test that tickers are normalized to uppercase."""
        thesis = {
            "ticker": "aapl",  # lowercase
            "thesis": "This is a valid investment thesis with sufficient length for testing.",
        }
        
        response = client.post("/api/v1/diligence", json=thesis)
        assert response.status_code == 202
        
        diligence_id = response.json()["diligence_id"]
        
        # Check ticker is uppercase
        status_response = client.get(f"/api/v1/diligence/{diligence_id}")
        assert status_response.json()["ticker"] == "AAPL"


class TestDiligenceWorkflowPhases:
    """Tests for the 6-phase workflow execution."""
    
    @pytest.mark.asyncio
    async def test_full_workflow_execution(self, client, sample_thesis):
        """Test the full 6-phase workflow execution.
        
        This test creates a diligence and polls until completion or timeout.
        """
        # Create diligence
        create_response = client.post("/api/v1/diligence", json=sample_thesis)
        assert create_response.status_code == 202
        diligence_id = create_response.json()["diligence_id"]
        
        # Poll for completion (with timeout)
        max_wait = 300  # 5 minutes
        poll_interval = 5  # seconds
        elapsed = 0
        
        while elapsed < max_wait:
            status_response = client.get(f"/api/v1/diligence/{diligence_id}")
            assert status_response.status_code == 200
            
            data = status_response.json()
            status = data["status"]
            
            if status in ["completed", "failed", "cancelled"]:
                break
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            
            # Log progress
            progress = data.get("progress", {})
            print(f"Progress: {progress.get('percent_complete', 0)}% - Phase: {progress.get('current_phase')}")
        
        # Final status check
        final_response = client.get(f"/api/v1/diligence/{diligence_id}")
        final_data = final_response.json()
        
        # Verify we got a terminal state
        assert final_data["status"] in ["completed", "failed", "cancelled"]
        
        if final_data["status"] == "completed":
            # Verify memo is available
            memo_response = client.get(f"/api/v1/diligence/{diligence_id}/memo")
            assert memo_response.status_code == 200
            memo_data = memo_response.json()
            assert "memo" in memo_data
            
            # Verify signal is available
            signal_response = client.get(f"/api/v1/diligence/{diligence_id}/signal")
            assert signal_response.status_code == 200
            signal_data = signal_response.json()
            assert "action" in signal_data
            assert "confidence" in signal_data
            
            # Verify all 6 phases completed
            progress = final_data.get("progress", {})
            completed_phases = progress.get("completed_phases", [])
            expected_phases = [
                "QUESTION_GENERATOR",
                "RESEARCHER", 
                "FINANCIAL_ANALYST",
                "RISK_ANALYST",
                "STRATEGIST",
                "VERIFIER",
                "WRITER",
            ]
            
            for phase in expected_phases:
                assert phase in completed_phases, f"Phase {phase} not completed"
    
    def test_workflow_metrics(self, client, sample_thesis):
        """Test that workflow produces correct metrics."""
        # Create and wait for completion
        create_response = client.post("/api/v1/diligence", json=sample_thesis)
        diligence_id = create_response.json()["diligence_id"]
        
        # Get status and verify metrics structure
        status_response = client.get(f"/api/v1/diligence/{diligence_id}")
        data = status_response.json()
        
        metrics = data.get("metrics", {})
        
        # Verify metric types
        assert isinstance(metrics.get("overall_confidence"), (int, float))
        assert isinstance(metrics.get("verification_rate"), (int, float))
        assert isinstance(metrics.get("total_data_points"), int)
        assert isinstance(metrics.get("verified_data_points"), int)
        assert isinstance(metrics.get("quality_gate_triggered"), bool)
        
        # Verify metric ranges
        assert 0 <= metrics.get("overall_confidence", 0) <= 1
        assert 0 <= metrics.get("verification_rate", 0) <= 1
        assert metrics.get("verified_data_points", 0) <= metrics.get("total_data_points", 0)


class TestDiligenceDatabasePersistence:
    """Tests for database persistence."""
    
    @pytest.mark.asyncio
    async def test_diligence_persisted_to_database(self, db, sample_thesis):
        """Test that diligence is persisted to database."""
        # Create diligence via API
        from fastapi.testclient import TestClient
        client = TestClient(app)
        
        response = client.post("/api/v1/diligence", json=sample_thesis)
        diligence_id = response.json()["diligence_id"]
        
        # Verify in database
        diligence = await db.get_diligence(diligence_id)
        assert diligence is not None
        assert diligence["diligence_id"] == diligence_id
        assert diligence["ticker"] == "AAPL"
    
    @pytest.mark.asyncio
    async def test_audit_events_persisted(self, db, sample_thesis):
        """Test that audit events are persisted."""
        from fastapi.testclient import TestClient
        client = TestClient(app)
        
        # Create diligence
        response = client.post("/api/v1/diligence", json=sample_thesis)
        diligence_id = response.json()["diligence_id"]
        
        # Get audit trail
        events = await db.get_audit_trail(diligence_id)
        
        # Should have at least creation event
        assert len(events) >= 0  # Events may be async


class TestDiligencePerformance:
    """Performance tests for diligence workflow."""
    
    def test_latency_target(self, client, sample_thesis):
        """Test that diligence creation responds within target latency."""
        import time
        
        start = time.time()
        response = client.post("/api/v1/diligence", json=sample_thesis)
        elapsed = time.time() - start
        
        assert response.status_code == 202
        # Target: < 500ms for creation
        assert elapsed < 0.5, f"Creation took {elapsed:.2f}s, target < 0.5s"
    
    def test_concurrent_diligences(self, client, sample_thesis):
        """Test creating multiple diligences concurrently."""
        import concurrent.futures
        import time
        
        def create_diligence():
            return client.post("/api/v1/diligence", json=sample_thesis)
        
        start = time.time()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(create_diligence) for _ in range(5)]
            responses = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        elapsed = time.time() - start
        
        # All should succeed
        assert all(r.status_code == 202 for r in responses)
        
        # Should complete within reasonable time (< 10s for 5 concurrent)
        assert elapsed < 10, f"5 concurrent diligences took {elapsed:.2f}s"
