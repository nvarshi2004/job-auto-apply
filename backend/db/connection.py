"""MongoDB Connection Module with Motor (Async Driver)

Provides async MongoDB connection using Motor with connection pooling,
error handling, and helper functions for database operations.
"""

import os
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import logging
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MongoDB:
    """MongoDB connection manager with connection pooling"""
    
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[AsyncIOMotorDatabase] = None
    
    @classmethod
    async def connect_to_database(cls, path: str = None) -> None:
        """
        Establish connection to MongoDB with connection pooling
        
        Args:
            path: MongoDB connection string (defaults to MONGODB_URL env var)
        """
        try:
            mongodb_url = path or os.getenv(
                "MONGODB_URL", 
                "mongodb://localhost:27017"
            )
            database_name = os.getenv("DATABASE_NAME", "job_auto_apply")
            
            logger.info(f"Connecting to MongoDB at {mongodb_url}")
            
            # Create client with connection pooling settings
            cls.client = AsyncIOMotorClient(
                mongodb_url,
                maxPoolSize=50,  # Maximum connections in pool
                minPoolSize=10,  # Minimum connections in pool
                maxIdleTimeMS=45000,  # Close connections idle for 45s
                serverSelectionTimeoutMS=5000,  # 5s timeout for server selection
                connectTimeoutMS=10000,  # 10s connection timeout
                socketTimeoutMS=20000,  # 20s socket timeout
                retryWrites=True,  # Retry write operations
                retryReads=True,  # Retry read operations
            )
            
            # Get database reference
            cls.db = cls.client[database_name]
            
            # Verify connection
            await cls.client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            
        except ConnectionFailure as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
        except ServerSelectionTimeoutError as e:
            logger.error(f"MongoDB server selection timeout: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error connecting to MongoDB: {e}")
            raise
    
    @classmethod
    async def close_database_connection(cls) -> None:
        """Close MongoDB connection and clean up resources"""
        try:
            if cls.client:
                logger.info("Closing MongoDB connection")
                cls.client.close()
                cls.client = None
                cls.db = None
                logger.info("MongoDB connection closed successfully")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")
            raise
    
    @classmethod
    async def get_database(cls) -> AsyncIOMotorDatabase:
        """
        Get database instance
        
        Returns:
            AsyncIOMotorDatabase instance
            
        Raises:
            RuntimeError: If database is not connected
        """
        if cls.db is None:
            raise RuntimeError(
                "Database not connected. Call connect_to_database() first."
            )
        return cls.db
    
    @classmethod
    async def check_connection(cls) -> bool:
        """
        Check if database connection is alive
        
        Returns:
            bool: True if connected, False otherwise
        """
        try:
            if cls.client:
                await cls.client.admin.command('ping')
                return True
            return False
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False


# Helper functions for database operations

async def get_database() -> AsyncIOMotorDatabase:
    """
    Dependency function to get database instance
    
    Returns:
        AsyncIOMotorDatabase instance
    """
    return await MongoDB.get_database()


@asynccontextmanager
async def get_collection(collection_name: str):
    """
    Context manager for collection operations
    
    Args:
        collection_name: Name of the collection
        
    Yields:
        AsyncIOMotorCollection instance
        
    Example:
        async with get_collection("users") as collection:
            await collection.find_one({"email": "test@example.com"})
    """
    try:
        db = await MongoDB.get_database()
        collection = db[collection_name]
        yield collection
    except Exception as e:
        logger.error(f"Error accessing collection {collection_name}: {e}")
        raise
    finally:
        # Cleanup if needed
        pass


async def create_indexes() -> None:
    """
    Create indexes for all collections
    Should be called during application startup
    """
    try:
        db = await MongoDB.get_database()
        
        # Users collection indexes
        await db.users.create_index("email", unique=True)
        await db.users.create_index("username", unique=True)
        await db.users.create_index("created_at")
        
        # Jobs collection indexes
        await db.jobs.create_index("user_id")
        await db.jobs.create_index("status")
        await db.jobs.create_index("created_at")
        await db.jobs.create_index([("title", "text"), ("description", "text")])
        
        # Applications collection indexes
        await db.applications.create_index("user_id")
        await db.applications.create_index("job_id")
        await db.applications.create_index("status")
        await db.applications.create_index("applied_at")
        await db.applications.create_index(
            [("user_id", 1), ("job_id", 1)], 
            unique=True
        )
        
        # Resumes collection indexes
        await db.resumes.create_index("user_id")
        await db.resumes.create_index("is_default")
        await db.resumes.create_index("created_at")
        
        logger.info("Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        raise


# Health check function
async def check_database_health() -> dict:
    """
    Check database health and return status information
    
    Returns:
        dict: Database health information
    """
    try:
        is_connected = await MongoDB.check_connection()
        
        if not is_connected:
            return {
                "status": "unhealthy",
                "database": "disconnected",
                "message": "Database connection is not available"
            }
        
        db = await MongoDB.get_database()
        
        # Get server info
        server_info = await db.client.server_info()
        
        # Get database stats
        stats = await db.command("dbStats")
        
        return {
            "status": "healthy",
            "database": "connected",
            "version": server_info.get("version"),
            "collections": stats.get("collections"),
            "data_size": stats.get("dataSize"),
            "storage_size": stats.get("storageSize"),
            "indexes": stats.get("indexes")
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "database": "error",
            "message": str(e)
        }
