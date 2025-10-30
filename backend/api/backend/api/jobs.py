from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func
from datetime import datetime, timedelta

# Local imports
from ..db import get_db
from ..models import User, UserPreferences, Job, JobSource, JobApplication
from ..auth import get_current_user

router = APIRouter(prefix="/api/jobs", tags=["jobs"])  # separate sub-router under /api

# --------- Schemas ---------
class JobCreate(BaseModel):
    title: str
    company: str
    location: Optional[str] = None
    remote: Optional[bool] = None
    description: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = Field(default="manual", description="source name e.g., linkedin, indeed")
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    tags: Optional[List[str]] = None
    posted_at: Optional[datetime] = None

class JobOut(BaseModel):
    id: int
    title: str
    company: str
    location: Optional[str]
    remote: Optional[bool]
    url: Optional[str]
    source: Optional[str]
    score: Optional[float] = Field(default=None, description="relevance score 0-100")
    posted_at: Optional[datetime]
    salary_min: Optional[int]
    salary_max: Optional[int]
    tags: List[str] = []

    class Config:
        orm_mode = True

class SearchResponse(BaseModel):
    total: int
    items: List[JobOut]

class MatchPreview(BaseModel):
    preferences: Dict[str, Any]
    items: List[JobOut]

# --------- Utility: text processing and scoring ---------
STOPWORDS = {
    "a","an","the","and","or","to","of","in","on","for","with","by","at","as","is","are","be","this","that","it","from"
}

def tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [t for t in ("".join([c.lower() if c.isalnum() or c.isspace() else " " for c in text]).split()) if t and t not in STOPWORDS]

