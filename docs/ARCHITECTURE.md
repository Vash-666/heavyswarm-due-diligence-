# Architecture Specification
## HeavySwarm Investment Due Diligence Engine v1.0.0

**Version:** 1.0.0  
**Date:** 2026-05-30  
**Status:** Draft

---

## 1. System Overview

### 1.1 Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │ Web UI      │  │ Trading     │  │ API Clients │  │ CLI         │                 │
│  │ (React)     │  │ System      │  │ (SDK)       │  │ (Python)    │                 │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │
└─────────┼────────────────┼────────────────┼────────────────┼────────────────────────┘
          │                │                │                │
          └────────────────┴────────────────┴────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │  • Rate Limiting  • Authentication  • Request Validation  • Logging         │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATION LAYER                                        │
│  ┌─────────────────────────────────────────────────────────────────────────────┐    │
│  │                         HeavySwarm Orchestrator                              │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │    │
│  │  │ State       │  │ Phase       │  │ Agent       │  │ Quality     │         │    │
│  │  │ Manager     │  │ Controller  │  │ Router      │  │ Controller  │         │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │    │
│  └─────────────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   AGENT POOL    │    │   DATA LAYER    │    │   AUDIT LAYER   │
│  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │
│  │ Agent 0-6 │  │    │  │ Cache     │  │    │  │ Event Log │  │
│  │ (7 agents)│  │    │  │ (Redis)   │  │    │  │ (Append)  │  │
│  └───────────┘  │    │  └───────────┘  │    │  └───────────┘  │
│  ┌───────────┐  │    │  ┌───────────┐  │    │  ┌───────────┐  │
│  │ Quality   │  │    │  │ State DB  │  │    │  │ Provenance│  │
│  │ Guardian  │  │    │  │ (Postgre) │  │    │  │ Graph     │  │
│  └───────────┘  │    │  └───────────┘  │    │  └───────────┘  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL INTEGRATIONS                                        │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐  │
│  │ SEC EDGAR   │  │ Bloomberg   │  │ News APIs   │  │ LLM APIs    │  │ Trading   │  │
│  │ API         │  │ API         │  │ (Multi)     │  │ (OpenAI/    │  │ Systems   │  │
│  │             │  │             │  │             │  │ Anthropic)  │  │           │  │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘  └───────────┘  │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Component Responsibilities

| Component | Responsibility | Technology |
|-----------|---------------|------------|
| API Gateway | Request routing, auth, rate limiting | FastAPI + middleware |
| Orchestrator | Phase management, agent coordination | Python async/await |
| State Manager | Shared state across agents | Redis + PostgreSQL |
| Agent Pool | 7 specialized agents | LLM-powered functions |
| Data Layer | Caching and persistence | Redis, PostgreSQL |
| Audit Layer | Immutable event log | Append-only PostgreSQL |

---

## 2. Agent Architecture

### 2.1 Agent Base Class

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from enum import Enum

class AgentPhase(Enum):
    QUESTION_GENERATOR = 0
    RESEARCHER = 1
    FINANCIAL_ANALYST = 2
    RISK_ANALYST = 3
    STRATEGIST = 4
    VERIFIER = 5
    WRITER = 6
    QUALITY_GUARDIAN = 7

@dataclass
class AgentConfig:
    model: str
    temperature: float
    max_tokens: int
    timeout_seconds: int
    retry_attempts: int

@dataclass
class AgentInput:
    thesis: InvestmentThesis
    context: Dict[str, Any]
    previous_outputs: Dict[AgentPhase, Any]
    state: DiligenceState

@dataclass
class AgentOutput:
    phase: AgentPhase
    data: Dict[str, Any]
    confidence: float
    provenance: List[DataProvenance]
    processing_time_ms: int
    metadata: Dict[str, Any]

