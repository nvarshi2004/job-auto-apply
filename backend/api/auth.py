"""Authentication API with OAuth2, JWT, and bcrypt

Provides user registration, login, token issuance/refresh, current user retrieval, and logout endpoints.
Includes robust error handling and security best practices.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from jose import JWTError, jwt
from passlib.context import CryptContext
from motor.motor_asyncio import AsyncIOMotorCollection

from db.connection import get_collection

logger = logging.getLogger(__name__)

router = APIRouter()

# Security configuration
SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-key-change-in-prod")
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))
REFRESH_TOKEN_EXPIRE_MINUTES = int(os.getenv("REFRESH_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


# Pydantic models
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenWithRefresh(Token):
    refresh_token: str
    refresh_expires_in: int


class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128)


class UserPublic(UserBase):
    id: str
    created_at: datetime


class UserInDB(UserBase):
    id: Optional[str]
    hashed_password: str
    created_at: datetime


# Utility functions

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_users_collection() -> AsyncIOMotorCollection:
    async with get_collection("users") as collection:
        return collection


async def get_user_by_email(email: str) -> Optional[UserInDB]:
    users = await get_users_collection()
    user = await users.find_one({"email": email})
    if not user:
        return None
    return UserInDB(
        id=str(user.get("_id")),
        email=user["email"],
        username=user["username"],
        hashed_password=user["hashed_password"],
        created_at=user.get("created_at", datetime.now(timezone.utc)),
    )


async def get_user_by_username(username: str) -> Optional[UserInDB]:
    users = await get_users_collection()
    user = await users.find_one({"username": username})
    if not user:
        return None
    return UserInDB(
        id=str(user.get("_id")),
        email=user["email"],
        username=user["username"],
        hashed_password=user["hashed_password"],
        created_at=user.get("created_at", datetime.now(timezone.utc)),
    )


async def authenticate_user(username: str, password: str) -> Optional[UserInDB]:
    user = await get_user_by_username(username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)]) -> UserPublic:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = await get_user_by_username(username)
    if user is None:
        raise credentials_exception
    return UserPublic(id=user.id, email=user.email, username=user.username, created_at=user.created_at)


# Routes

@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate):
    users = await get_users_collection()
    
    # Check for existing user
    if await users.find_one({"$or": [{"email": user.email}, {"username": user.username}]}):
        raise HTTPException(status_code=400, detail="Email or username already registered")
    
    hashed_password = get_password_hash(user.password)
    doc = {
        "email": user.email,
        "username": user.username,
        "hashed_password": hashed_password,
        "created_at": datetime.now(timezone.utc)
    }
    result = await users.insert_one(doc)
    
    return UserPublic(
        id=str(result.inserted_id),
        email=user.email,
        username=user.username,
        created_at=doc["created_at"]
    )


@router.post("/login", response_model=TokenWithRefresh)
async def login(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    refresh_token_expires = timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    refresh_token = create_refresh_token(
        data={"sub": user.username}, expires_delta=refresh_token_expires
    )
    
    return TokenWithRefresh(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=int(access_token_expires.total_seconds()),
        refresh_expires_in=int(refresh_token_expires.total_seconds()),
    )


class RefreshTokenRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=Token)
async def refresh_token(payload: RefreshTokenRequest):
    try:
        decoded = jwt.decode(payload.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        if decoded.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        username: str = decoded.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=int(access_token_expires.total_seconds()),
    )


@router.get("/me", response_model=UserPublic)
async def read_users_me(current_user: Annotated[UserPublic, Depends(get_current_user)]):
    return current_user


@router.post("/logout")
async def logout():
    # For stateless JWT, logout is handled on the client side by discarding the token
    return {"message": "Logged out successfully"}
