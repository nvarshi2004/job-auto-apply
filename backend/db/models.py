from pymongo import MongoClient
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from bson import ObjectId

# MongoDB connection (use environment variables in production)
MONGO_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "job_auto_apply"

client = MongoClient(MONGO_URI)
db = client[DATABASE_NAME]

# Collections
users_collection = db["users"]
jobs_collection = db["jobs"]
applications_collection = db["applications"]

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")

class User(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id")
    username: str
    email: str
    password_hash: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    profile: Optional[dict] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class Job(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id")
    title: str
    company: str
    location: Optional[str] = None
    description: str
    url: str
    source: str  # LinkedIn, Indeed, etc.
    posted_date: Optional[datetime] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    salary: Optional[str] = None
    job_type: Optional[str] = None  # Full-time, Part-time, Contract
    remote: Optional[bool] = False
    skills: Optional[List[str]] = []

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class Application(BaseModel):
    id: Optional[PyObjectId] = Field(alias="_id")
    user_id: PyObjectId
    job_id: PyObjectId
    status: str  # applied, pending, rejected, interview
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    notes: Optional[str] = None
    resume_used: Optional[str] = None
    cover_letter: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

# Helper functions
def get_user_by_username(username: str):
    return users_collection.find_one({"username": username})

def create_user(user_data: dict):
    result = users_collection.insert_one(user_data)
    return result.inserted_id

def get_jobs(filters: dict = None, limit: int = 50):
    if filters is None:
        filters = {}
    return list(jobs_collection.find(filters).limit(limit))

def create_job(job_data: dict):
    result = jobs_collection.insert_one(job_data)
    return result.inserted_id

def create_application(application_data: dict):
    result = applications_collection.insert_one(application_data)
    return result.inserted_id

def get_user_applications(user_id: str):
    return list(applications_collection.find({"user_id": ObjectId(user_id)}))
