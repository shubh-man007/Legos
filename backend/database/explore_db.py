import os
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def explore_database():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        print("🔍 Legos AI Database Explorer")
        print("=" * 50)
        
        # Show all tables
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
        """)
        tables = cursor.fetchall()
        
        print(f"\n📊 Found {len(tables)} tables:")
        for table in tables:
            print(f"  - {table['table_name']}")
        
        # Show counts for each table
        print(f"\n📈 Table Record Counts:")
        for table in tables:
            table_name = table['table_name']
            cursor.execute(f"SELECT COUNT(*) as count FROM {table_name};")
            count = cursor.fetchone()['count']
            print(f"  - {table_name}: {count} records")
        
        # Show recent companies
        print(f"\n🏢 Recent Companies:")
        cursor.execute("""
            SELECT id, name, created_at 
            FROM companies 
            ORDER BY created_at DESC 
            LIMIT 5;
        """)
        companies = cursor.fetchall()
        for company in companies:
            print(f"  - {company['name']} (ID: {company['id'][:8]}...)")
        
        # Show recent deals
        print(f"\n🤝 Recent Deals:")
        cursor.execute("""
            SELECT d.id, d.deal_name, c.name as company_name, d.created_at
            FROM deals d
            JOIN companies c ON d.company_id = c.id
            ORDER BY d.created_at DESC 
            LIMIT 5;
        """)
        deals = cursor.fetchall()
        for deal in deals:
            print(f"  - {deal['deal_name']} ({deal['company_name']})")
        
        # Show recent file uploads
        print(f"\n📁 Recent File Uploads:")
        cursor.execute("""
            SELECT fu.id, fu.original_filename, c.name as company_name, fu.created_at
            FROM file_uploads fu
            JOIN deals d ON fu.deal_id = d.id
            JOIN companies c ON d.company_id = c.id
            ORDER BY fu.created_at DESC 
            LIMIT 5;
        """)
        files = cursor.fetchall()
        for file in files:
            print(f"  - {file['original_filename']} ({file['company_name']})")
        
        # Show recent processing jobs
        print(f"\n⚙️ Recent Processing Jobs:")
        cursor.execute("""
            SELECT pj.id, pj.job_type, pj.status, pj.created_at,
                   c.name as company_name
            FROM processing_jobs pj
            LEFT JOIN deals d ON pj.metadata->>'deal_id' = d.id::text
            LEFT JOIN companies c ON d.company_id = c.id
            ORDER BY pj.created_at DESC 
            LIMIT 5;
        """)
        jobs = cursor.fetchall()
        for job in jobs:
            company = job['company_name'] or 'Pipeline Job'
            print(f"  - {job['job_type']} ({job['status']}) - {company}")
        
        # Show document analyses
        print(f"\n📄 Document Analyses:")
        cursor.execute("""
            SELECT da.id, da.document_type, da.classification_confidence,
                   fu.original_filename, c.name as company_name
            FROM document_analysis da
            JOIN file_uploads fu ON da.file_upload_id = fu.id
            JOIN deals d ON fu.deal_id = d.id
            JOIN companies c ON d.company_id = c.id
            ORDER BY da.created_at DESC 
            LIMIT 5;
        """)
        analyses = cursor.fetchall()
        for analysis in analyses:
            confidence = analysis['classification_confidence'] or 0
            print(f"  - {analysis['original_filename']} ({analysis['document_type']}, {confidence:.2f} confidence)")
        
        cursor.close()
        conn.close()
        
        print(f"\n✅ Database exploration complete!")
        
    except Exception as e:
        print(f"❌ Error exploring database: {e}")

def show_table_schema(table_name):
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = %s
            ORDER BY ordinal_position;
        """, (table_name,))
        
        columns = cursor.fetchall()
        print(f"\n📋 Schema for table '{table_name}':")
        for col in columns:
            nullable = "NULL" if col['is_nullable'] == 'YES' else "NOT NULL"
            default = f" DEFAULT {col['column_default']}" if col['column_default'] else ""
            print(f"  - {col['column_name']}: {col['data_type']} {nullable}{default}")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error showing schema: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        table_name = sys.argv[1]
        show_table_schema(table_name)
    else:
        explore_database()
        
    print(f"\n💡 Usage:")
    print(f"  python src/database/explore_db.py          # Show overview")
    print(f"  python src/database/explore_db.py companies # Show table schema")
