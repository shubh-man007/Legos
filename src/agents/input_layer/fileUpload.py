import os
import uuid
import hashlib
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field, constr
from google.cloud import storage
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime


class CompanyCreate(BaseModel):
    name: str = constr(strip_whitespace=True, min_length=1, max_length=255)
    metadata: Optional[Dict] = Field(default_factory=dict)


class DealCreate(BaseModel):
    company_id: str
    deal_name: str = constr(strip_whitespace=True, min_length=1, max_length=255)
    deal_type: Optional[str] = None
    metadata: Optional[Dict] = Field(default_factory=dict)


class FileUploadCreate(BaseModel):
    deal_id: str
    original_filename: str = constr(min_length=1, max_length=500)
    file_tags: List[str] = Field(default_factory=list)
    metadata: Optional[Dict] = Field(default_factory=dict)


class DatabaseManager:
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
    
    def get_connection(self):
        return psycopg2.connect(self.connection_string, cursor_factory=RealDictCursor)
    
    def create_company(self, company_data: CompanyCreate) -> Tuple[str, bool]:
        """Create a new company or return existing one"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Check if company exists
                cursor.execute("SELECT id FROM companies WHERE name = %s", (company_data.name,))
                existing = cursor.fetchone()
                
                if existing:
                    return existing['id'], False  # Existing company
                
                # Create new company
                company_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO companies (id, name, metadata)
                    VALUES (%s, %s, %s)
                """, (company_id, company_data.name, json.dumps(company_data.metadata)))
                
                conn.commit()
                return company_id, True  # New company
    
    def create_deal(self, deal_data: DealCreate) -> Tuple[str, bool]:
        """Create a new deal or return existing one"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                # Check if deal exists
                cursor.execute("""
                    SELECT id FROM deals 
                    WHERE company_id = %s AND deal_name = %s
                """, (deal_data.company_id, deal_data.deal_name))
                existing = cursor.fetchone()
                
                if existing:
                    return existing['id'], False  # Existing deal
                
                # Create new deal
                deal_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO deals (id, company_id, deal_name, deal_type, metadata)
                    VALUES (%s, %s, %s, %s, %s)
                """, (deal_id, deal_data.company_id, deal_data.deal_name, 
                      deal_data.deal_type, json.dumps(deal_data.metadata)))
                
                conn.commit()
                return deal_id, True  # New deal
    
    def create_file_tags(self, tag_names: List[str]) -> List[str]:
        """Create file tags and return their IDs"""
        if not tag_names:
            return []
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                tag_ids = []
                for tag_name in tag_names:
                    # Check if tag exists
                    cursor.execute("SELECT id FROM file_tags WHERE name = %s", (tag_name,))
                    existing = cursor.fetchone()
                    
                    if existing:
                        tag_ids.append(existing['id'])
                    else:
                        # Create new tag
                        tag_id = str(uuid.uuid4())
                        cursor.execute("""
                            INSERT INTO file_tags (id, name)
                            VALUES (%s, %s)
                        """, (tag_id, tag_name))
                        tag_ids.append(tag_id)
                
                conn.commit()
                return tag_ids
    
    def upload_file_and_create_record(self, 
                                    bucket_name: str, 
                                    local_file_path: str,
                                    file_upload_data: FileUploadCreate,
                                    company_name: str,
                                    deal_name: str,
                                    deal_type: Optional[str] = None) -> Dict:
        """
        Complete file upload workflow:
        1. Create company if not exists
        2. Create deal if not exists  
        3. Upload file to GCS
        4. Create file upload record
        5. Link file tags
        """
        try:
            # Get file info
            file_size = os.path.getsize(local_file_path)
            file_hash = self._calculate_file_hash(local_file_path)
            mime_type = self._get_mime_type(local_file_path)
            
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 1. Create or get company
                    company_data = CompanyCreate(name=company_name)
                    company_id, is_new_company = self.create_company(company_data)
                    
                    # 2. Create or get deal
                    deal_data = DealCreate(
                        company_id=company_id,
                        deal_name=deal_name,
                        deal_type=deal_type
                    )
                    deal_id, is_new_deal = self.create_deal(deal_data)
                    
                    # 3. Upload to GCS
                    gcs_path = self._upload_to_gcs(
                        bucket_name, local_file_path, 
                        company_id, deal_id, file_upload_data.original_filename
                    )
                    
                    # 4. Create file upload record
                    file_upload_id = str(uuid.uuid4())
                    cursor.execute("""
                        INSERT INTO file_uploads (
                            id, deal_id, original_filename, gcs_bucket, gcs_path,
                            file_size, mime_type, file_hash, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        file_upload_id, deal_id, file_upload_data.original_filename,
                        bucket_name, gcs_path, file_size, mime_type, file_hash,
                        json.dumps(file_upload_data.metadata)
                    ))
                    
                    # 5. Create and link file tags
                    if file_upload_data.file_tags:
                        tag_ids = self.create_file_tags(file_upload_data.file_tags)
                        for tag_id in tag_ids:
                            cursor.execute("""
                                INSERT INTO file_upload_tags (file_upload_id, tag_id)
                                VALUES (%s, %s)
                            """, (file_upload_id, tag_id))
                    
                    conn.commit()
                    
                    return {
                        "status": "success",
                        "file_upload_id": file_upload_id,
                        "company_id": company_id,
                        "deal_id": deal_id,
                        "gcs_path": gcs_path,
                        "is_new_company": is_new_company,
                        "is_new_deal": is_new_deal,
                        "file_size": file_size,
                        "file_hash": file_hash
                    }
                    
        except Exception as e:
            return {
                "status": "error",
                "message": f"Upload failed: {str(e)}"
            }
    
    def create_processing_job(self, file_upload_id: str, job_type: str = "full_pipeline") -> str:
        """Create a processing job for a file upload"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                job_id = str(uuid.uuid4())
                cursor.execute("""
                    INSERT INTO processing_jobs (id, file_upload_id, job_type, status)
                    VALUES (%s, %s, %s, 'pending')
                """, (job_id, file_upload_id, job_type))
                
                conn.commit()
                return job_id
    
    def update_processing_job_status(self, job_id: str, status: str, error_message: str = None):
        """Update processing job status"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                if status == 'running':
                    cursor.execute("""
                        UPDATE processing_jobs 
                        SET status = %s, started_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (status, job_id))
                elif status in ['completed', 'failed']:
                    cursor.execute("""
                        UPDATE processing_jobs 
                        SET status = %s, completed_at = CURRENT_TIMESTAMP, error_message = %s
                        WHERE id = %s
                    """, (status, error_message, job_id))
                else:
                    cursor.execute("""
                        UPDATE processing_jobs 
                        SET status = %s
                        WHERE id = %s
                    """, (status, job_id))
                
                conn.commit()
    
    def store_analysis_results(self, file_upload_id: str, job_id: str, analysis_data: Dict) -> str:
        """Store document analysis results"""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                analysis_id = str(uuid.uuid4())
                
                cursor.execute("""
                    INSERT INTO document_analysis (
                        id, file_upload_id, processing_job_id,
                        detected_type, extraction_engine, pages_processed,
                        extraction_confidence, document_type, classification_confidence,
                        key_topics, summary, word_count, character_count,
                        contract_type, parties, key_dates, jurisdiction,
                        processing_log, warnings, errors, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                """, (
                    analysis_id, file_upload_id, job_id,
                    analysis_data.get('detected_type'),
                    analysis_data.get('extraction_engine'),
                    analysis_data.get('pages_processed'),
                    analysis_data.get('extraction_confidence'),
                    analysis_data.get('document_type'),
                    analysis_data.get('classification_confidence'),
                    analysis_data.get('key_topics', []),
                    analysis_data.get('summary'),
                    analysis_data.get('word_count'),
                    analysis_data.get('character_count'),
                    analysis_data.get('contract_type'),
                    analysis_data.get('parties', []),
                    json.dumps(analysis_data.get('key_dates', {})),
                    analysis_data.get('jurisdiction'),
                    analysis_data.get('processing_log', []),
                    analysis_data.get('warnings', []),
                    analysis_data.get('errors', []),
                    json.dumps(analysis_data.get('metadata', {}))
                ))
                
                conn.commit()
                return analysis_id
    
    def store_redlines(self, analysis_id: str, redlines: List[Dict]):
        """Store redlines for a document analysis"""
        if not redlines:
            return
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                for redline in redlines:
                    redline_id = str(uuid.uuid4())
                    cursor.execute("""
                        INSERT INTO redlines (
                            id, document_analysis_id, issue_description,
                            severity, clause_reference, recommendation, category
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        redline_id, analysis_id,
                        redline.get('issue', ''),
                        redline.get('severity', 'medium'),
                        redline.get('clause', ''),
                        redline.get('recommendation', ''),
                        redline.get('category', 'general')
                    ))
                
                conn.commit()
    
    def store_common_grounds(self, analysis_id: str, common_grounds: List[Dict]):
        """Store common grounds for a document analysis"""
        if not common_grounds:
            return
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                for ground in common_grounds:
                    ground_id = str(uuid.uuid4())
                    cursor.execute("""
                        INSERT INTO common_grounds (
                            id, document_analysis_id, area, description, leverage, category
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        ground_id, analysis_id,
                        ground.get('area', ''),
                        ground.get('description', ''),
                        ground.get('leverage', ''),
                        ground.get('category', 'general')
                    ))
                
                conn.commit()
    
    def _upload_to_gcs(self, bucket_name: str, local_file_path: str, 
                      company_id: str, deal_id: str, filename: str) -> str:
        """Upload file to GCS with organized path structure"""
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        
        # Create organized path: companies/{company_id}/deals/{deal_id}/files/{filename}
        gcs_path = f"companies/{company_id}/deals/{deal_id}/files/{filename}"
        
        blob = bucket.blob(gcs_path)
        blob.upload_from_filename(local_file_path)
        
        return gcs_path
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """Calculate SHA-256 hash of file"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type of file"""
        import mimetypes
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"


