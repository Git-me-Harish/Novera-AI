"""
Authentication endpoints (placeholder for Phase 1).
Will implement JWT-based authentication in next phase.
"""
from fastapi import APIRouter

router = APIRouter()

@router.post("/auth/login")
async def login():
    """Login endpoint - to be implemented."""
    return {"message": "Authentication endpoint - coming soon"}

@router.post("/auth/register")
async def register():
    """Registration endpoint - to be implemented."""
    return {"message": "Registration endpoint - coming soon"}