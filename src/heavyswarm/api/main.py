"""FastAPI application for HeavySwarm Due Diligence Engine."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from heavyswarm.api.routes import diligence, health, webhooks
from heavyswarm.core.config import settings
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
    
    yield
    
    # Shutdown
    logger.info("HeavySwarm Due Diligence Engine shutting down")


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
