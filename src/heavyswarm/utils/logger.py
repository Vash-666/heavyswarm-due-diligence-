"""Structured logging configuration for HeavySwarm."""

import logging
import sys
from typing import Any, Dict

import structlog


def setup_logging(log_level: str = "INFO", json_format: bool = False) -> None:
    """Configure structured logging.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Whether to output JSON formatted logs
    """
    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )
    
    # Configure structlog
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.ExtraAdder(),
    ]
    
    if json_format:
        # Production: JSON format
        structlog.configure(
            processors=shared_processors + [
                structlog.processors.dict_tracebacks,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level.upper())
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        # Development: Pretty format
        structlog.configure(
            processors=shared_processors + [
                structlog.dev.ConsoleRenderer(colors=True),
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, log_level.upper())
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=True,
        )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a structured logger.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name)


class AuditLogger:
    """Specialized logger for audit events.
    
    Ensures all audit events are logged with required fields
    for compliance purposes.
    """
    
    def __init__(self, logger: structlog.stdlib.BoundLogger):
        """Initialize audit logger.
        
        Args:
            logger: Base logger
        """
        self.logger = logger.bind(audit=True)
    
    def log_event(
        self,
        event_type: str,
        diligence_id: str,
        agent_id: str,
        details: Dict[str, Any],
    ) -> None:
        """Log an audit event.
        
        Args:
            event_type: Type of event
            diligence_id: Associated diligence ID
            agent_id: Agent that triggered the event
            details: Additional event details
        """
        self.logger.info(
            f"audit.{event_type}",
            diligence_id=diligence_id,
            agent_id=agent_id,
            event_type=event_type,
            details=details,
        )
    
    def log_phase_start(
        self,
        diligence_id: str,
        phase: str,
    ) -> None:
        """Log phase start event."""
        self.log_event(
            "phase_start",
            diligence_id,
            phase,
            {"phase": phase},
        )
    
    def log_phase_complete(
        self,
        diligence_id: str,
        phase: str,
        confidence: float,
        processing_time_ms: int,
    ) -> None:
        """Log phase completion event."""
        self.log_event(
            "phase_complete",
            diligence_id,
            phase,
            {
                "phase": phase,
                "confidence": confidence,
                "processing_time_ms": processing_time_ms,
            },
        )
    
    def log_decision(
        self,
        diligence_id: str,
        decision: str,
        confidence: float,
        reasoning: str,
    ) -> None:
        """Log a decision event."""
        self.log_event(
            "decision",
            diligence_id,
            "system",
            {
                "decision": decision,
                "confidence": confidence,
                "reasoning": reasoning,
            },
        )
    
    def log_data_verification(
        self,
        diligence_id: str,
        data_id: str,
        verification_level: str,
        verified: bool,
    ) -> None:
        """Log data verification event."""
        self.log_event(
            "data_verification",
            diligence_id,
            "verifier",
            {
                "data_id": data_id,
                "verification_level": verification_level,
                "verified": verified,
            },
        )
