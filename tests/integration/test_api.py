"""Integration tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient

from heavyswarm.api.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestHealthEndpoints:
    """Test health check endpoints."""
    
    def test_health_check(self, client):
        """Test basic health check."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    def test_readiness_check(self, client):
        """Test readiness check."""
        response = client.get("/ready")
        
        assert response.status_code == 200
        data = response.json()
        assert "ready" in data
        assert "checks" in data
    
    def test_liveness_check(self, client):
        """Test liveness check."""
        response = client.get("/live")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"


class TestDiligenceEndpoints:
    """Test diligence API endpoints."""
    
    def test_create_diligence(self, client):
        """Test creating a diligence."""
        response = client.post(
            "/api/v1/diligence",
            json={
                "ticker": "AAPL",
                "thesis": "Apple's AI integration will drive services revenue growth",
                "time_horizon": "medium_term",
                "risk_tolerance": "moderate",
                "position_size": 0.05,
            },
        )
        
        assert response.status_code == 202
        data = response.json()
        assert "diligence_id" in data
        assert data["status"] == "pending"
        assert "polling_url" in data
    
    def test_create_diligence_invalid_ticker(self, client):
        """Test creating diligence with invalid ticker."""
        response = client.post(
            "/api/v1/diligence",
            json={
                "ticker": "",
                "thesis": "Test thesis",
                "position_size": 0.05,
            },
        )
        
        assert response.status_code == 422
    
    def test_create_diligence_short_thesis(self, client):
        """Test creating diligence with short thesis."""
        response = client.post(
            "/api/v1/diligence",
            json={
                "ticker": "AAPL",
                "thesis": "Short",
                "position_size": 0.05,
            },
        )
        
        assert response.status_code == 422
    
    def test_get_diligence_not_found(self, client):
        """Test getting non-existent diligence."""
        response = client.get("/api/v1/diligence/non-existent-id")
        
        assert response.status_code == 404
    
    def test_list_diligences(self, client):
        """Test listing diligences."""
        response = client.get("/api/v1/diligence")
        
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "diligences" in data


class TestWebhookEndpoints:
    """Test webhook API endpoints."""
    
    def test_create_webhook(self, client):
        """Test creating a webhook."""
        response = client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com/webhook",
                "events": ["diligence.completed"],
            },
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "webhook_id" in data
        assert data["status"] == "active"
    
    def test_list_webhooks(self, client):
        """Test listing webhooks."""
        response = client.get("/api/v1/webhooks")
        
        assert response.status_code == 200
        data = response.json()
        assert "webhooks" in data
