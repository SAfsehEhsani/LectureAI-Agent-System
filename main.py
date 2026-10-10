import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

# Re-export app from backend.main for root-level deployment entrypoint
try:
    from backend.main import app
except ImportError:
    from main import app
