from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db.models import create_application, get_user_applications, applications_collection
from bson import ObjectId

router = APIRouter()

class ApplicationCreate(BaseModel):
    user_id: str
    job_id: str
    notes: Optional[str] = None
    resume_used: Optional[str] = None
    cover_letter: Optional[str] = None

class ApplicationUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None

class ApplicationResponse(BaseModel):
    id: str
    user_id: str
    job_id: str
    status: str
    applied_at: datetime
    notes: Optional[str] = None
    resume_used: Optional[str] = None
    cover_letter: Optional[str] = None

@router.post("/", status_code=201, response_model=dict)
async def create_application_endpoint(application: ApplicationCreate):
    """
    Submit a new job application
    """
    try:
        application_data = application.dict()
        application_data['status'] = 'applied'
        application_data['applied_at'] = datetime.utcnow()
        application_data['user_id'] = ObjectId(application_data['user_id'])
        application_data['job_id'] = ObjectId(application_data['job_id'])
        
        app_id = create_application(application_data)
        return {
            "message": "Application submitted successfully",
            "application_id": str(app_id)
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating application: {str(e)}"
        )

@router.get("/user/{user_id}", response_model=List[ApplicationResponse])
async def get_user_applications_endpoint(user_id: str):
    """
    Get all applications for a specific user
    """
    try:
        applications = get_user_applications(user_id)
        
        # Convert ObjectId to string for JSON serialization
        for app in applications:
            app['id'] = str(app.pop('_id'))
            app['user_id'] = str(app['user_id'])
            app['job_id'] = str(app['job_id'])
        
        return applications
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching applications: {str(e)}"
        )

@router.get("/{application_id}", response_model=ApplicationResponse)
async def get_application(application_id: str):
    """
    Get a specific application by ID
    """
    try:
        application = applications_collection.find_one({"_id": ObjectId(application_id)})
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        
        application['id'] = str(application.pop('_id'))
        application['user_id'] = str(application['user_id'])
        application['job_id'] = str(application['job_id'])
        return application
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid application ID: {str(e)}"
        )

@router.put("/{application_id}", response_model=dict)
async def update_application(application_id: str, update_data: ApplicationUpdate):
    """
    Update an application status or notes
    """
    try:
        update_dict = {k: v for k, v in update_data.dict().items() if v is not None}
        
        result = applications_collection.update_one(
            {"_id": ObjectId(application_id)},
            {"$set": update_dict}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        
        return {"message": "Application updated successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error updating application: {str(e)}"
        )

@router.delete("/{application_id}")
async def delete_application(application_id: str):
    """
    Delete an application
    """
    try:
        result = applications_collection.delete_one({"_id": ObjectId(application_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Application not found")
        return {"message": "Application deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error deleting application: {str(e)}"
        )
