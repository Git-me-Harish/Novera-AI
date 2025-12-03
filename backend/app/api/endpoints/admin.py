"""
Admin API endpoints for user and system management.
Only accessible by users with admin role.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from loguru import logger

from app.db.session import get_db
from app.models.user import User
from app.models.document import Document
from app.api.dependencies.auth import get_current_admin_user
from app.core.security import get_password_hash, validate_password_strength, validate_email


router = APIRouter()


# Request/Response Models
class CreateUserRequest(BaseModel):
    """Admin creates new user."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: Optional[str] = None
    role: str = Field(default="user", pattern="^(user|admin)$")
    is_active: bool = True


class UpdateUserRequest(BaseModel):
    """Admin updates user."""
    full_name: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(user|admin)$")
    is_active: Optional[bool] = None
    is_verified: Optional[bool] = None


class UserListItem(BaseModel):
    """User in admin list."""
    id: str
    email: str
    username: str
    full_name: Optional[str]
    role: str
    is_active: bool
    is_verified: bool
    created_at: str
    last_login: Optional[str]
    document_count: int = 0


class UserStatsResponse(BaseModel):
    """User statistics."""
    total_users: int
    active_users: int
    admin_users: int
    regular_users: int
    verified_users: int


class SystemStatsResponse(BaseModel):
    """System-wide statistics."""
    total_users: int
    total_documents: int
    total_chunks: int
    active_sessions: int
    storage_used_mb: float


# User Management Endpoints

@router.get("/admin/users", response_model=dict)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    role: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    List all users with filtering and pagination.
    Admin only.
    """
    # Build query
    query = select(User)
    
    if role:
        query = query.where(User.role == role)
    
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (User.email.ilike(search_pattern)) |
            (User.username.ilike(search_pattern)) |
            (User.full_name.ilike(search_pattern))
        )
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get users
    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()
    
    # Get document counts for each user
    user_list = []
    for user in users:
        # Count documents
        doc_count_query = select(func.count()).select_from(Document).where(
            Document.uploaded_by == user.id
        )
        doc_count_result = await db.execute(doc_count_query)
        doc_count = doc_count_result.scalar()
        
        user_list.append(
            UserListItem(
                id=str(user.id),
                email=user.email,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                is_active=user.is_active,
                is_verified=user.is_verified,
                created_at=user.created_at.isoformat(),
                last_login=user.last_login.isoformat() if user.last_login else None,
                document_count=doc_count
            )
        )
    
    return {
        "total": total,
        "users": user_list
    }


@router.get("/admin/users/stats", response_model=UserStatsResponse)
async def get_user_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Get user statistics.
    Admin only.
    """
    # Total users
    total_result = await db.execute(select(func.count()).select_from(User))
    total = total_result.scalar()
    
    # Active users
    active_result = await db.execute(
        select(func.count()).select_from(User).where(User.is_active == True)
    )
    active = active_result.scalar()
    
    # Admin users
    admin_result = await db.execute(
        select(func.count()).select_from(User).where(User.role == "admin")
    )
    admins = admin_result.scalar()
    
    # Verified users
    verified_result = await db.execute(
        select(func.count()).select_from(User).where(User.is_verified == True)
    )
    verified = verified_result.scalar()
    
    return UserStatsResponse(
        total_users=total,
        active_users=active,
        admin_users=admins,
        regular_users=total - admins,
        verified_users=verified
    )


