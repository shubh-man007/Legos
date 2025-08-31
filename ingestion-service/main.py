from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
from workflow import execute_workflow, process_document_from_state, analyze_all_documents_in_state
from processor import process_gcs_file
from agents.state.state import State
import tempfile

load_dotenv()

app = FastAPI(
    title="Legos AI Contract Review API",
    description="AI-powered contract analysis and negotiation assistance",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Legos AI Contract Review API", "status": "running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "legos-api"}

@app.post("/analyze/document")
async def analyze_document(
    document_id: str,
    raw_text: str,
    chunks: List[Dict[str, Any]] = None
):
    try:
        result = await execute_workflow(document_id, raw_text, chunks)
        return {
            "status": "success",
            "document_id": document_id,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/analyze/upload")
async def analyze_uploaded_document(
    file: UploadFile = File(...),
    document_id: str = None
):
    try:
        if not document_id:
            document_id = f"upload_{file.filename}_{os.urandom(4).hex()}"
        
        # Read file content
        content = await file.read()
        
        if file.content_type == "text/plain":
            raw_text = content.decode("utf-8")
        elif file.content_type == "application/pdf":
            # Basic PDF handling 
            raw_text = f"PDF content from {file.filename} - processing required"
        else:
            raw_text = content.decode("utf-8", errors="ignore")
        
        result = await execute_workflow(document_id, raw_text)
        
        return {
            "status": "success",
            "document_id": document_id,
            "filename": file.filename,
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File analysis failed: {str(e)}")

@app.post("/analyze/gcs")
async def analyze_gcs_document(
    bucket_name: str,
    file_path: str,
    document_id: str = None
):
    try:
        if not document_id:
            document_id = f"gcs_{bucket_name}_{file_path.replace('/', '_')}"
        
        # Process through existing GCS pipeline
        metadata = {"source": "gcs", "bucket": bucket_name, "path": file_path}
        await process_gcs_file(bucket_name, file_path, metadata)
        
        # For now, return success message
        # In full implementation, you'd retrieve the processed text from state
        return {
            "status": "success",
            "document_id": document_id,
            "message": "GCS document processed successfully",
            "next_step": "Retrieve processed text from state for analysis"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GCS processing failed: {str(e)}")

@app.get("/document/{document_id}")
async def get_document_analysis(document_id: str):
    try:
        # This would need to be integrated with your actual state management
        # For now, creating a mock state for demonstration
        mock_state = State()
        mock_state.raw_contents[document_id] = "Sample document content for testing"
        
        result = await process_document_from_state(mock_state, document_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve document: {str(e)}")

@app.post("/batch/analyze")
async def batch_analyze_documents(documents: List[Dict[str, Any]]):
    try:
        results = []
        for doc in documents:
            doc_id = doc.get("document_id", f"batch_{len(results)}")
            raw_text = doc.get("raw_text", "")
            chunks = doc.get("chunks", [])
            
            result = await execute_workflow(doc_id, raw_text, chunks)
            results.append({
                "document_id": doc_id,
                "result": result
            })
        
        return {
            "status": "success",
            "processed_count": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Batch analysis failed: {str(e)}")

@app.post("/analyze/state")
async def analyze_documents_in_state(state_data: Dict[str, Any]):
    try:
        # Create state from provided data
        state = State()
        
        # Populate state with provided data
        if "raw_contents" in state_data:
            state.raw_contents = state_data["raw_contents"]
        if "chunks" in state_data:
            state.chunks = state_data["chunks"]
        if "mime_types" in state_data:
            state.mime_types = state_data["mime_types"]
        
        # Analyze all documents in state
        result = await analyze_all_documents_in_state(state)
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"State analysis failed: {str(e)}")

@app.get("/workflow/status")
async def get_workflow_status():
    return {
        "status": "operational",
        "agents": ["phraser", "attorney"],
        "workflow": "phraser -> attorney -> end",
        "features": [
            "document_classification",
            "summarization", 
            "redline_identification",
            "common_grounds_analysis"
        ],
        "state_integration": "enabled",
        "rag_support": "enabled"
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port) 