class BaseAgent(ABC):
    """Base class for all HeavySwarm agents"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.phase: AgentPhase = None
    
    @abstractmethod
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute agent's specific task"""
        pass
    
    @abstractmethod
    def validate_output(self, output: AgentOutput) -> bool:
        """Validate output meets contract requirements"""
        pass
    
    async def run_with_retry(self, input_data: AgentInput) -> AgentOutput:
        """Execute with retry logic"""
        for attempt in range(self.config.retry_attempts):
            try:
                output = await self.execute(input_data)
                if self.validate_output(output):
                    return output
            except Exception as e:
                if attempt == self.config.retry_attempts - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

### 2.2 Agent Configuration Matrix

| Agent | Model | Temp | Max Tokens | Timeout | Retries | Fallback Chain |
|-------|-------|------|------------|---------|---------|----------------|
| question_generator | claude-3-5-sonnet | 0.3 | 4000 | 30s | 3 | - |
| researcher | gpt-4o | 0.2 | 8000 | 60s | 3 | - |
| financial_analyst | claude-3-5-sonnet | 0.1 | 6000 | 45s | 3 | - |
| risk_analyst | claude-3-5-sonnet | 0.2 | 5000 | 45s | 3 | - |
| strategist | grok-4.20-reasoning | 0.3 | 6000 | 60s | 3 | grok-4.20 → claude-3.5 → gpt-4o |
| verifier | grok-4.20-reasoning | 0.1 | 8000 | 60s | 3 | grok-4.20 → claude-3.5 → gpt-4o |
| writer | claude-3-5-sonnet | 0.2 | 10000 | 60s | 3 | - |
| qualityguardian | gpt-4o | 0.1 | 4000 | 30s | 2 | - |

#### Model Selection Rationale

**Grok for Strategist & Verifier:**
- `grok-4.20-reasoning` is assigned to phases requiring complex reasoning:
  - **Strategist**: Scenario analysis with devil's advocate requires deep reasoning
  - **Verifier**: Fact-checking and bias detection benefits from extended thinking
- Fallback chain: Grok → Claude 3.5 Sonnet → GPT-4o

**Claude for Analysis & Writing:**
- `claude-3-5-sonnet` handles financial analysis, risk assessment, and memo writing
- Superior at nuanced analysis and long-form content generation

**GPT-4o for Research & Quality:**
- `gpt-4o` excels at parallel research tasks and quick quality checks
- Fast inference with structured output capabilities

---

## 3. State Management

### 3.1 Diligence State Schema

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum
import uuid

class DiligenceStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    QUALITY_GATE = "quality_gate"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class InvestmentThesis:
    ticker: str
    thesis: str
    time_horizon: str  # short_term, medium_term, long_term
    risk_tolerance: str  # conservative, moderate, aggressive
    position_size: float
    priority: str  # low, medium, high, critical
    deadline: Optional[datetime] = None
    metadata: Dict = field(default_factory=dict)

@dataclass
class DataProvenance:
    data_id: str
    value: any
    source_url: str
    retrieved_at: datetime
    verified_by: str
    verification_level: str  # L1, L2, L3, L4
    confidence: float
    chain_of_custody: List[str] = field(default_factory=list)

@dataclass
class PhaseResult:
    phase: AgentPhase
    output: Dict
    confidence: float
    processing_time_ms: int
    completed_at: datetime
    agent_id: str

