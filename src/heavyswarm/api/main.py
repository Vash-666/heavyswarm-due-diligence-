"""FastAPI application for HeavySwarm Due Diligence Engine."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from heavyswarm.api.routes import diligence, health, webhooks
from heavyswarm.core.config import settings
from heavyswarm.services.database import db_service
from heavyswarm.services.background_tasks import (
    BackgroundTaskManager,
    set_task_manager,
)
from heavyswarm.services.llm_client import LLMClient
from heavyswarm.core.orchestrator_factory import create_orchestrator_factory
from heavyswarm.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan handler.
    
    Handles startup and shutdown events.
    """
    # Startup
    setup_logging(
        log_level=settings.log_level,
        json_format=settings.is_production,
    )
    logger.info(
        "HeavySwarm Due Diligence Engine starting",
        extra={
            "version": "1.0.0",
            "environment": settings.environment,
        },
    )
    
    # Initialize database
    try:
        await db_service.connect()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        # Continue without database - endpoints will fail gracefully
    
    # Initialize LLM client
    llm_client = LLMClient(settings)
    
    # Initialize background task manager
    try:
        orchestrator_factory = create_orchestrator_factory(
            db_service=db_service,
            llm_client=llm_client,
            max_concurrent=settings.max_concurrent_diligences,
        )
        
        task_manager = BackgroundTaskManager(
            db_service=db_service,
            orchestrator_factory=orchestrator_factory.create_orchestrator,
            max_concurrent=settings.max_concurrent_diligences,
        )
        
        set_task_manager(task_manager)
        logger.info("Background task manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize task manager: {e}")
        task_manager = None
    
    yield
    
    # Shutdown
    logger.info("HeavySwarm Due Diligence Engine shutting down")
    
    # Shutdown task manager
    if task_manager:
        try:
            await task_manager.shutdown(wait=True, timeout=30.0)
        except Exception as e:
            logger.error(f"Error shutting down task manager: {e}")
    
    # Disconnect database
    try:
        await db_service.disconnect()
        logger.info("Database disconnected")
    except Exception as e:
        logger.error(f"Error disconnecting from database: {e}")


# Create FastAPI app
app = FastAPI(
    title="HeavySwarm Investment Due Diligence Engine",
    description="""
    A 7-agent multi-phase analysis system for institutional-quality investment research.
    
    ## Features
    
    - **6-Phase Analysis**: Question generation, research, financial analysis, 
      risk analysis, strategy, verification, and memo writing
    - **Quality Guardian**: Conditional quality gate for high-stakes decisions
    - **Data Verification**: L1-L4 verification pipeline for data integrity
    - **Trading Integration**: Standardized trading signals with webhook delivery
    - **Full Audit Trail**: Complete provenance tracking for compliance
    
    ## Quality Equation
    
    - 65% Prompts
    - 20% Memory
    - 10% Model
    - 5% Tools
    """,
    version="1.0.0",
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unhandled exceptions."""
    logger.error(
        "Unhandled exception",
        extra={
            "path": request.url.path,
            "error": str(exc),
        },
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
            }
        },
    )


# Include routers
app.include_router(health.router, tags=["Health"])
app.include_router(diligence.router, prefix="/api/v1", tags=["Diligence"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["Webhooks"])


@app.get("/")
async def root() -> dict:
    """Root endpoint."""
    return {
        "name": "HeavySwarm Investment Due Diligence Engine",
        "version": "1.0.0",
        "documentation": "/docs",
        "health": "/health",
    }
