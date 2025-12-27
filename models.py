from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Organization(Base):
    """Organizations table"""
    __tablename__ = "organizations"
    
    id = Column(String, primary_key=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    subscription_status = Column(String(50), default="active")
    plan_type = Column(String(50), default="starter")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    """Users table"""
    __tablename__ = "users"
    
    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    full_name = Column(String(255))
    password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    organization = relationship("Organization", back_populates="users")


class Document(Base):
    """Documents table"""
    __tablename__ = "documents"
    
    id = Column(String, primary_key=True)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    filename = Column(String(500), nullable=False)
    gcs_object_key = Column(String(500), nullable=False)
    status = Column(String(50), default="processing", index=True)
    expiry_date = Column(DateTime(timezone=True), nullable=True)
    manual_override = Column(Boolean, default=False)
    manual_override_date = Column(DateTime(timezone=True), nullable=True)
    confidence_score = Column(Float, nullable=True)
    needs_review_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationship
    organization = relationship("Organization", back_populates="documents")


class APIKey(Base):
    """API Keys table"""
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_key = Column(String(255), unique=True, nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)