# Example usage and API integration
def upload_file_via_api(bucket_name: str, 
                       local_file_path: str,
                       company_name: str,
                       deal_name: str,
                       file_tags: List[str] = None,
                       deal_type: str = None,
                       db_connection_string: str = None) -> Dict:
    """
    Main function for file upload via API
    """
    if not db_connection_string:
        db_connection_string = os.getenv("DATABASE_URL")
    
    if not db_connection_string:
        return {"status": "error", "message": "Database connection string not provided"}
    
    db_manager = DatabaseManager(db_connection_string)
    
    file_upload_data = FileUploadCreate(
        deal_id="",  # Will be set during processing
        original_filename=os.path.basename(local_file_path),
        file_tags=file_tags or [],
        metadata={}
    )
    
    return db_manager.upload_file_and_create_record(
        bucket_name=bucket_name,
        local_file_path=local_file_path,
        file_upload_data=file_upload_data,
        company_name=company_name,
        deal_name=deal_name,
        deal_type=deal_type
    )


if __name__ == "__main__":
    # Example usage
    result = upload_file_via_api(
        bucket_name="client-context",
        local_file_path="/path/to/document.pdf",
        company_name="Techflow Solutions Inc",
        deal_name="Q4 2024 Partnership Agreement",
        file_tags=["contract", "nda"],
        deal_type="partnership"
    )
    print(result)
