from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
import io
import os
import base64
from cryptography.fernet import Fernet, InvalidToken

# Local imports (assuming similar structure to auth.py)
from ..db import get_db
from ..models import User, UserProfile, UserPreferences, GmailConfig
from ..auth import get_current_user
from ..resume_parser import parse_resume  # should return dict of extracted fields

router = APIRouter(prefix="/api", tags=["user"])

# ---------- Security helpers ----------

FERNET_KEY_ENV = "GMAIL_SECRET_KEY"

def _get_fernet() -> Fernet:
    key = os.getenv(FERNET_KEY_ENV)
    if not key:
        # In production, this must be set as a 32-byte urlsafe base64 key
        # e.g., Fernet.generate_key().decode()
        raise RuntimeError("Server encryption key missing: set GMAIL_SECRET_KEY env var")
    try:
        # Accept both raw and base64-encoded representations
        key_bytes = key.encode()
        # Validate key length by constructing Fernet
        return Fernet(key_bytes)
    except Exception as e:
        raise RuntimeError("Invalid GMAIL_SECRET_KEY configured") from e


def encrypt_secret(plaintext: str) -> str:
    f = _get_fernet()
    token = f.encrypt(plaintext.encode())
    return token.decode()


def decrypt_secret(token: str) -> str:
    f = _get_fernet()
    try:
        value = f.decrypt(token.encode()).decode()
        return value
    except InvalidToken:
        raise HTTPException(status_code=400, detail="Stored credential cannot be decrypted")

# ---------- Schemas ----------

class ProfileIn(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    headline: Optional[str] = None
    summary: Optional[str] = None
    links: Optional[Dict[str, str]] = None

class ProfileOut(ProfileIn):
    email: EmailStr

class PreferencesIn(BaseModel):
    job_titles: Optional[List[str]] = Field(default=None, description="Preferred job titles")
    locations: Optional[List[str]] = None
    remote_only: Optional[bool] = None
    min_salary: Optional[int] = None
    tech_stack: Optional[List[str]] = None
    keywords_include: Optional[List[str]] = None
    keywords_exclude: Optional[List[str]] = None

class ResumeParseOut(BaseModel):
    parsed: Dict[str, Any]

class GmailConfigIn(BaseModel):
    email: EmailStr
    app_password: str  # will be encrypted server-side

class GmailConfigOut(BaseModel):
    email: EmailStr
    has_password: bool

# ---------- Helpers ----------

def _get_or_create_profile(db: Session, user_id: int) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _get_or_create_preferences(db: Session, user_id: int) -> UserPreferences:
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    if not prefs:
        prefs = UserPreferences(user_id=user_id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs

# ---------- Routes ----------

@router.get("/profile", response_model=ProfileOut)
def get_profile(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    profile = _get_or_create_profile(db, current_user.id)
    return ProfileOut(
        email=current_user.email,
        full_name=profile.full_name,
        phone=profile.phone,
        location=profile.location,
        headline=profile.headline,
        summary=profile.summary,
        links=profile.links or {},
    )


@router.put("/profile", response_model=ProfileOut)
def update_profile(payload: ProfileIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    profile = _get_or_create_profile(db, current_user.id)

    # Update only provided fields
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(profile, field, value)

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return ProfileOut(
        email=current_user.email,
        full_name=profile.full_name,
        phone=profile.phone,
        location=profile.location,
        headline=profile.headline,
        summary=profile.summary,
        links=profile.links or {},
    )


@router.post("/resume", response_model=ResumeParseOut)
async def upload_resume(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Basic validation
    allowed = {"application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/msword", "text/plain"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported resume format")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    # Parse resume using service
    try:
        parsed = parse_resume(io.BytesIO(content), filename=file.filename, content_type=file.content_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {str(e)}")

    # Optionally, persist some extracted fields to profile if empty
    profile = _get_or_create_profile(db, current_user.id)
    updates = {}
    if not profile.full_name and parsed.get("name"):
        updates["full_name"] = parsed["name"]
    if not profile.phone and parsed.get("phone"):
        updates["phone"] = parsed["phone"]
    if not profile.location and parsed.get("location"):
        updates["location"] = parsed["location"]
    if not profile.summary and parsed.get("summary"):
        updates["summary"] = parsed["summary"]

    if updates:
        for k, v in updates.items():
            setattr(profile, k, v)
        db.add(profile)
        db.commit()

    return ResumeParseOut(parsed=parsed)


@router.put("/preferences", response_model=PreferencesIn)
def update_preferences(payload: PreferencesIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    prefs = _get_or_create_preferences(db, current_user.id)

    for field, value in payload.dict(exclude_unset=True).items():
        setattr(prefs, field, value)

    db.add(prefs)
    db.commit()
    db.refresh(prefs)

    return PreferencesIn(**{
        "job_titles": prefs.job_titles or [],
        "locations": prefs.locations or [],
        "remote_only": prefs.remote_only,
        "min_salary": prefs.min_salary,
        "tech_stack": prefs.tech_stack or [],
        "keywords_include": prefs.keywords_include or [],
        "keywords_exclude": prefs.keywords_exclude or [],
    })


@router.post("/gmail-config", response_model=GmailConfigOut)
def set_gmail_config(payload: GmailConfigIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not payload.app_password:
        raise HTTPException(status_code=400, detail="App password is required")

    enc = encrypt_secret(payload.app_password)

    config = db.query(GmailConfig).filter(GmailConfig.user_id == current_user.id).first()
    if not config:
        config = GmailConfig(user_id=current_user.id, email=payload.email, enc_app_password=enc)
    else:
        config.email = payload.email
        config.enc_app_password = enc

    db.add(config)
    db.commit()
    db.refresh(config)

    return GmailConfigOut(email=config.email, has_password=bool(config.enc_app_password))


@router.get("/gmail-config", response_model=GmailConfigOut)
def get_gmail_config(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    config = db.query(GmailConfig).filter(GmailConfig.user_id == current_user.id).first()
    if not config:
        return GmailConfigOut(email=current_user.email, has_password=False)
    return GmailConfigOut(email=config.email, has_password=bool(config.enc_app_password))
