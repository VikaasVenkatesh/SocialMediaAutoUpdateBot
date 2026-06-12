"""
Vercel serverless entry point for the dashboard.

Vercel's @vercel/python runtime serves the module-level `app` (a WSGI app).
On Vercel there is no local SQLite DB, so the snapshot layer falls back to the
committed data/snapshot.json. Re-export + push to update what's shown.
"""

import os
import sys

# Make the repo root importable (config.py, dashboard.py, snapshot.py live there).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dashboard import app  # noqa: E402  (WSGI app served by Vercel)