@dataclass
class DiligenceState:
    """Central state object shared across all agents"""
    
    # Identity
    diligence_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    # Input
    thesis: Optional[InvestmentThesis] = None
    
    # Progress
    status: DiligenceStatus = DiligenceStatus.PENDING
    current_phase: Optional[AgentPhase] = None
    completed_phases: List[AgentPhase] = field(default_factory=list)
    
    # Results
    phase_results: Dict[AgentPhase, PhaseResult] = field(default_factory=dict)
    data_provenance: Dict[str, DataProvenance] = field(default_factory=dict)
    
    # Aggregated metrics
    overall_confidence: float = 0.0
    verification_rate: float = 0.0
    total_data_points: int = 0
    verified_data_points: int = 0
    
    # Quality gate
    quality_gate_triggered: bool = False
    quality_gate_result: Optional[Dict] = None
    
    # Final output
    memo: Optional[Dict] = None
    trading_signal: Optional[Dict] = None
    
    # Audit
    events: List[Dict] = field(default_factory=list)
    
    def add_event(self, event_type: str, agent_id: str, details: Dict):
        """Add immutable audit event"""
        self.events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "agent_id": agent_id,
            "details": details
        })
    
    def get_context_for_phase(self, phase: AgentPhase) -> Dict:
        """Get relevant context for a specific phase"""
        context = {
            "thesis": self.thesis,
            "previous_phases": {}
        }
        
        # Include outputs from previous phases
        for p in AgentPhase:
            if p.value < phase.value and p in self.phase_results:
                context["previous_phases"][p.name] = self.phase_results[p].output
        
        return context
```

### 3.2 State Persistence

```python
class StateManager:
    """Manages persistence and retrieval of diligence state"""
    
    def __init__(self, redis_client, db_client):
        self.redis = redis_client
        self.db = db_client
    
    async def save_state(self, state: DiligenceState) -> None:
        """Save state to Redis (hot) and DB (persistent)"""
        # Hot cache (Redis) - 1 hour TTL
        await self.redis.setex(
            f"diligence:{state.diligence_id}",
            3600,
            json.dumps(state, cls=DiligenceStateEncoder)
        )
        
        # Persistent storage (PostgreSQL)
        await self.db.execute(
            """
            INSERT INTO diligence_states (id, state, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (id) DO UPDATE SET
                state = EXCLUDED.state,
                updated_at = EXCLUDED.updated_at
            """,
            state.diligence_id,
            json.dumps(state, cls=DiligenceStateEncoder)
        )
    
    async def load_state(self, diligence_id: str) -> Optional[DiligenceState]:
        """Load state from cache or DB"""
        # Try cache first
        cached = await self.redis.get(f"diligence:{diligence_id}")
        if cached:
            return json.loads(cached, cls=DiligenceStateDecoder)
        
        # Fall back to DB
        row = await self.db.fetchrow(
            "SELECT state FROM diligence_states WHERE id = $1",
            diligence_id
        )
        if row:
            return json.loads(row["state"], cls=DiligenceStateDecoder)
        
        return None
