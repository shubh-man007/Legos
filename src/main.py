from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import os
import sys
import asyncio
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from services.pipeline import PipelineService
from services.upload import UploadService
from utils.utils import db_health
from workflow import run_pipeline

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

app = FastAPI(
    title="Legos.ai",
    description="Legos: Slipp'in Jimmy's assistant",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pipeline_service = PipelineService()
upload_service = UploadService()


@app.get("/", response_model=Dict[str, str])
async def root():
    return {
        "message": "Better Call Legos",
        "status": "operational",
        "version": "1.0.0"
    }


@app.get("/health", response_model=Dict[str, str])
async def health_check():
    db_status = db_health()
    return {
        "status": "healthy",
        "service": "legos-ai-api",
        "database": db_status
    }


@app.post("/pipeline/process")
async def process_documents_pipeline(
    bucket_name: str = Form(..., description="GCS bucket name"),
    folder_path: str = Form(..., description="GCS folder path")
) -> JSONResponse:
    """
    Process documents from GCS bucket and folder through the complete AI pipeline.
    
    This endpoint:
    1. Downloads all documents from the specified GCS location
    2. Processes them through the AI agents (detection, extraction, analysis)
    3. Stores the results in the database
    4. Returns comprehensive analysis results
    
    Args:
        bucket_name: Google Cloud Storage bucket name
        folder_path: Path to the folder containing documents
        
    Returns:
        JSON response with processing results and analysis data
    """
    try:
        pipeline_results = await run_pipeline(bucket_name, folder_path)
        
        if pipeline_results.get("status") != "success":
            raise HTTPException(
                status_code=500, 
                detail=f"Pipeline processing failed: {pipeline_results.get('error', 'Unknown error')}"
            )
        
        # Store results in database
        pipeline_id = pipeline_service.store_pipeline_results(
            bucket_name, folder_path, pipeline_results
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": f"Pipeline completed successfully for gs://{bucket_name}/{folder_path}",
                "pipeline_id": pipeline_id,
                "summary": {
                    "files_processed": pipeline_results.get("files_processed", 0),
                    "chunks_created": pipeline_results.get("chunks_created", 0),
                    "documents_analyzed": pipeline_results.get("documents_analyzed", 0)
                },
                "results": pipeline_results.get("results", {}),
                "processing_log": pipeline_results.get("processing_log", []),
                "errors": pipeline_results.get("errors", []),
                "warnings": pipeline_results.get("warnings", [])
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Pipeline execution failed: {str(e)}"
        )


@app.post("/upload/file")
async def upload_file(
    file: UploadFile = File(..., description="File to upload"),
    company_name: str = Form(..., description="Company name"),
    deal_name: str = Form(..., description="Deal or project name"),
    file_tags: Optional[str] = Form(None, description="Comma-separated file tags"),
    deal_type: Optional[str] = Form(None, description="Type of deal (e.g., nda, msa, partnership)"),
    bucket_name: Optional[str] = Form(None, description="GCS bucket name (optional)")
) -> JSONResponse:
    """
    Upload a file to the platform for processing.
    
    This endpoint:
    1. Accepts file uploads via drag-and-drop or direct upload
    2. Stores the file in Google Cloud Storage
    3. Creates database records for tracking
    4. Queues the file for AI processing
    
    Args:
        file: The file to upload
        company_name: Name of the company
        deal_name: Name of the deal or project
        file_tags: Optional comma-separated tags for categorization
        deal_type: Optional type of deal
        bucket_name: Optional GCS bucket (uses default if not provided)
        
    Returns:
        JSON response with upload confirmation and processing details
    """
    try:
        tags_list = []
        if file_tags:
            tags_list = [tag.strip() for tag in file_tags.split(",") if tag.strip()]
        
        result = await upload_service.upload_file(
            file=file,
            company_name=company_name,
            deal_name=deal_name,
            file_tags=tags_list,
            deal_type=deal_type,
            bucket_name=bucket_name
        )
        
        return JSONResponse(
            status_code=200,
            content=result
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"File upload failed: {str(e)}"
        )


@app.get("/upload/status/{file_upload_id}")
async def get_upload_status(file_upload_id: str) -> JSONResponse:
    try:
        status = upload_service.get_upload_status(file_upload_id)
        
        if not status:
            raise HTTPException(
                status_code=404,
                detail=f"File upload not found: {file_upload_id}"
            )
        
        return JSONResponse(
            status_code=200,
            content=status
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get upload status: {str(e)}"
        )


@app.get("/uploads")
async def list_uploads(
    company_name: Optional[str] = Query(None, description="Filter by company name"),
    deal_name: Optional[str] = Query(None, description="Filter by deal name"),
    limit: int = Query(50, ge=1, le=100, description="Number of results to return"),
    offset: int = Query(0, ge=0, description="Number of results to skip")
) -> JSONResponse:
    try:
        result = upload_service.list_uploads(
            company_name=company_name,
            deal_name=deal_name,
            limit=limit,
            offset=offset
        )
        
        return JSONResponse(
            status_code=200,
            content=result
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list uploads: {str(e)}"
        )


@app.get("/pipeline/results/{pipeline_id}")
async def get_pipeline_results(pipeline_id: str) -> JSONResponse:
    try:
        results = pipeline_service.get_pipeline_results(pipeline_id)
        
        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"Pipeline results not found: {pipeline_id}"
            )
        
        return JSONResponse(
            status_code=200,
            content=results
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pipeline results: {str(e)}"
        )


