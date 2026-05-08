"""
FastAPI Application

Main web server for language tutor.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import os
import traceback

# Import routes
from language_tutor.routes import session, conversation

app = FastAPI(
    title="Language Tutor",
    description="AI-powered language learning with voice interaction",
    version="0.1.0",
)


# CORS origins: localhost variants by default; extend via CORS_ORIGINS env var.
# Example: export CORS_ORIGINS="https://myserver.local:8080,http://192.168.1.10:8080"
_DEFAULT_ORIGINS = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:3000",   # common dev port
]
_env_origins = os.getenv("CORS_ORIGINS", "")
ALLOWED_ORIGINS = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins
    else _DEFAULT_ORIGINS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# Mount static files
static_dir = Path(__file__).parent / "templates" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Basic health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "language-tutor",
        "version": "0.1.0"
    }

# Serve main UI
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve main application UI."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        return template_path.read_text()
    return "<h1>Template not found</h1>"


@app.get("/memory", response_class=HTMLResponse)
async def memory_viewer():
    """Serve the Engram memory viewer page."""
    template_path = Path(__file__).parent / "templates" / "memory.html"
    if template_path.exists():
        return template_path.read_text()
    return "<h1>Memory viewer template not found</h1>"

# Mount API routes
app.include_router(session.router, prefix="/api/session", tags=["session"])
app.include_router(conversation.router, prefix="/api/conversation", tags=["conversation"])


if __name__ == "__main__":
    import uvicorn
    
    print("Starting Language Tutor...")
    print("Open browser to: http://localhost:8080")
    
    uvicorn.run(
        "language_tutor.app:app",
        host="0.0.0.0",
        port=8080,
        log_level="info",
    )

# Show tracebacks only when explicitly running in a debug/development mode.
DEBUG_EXCEPTIONS = os.getenv("LANGUAGE_TUTOR_DEBUG_EXCEPTIONS", "0") == "1"


@app.exception_handler(Exception)
async def debug_exception_handler(request: Request, exc: Exception):
    from fastapi.responses import JSONResponse

    content = {"error": str(exc)}
    if DEBUG_EXCEPTIONS:
        content["traceback"] = traceback.format_exc()

    return JSONResponse(status_code=500, content=content)