def jaccard(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    inter = len(sa & sb)
    union = len(sa | sb)
    return inter / union if union else 0.0

DEFAULT_DECAY_DAYS = 30

def time_decay(posted_at: Optional[datetime], half_life_days: int = DEFAULT_DECAY_DAYS) -> float:
    if not posted_at:
        return 1.0
    dt = datetime.utcnow() - posted_at
    if dt.total_seconds() <= 0:
        return 1.0
    # exponential half-life decay
    half_life = timedelta(days=half_life_days)
    decay = 0.5 ** (dt.total_seconds() / half_life.total_seconds())
    return max(0.1, float(decay))

def compute_relevance(job: Job, prefs: Optional[UserPreferences]) -> float:
    # Aggregate tokens from job
    title_tokens = tokenize(job.title or "")
    desc_tokens = tokenize(job.description or "")
    tags_tokens = tokenize(" ".join(job.tags or [])) if hasattr(job, "tags") and job.tags else []

    job_tokens = title_tokens + desc_tokens + tags_tokens

    # Preferences
    if not prefs:
        base = 0.35  # some baseline even without prefs
        return round(100 * min(1.0, base * time_decay(getattr(job, "posted_at", None))), 2)

    include_kw = set([t.lower() for t in (prefs.keywords_include or [])])
    exclude_kw = set([t.lower() for t in (prefs.keywords_exclude or [])])
    tech = set([t.lower() for t in (prefs.tech_stack or [])])
    titles = set([t.lower() for t in (prefs.job_titles or [])])
    locs = set([t.lower() for t in (prefs.locations or [])])

    # Components
    title_match = jaccard(title_tokens, list(titles))
    tech_match = jaccard(job_tokens, list(tech))
    include_match = jaccard(job_tokens, list(include_kw))
    exclude_penalty = 1.0 if not exclude_kw else (1.0 - min(0.9, jaccard(job_tokens, list(exclude_kw))))

    # Remote/location preference
    loc_bonus = 0.0
    if prefs.remote_only is True:
        if getattr(job, "remote", False):
            loc_bonus += 0.1
        else:
            loc_bonus -= 0.2
    if locs:
        job_loc = (job.location or "").lower()
        if any(l in job_loc for l in locs):
            loc_bonus += 0.1

    # Salary preference
    salary_bonus = 0.0
    if prefs.min_salary and getattr(job, "salary_max", None):
        if job.salary_max and job.salary_max >= prefs.min_salary:
            salary_bonus += 0.1
        else:
            salary_bonus -= 0.15

    recency = time_decay(getattr(job, "posted_at", None))  # 0.1 - 1.0

    # Weighted sum before decay and penalties
    score = (
        0.45 * title_match +
        0.25 * tech_match +
        0.20 * include_match +
        0.10 * (1.0 + loc_bonus + salary_bonus)
    )
    score = max(0.0, min(1.5, score))  # clamp pre-decay
    score *= exclude_penalty
    score *= recency

    return round(100 * max(0.0, min(1.0, score)), 2)

# --------- Query helpers ---------

def base_job_query(db: Session):
    return db.query(Job)


def apply_filters(q, title: Optional[str], company: Optional[str], locations: Optional[List[str]], remote: Optional[bool], min_salary: Optional[int], posted_within_days: Optional[int], tags: Optional[List[str]]):
    if title:
        q = q.filter(func.lower(Job.title).like(f"%{title.lower()}%"))
    if company:
        q = q.filter(func.lower(Job.company).like(f"%{company.lower()}%"))
    if locations:
        predicates = [func.lower(Job.location).like(f"%{l.lower()}%") for l in locations]
        q = q.filter(or_(*predicates))
    if remote is not None:
        q = q.filter(Job.remote == remote)
    if min_salary is not None:
        q = q.filter(or_(Job.salary_max >= min_salary, Job.salary_min >= min_salary))
    if posted_within_days is not None and posted_within_days > 0:
        cutoff = datetime.utcnow() - timedelta(days=posted_within_days)
        q = q.filter(or_(Job.posted_at == None, Job.posted_at >= cutoff))
    if tags:
        # assuming tags stored as comma-separated string or JSON list in model, we use LIKE fallback
        for t in tags:
            q = q.filter(func.lower(Job.tags_text).like(f"%{t.lower()}%")) if hasattr(Job, "tags_text") else q
    return q

# --------- Endpoints ---------

@router.get("/", response_model=SearchResponse)
def list_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    title: Optional[str] = None,
    company: Optional[str] = None,
    locations: Optional[List[str]] = Query(default=None),
    remote: Optional[bool] = None,
    min_salary: Optional[int] = None,
    posted_within_days: Optional[int] = Query(default=None, ge=1, le=365),
    tags: Optional[List[str]] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = apply_filters(base_job_query(db), title, company, locations, remote, min_salary, posted_within_days, tags)
    total = q.count()

    # Load preferences for scoring
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()

    q = q.order_by(Job.posted_at.desc().nullslast())
    items = q.offset((page - 1) * per_page).limit(per_page).all()

    result: List[JobOut] = []
    for job in items:
        score = compute_relevance(job, prefs)
        result.append(JobOut(
            id=job.id,
            title=job.title,
            company=job.company,
            location=job.location,
            remote=job.remote,
            url=job.url,
            source=getattr(job, "source", None),
            posted_at=getattr(job, "posted_at", None),
            salary_min=getattr(job, "salary_min", None),
            salary_max=getattr(job, "salary_max", None),
            tags=getattr(job, "tags", []) if hasattr(job, "tags") and job.tags else [],
            score=score,
        ))

    return SearchResponse(total=total, items=result)


@router.get("/match", response_model=MatchPreview)
def match_jobs(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()

    q = base_job_query(db)
    # quick coarse filtering by titles/keywords to reduce row count
    if prefs:
        predicates = []
        if prefs.job_titles:
            for t in prefs.job_titles:
                predicates.append(func.lower(Job.title).like(f"%{t.lower()}%"))
        if prefs.keywords_include:
            for k in prefs.keywords_include:
                predicates.append(func.lower(Job.description).like(f"%{k.lower()}%"))
        if predicates:
            q = q.filter(or_(*predicates))
        if prefs.remote_only is True:
            q = q.filter(Job.remote == True)
        if prefs.locations:
            loc_preds = [func.lower(Job.location).like(f"%{l.lower()}%") for l in prefs.locations]
            q = q.filter(or_(*loc_preds))
        if prefs.min_salary:
            q = q.filter(or_(Job.salary_max >= prefs.min_salary, Job.salary_min >= prefs.min_salary))

    items = q.order_by(Job.posted_at.desc().nullslast()).offset((page - 1) * per_page).limit(per_page).all()

    # score and sort in memory by score desc
    scored: List[JobOut] = []
    for job in items:
        scored.append(JobOut(
            id=job.id,
            title=job.title,
            company=job.company,
            location=job.location,
            remote=job.remote,
            url=job.url,
            source=getattr(job, "source", None),
            posted_at=getattr(job, "posted_at", None),
            salary_min=getattr(job, "salary_min", None),
            salary_max=getattr(job, "salary_max", None),
            tags=getattr(job, "tags", []) if hasattr(job, "tags") and job.tags else [],
            score=compute_relevance(job, prefs),
        ))

    scored.sort(key=lambda x: (x.score or 0.0), reverse=True)

    return MatchPreview(
        preferences={
            "job_titles": prefs.job_titles if prefs else [],
            "locations": prefs.locations if prefs else [],
            "remote_only": prefs.remote_only if prefs else None,
            "min_salary": prefs.min_salary if prefs else None,
            "tech_stack": prefs.tech_stack if prefs else [],
            "keywords_include": prefs.keywords_include if prefs else [],
            "keywords_exclude": prefs.keywords_exclude if prefs else [],
        },
        items=scored,
    )


@router.post("/", response_model=JobOut, status_code=201)
def create_job(payload: JobCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    # Optional: deduplicate by URL or (company,title,location)
    existing = None
    if payload.url:
        existing = db.query(Job).filter(func.lower(Job.url) == payload.url.lower()).first()
    if not existing:
        existing = db.query(Job).filter(
            func.lower(Job.company) == payload.company.lower(),
            func.lower(Job.title) == payload.title.lower(),
            (func.lower(Job.location) == (payload.location or "").lower())
        ).first()

    if existing:
        # Update existing lightly
        existing.description = payload.description or existing.description
        existing.salary_min = payload.salary_min if payload.salary_min is not None else existing.salary_min
        existing.salary_max = payload.salary_max if payload.salary_max is not None else existing.salary_max
        existing.remote = payload.remote if payload.remote is not None else existing.remote
        existing.source = payload.source or existing.source
        existing.posted_at = payload.posted_at or existing.posted_at
        # naive tags merge
        if payload.tags:
            cur = set(getattr(existing, "tags", []) or [])
            cur.update(payload.tags)
            if hasattr(existing, "tags"):
                existing.tags = list(cur)
            if hasattr(existing, "tags_text"):
                existing.tags_text = ",".join(sorted(cur))
        db.add(existing)
        db.commit()
        db.refresh(existing)
        job = existing
    else:
        job = Job(
            title=payload.title,
            company=payload.company,
            location=payload.location,
            remote=payload.remote,
            description=payload.description,
            url=payload.url,
            source=payload.source,
            salary_min=payload.salary_min,
            salary_max=payload.salary_max,
            posted_at=payload.posted_at or datetime.utcnow(),
        )
        if hasattr(Job, "tags") and payload.tags:
            job.tags = payload.tags
        if hasattr(Job, "tags_text") and payload.tags:
            job.tags_text = ",".join(sorted(payload.tags))

        db.add(job)
        db.commit()
        db.refresh(job)

    # score against current user's prefs
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == current_user.id).first()
    return JobOut(
        id=job.id,
        title=job.title,
        company=job.company,
        location=job.location,
        remote=job.remote,
        url=job.url,
        source=getattr(job, "source", None),
        posted_at=getattr(job, "posted_at", None),
        salary_min=getattr(job, "salary_min", None),
        salary_max=getattr(job, "salary_max", None),
        tags=getattr(job, "tags", []) if hasattr(job, "tags") and job.tags else [],
        score=compute_relevance(job, prefs),
    )


# Mount this router under the main /api router in backend/app/main.py
# Example:
# from .api import jobs as jobs_router
# app.include_router(jobs_router.router)
