"""Enumeration definitions for HeavySwarm."""

from enum import Enum, auto


class AgentPhase(Enum):
    """Enumeration of agent phases in the HeavySwarm workflow."""
    
    QUESTION_GENERATOR = 0
    RESEARCHER = 1
    FINANCIAL_ANALYST = 2
    RISK_ANALYST = 3
    STRATEGIST = 4
    VERIFIER = 5
    WRITER = 6
    QUALITY_GUARDIAN = 7
    
    @property
    def display_name(self) -> str:
        """Get human-readable display name."""
        names = {
            AgentPhase.QUESTION_GENERATOR: "Question Generator",
            AgentPhase.RESEARCHER: "Researcher",
            AgentPhase.FINANCIAL_ANALYST: "Financial Analyst",
            AgentPhase.RISK_ANALYST: "Risk Analyst",
            AgentPhase.STRATEGIST: "Strategist",
            AgentPhase.VERIFIER: "Verifier",
            AgentPhase.WRITER: "Writer",
            AgentPhase.QUALITY_GUARDIAN: "Quality Guardian",
        }
        return names.get(self, self.name)


class DiligenceStatus(Enum):
    """Status of a diligence analysis."""
    
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    VERIFYING = "verifying"
    QUALITY_GATE = "quality_gate"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TimeHorizon(Enum):
    """Investment time horizon."""
    
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class RiskTolerance(Enum):
    """Risk tolerance level."""
    
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


class Priority(Enum):
    """Task priority level."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class VerificationLevel(Enum):
    """Data verification levels."""
    
    L1 = "L1"  # Source-attested
    L2 = "L2"  # Cross-referenced
    L3 = "L3"  # Real-time validated
    L4 = "L4"  # Human-verified


class Recommendation(Enum):
    """Investment recommendation."""
    
    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"
    WATCH = "watch"


class RiskRating(Enum):
    """Risk rating."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class SignalAction(Enum):
    """Trading signal action."""
    
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class SignalUrgency(Enum):
    """Trading signal urgency."""
    
    IMMEDIATE = "immediate"
    THIS_WEEK = "this_week"
    THIS_MONTH = "this_month"
    WATCH = "watch"


class BiasType(Enum):
    """Types of cognitive bias."""
    
    CONFIRMATION = "confirmation_bias"
    ANCHORING = "anchoring_bias"
    RECENCY = "recency_bias"
    SURVIVORSHIP = "survivorship_bias"


class RiskCategory(Enum):
    """Risk categories."""
    
    MARKET = "market_risks"
    CREDIT = "credit_risks"
    OPERATIONAL = "operational_risks"
    REGULATORY = "regulatory_risks"
    ESG = "esg_risks"