@app.get("/api/endpoints")
async def get_api_endpoints() -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            "api_name": "Legos.ai",
            "version": "1.0.0",
            "status": "operational",
            "description": "AI-powered contract analysis and negotiation assistance platform",
            "endpoints": {
                "GET /": {
                    "description": "API root endpoint - basic status",
                    "response": "API information and status"
                },
                "GET /health": {
                    "description": "Health check endpoint",
                    "response": "Service health status"
                },
                "POST /pipeline/process": {
                    "description": "Process documents from GCS through complete AI pipeline",
                    "parameters": {
                        "bucket_name": "GCS bucket name (required)",
                        "folder_path": "GCS folder path (required)"
                    },
                    "response": "Complete analysis results with database storage"
                },
                "POST /upload/file": {
                    "description": "Upload file for processing",
                    "parameters": {
                        "file": "File to upload (required)",
                        "company_name": "Company name (required)",
                        "deal_name": "Deal/project name (required)",
                        "file_tags": "Comma-separated tags (optional)",
                        "deal_type": "Type of deal (optional)",
                        "bucket_name": "GCS bucket (optional)"
                    },
                    "response": "Upload confirmation and processing details"
                },
                "GET /upload/status/{file_upload_id}": {
                    "description": "Get file upload and processing status",
                    "parameters": {
                        "file_upload_id": "Upload ID (required)"
                    },
                    "response": "Upload status and processing information"
                },
                "GET /uploads": {
                    "description": "List file uploads with filtering",
                    "parameters": {
                        "company_name": "Filter by company (optional)",
                        "deal_name": "Filter by deal (optional)",
                        "limit": "Results limit (default: 50)",
                        "offset": "Results offset (default: 0)"
                    },
                    "response": "List of uploads with metadata"
                },
                "GET /pipeline/results/{pipeline_id}": {
                    "description": "Get results from completed pipeline run",
                    "parameters": {
                        "pipeline_id": "Pipeline ID (required)"
                    },
                    "response": "Pipeline results and analysis data"
                },
                "GET /api/endpoints": {
                    "description": "This endpoint - API documentation",
                    "response": "Complete API endpoint documentation"
                }
            },
            "features": [
                "GCS integration for document storage",
                "AI-powered document analysis",
                "Contract classification and risk assessment",
                "Redline identification and recommendations",
                "Common grounds analysis",
                "Vector storage with Pinecone",
                "PostgreSQL database integration",
                "File upload and processing tracking",
                "Comprehensive API documentation"
            ],
            "ai_agents": [
                "file_agent - File detection and metadata extraction",
                "detection_agent - Document type classification",
                "extraction_agent - Content extraction and chunking",
                "phraser_agent - Document summarization and classification",
                "attorney_agent - Legal analysis and redline identification"
            ],
            "supported_file_types": [
                "PDF (text and scanned)",
                "Word documents (.docx, .doc)",
                "Excel spreadsheets (.xlsx, .xls)",
                "Text files (.txt, .md)",
                "Images (PNG, JPG, JPEG, TIFF)"
            ]
        }
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "message": "Internal server error",
            "detail": str(exc) if os.getenv("DEBUG", "false").lower() == "true" else "An unexpected error occurred"
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )