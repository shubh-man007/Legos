import os
import uuid
import json
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")


class PipelineService:    
    def __init__(self):
        self.db_url = DATABASE_URL
    
    def _get_connection(self):
        return psycopg2.connect(self.db_url, cursor_factory=RealDictCursor)
    
    def store_pipeline_results(self, 
                             bucket_name: str, 
                             folder_path: str, 
                             pipeline_results: Dict[str, Any]) -> str:
        pipeline_id = str(uuid.uuid4())
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    company_name = self._extract_company_name(folder_path)
                    deal_name = f"Pipeline Run {pipeline_id[:8]}"
                    
                    company_id = self._get_or_create_company(cursor, company_name)
                    deal_id = self._get_or_create_deal(cursor, company_id, deal_name, "pipeline_processing")
                    
                    cursor.execute("""
                        INSERT INTO processing_jobs (
                            id, file_upload_id, job_type, status, 
                            started_at, completed_at, metadata
                        ) VALUES (
                            %s, NULL, 'full_pipeline', 'completed',
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s
                        )
                    """, (pipeline_id, json.dumps({"bucket": bucket_name, "folder": folder_path})))
                    
                    results = pipeline_results.get("results", {})
                    for filename, doc_result in results.items():
                        self._store_document_analysis(
                            cursor, pipeline_id, deal_id, filename, doc_result
                        )
                    
                    conn.commit()
                    return pipeline_id
                    
        except Exception as e:
            raise Exception(f"Failed to store pipeline results: {str(e)}")
    
    def _extract_company_name(self, folder_path: str) -> str:
        # Remove suffixes and clean name
        parts = folder_path.split('/')
        if parts:
            company_part = parts[-1]
            import re
            company_name = re.sub(r'_\d+$', '', company_part)
            return company_name.replace('_', ' ').title()
        return "Unknown Company"
    
    def _get_or_create_company(self, cursor, company_name: str) -> str:
        cursor.execute("SELECT id FROM companies WHERE name = %s", (company_name,))
        result = cursor.fetchone()
        
        if result:
            return result['id']
        
        # Create new company
        company_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO companies (id, name, metadata)
            VALUES (%s, %s, %s)
        """, (company_id, company_name, json.dumps({})))
        
        return company_id
    
    def _get_or_create_deal(self, cursor, company_id: str, deal_name: str, deal_type: str) -> str:
        cursor.execute("""
            SELECT id FROM deals 
            WHERE company_id = %s AND deal_name = %s
        """, (company_id, deal_name))
        result = cursor.fetchone()
        
        if result:
            return result['id']
        
        # Create new deal
        deal_id = str(uuid.uuid4())
        cursor.execute("""
            INSERT INTO deals (id, company_id, deal_name, deal_type, metadata)
            VALUES (%s, %s, %s, %s, %s)
        """, (deal_id, company_id, deal_name, deal_type, json.dumps({})))
        
        return deal_id
    
    def _store_document_analysis(self, 
                               cursor, 
                               pipeline_id: str, 
                               deal_id: str, 
                               filename: str, 
                               doc_result: Dict[str, Any]):        
        # Create file upload record with unique GCS path
        file_upload_id = str(uuid.uuid4())
        unique_gcs_path = f"pipeline/{pipeline_id[:8]}/{filename}"
        
        cursor.execute("""
            INSERT INTO file_uploads (
                id, deal_id, original_filename, gcs_bucket, gcs_path,
                file_size, mime_type, file_hash, upload_status, metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, 'completed', %s
            )
        """, (
            file_upload_id, deal_id, filename, 
            "pipeline_upload", unique_gcs_path, 
            0, "application/octet-stream", "", 
            json.dumps({"source": "pipeline", "pipeline_id": pipeline_id})
        ))
        
        # Store document analysis
        analysis_id = str(uuid.uuid4())
        classification = doc_result.get("classification", {})
        summary = doc_result.get("summary", "")
        
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
            analysis_id, file_upload_id, pipeline_id,
            doc_result.get("file_type", "unknown"),
            doc_result.get("extraction_engine", "unknown"),
            doc_result.get("chunks_created", 0),
            1.0,  # extraction_confidence
            classification.get("type", "unknown"),
            classification.get("confidence", 0.0),
            classification.get("key_topics", []),
            summary,
            len(summary.split()) if summary else 0,
            len(summary) if summary else 0,
            doc_result.get("contract_type", "unknown"),
            [],  # parties
            json.dumps({}),  # key_dates
            None,  # jurisdiction
            [],  # processing_log
            [],  # warnings
            [],  # errors
            json.dumps({"classification": classification})
        ))
        
        # Store redlines
        redlines = doc_result.get("redlines", [])
        for redline in redlines:
            redline_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO redlines (
                    id, document_analysis_id, issue_description,
                    severity, clause_reference, recommendation, category
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                redline_id, analysis_id,
                redline.get("issue", ""),
                redline.get("severity", "medium"),
                redline.get("clause", ""),
                redline.get("recommendation", ""),
                "general"
            ))
        
        # Store common grounds
        common_grounds = doc_result.get("common_grounds", [])
        for ground in common_grounds:
            ground_id = str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO common_grounds (
                    id, document_analysis_id, area, description, leverage, category
                ) VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                ground_id, analysis_id,
                ground.get("area", ""),
                ground.get("description", ""),
                ground.get("leverage", ""),
                "general"
            ))
    
    def get_pipeline_results(self, pipeline_id: str) -> Optional[Dict[str, Any]]:
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    # Get pipeline job info
                    cursor.execute("""
                        SELECT pj.*, c.name as company_name, d.deal_name
                        FROM processing_jobs pj
                        LEFT JOIN deals d ON pj.metadata->>'deal_id' = d.id::text
                        LEFT JOIN companies c ON d.company_id = c.id
                        WHERE pj.id = %s
                    """, (pipeline_id,))
                    
                    job_info = cursor.fetchone()
                    if not job_info:
                        return None
                    
                    # Get document analyses
                    cursor.execute("""
                        SELECT da.*, fu.original_filename
                        FROM document_analysis da
                        JOIN file_uploads fu ON da.file_upload_id = fu.id
                        WHERE da.processing_job_id = %s
                    """, (pipeline_id,))
                    
                    analyses = cursor.fetchall()
                    
                    # Get redlines and common grounds for each analysis
                    results = {}
                    for analysis in analyses:
                        filename = analysis['original_filename']
                        
                        # Get redlines
                        cursor.execute("""
                            SELECT issue_description, severity, clause_reference, recommendation
                            FROM redlines WHERE document_analysis_id = %s
                        """, (analysis['id'],))
                        redlines = [dict(row) for row in cursor.fetchall()]
                        
                        # Get common grounds
                        cursor.execute("""
                            SELECT area, description, leverage
                            FROM common_grounds WHERE document_analysis_id = %s
                        """, (analysis['id'],))
                        common_grounds = [dict(row) for row in cursor.fetchall()]
                        
                        results[filename] = {
                            "summary": analysis['summary'],
                            "classification": {
                                "type": analysis['document_type'],
                                "confidence": analysis['classification_confidence'],
                                "key_topics": analysis['key_topics']
                            },
                            "redlines": redlines,
                            "common_grounds": common_grounds,
                            "contract_type": analysis['contract_type'],
                            "extraction_engine": analysis['extraction_engine'],
                            "chunks_created": analysis['pages_processed'],
                            "file_type": analysis['detected_type']
                        }
                    
                    return {
                        "pipeline_id": pipeline_id,
                        "company_name": job_info['company_name'],
                        "deal_name": job_info['deal_name'],
                        "status": job_info['status'],
                        "created_at": job_info['started_at'].isoformat(),
                        "results": results
                    }
                    
        except Exception as e:
            raise Exception(f"Failed to retrieve pipeline results: {str(e)}")
