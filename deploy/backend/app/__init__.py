"""ProReadyEngineer backend application."""

# Import and expose the FastAPI app from main
# This allows 'from app import app' or 'from app.main import app'
try:
    from main import app
except ImportError:
    # Fallback for when main imports app
    app = None
