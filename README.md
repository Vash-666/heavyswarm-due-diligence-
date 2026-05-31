# HeavySwarm Investment Due Diligence Engine v1.0.0

A production-grade, 7-agent investment due diligence system that leverages the HeavySwarm pattern to deliver institutional-quality investment research with built-in verification, audit trails, and trading system integration.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    HEAVYSWARM INVESTMENT DUE DILIGENCE ENGINE               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  INPUT: Investment Thesis                                                   │
│       ↓                                                                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ PHASE 0: @question_generator                                         │   │
│  │ PHASE 1: @researcher (Parallel)                                      │   │
│  │ PHASE 2: @financial_analyst + @risk_analyst (Parallel)               │   │
│  │ PHASE 3: @strategist (Grok reasoning)                                │   │
│  │ PHASE 4: @verifier (Grok reasoning)                                  │   │
│  │ PHASE 5: @writer                                                     │   │
│  │ QUALITY GATE: @qualityguardian (Conditional)                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│       ↓                                                                     │
│  OUTPUT: Investment Memo + Trading Signal + Audit Trail                     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Supported LLM Providers

HeavySwarm supports multiple LLM providers with intelligent fallback chains:

| Provider | Models | Best For |
|----------|--------|----------|
| **Anthropic** | Claude 3.5 Sonnet, Claude 3 Opus | General purpose, nuanced analysis |
| **OpenAI** | GPT-4o, GPT-4 Turbo, o1 series | Fast inference, structured output |
| **xAI** | Grok 4.20 Reasoning, Grok 4.3, Grok 2 | Complex reasoning, fact-checking |

## Quality Equation

Per HeavySwarm pattern requirements:
- **65% Prompts** - High-quality, versioned prompts
- **20% Memory** - Context retention across phases
- **10% Model** - Appropriate model selection
- **5% Tools** - External data/tool integration

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (optional)

### Installation

```bash
# Clone repository
git clone <repository-url>
cd heavyswarm-due-diligence

# Install dependencies
pip install -e ".[dev]"

# Set up environment
cp .env.example .env
# Edit .env with your API keys (OpenAI, Anthropic, and/or xAI)

# Run database migrations
alembic upgrade head

# Start the API
uvicorn heavyswarm.api.main:app --reload
```

### Docker Setup

```bash
# Start all services
docker-compose up -d

# Run migrations
docker-compose run migrate

# View logs
docker-compose logs -f api
```

## API Usage

### Create a Diligence

```bash
curl -X POST http://localhost:8000/api/v1/diligence \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "thesis": "Apple's AI integration will drive services revenue growth",
    "time_horizon": "medium_term",
    "risk_tolerance": "moderate",
    "position_size": 0.05
  }'
```

### Get Status

```bash
curl http://localhost:8000/api/v1/diligence/{diligence_id}
```

### Get Trading Signal

```bash
curl http://localhost:8000/api/v1/diligence/{diligence_id}/signal
```

## Project Structure

```
heavyswarm-due-diligence/
├── src/heavyswarm/           # Main source code
│   ├── agents/               # Agent implementations
│   ├── api/                  # FastAPI application
│   ├── core/                 # Core components
│   ├── services/             # Business services
│   └── utils/                # Utilities
├── tests/                    # Test suite
│   ├── unit/                 # Unit tests
│   └── integration/          # Integration tests
├── migrations/               # Database migrations
├── prompts/                  # Prompt registry
├── docs/                     # Documentation
├── docker-compose.yml        # Docker services
├── Dockerfile                # Container image
├── pyproject.toml            # Project config
└── README.md                 # This file
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/heavyswarm --cov-report=html

# Run specific test file
pytest tests/unit/test_agents.py
```

### Code Quality

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type checking
mypy src/heavyswarm
```

### Adding New Agents

1. Create agent class in `src/heavyswarm/agents/`
2. Inherit from `BaseAgent` or `ParallelAgent`
3. Implement `execute()` and `validate_output()` methods
4. Add tests in `tests/unit/test_agents.py`
5. Register in `src/heavyswarm/agents/__init__.py`

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection | `postgresql+asyncpg://...` |
| `REDIS_URL` | Redis connection | `redis://localhost:6379/0` |
| `OPENAI_API_KEY` | OpenAI API key | None |
| `ANTHROPIC_API_KEY` | Anthropic API key | None |
| `XAI_API_KEY` | xAI Grok API key | None |
| `DEFAULT_MODEL` | Default LLM model | `claude-3-5-sonnet-20241022` |
| `FALLBACK_MODEL` | Fallback LLM model | `gpt-4o` |
| `CONFIDENCE_THRESHOLD` | Quality gate threshold | 0.85 |
| `LOG_LEVEL` | Logging level | INFO |

See `.env.example` for complete list.

## Monitoring

The system exposes Prometheus metrics at `/metrics`:

- `diligence_duration` - End-to-end processing time
- `phase_duration` - Per-phase processing time
- `confidence_score` - Final confidence score
- `verification_rate` - % of data points verified
- `agent_errors` - Errors per agent

## Roadmap

### Milestone 1: Foundation (Week 1-2) ✓
- [x] Project scaffolding
- [x] Database schema
- [x] Agent base classes
- [x] Orchestration framework
- [x] Configuration management
- [x] Logging and audit trail
- [x] Docker setup

### Milestone 2: Core Agents (Week 3-5)
- [ ] @question_generator
- [ ] @researcher with data sources
- [ ] @financial_analyst with models
- [ ] @risk_analyst with matrix

### Milestone 3: Analysis & Verification (Week 6-7)
- [ ] @strategist with scenarios
- [ ] @verifier with fact-checking
- [ ] @writer with memo generation
- [ ] @qualityguardian gate

### Milestone 4: Integration & Testing (Week 8-9)
- [ ] Trading API integration
- [ ] End-to-end testing
- [ ] Performance optimization
- [ ] Security audit

### Milestone 5: Production (Week 10)
- [ ] Production deployment
- [ ] Monitoring setup
- [ ] Documentation
- [ ] Runbooks

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Support

For questions or issues:
- Email: team@heavyswarm.io
- Issues: GitHub Issues
- Documentation: `/docs` folder
