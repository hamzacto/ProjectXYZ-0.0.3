# tasks.py
import io
import base64
import pdfplumber
import logging
from celery import Celery
from langchain_text_splitters import CharacterTextSplitter
from langchain.docstore.document import Document
from langchain_milvus.vectorstores import Milvus as LangchainMilvus
import os
import traceback
from langchain_openai import OpenAIEmbeddings
from dotenv import load_dotenv

# Configure Celery with the solo pool for Windows
celery_app = Celery(
    'milvus_tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# Add Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_pool_restarts=True,
    worker_concurrency=1,
    task_track_started=True
)

# For Windows, force the solo pool
if os.name == 'nt':  # Windows
    celery_app.conf.update(
        worker_pool='solo',
        worker_max_tasks_per_child=1
    )

logger = logging.getLogger(__name__)

# Add this near the top of the file with other imports
load_dotenv()

@celery_app.task(bind=True)
def process_file_task(self, file_data: dict):
    """
    Decodes the file, extracts text (PDF or plain text), splits it into chunks,
    generates embeddings using OpenAI, and inserts the documents into Milvus.
    """
    try:
        # Add more detailed logging
        logger.info(f"Starting task with data: {file_data.get('name')}, size: {file_data.get('size')}")
        
        # Log embedding initialization
        logger.info("Initializing OpenAI embedding function...")
        embedding_function = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=os.getenv("OPENAI_API_KEY")
        )
        logger.info("Embedding function initialized successfully")
        
        # Log Milvus connection attempt
        logger.info(f"Attempting to connect to Milvus with collection: {file_data['collection_name']}")
        milvus_store = LangchainMilvus(
            embedding_function=embedding_function,
            collection_name=file_data["collection_name"],
            connection_args={"uri": "http://127.0.0.1:19530", "token": ""},
            consistency_level="Session",
            drop_old=False,
            auto_id=True,
            primary_field="id",
            text_field="text",
            vector_field="embedding"
        )
        logger.info("Milvus connection established successfully")
        
        # Test if content is properly decoded
        try:
            file_bytes = base64.b64decode(file_data["content"])
            logger.info(f"Successfully decoded file content, size: {len(file_bytes)} bytes")
        except Exception as e:
            logger.error(f"Failed to decode base64 content: {str(e)}")
            raise
        
        # Extract text based on file type
        text_content = ""
        if file_data["type"].lower() == "application/pdf":
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                num_pages = len(pdf.pages)
                logger.info(f"PDF has {num_pages} pages")
                for page_idx, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    text_content += page_text + "\n"
                    # Optional: update state to show progress during extraction
                    self.update_state(
                        state='PROGRESS', 
                        meta={"message": f"Extracted page {page_idx+1}/{num_pages}"}
                    )
        else:
            text_content = file_bytes.decode("utf-8", errors="ignore")
            logger.info("Extracted text from non-PDF file")
        
        # Log the length of the extracted text
        logger.info(f"Extracted text length: {len(text_content)} characters")
        
        # Split the text into chunks using CharacterTextSplitter.
        splitter = CharacterTextSplitter(
            chunk_size=file_data.get("chunk_size", 1000),
            chunk_overlap=file_data.get("chunk_overlap", 200),
            separator="\n"
        )
        chunks = splitter.split_text(text_content)
        total_chunks = len(chunks)
        if not chunks:
            raise Exception("No text extracted from the file.")
        
        # Update state with the total number of chunks
        self.update_state(state='PROGRESS', meta={"processed_chunks": 0, "total_chunks": total_chunks})
        
        documents = []
        batch_size = file_data.get("batch_size", 50)
        for idx, chunk in enumerate(chunks):
            documents.append(Document(page_content=chunk, metadata={"file_name": file_data["name"], "chunk_index": idx}))
            
            # When a batch is ready, insert and update progress.
            if (idx + 1) % batch_size == 0:
                milvus_store.add_documents(documents)
                logger.info(f"Inserted batch: {idx + 1} chunks processed")
                documents = []  # reset the batch
                self.update_state(state='PROGRESS', meta={"processed_chunks": idx + 1, "total_chunks": total_chunks})
        
        # Insert any remaining documents in the final batch
        if documents:
            milvus_store.add_documents(documents)
            self.update_state(state='PROGRESS', meta={"processed_chunks": total_chunks, "total_chunks": total_chunks})
        
        logger.info(f"Inserted {total_chunks} chunks for file {file_data['name']} into Milvus.")
        return {"status": "completed", "processed_chunks": total_chunks, "total_chunks": total_chunks}
        
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Task failed with error: {str(e)}", exc_info=True)
        self.update_state(
            state='FAILURE',
            meta={
                'error': str(e),
                'exc_type': type(e).__name__,
                'exc_traceback': tb
            }
        )
        raise e
