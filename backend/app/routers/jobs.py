from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db.models import get_jobs, create_job, jobs_collection
from bson import ObjectId

router = APIRouter()

class JobResponse(BaseModel):
    id: str
    title: str
    company: str
    location: Optional[str] = None
    description: str
    url: str
    source: str
    posted_date: Optional[datetime] = None
    scraped_at: datetime
    salary: Optional[str] = None
    job_type: Optional[str] = None
    remote: Optional[bool] = False
    skills: Optional[List[str]] = []

@router.get("/", response_model=List[JobResponse])
async def list_jobs(
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    source: Optional[str] = None,
    remote: Optional[bool] = None,
    keyword: Optional[str] = None
):
    """
    List all jobs with optional filters
    """
    filters = {}
    
    if source:
        filters['source'] = source
    
    if remote is not None:
        filters['remote'] = remote
    
    if keyword:
        filters['$or'] = [
            {'title': {'$regex': keyword, '$options': 'i'}},
            {'description': {'$regex': keyword, '$options': 'i'}},
            {'company': {'$regex': keyword, '$options': 'i'}}
        ]
    
    jobs = list(jobs_collection.find(filters).skip(skip).limit(limit))
    
    # Convert ObjectId to string for JSON serialization
    for job in jobs:
        job['id'] = str(job.pop('_id'))
    
    return jobs

@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    """
    Get a specific job by ID
    """
    try:
        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        
        job['id'] = str(job.pop('_id'))
        return job
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid job ID: {str(e)}")

@router.post("/", status_code=201)
async def create_job_endpoint(job_data: dict):
    """
    Create a new job listing (admin/scraper use)
    """
    try:
        job_id = create_job(job_data)
        return {"message": "Job created successfully", "job_id": str(job_id)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating job: {str(e)}")

@router.delete("/{job_id}")
async def delete_job(job_id: str):
    """
    Delete a job listing
    """
    try:
        result = jobs_collection.delete_one({"_id": ObjectId(job_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"message": "Job deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error deleting job: {str(e)}")
