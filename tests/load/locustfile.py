"""Load testing for HeavySwarm Due Diligence Engine using Locust."""

import random
from typing import Optional

from locust import HttpUser, task, between, events
from locust.runners import MasterRunner


class HeavySwarmUser(HttpUser):
    """Simulates a user interacting with HeavySwarm API."""
    
    wait_time = between(5, 15)  # Wait 5-15 seconds between tasks
    
    # Sample tickers for testing
    TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "META", "NVDA", "JPM", "V", "WMT"]
    
    # Sample theses
    THESES = [
        "Strong revenue growth driven by AI integration",
        "Market leader with sustainable competitive advantage",
        "Undervalued based on DCF analysis",
        "Potential headwinds from regulatory scrutiny",
        "Expanding into new markets with high growth potential",
    ]
    
    def on_start(self):
        """Called when a user starts."""
        self.diligence_ids = []
    
    @task(5)
    def create_diligence(self):
        """Create a new diligence."""
        ticker = random.choice(self.TICKERS)
        thesis = random.choice(self.THESES)
        
        payload = {
            "ticker": ticker,
            "thesis": thesis,
            "time_horizon": random.choice(["short_term", "medium_term", "long_term"]),
            "risk_tolerance": random.choice(["conservative", "moderate", "aggressive"]),
            "position_size": random.uniform(0.01, 0.1),
            "priority": random.choice(["low", "medium", "high"]),
        }
        
        with self.client.post(
            "/api/v1/diligence",
            json=payload,
            catch_response=True,
        ) as response:
            if response.status_code == 202:
                diligence_id = response.json().get("diligence_id")
                if diligence_id:
                    self.diligence_ids.append(diligence_id)
                response.success()
            else:
                response.failure(f"Failed to create diligence: {response.status_code}")
    
    @task(3)
    def get_diligence_status(self):
        """Get diligence status."""
        if not self.diligence_ids:
            return
        
        diligence_id = random.choice(self.diligence_ids)
        
        with self.client.get(
            f"/api/v1/diligence/{diligence_id}",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                # Diligence not found, remove from list
                self.diligence_ids.remove(diligence_id)
                response.success()
            else:
                response.failure(f"Failed to get status: {response.status_code}")
    
    @task(2)
    def list_diligences(self):
        """List all diligences."""
        with self.client.get(
            "/api/v1/diligence?limit=10",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Failed to list diligences: {response.status_code}")
    
    @task(1)
    def get_health(self):
        """Check health endpoint."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(1)
    def get_metrics(self):
        """Get Prometheus metrics."""
        with self.client.get("/metrics", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Metrics failed: {response.status_code}")


class HeavySwarmPeakLoadUser(HeavySwarmUser):
    """User that simulates peak load with shorter wait times."""
    
    wait_time = between(1, 3)
    weight = 1  # 1% of users


class HeavySwarmSustainedLoadUser(HeavySwarmUser):
    """User that simulates sustained load with normal wait times."""
    
    wait_time = between(5, 15)
    weight = 99  # 99% of users


@events.request.add_listener
def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
    """Log slow requests."""
    if response_time > 5000:  # Log requests over 5 seconds
        print(f"SLOW REQUEST: {request_type} {name} took {response_time}ms")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when the test stops."""
    print("\n" + "="*60)
    print("LOAD TEST COMPLETE")
    print("="*60)
    
    if isinstance(environment.runner, MasterRunner):
        stats = environment.runner.stats
        
        print(f"\nTotal Requests: {stats.total.num_requests}")
        print(f"Failed Requests: {stats.total.num_failures}")
        print(f"Average Response Time: {stats.total.avg_response_time:.2f}ms")
        print(f"95th Percentile: {stats.total.get_response_time_percentile(0.95):.2f}ms")
        print(f"99th Percentile: {stats.total.get_response_time_percentile(0.99):.2f}ms")
        print(f"Requests/sec: {stats.total.total_rps:.2f}")
