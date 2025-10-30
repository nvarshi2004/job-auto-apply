"""FastAPI Main Application

Complete FastAPI application with CORS, routers, logging, 
exception handlers, and startup/shutdown events.
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from db.connection import MongoDB, create_indexes, check_database_health
from api.auth import router as auth_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('app.log')
    ]
)
logger = logging.getLogger(__name__)


# Lifespan context manager for startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown events
    Handles database connection and cleanup
    """
    # Startup
    logger.info("Application startup initiated")
    try:
        # Connect to MongoDB
        await MongoDB.connect_to_database()
        logger.info("MongoDB connection established")
        
        # Create database indexes
        await create_indexes()
        logger.info("Database indexes created")
        
        # Check database health
        health = await check_database_health()
        logger.info(f"Database health check: {health['status']}")
        
        logger.info("Application startup completed successfully")
        
    except Exception as e:
        logger.error(f"Error during startup: {e}")
        raise
    
    yield  # Application runs here
    
    # Shutdown
    logger.info("Application shutdown initiated")
    try:
        await MongoDB.close_database_connection()
        logger.info("MongoDB connection closed")
        logger.info("Application shutdown completed successfully")
        
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


# Initialize FastAPI application
app = FastAPI(
    title="Job Auto Apply API",
    description="Automated job application system for college students with AI-powered resume matching",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)


# CORS middleware configuration
allowed_origins = os.getenv(
    "ALLOWED_ORIGINS", 
    "http://localhost:3000,http://localhost:5173,http://localhost:8080"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if os.getenv("ENVIRONMENT") == "production" else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)


# Custom exception handlers

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """
    Handle HTTP exceptions
    """
    logger.error(f"HTTP error occurred: {exc.status_code} - {exc.detail}")
    logger.error(f"Request path: {request.url.path}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "status_code": exc.status_code,
                "message": exc.detail,
                "type": "HTTPException",
                "path": str(request.url.path)
            }
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handle request validation errors
    """
    logger.error(f"Validation error: {exc.errors()}")
    logger.error(f"Request path: {request.url.path}")
    logger.error(f"Request body: {exc.body}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "message": "Validation error",
                "type": "ValidationError",
                "details": exc.errors(),
                "path": str(request.url.path)
            }
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Handle all other exceptions
    """
    logger.exception(f"Unexpected error occurred: {str(exc)}")
    logger.error(f"Request path: {request.url.path}")
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Internal server error",
                "type": "InternalServerError",
                "details": str(exc) if os.getenv("ENVIRONMENT") != "production" else "An unexpected error occurred",
                "path": str(request.url.path)
            }
        },
    )


# Middleware for request logging

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Log all incoming requests and their responses
    """
    logger.info(f"Request: {request.method} {request.url.path}")
    logger.debug(f"Request headers: {dict(request.headers)}")
    
    try:
        response = await call_next(request)
        logger.info(f"Response: {request.method} {request.url.path} - Status: {response.status_code}")
        return response
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        raise


# Include routers
app.include_router(
    auth_router, 
    prefix="/api/v1/auth", 
    tags=["Authentication"]
)

# Placeholder for additional routers
# from api.jobs import router as jobs_router
# app.include_router(jobs_router, prefix="/api/v1/jobs", tags=["Jobs"])

# from api.applications import router as applications_router
# app.include_router(applications_router, prefix="/api/v1/applications", tags=["Applications"])

# from api.resumes import router as resumes_router
# app.include_router(resumes_router, prefix="/api/v1/resumes", tags=["Resumes"])

# from api.users import router as users_router
# app.include_router(users_router, prefix="/api/v1/users", tags=["Users"])


# Root endpoint

@app.get("/", tags=["Root"])
async def root() -> Dict[str, Any]:
    """
    Root endpoint with API information
    """
    return {
        "message": "Welcome to Job Auto Apply API",
        "version": "1.0.0",
        "description": "Automated job application system for college students",
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json"
        },
        "status": "running"
    }


# Health check endpoint

@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """
    Health check endpoint with database status
    """
    db_health = await check_database_health()
    
    return {
        "status": "healthy" if db_health["status"] == "healthy" else "degraded",
        "api": "running",
        "database": db_health,
        "version": "1.0.0"
    }


# Readiness probe

@app.get("/ready", tags=["Health"])
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness check endpoint for Kubernetes/container orchestration
    """
    try:
        is_connected = await MongoDB.check_connection()
        
        if not is_connected:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "not_ready",
                    "reason": "Database not connected"
                }
            )
        
        return {
            "status": "ready",
            "database": "connected"
        }
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "reason": str(e)
            }
        )


# Liveness probe

@app.get("/live", tags=["Health"])
async def liveness_check() -> Dict[str, str]:
    """
    Liveness check endpoint for Kubernetes/container orchestration
    """
    return {"status": "alive"}


# API information endpoint

@app.get("/api/v1/info", tags=["Info"])
async def api_info() -> Dict[str, Any]:
    """
    Get API information and available endpoints
    """
    return {
        "api_name": "Job Auto Apply API",
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "endpoints": {
            "auth": "/api/v1/auth",
            "jobs": "/api/v1/jobs",
            "applications": "/api/v1/applications",
            "resumes": "/api/v1/resumes",
            "users": "/api/v1/users"
        },
        "features": [
            "JWT Authentication",
            "OAuth2 Support",
            "Resume Parsing",
            "AI-Powered Matching",
            "Automated Application",
            "Application Tracking"
        ]
    }


if __name__ == "__main__":
    import uvicorn
    
    # Run the application
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENVIRONMENT", "development") == "development",
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        access_log=True
    )