```

---

## 4. Orchestration Flow

### 4.1 Phase Execution Sequence

```python
class HeavySwarmOrchestrator:
    """Orchestrates the 6-phase + quality gate workflow"""
    
    def __init__(self, agents: Dict[AgentPhase, BaseAgent], state_manager: StateManager):
        self.agents = agents
        self.state_manager = state_manager
        self.phase_order = [
            AgentPhase.QUESTION_GENERATOR,
            AgentPhase.RESEARCHER,
            AgentPhase.FINANCIAL_ANALYST,
            AgentPhase.RISK_ANALYST,
            AgentPhase.STRATEGIST,
            AgentPhase.VERIFIER,
            AgentPhase.WRITER,
            AgentPhase.QUALITY_GUARDIAN
        ]
    
    async def run_diligence(self, thesis: InvestmentThesis) -> DiligenceState:
        """Execute full diligence workflow"""
        # Initialize state
        state = DiligenceState(thesis=thesis)
        state.status = DiligenceStatus.IN_PROGRESS
        await self.state_manager.save_state(state)
        
        try:
            # Phase 0: Question Generation
            await self._execute_phase(state, AgentPhase.QUESTION_GENERATOR)
            
            # Phase 1: Research (Parallel sub-tasks)
            await self._execute_phase(state, AgentPhase.RESEARCHER)
            
            # Phase 2: Analysis (Parallel)
            await asyncio.gather(
                self._execute_phase(state, AgentPhase.FINANCIAL_ANALYST),
                self._execute_phase(state, AgentPhase.RISK_ANALYST)
            )
            
            # Phase 3: Strategy
            await self._execute_phase(state, AgentPhase.STRATEGIST)
            
            # Phase 4: Verification
            await self._execute_phase(state, AgentPhase.VERIFIER)
            
            # Check confidence threshold
            if state.overall_confidence < 0.85:
                state.quality_gate_triggered = True
                state.status = DiligenceStatus.QUALITY_GATE
                await self.state_manager.save_state(state)
            
            # Phase 5: Writing
            await self._execute_phase(state, AgentPhase.WRITER)
            
            # Quality Gate (conditional)
            if state.quality_gate_triggered:
                await self._execute_phase(state, AgentPhase.QUALITY_GUARDIAN)
            
            state.status = DiligenceStatus.COMPLETED
            
        except Exception as e:
            state.status = DiligenceStatus.FAILED
            state.add_event("error", "orchestrator", {"error": str(e)})
            raise
        
        finally:
            await self.state_manager.save_state(state)
        
        return state
    
    async def _execute_phase(self, state: DiligenceState, phase: AgentPhase) -> None:
        """Execute a single phase"""
        agent = self.agents[phase]
        state.current_phase = phase
        state.add_event("phase_started", phase.name, {})
        
        # Prepare input
        context = state.get_context_for_phase(phase)
        input_data = AgentInput(
            thesis=state.thesis,
            context=context,
            previous_outputs={p: r.output for p, r in state.phase_results.items()},
            state=state
        )
        
        # Execute with timing
        start_time = time.time()
        output = await agent.run_with_retry(input_data)
        processing_time = int((time.time() - start_time) * 1000)
        
        # Store result
        phase_result = PhaseResult(
            phase=phase,
            output=output.data,
            confidence=output.confidence,
            processing_time_ms=processing_time,
            completed_at=datetime.utcnow(),
            agent_id=phase.name
        )
        state.phase_results[phase] = phase_result
        state.completed_phases.append(phase)
        
        # Update aggregates
        if phase == AgentPhase.VERIFIER:
            state.overall_confidence = output.confidence
        
        state.add_event("phase_completed", phase.name, {
            "confidence": output.confidence,
            "processing_time_ms": processing_time
        })
        
        await self.state_manager.save_state(state)
