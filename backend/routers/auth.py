"""
Authentication Router - Google OAuth and JWT token management
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from authlib.integrations.starlette_client import OAuth
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import os
import hashlib
from math import floor

from database import get_db
from models import User, UserSession
from services.redis_store import is_token_revoked, revoke_token

router = APIRouter()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:4200")

# Google OAuth setup
oauth = OAuth()
oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, expire


def verify_token(token: str):
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Dependency to get current authenticated user"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = auth_header.split(" ")[1]
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    if await is_token_revoked(token_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )
    
    session = db.query(UserSession).filter(
        UserSession.token_hash == token_hash,
        UserSession.is_valid == True
    ).first()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if session.expires_at and session.expires_at <= datetime.utcnow():
        session.is_valid = False
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    
    return user


@router.get("/google/login")
async def google_login(request: Request):
    """Initiate Google OAuth login"""
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/google/callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle Google OAuth callback"""
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get('userinfo')
        
        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")
        
        # Check if user exists
        user = db.query(User).filter(User.google_id == user_info['sub']).first()
        
        if not user:
            # Check by email as fallback
            user = db.query(User).filter(User.email == user_info['email']).first()
            if user:
                # Link Google account to existing user
                user.google_id = user_info['sub']
                user.picture = user_info.get('picture')
            else:
                # Create new user
                user = User(
                    email=user_info['email'],
                    name=user_info.get('name'),
                    picture=user_info.get('picture'),
                    google_id=user_info['sub'],
                    is_active=True
                )
                db.add(user)
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.commit()
        db.refresh(user)
        
        # Create JWT token
        access_token, expires_at = create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )
        
        # Store session
        token_hash = hashlib.sha256(access_token.encode()).hexdigest()
        session = UserSession(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_valid=True
        )
        db.add(session)
        db.commit()
        
        # Redirect to frontend with token
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/callback?token={access_token}"
        )
        
    except Exception as e:
        # Redirect to frontend with error
        return RedirectResponse(
            url=f"{FRONTEND_URL}/auth/callback?error={str(e)}"
        )


from pydantic import BaseModel

class MobileAuthRequest(BaseModel):
    id_token: str


class OnboardingUpdateRequest(BaseModel):
    phone: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None
    trading_experience: Optional[str] = None

@router.post("/google/mobile")
async def google_mobile_auth(request: MobileAuthRequest, db: Session = Depends(get_db)):
    """
    Mobile Google Sign-In endpoint.
    Accepts a Google ID token from the Flutter app, verifies it,
    and returns a JWT access token.
    """
    import httpx
    
    try:
        # Verify the Google ID token
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={request.id_token}"
            )
        
        if resp.status_code != 200:
            raise HTTPException(status_code=401, detail="Invalid Google ID token")
        
        token_info = resp.json()
        
        # Verify the token is for our app
        google_client_id = os.getenv("GOOGLE_CLIENT_ID")
        if token_info.get("aud") != google_client_id:
            raise HTTPException(status_code=401, detail="Token not issued for this app")
        
        email = token_info.get("email")
        google_id = token_info.get("sub")
        name = token_info.get("name", "")
        picture = token_info.get("picture", "")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email not found in token")
        
        # Find or create user
        user = db.query(User).filter(User.google_id == google_id).first()
        
        if not user:
            user = db.query(User).filter(User.email == email).first()
            if user:
                user.google_id = google_id
                user.picture = picture
            else:
                user = User(
                    email=email,
                    name=name,
                    picture=picture,
                    google_id=google_id,
                    is_active=True
                )
                db.add(user)
        
        user.last_login = datetime.utcnow()
        db.commit()
        db.refresh(user)
        
        # Create JWT token
        access_token, expires_at = create_access_token(
            data={"sub": str(user.id), "email": user.email}
        )
        
        # Store session
        token_hash = hashlib.sha256(access_token.encode()).hexdigest()
        session = UserSession(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            is_valid=True
        )
        db.add(session)
        db.commit()
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "picture": user.picture,
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Authentication error: {str(e)}")



@router.get("/me")
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user info"""
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture": current_user.picture,
        "is_admin": current_user.is_admin,
        "phone": current_user.phone,
        "address": current_user.address,
        "occupation": current_user.occupation,
        "trading_experience": current_user.trading_experience,
        "onboarding_completed": current_user.onboarding_completed,
        "onboarding_skipped": current_user.onboarding_skipped
    }


@router.put("/onboarding")
async def update_onboarding(
    payload: OnboardingUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save onboarding/profile information for the current user."""
    if payload.phone is not None:
        current_user.phone = payload.phone.strip() or None
    if payload.address is not None:
        current_user.address = payload.address.strip() or None
    if payload.occupation is not None:
        current_user.occupation = payload.occupation.strip() or None
    if payload.trading_experience is not None:
        current_user.trading_experience = payload.trading_experience.strip() or None

    current_user.onboarding_completed = True
    current_user.onboarding_skipped = False
    db.commit()
    db.refresh(current_user)

    return {
        "message": "Onboarding details saved successfully",
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.name,
            "picture": current_user.picture,
            "is_admin": current_user.is_admin,
            "phone": current_user.phone,
            "address": current_user.address,
            "occupation": current_user.occupation,
            "trading_experience": current_user.trading_experience,
            "onboarding_completed": current_user.onboarding_completed,
            "onboarding_skipped": current_user.onboarding_skipped
        }
    }


@router.post("/onboarding/skip")
async def skip_onboarding(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark onboarding as skipped for now (user can complete later)."""
    current_user.onboarding_skipped = True
    db.commit()
    db.refresh(current_user)
    return {"message": "Onboarding skipped", "onboarding_skipped": True}


@router.post("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Logout and invalidate current session"""
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1]
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    
    # Invalidate session
    session = db.query(UserSession).filter(
        UserSession.token_hash == token_hash,
        UserSession.user_id == current_user.id
    ).first()
    
    if session:
        session.is_valid = False
        db.commit()

    payload = verify_token(token)
    exp = payload.get("exp") if payload else None
    ttl_seconds = 60
    if isinstance(exp, (int, float)):
        ttl_seconds = max(60, floor(float(exp) - datetime.utcnow().timestamp()))

    await revoke_token(token_hash, ttl_seconds)
    
    return {"message": "Logged out successfully"}
