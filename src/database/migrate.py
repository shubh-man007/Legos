import os
import sys
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://legos_user:legos_password@localhost:5432/legos_ai")


def create_database():
    try:
        from urllib.parse import urlparse, unquote
        parsed = urlparse(DATABASE_URL)
        
        conn = psycopg2.connect(
            host=parsed.hostname,
            port=parsed.port or 5432,
            user=parsed.username,
            password=unquote(parsed.password),
            database='postgres'  
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        
        cursor = conn.cursor()
        
        db_name = parsed.path[1:]  # Remove leading slash
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        exists = cursor.fetchone()
        
        if not exists:
            cursor.execute(f'CREATE DATABASE "{db_name}"')
            print(f"Database '{db_name}' created successfully")
        else:
            print(f"Database '{db_name}' already exists")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error creating database: {e}")
        return False
    
    return True


def apply_database_schema():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        schema_file = os.path.join(os.path.dirname(__file__), 'schema.sql')
        
        if not os.path.exists(schema_file):
            print(f"Schema file not found: {schema_file}")
            return False
        
        with open(schema_file, 'r') as f:
            schema_sql = f.read()
        
        cursor.execute(schema_sql)
        conn.commit()
        
        print("Database schema applied successfully")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error applying schema: {e}")
        return False
    
    return True


def seed_initial_data():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        # Common file tags
        common_tags = [
            'contract',
            'nda',
            'msa',
            'dpa',
            'company_profile',
            'historical_data',
            'playbook',
            'financial',
            'legal',
            'technical',
            'marketing',
            'hr',
            'compliance'
        ]
        
        for tag in common_tags:
            cursor.execute("""
                INSERT INTO file_tags (id, name, description)
                VALUES (gen_random_uuid(), %s, %s)
                ON CONFLICT (name) DO NOTHING
            """, (tag, f"Tag for {tag} documents"))
        
        conn.commit()
        print(f"Seeded {len(common_tags)} common file tags")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error seeding initial data: {e}")
        return False
    
    return True


def fix_processing_jobs_table():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        print("Fixing processing_jobs table...")
        
        # Drop the existing foreign key constraint
        print("1. Dropping existing foreign key constraint...")
        cursor.execute("ALTER TABLE processing_jobs DROP CONSTRAINT IF EXISTS processing_jobs_file_upload_id_fkey;")
        
        # Make file_upload_id nullable
        print("2. Making file_upload_id nullable...")
        cursor.execute("ALTER TABLE processing_jobs ALTER COLUMN file_upload_id DROP NOT NULL;")
        
        # Re-add the foreign key constraint but allow NULL values
        print("3. Re-adding foreign key constraint...")
        cursor.execute("""
            ALTER TABLE processing_jobs 
            ADD CONSTRAINT processing_jobs_file_upload_id_fkey 
            FOREIGN KEY (file_upload_id) REFERENCES file_uploads(id) ON DELETE CASCADE;
        """)
        
        # Update the index to handle NULL values
        print("4. Updating index...")
        cursor.execute("DROP INDEX IF EXISTS idx_processing_jobs_file_upload_id;")
        cursor.execute("""
            CREATE INDEX idx_processing_jobs_file_upload_id 
            ON processing_jobs(file_upload_id) 
            WHERE file_upload_id IS NOT NULL;
        """)
        
        conn.commit()
        print("processing_jobs table fixed successfully!")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error fixing processing_jobs table: {e}")
        return False
    
    return True


def test_database_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        cursor.execute("SELECT version();")
        version = cursor.fetchone()
        print(f"Database connection successful")
        print(f"PostgreSQL version: {version[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM companies;")
        company_count = cursor.fetchone()[0]
        print(f"Companies table: {company_count} records")
        
        cursor.execute("SELECT COUNT(*) FROM file_tags;")
        tag_count = cursor.fetchone()[0]
        print(f"File tags: {tag_count} records")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Database connection test failed: {e}")
        return False
    
    return True


def main():
    print("Starting Legos AI Database Migration")
    print("---" * 10)
    
    print("\n1. Creating database...")
    if not create_database():
        sys.exit(1)
    
    print("\n2. Applying database schema...")
    if not apply_database_schema():
        sys.exit(1)
    
    print("\n3. Fixing processing_jobs table...")
    if not fix_processing_jobs_table():
        sys.exit(1)
    
    print("\n4. Seeding initial data...")
    if not seed_initial_data():
        sys.exit(1)
    
    print("\n5. Testing database connection...")
    if not test_database_connection():
        sys.exit(1)


if __name__ == "__main__":
    main()