```

---

## 5. Data Verification Pipeline

### 5.1 Verification Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    DATA VERIFICATION PIPELINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Raw Data                                                        │
│     │                                                            │
│     ▼                                                            │
│  ┌─────────────────┐                                            │
│  │ L1: Source      │ ──► Store URL + timestamp                   │
│  │ Attribution     │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│     ┌─────┴─────┐                                                │
│     │           │                                                │
│     ▼           ▼                                                │
│  ┌──────┐   ┌──────┐                                            │
│  │ Key  │   │ Non- │                                            │
│  │ Data?│   │ Key  │                                            │
│  └──┬───┘   └──┬───┘                                            │
│     │          │                                                 │
│     ▼          ▼                                                 │
│  ┌────────┐  ┌────────┐                                         │
│  │ L2:    │  │ Accept │                                         │
│  │ Cross- │  │ L1     │                                         │
│  │ Ref    │  │        │                                         │
│  └───┬────┘  └────────┘                                         │
│      │                                                           │
│      ▼                                                           │
│  ┌─────────────────┐                                            │
│  │ L3: Real-time   │ ──► Validate against live API              │
│  │ Validation      │                                            │
│  └────────┬────────┘                                            │
│           │                                                      │
│     ┌─────┴─────┐                                                │
│     │           │                                                │
│     ▼           ▼                                                │
│  ┌──────┐   ┌──────┐                                            │
│  │ Pass │   │ Fail │                                            │
│  └──┬───┘   └──┬───┘                                            │
│     │          │                                                 │
│     ▼          ▼                                                 │
│  ┌────────┐  ┌────────┐                                         │
│  │ Accept │  │ L4:    │                                         │
│  │ L3     │  │ Human  │                                         │
│  │        │  │ Review │                                         │
│  └────────┘  └────────┘                                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 Verification Service

```python
class VerificationService:
    """Handles multi-level data verification"""
    
    def __init__(self, cache: Redis, validators: Dict[str, DataValidator]):
        self.cache = cache
        self.validators = validators
    
    async def verify_data_point(
        self,
        data_point: DataPoint,
        required_level: str = "L2"
    ) -> VerificationResult:
        """Verify a single data point through all levels"""
        
        result = VerificationResult(
            data_id=data_point.id,
            requested_level=required_level,
            achieved_level=None,
            verified=False,
            sources=[],
            errors=[]
        )
        
        # L1: Source attribution (always required)
        if not data_point.source_url:
            result.errors.append("No source URL provided")
            return result
        
        result.sources.append({
            "url": data_point.source_url,
            "retrieved_at": datetime.utcnow().isoformat()
        })
        result.achieved_level = "L1"
        
        # L2: Cross-reference (for key data)
        if required_level in ["L2", "L3", "L4"]:
            cross_refs = await self._find_cross_references(data_point)
            if len(cross_refs) < 1:
                result.errors.append("Insufficient cross-references")
                return result
            result.sources.extend(cross_refs)
            result.achieved_level = "L2"
        
        # L3: Real-time validation
        if required_level in ["L3", "L4"]:
            validator = self.validators.get(data_point.type)
            if validator:
                is_valid = await validator.validate(data_point)
                if not is_valid:
                    result.errors.append("Real-time validation failed")
                    return result
            result.achieved_level = "L3"
        
        result.verified = True
        return result
    
    async def _find_cross_references(self, data_point: DataPoint) -> List[Dict]:
        """Find additional sources for cross-referencing"""
        # Implementation: Search cache, query alternative sources
        pass
```

---

## 6. Error Handling & Resilience

### 6.1 Error Categories

| Category | Examples | Handling Strategy |
|----------|----------|-------------------|
| Transient | API timeout, rate limit | Retry with exponential backoff |
| Data | Missing data, stale data | Degrade gracefully, flag for review |
| Agent | LLM hallucination, invalid output | Validation, fallback prompts |
| System | DB failure, network partition | Circuit breaker, queue for retry |

### 6.2 Circuit Breaker Pattern

```python
from circuitbreaker import circuit

class ResilientAgent(BaseAgent):
    """Agent with built-in resilience patterns"""
    
    @circuit(failure_threshold=5, recovery_timeout=60)
    async def execute(self, input_data: AgentInput) -> AgentOutput:
        """Execute with circuit breaker protection"""
        return await super().execute(input_data)
    
    async def execute_with_fallback(self, input_data: AgentInput) -> AgentOutput:
        """Execute with fallback to simpler model"""
        try:
            return await self.execute(input_data)
        except CircuitBreakerError:
            # Fallback to lighter model
            fallback_config = AgentConfig(
                model="gpt-3.5-turbo",
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                timeout_seconds=self.config.timeout_seconds,
                retry_attempts=1
            )
            fallback_agent = self.__class__(fallback_config)
            return await fallback_agent.execute(input_data)
```

---

## 7. Monitoring & Observability

### 7.1 Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `diligence_duration` | Histogram | End-to-end processing time |
| `phase_duration` | Histogram | Per-phase processing time |
| `confidence_score` | Gauge | Final confidence score |
| `verification_rate` | Gauge | % of data points verified |
| `agent_errors` | Counter | Errors per agent |
| `active_diligences` | Gauge | Currently running analyses |

### 7.2 Tracing

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

class TracedOrchestrator(HeavySwarmOrchestrator):
    """Orchestrator with distributed tracing"""
    
    async def run_diligence(self, thesis: InvestmentThesis) -> DiligenceState:
        with tracer.start_as_current_span("diligence") as span:
            span.set_attribute("ticker", thesis.ticker)
            span.set_attribute("priority", thesis.priority)
            
            state = await super().run_diligence(thesis)
            
            span.set_attribute("confidence", state.overall_confidence)
            span.set_attribute("duration_ms", 
                (datetime.utcnow() - state.created_at).total_seconds() * 1000)
            
            return state
```

