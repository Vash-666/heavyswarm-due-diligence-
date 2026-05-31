# Handoff Document
## HeavySwarm Investment Due Diligence Engine v1.0.0

**From:** Product Owner  
**To:** @scaffolder  
**Date:** 2026-05-30  
**Status:** Ready for Implementation

---

## Executive Summary

The Product Requirements Document (PRD) for the HeavySwarm Investment Due Diligence Engine is complete. This document summarizes the handoff package and provides guidance for the implementation phase.

---

## Handoff Package Contents

### 1. Core Documentation

| Document | Location | Purpose |
|----------|----------|---------|
| **PRD** | `docs/PRD.md` | Complete product requirements |
| **Architecture** | `docs/ARCHITECTURE.md` | System design & component specs |
| **API Specification** | `docs/API_SPEC.md` | REST API contracts |
| **Roadmap** | `docs/ROADMAP.md` | 10-week implementation plan |
| **Risk Assessment** | `docs/RISKS.md` | Risk matrix & mitigations |
| **This Handoff** | `docs/HANDOFF.md` | Implementation guidance |

### 2. Prompt Registry

| File | Location | Description |
|------|----------|-------------|
| Registry | `prompts/v1.0.0/registry.json` | Prompt metadata & config |
| System Prompts | `prompts/v1.0.0/{agent}/` | Agent-specific prompts |

---

## Key Decisions & Rationale

### Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **7 Agents** | 6 HeavySwarm phases + Quality Guardian gate |
| **Claude 3.5 Sonnet** | Primary model for analysis agents (reasoning quality) |
| **GPT-4o** | Secondary model for research/strategy (speed/cost) |
| **PostgreSQL + Redis** | Persistence + hot cache for state management |
| **FastAPI** | Modern Python async framework |
| **Quality Equation 65/20/10/5** | Heavy emphasis on prompt engineering |

### Quality Thresholds

| Metric | Threshold | Enforcement |
|--------|-----------|-------------|
| Confidence Score | >85% | Quality Guardian blocks if below |
| Verification Rate | >95% | L1-L4 verification pipeline |
| End-to-End Latency | <5 min | Timeout + degradation |
| False Positive Rate | <5% | Backtesting validation |

---

## Critical Implementation Notes

### 1. Data Verification is Non-Negotiable

Every data point must have:
- **L1**: Source URL + timestamp
- **L2**: Cross-reference (for key metrics)
- **L3**: Real-time validation (for prices)
- **L4**: Human review (for disputed data)

The `@verifier` agent enforces this. Do not skip verification for speed.

### 2. Agent I/O Contracts Are Strict

Each agent has defined input/output schemas in the PRD. The orchestrator depends on these contracts. Changing them requires updating:
- The agent implementation
- The orchestrator's phase handoff logic
- The state management schema

### 3. Quality Guardian Trigger Conditions

The `@qualityguardian` MUST be triggered when:
- Confidence < 85%
- Risk score > 70
- Position size > 5%
- Any anomaly detected

This is a safety feature. Do not bypass.

### 4. Trading System Integration

The API produces a standardized trading signal. Key requirements:
- Webhook delivery with retry
- Signal idempotency (prevent duplicates)
- Full audit trail for compliance
- Position sizing with risk limits

### 5. Audit Trail is Immutable

Every action must be logged:
- Agent executions
- Data point provenance
- Confidence scores
- Quality gate decisions

Use append-only storage. Never delete or modify audit events.

---

## Implementation Priority

### Week 1-2: Foundation (M1)
**Must Have:**
- [ ] Project scaffolding
- [ ] Database schema
- [ ] State management
- [ ] Agent base class
- [ ] Orchestrator skeleton

**Nice to Have:**
- [ ] Monitoring setup
- [ ] CI/CD pipeline

### Week 3-5: Core Agents (M2)
**Must Have:**
- [ ] @question_generator
- [ ] @researcher with data sources
- [ ] @financial_analyst with DCF/comps
- [ ] @risk_analyst with matrix
- [ ] @strategist with scenarios
- [ ] @verifier with fact-checking
- [ ] @writer with memo generation

**Nice to Have:**
- [ ] PDF export
- [ ] Advanced visualizations

### Week 6-7: Quality & Performance (M3)
**Must Have:**
- [ ] @qualityguardian implementation
- [ ] Confidence calibration
- [ ] Performance optimization
- [ ] <5 min latency target

**Nice to Have:**
- [ ] Advanced caching strategies

### Week 8-9: Integration & Testing (M4)
**Must Have:**
- [ ] Trading API integration
- [ ] Webhook system
- [ ] >90% test coverage
- [ ] Security audit

**Nice to Have:**
- [ ] Additional trading system connectors

### Week 10: Production (M5)
**Must Have:**
- [ ] Production deployment
- [ ] Monitoring & alerting
- [ ] Documentation
- [ ] Runbooks

**Nice to Have:**
- [ ] Auto-scaling configuration

---

## Known Gaps & TBD Items

| Item | Status | Owner | Notes |
|------|--------|-------|-------|
| Bloomberg API license | TBD | Business | Required for M2 |
| Trading system credentials | TBD | Security | Required for M4 |
| Production cloud account | TBD | DevOps | Required for M5 |
| Legal disclaimers | TBD | Legal | Required for M5 |
| User training plan | TBD | Training | Post-launch |

---

## Success Criteria for Implementation

The implementation is successful when:

1. **All 7 agents execute correctly** in the 6-phase + quality gate flow
2. **Data verification rate >95%** on all test cases
3. **Confidence score >85%** average across test tickers
4. **End-to-end latency <5 minutes** for standard analyses
5. **Trading signals** are correctly formatted and delivered
6. **Full audit trail** is maintained for every diligence
7. **Quality guardian** triggers appropriately and makes correct decisions
8. **All tests pass** with >90% coverage
9. **Security audit** finds no critical vulnerabilities
10. **Production deployment** is stable for 48 hours

---

## Questions for @scaffolder

Before beginning implementation, please confirm:

1. **Tech Stack**: Confirm FastAPI + PostgreSQL + Redis is acceptable
2. **LLM Budget**: Estimated 45K tokens per diligence - confirm budget
3. **Deployment Target**: AWS, GCP, or Azure preference?
4. **Trading System**: Which OMS will we integrate with first?
5. **Team Size**: How many developers available? (affects timeline)

---

## Contact & Escalation

| Issue Type | Contact | Response Time |
|------------|---------|---------------|
| Requirements clarification | Product Owner | 24 hours |
| Architecture questions | Product Owner | 24 hours |
| Blockers | Product Owner + Tech Lead | 4 hours |
| Scope changes | Steering Committee | 48 hours |

---

## Sign-Off

**Product Owner:**
- [x] PRD complete
- [x] Architecture approved
- [x] API contracts defined
- [x] Roadmap finalized
- [x] Risks documented

**@scaffolder Acceptance:**
- [ ] Requirements understood
- [ ] Technical approach validated
- [ ] Timeline confirmed
- [ ] Resources allocated
- [ ] Ready to begin

---

## Next Steps

1. **@scaffolder** reviews this handoff package
2. **@scaffolder** confirms acceptance criteria understanding
3. **@scaffolder** begins Milestone 1: Foundation
4. **Product Owner** available for daily standups during M1
5. **M1 Quality Gate** review at end of Week 2

---

**Ready for implementation. Good luck!**
