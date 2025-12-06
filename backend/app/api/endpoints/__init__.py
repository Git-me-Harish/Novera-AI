"""
API endpoints module.
"""
from app.api.endpoints import (
    health,
    auth,
    documents,
    chat,
    search,
    admin,
    document_editor
)

__all__ = [
    'health',
    'auth',
    'documents',
    'chat',
    'search',
    'admin',
    'document_editor'
]