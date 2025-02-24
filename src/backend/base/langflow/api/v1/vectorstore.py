from __future__ import annotations
#### Milvus ####
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pymilvus import connections
import os
from typing import TYPE_CHECKING
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections
from sqlalchemy.ext.asyncio import create_async_engine
from dotenv import load_dotenv
from redis import asyncio as aioredis
from langflow.tasks import process_file_task

redis = aioredis.from_url("redis://localhost:6379")

if TYPE_CHECKING:
    from langflow.services.settings.service import SettingsService

router = APIRouter(tags=["Vector Store"])

async_engine = create_async_engine(
    "sqlite+aiosqlite:///database.db",
    echo=False,
    future=True
)

load_dotenv()

MILVUS_HOST = os.getenv('MILVUS_HOST')
MILVUS_PORT = os.getenv('MILVUS_PORT')
MILVUS_USER = os.getenv('MILVUS_USER')
MILVUS_PASSWORD = os.getenv('MILVUS_PASSWORD')

OLLAMA_API_URL = os.getenv('OLLAMA_API_URL')
MILVUS_HOST = os.getenv('MILVUS_HOST')
MILVUS_PORT = os.getenv('MILVUS_PORT')
MILVUS_USER = os.getenv('MILVUS_USER')
MILVUS_PASSWORD = os.getenv('MILVUS_PASSWORD')
MILVUS_DATABASE = os.getenv('MILVUS_DATABASE')

# Request and response schemas
class FileInsertRequest(BaseModel):
    id: str
    name: str
    type: str  # e.g. "application/pdf" or "text/plain"
    size: int
    category: str
    content: str  # Base64-encoded file content
    collection_name: str
    batch_size: int = Field(default=50, gt=0, description="Number of chunks per batch")
    chunk_size: int = Field(default=1000, gt=0, description="Size of each text chunk")
    chunk_overlap: int = Field(default=200, gt=0, description="Overlap between chunks")

class ProcessingStatus(BaseModel):
    task_id: str
    status: str
    processed_chunks: int = 0
    total_chunks: int = 0
    error: str = None

connections.connect(alias="default", host="localhost", port=19530)
@router.post("/milvus/insert_file", status_code=status.HTTP_202_ACCEPTED)
async def insert_file(file: FileInsertRequest):
    """
    Receives a Base64-encoded file and enqueues a Celery task to process it.
    """
    try:
        # Enqueue the file processing task
        celery_task = process_file_task.delay(file.dict())
        task_id = celery_task.id
        logger.info(f"Started Celery task {task_id} for file {file.name}")
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={"message": "File processing started", "task_id": task_id},
        )
    except Exception as e:
        logger.error(f"Error initiating file processing: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}",
        )

@router.get("/milvus/task/{task_id}", response_model=ProcessingStatus)
async def get_task_status(task_id: str):
    """
    Returns the status of a given Celery task.
    """
    from celery.result import AsyncResult
    result = AsyncResult(task_id)
    status_map = {
        'PENDING': 'processing',
        'STARTED': 'processing',
        'SUCCESS': 'completed',
        'FAILURE': 'failed',
        'RETRY': 'processing'
    }
    current_status = status_map.get(result.status, result.status)
    meta = result.info if result.info else {}
    return ProcessingStatus(
        task_id=task_id,
        status=current_status,
        processed_chunks=meta.get("processed_chunks", 0),
        total_chunks=meta.get("total_chunks", 0),
        error=meta.get("error", ""),
    )

@router.post("/milvus/collections", status_code=status.HTTP_201_CREATED)
async def create_collection(collection_name: str):
    try:
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=7000),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1536),
        ]

        schema = CollectionSchema(fields, description="Example collection schema for Langflow RAG")

        # Create collection
        collection = Collection(name=collection_name, schema=schema)
        print(f"Collection '{collection_name}' created with schema: {collection.schema}")

        # Define index parameters
        index_params = {
            "index_type": "IVF_FLAT",
            "metric_type": "L2",
            "params": {"nlist": 128},
        }

        # Create the index on the embedding field
        collection.create_index(field_name="embedding", index_params=index_params)

        # Load the collection into memory for search operations
        collection.load()
        print(f"Index created: {collection.indexes}")
        return {"message": f"Collection '{collection_name}' created successfully with schema and index."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))