"""
Database models for NSE Platform
"""

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    """User model for authentication"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=True)
    picture = Column(Text, nullable=True)  # Google profile picture URL
    google_id = Column(String(255), unique=True, nullable=True)
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<User {self.email}>"


class UserSession(Base):
    """Session tracking for users"""
    __tablename__ = "user_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    token_hash = Column(String(255), unique=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_valid = Column(Boolean, default=True)

    def __repr__(self):
        return f"<UserSession user_id={self.user_id}>"


class Strategy(Base):
    """Options/Futures Strategy model"""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    name = Column(String(255), nullable=False)
    symbol = Column(String(50), nullable=False)
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    positions = relationship("Position", back_populates="strategy", cascade="all, delete-orphan")
    user = relationship("User")

    def __repr__(self):
        return f"<Strategy {self.name} ({self.symbol})>"


class Position(Base):
    """Individual leg of a strategy"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, index=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), index=True, nullable=False)
    
    segment = Column(String(20), nullable=False)  # OPTSTK, OPTIDX, FUTSTK, FUTIDX
    expiry = Column(String(20), nullable=False)   # DD-Mon-YYYY
    strike = Column(Float, nullable=True)         # Null for Futures
    option_type = Column(String(10), nullable=True) # CE, PE, or None for Futures
    action = Column(String(10), nullable=False)   # BUY, SELL
    qty = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    strategy = relationship("Strategy", back_populates="positions")

    def __repr__(self):
        return f"<Position {self.action} {self.qty}x {self.strike or ''}{self.option_type or ''} {self.expiry}>"
