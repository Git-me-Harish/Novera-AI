"""
Database models for documents and chunks with pgvector support.
Implements the core data schema for the RAG system.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4
from sqlalchemy import (
    Column, String, Integer, DateTime, ForeignKey, 
    Text, ARRAY, Boolean, Float, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db.session import Base


class Document(Base):
    """
    Stores metadata about uploaded documents.
    Each document can have multiple chunks.
    """
    __tablename__ = "documents"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Document Metadata
    filename = Column(String(255), nullable=False, index=True)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=False, unique=True, index=True)
    
    # Classification
    doc_type = Column(String(50), nullable=False, index=True)  # 'finance', 'hrms', 'policy', etc.
    department = Column(String(100), index=True)
    
    # Content Information
    total_pages = Column(Integer, default=0)
    total_chunks = Column(Integer, default=0)
    has_tables = Column(Boolean, default=False)
    has_images = Column(Boolean, default=False)
    
    # Processing Status
    status = Column(
        String(20), 
        nullable=False, 
        default="pending",
        index=True
    )  # 'pending', 'processing', 'completed', 'failed'
    processing_error = Column(Text, nullable=True)
    
    # Timestamps
    upload_date = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    processed_date = Column(DateTime, nullable=True)
    last_accessed = Column(DateTime, nullable=True)
    
    # Uploader Information
    uploaded_by = Column(UUID(as_uuid=True), nullable=False)  # User ID
    
    # Rich Metadata (JSONB for flexible schema)
    metadata = Column(JSON, nullable=False, default=dict)
    # Example metadata structure:
    # {
    #     "author": "John Doe",
    #     "created_date": "2024-01-15",
    #     "version": "1.2",
    #     "tags": ["payroll", "q4-2024"],
    #     "custom_fields": {...}
    # }
    
    # Relationships
    chunks = relationship(
        "Chunk", 
        back_populates="document", 
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    # Indexes
    __table_args__ = (
        Index('idx_doc_type_dept', 'doc_type', 'department'),
        Index('idx_status_upload', 'status', 'upload_date'),
        Index('idx_metadata_gin', 'metadata', postgresql_using='gin'),
    )
    
    def __repr__(self) -> str:
        return f"<Document(id={self.id}, filename={self.filename}, status={self.status})>"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary for API responses."""
        return {
            "id": str(self.id),
            "filename": self.filename,
            "doc_type": self.doc_type,
            "department": self.department,
            "total_pages": self.total_pages,
            "total_chunks": self.total_chunks,
            "status": self.status,
            "upload_date": self.upload_date.isoformat() if self.upload_date else None,
            "metadata": self.metadata
        }


class Chunk(Base):
    """
    Stores individual text chunks with embeddings for semantic search.
    Each chunk belongs to one document and contains vector embedding.
    """
    __tablename__ = "chunks"
    
    # Primary Key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Foreign Key to Document
    document_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Chunk Information
    chunk_index = Column(Integer, nullable=False)  # Order within document
    content = Column(Text, nullable=False)
    content_length = Column(Integer, nullable=False)  # Character count
    token_count = Column(Integer, nullable=False)
    
    # Chunk Classification
    chunk_type = Column(
        String(50), 
        nullable=False,
        index=True
    )  # 'text', 'table', 'summary', 'header'
    
    # Context Information
    page_numbers = Column(ARRAY(Integer), nullable=False, default=list)
    section_title = Column(String(512), nullable=True)
    preceding_context = Column(Text, nullable=True)  # For better retrieval
    
    # Vector Embedding (pgvector)
    embedding = Column(Vector(1536), nullable=False)  # OpenAI embedding dimension
    
    # Metadata (JSONB for flexibility)
    metadata = Column(JSON, nullable=False, default=dict)
    # Example metadata structure:
    # {
    #     "table_headers": ["Column1", "Column2"],
    #     "financial_entities": ["$1000", "Q4 2024"],
    #     "parent_section": "Benefits Policy",
    #     "confidence_score": 0.95
    # }
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    # Indexes for Performance
    __table_args__ = (
        # Composite index for document queries
        Index('idx_doc_chunk', 'document_id', 'chunk_index'),
        
        # IVFFlat index for vector similarity search
        Index(
            'idx_embedding_cosine',
            'embedding',
            postgresql_using='ivfflat',
            postgresql_with={'lists': 100},
            postgresql_ops={'embedding': 'vector_cosine_ops'}
        ),
        
        # GIN index for metadata queries
        Index('idx_chunk_metadata_gin', 'metadata', postgresql_using='gin'),
        
        # GIN index for full-text search on content
        Index(
            'idx_content_fts',
            'content',
            postgresql_using='gin',
            postgresql_ops={'content': 'gin_trgm_ops'}
        ),
        
        # Index for chunk type filtering
        Index('idx_chunk_type_doc', 'chunk_type', 'document_id'),
    )
    
    def __repr__(self) -> str:
        return f"<Chunk(id={self.id}, doc_id={self.document_id}, type={self.chunk_type}, index={self.chunk_index})>"
    
    def to_dict(self, include_embedding: bool = False) -> Dict[str, Any]:
        """Convert model to dictionary for API responses."""
        result = {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "chunk_index": self.chunk_index,
            "content": self.content,
            "chunk_type": self.chunk_type,
            "page_numbers": self.page_numbers,
            "section_title": self.section_title,
            "token_count": self.token_count,
            "metadata": self.metadata
        }
        
        if include_embedding:
            result["embedding"] = self.embedding
        
        return result


class User(Base):
    """
    User model for authentication and authorization.
    Supports Admin and User roles.
    """
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    
    # Role-based access control
    role = Column(String(20), nullable=False, default="user")  # 'admin' or 'user'
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Metadata
    metadata = Column(JSON, nullable=False, default=dict)
    
    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"
    
    def is_admin(self) -> bool:
        """Check if user has admin privileges."""
        return self.role == "admin"


__all__ = ["Document", "Chunk", "User", "Base"]