---

## 8. Security Considerations

### 8.1 Data Protection

| Layer | Measure |
|-------|---------|
| Transport | TLS 1.3 for all connections |
| Storage | Encryption at rest (AES-256) |
| API Keys | Stored in secrets manager, rotated monthly |
| PII | No PII stored; ticker symbols only |

### 8.2 Access Control

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify JWT token"""
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

@app.post("/api/v1/diligence")
async def create_diligence(
    thesis: InvestmentThesis,
    user: dict = Depends(verify_token)
):
    """Create new diligence with auth"""
    # Check permissions
    if not has_permission(user["role"], "create_diligence"):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    
    # Proceed with creation
    ...
```

---

## 9. Deployment Architecture

### 9.1 Container Strategy

```yaml
# docker-compose.yml
version: '3.8'
services:
  api:
    build: ./api
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379
      - DB_URL=postgresql://db:5432/diligence
    depends_on:
      - redis
      - db
  
  worker:
    build: ./worker
    environment:
      - REDIS_URL=redis://redis:6379
      - DB_URL=postgresql://db:5432/diligence
    depends_on:
      - redis
      - db
    deploy:
      replicas: 3
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
  
  db:
    image: postgres:15-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      - POSTGRES_DB=diligence
      - POSTGRES_USER=diligence
      - POSTGRES_PASSWORD_FILE=/run/secrets/db_password
```

### 9.2 Kubernetes Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: diligence-engine
spec:
  replicas: 3
  selector:
    matchLabels:
      app: diligence-engine
  template:
    metadata:
      labels:
        app: diligence-engine
    spec:
      containers:
      - name: api
        image: diligence-engine:v1.0.0
        ports:
        - containerPort: 8000
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        env:
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: diligence-secrets
              key: redis-url
```

---

## 10. Appendices

### Appendix A: Database Schema

```sql
-- Core tables
CREATE TABLE diligence_states (
    id UUID PRIMARY KEY,
    state JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diligence_id UUID REFERENCES diligence_states(id),
    event_type VARCHAR(50) NOT NULL,
    agent_id VARCHAR(50) NOT NULL,
    details JSONB,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE data_provenance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    diligence_id UUID REFERENCES diligence_states(id),
    data_id VARCHAR(100) NOT NULL,
    value JSONB,
    source_url TEXT,
    verification_level VARCHAR(10),
    confidence FLOAT,
    chain_of_custody JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_diligence_status ON diligence_states((state->>'status'));
CREATE INDEX idx_audit_diligence ON audit_events(diligence_id);
CREATE INDEX idx_provenance_diligence ON data_provenance(diligence_id);
```

### Appendix B: Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `OPENAI_API_KEY` | OpenAI API key | No* |
| `ANTHROPIC_API_KEY` | Anthropic API key | No* |
| `XAI_API_KEY` | xAI Grok API key | No* |
| `REDIS_URL` | Redis connection string | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `BLOOMBERG_API_KEY` | Bloomberg API (optional) | No |
| `ALPHA_VANTAGE_KEY` | Alpha Vantage API (optional) | No |
| `LOG_LEVEL` | Logging level (default: INFO) | No |
| `MAX_CONCURRENT_DILIGENCES` | Concurrency limit (default: 10) | No |

\* At least one LLM provider API key is required. The system supports OpenAI, Anthropic, and xAI Grok with automatic fallback between providers.

---

**End of Architecture Specification**
