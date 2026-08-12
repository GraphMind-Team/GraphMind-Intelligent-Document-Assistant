"""Documents module routes.

Stub for Story 1.1 (running project skeleton). No endpoints are defined yet;
this router is registered in `app.main` so the module's presence is visible
from day one. Real document ingestion/library endpoints arrive later.
"""

from fastapi import APIRouter

router = APIRouter(prefix="/documents", tags=["documents"])