@router.post("/admin/users", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Create a new user.
    Admin only.
    """
    # Validate email
    if not validate_email(request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format"
        )
    
    # Validate password
    is_valid, error_msg = validate_password_strength(request.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    # Check if email exists
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if username exists
    result = await db.execute(select(User).where(User.username == request.username))
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )
    
    # Create user
    new_user = User(
        email=request.email,
        username=request.username,
        hashed_password=get_password_hash(request.password),
        full_name=request.full_name,
        role=request.role,
        is_active=request.is_active,
        is_verified=True,
        user_metadata={"created_by": str(admin.id), "created_by_admin": True}
    )
    
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    
    logger.info(f"Admin {admin.email} created new user: {new_user.email}")
    
    return {
        "message": "User created successfully",
        "user": new_user.to_dict()
    }


@router.get("/admin/users/{user_id}", response_model=dict)
async def get_user_details(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Get detailed information about a specific user.
    Admin only.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Get document stats
    doc_count_query = select(func.count()).select_from(Document).where(
        Document.uploaded_by == user_id
    )
    doc_count_result = await db.execute(doc_count_query)
    doc_count = doc_count_result.scalar()
    
    # Get recent documents
    recent_docs_query = select(Document).where(
        Document.uploaded_by == user_id
    ).order_by(Document.upload_date.desc()).limit(5)
    recent_docs_result = await db.execute(recent_docs_query)
    recent_docs = recent_docs_result.scalars().all()
    
    return {
        "user": user.to_dict(),
        "stats": {
            "total_documents": doc_count,
        },
        "recent_documents": [
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "upload_date": doc.upload_date.isoformat(),
                "status": doc.status
            }
            for doc in recent_docs
        ]
    }


@router.put("/admin/users/{user_id}", response_model=dict)
async def update_user(
    user_id: UUID,
    request: UpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Update user information.
    Admin only.
    """
    # Prevent admin from deactivating themselves
    if user_id == admin.id and request.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )
    
    # Prevent admin from removing their own admin role
    if user_id == admin.id and request.role == "user":
        # Check if there are other admins
        admin_count_result = await db.execute(
            select(func.count()).select_from(User).where(
                User.role == "admin",
                User.is_active == True,
                User.id != admin.id
            )
        )
        other_admins = admin_count_result.scalar()
        
        if other_admins == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove admin role. You are the only active admin."
            )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update fields
    if request.full_name is not None:
        user.full_name = request.full_name
    if request.role is not None:
        user.role = request.role
    if request.is_active is not None:
        user.is_active = request.is_active
    if request.is_verified is not None:
        user.is_verified = request.is_verified
    
    user.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(user)
    
    logger.info(f"Admin {admin.email} updated user {user.email}")
    
    return {
        "message": "User updated successfully",
        "user": user.to_dict()
    }


@router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Delete a user and all their data.
    Admin only.
    """
    # Prevent admin from deleting themselves
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Delete user's documents and chunks (cascade should handle this)
    await db.execute(delete(Document).where(Document.uploaded_by == user_id))
    
    # Delete user
    await db.delete(user)
    await db.commit()
    
    logger.info(f"Admin {admin.email} deleted user {user.email}")
    
    return {
        "message": "User deleted successfully",
        "user_id": str(user_id)
    }


@router.post("/admin/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: UUID,
    new_password: str = Query(..., min_length=8),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Reset a user's password.
    Admin only.
    """
    # Validate password
    is_valid, error_msg = validate_password_strength(new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    # Update password
    user.hashed_password = get_password_hash(new_password)
    user.updated_at = datetime.utcnow()
    
    await db.commit()
    
    logger.info(f"Admin {admin.email} reset password for user {user.email}")
    
    return {
        "message": "Password reset successfully"
    }


# System Management Endpoints

@router.get("/admin/stats", response_model=SystemStatsResponse)
async def get_system_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    Get system-wide statistics.
    Admin only.
    """
    # Total users
    user_count_result = await db.execute(select(func.count()).select_from(User))
    total_users = user_count_result.scalar()
    
    # Total documents
    doc_count_result = await db.execute(select(func.count()).select_from(Document))
    total_docs = doc_count_result.scalar()
    
    # Total chunks
    from app.models.document import Chunk
    chunk_count_result = await db.execute(select(func.count()).select_from(Chunk))
    total_chunks = chunk_count_result.scalar()
    
    # Storage used (sum of file sizes)
    storage_result = await db.execute(
        select(func.sum(Document.file_size_bytes)).select_from(Document)
    )
    storage_bytes = storage_result.scalar() or 0
    storage_mb = storage_bytes / (1024 * 1024)
    
    return SystemStatsResponse(
        total_users=total_users,
        total_documents=total_docs,
        total_chunks=total_chunks,
        active_sessions=0,
        storage_used_mb=round(storage_mb, 2)
    )


@router.get("/admin/documents", response_model=dict)
async def list_all_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    doc_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    user_id: Optional[UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_admin_user)
):
    """
    List all documents across all users.
    Admin only.
    """
    # Build query
    query = select(Document)
    
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    
    if status:
        query = query.where(Document.status == status)
    
    if user_id:
        query = query.where(Document.uploaded_by == user_id)
    
    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar()
    
    # Get documents
    query = query.order_by(Document.upload_date.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    documents = result.scalars().all()
    
    # Get user info for each document
    doc_list = []
    for doc in documents:
        user_result = await db.execute(select(User).where(User.id == doc.uploaded_by))
        user = user_result.scalar_one_or_none()
        
        doc_list.append({
            "id": str(doc.id),
            "filename": doc.filename,
            "doc_type": doc.doc_type,
            "department": doc.department,
            "total_pages": doc.total_pages or 0,
            "total_chunks": doc.total_chunks or 0,
            "status": doc.status,
            "upload_date": doc.upload_date.isoformat(),
            "processed_date": doc.processed_date.isoformat() if doc.processed_date else None,
            "uploaded_by": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username
            } if user else None
        })
    
    return {
        "total": total,
        "documents": doc_list
    }


__all__ = ['router']