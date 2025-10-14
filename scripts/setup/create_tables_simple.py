#!/usr/bin/env python3
"""
Alternative script to create tables using Supabase Python client.
This script uses the Supabase client library for easier connection management.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

def get_supabase_client() -> Client:
    """Create and return a Supabase client."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in environment")
    
    return create_client(url, key)

def create_tables_with_supabase():
    """Create tables using Supabase client with RPC calls."""
    
    # SQL statements to create tables
    create_tables_sql = """
    -- Users table
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) UNIQUE NOT NULL,
        hashed_password VARCHAR(255) NOT NULL,
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Files table
    CREATE TABLE IF NOT EXISTS files (
        id SERIAL PRIMARY KEY,
        filename VARCHAR(512) NOT NULL,
        size_bytes INTEGER NOT NULL,
        content_type VARCHAR(128) NOT NULL,
        status VARCHAR(64) DEFAULT 'uploaded',
        storage_path VARCHAR(1024),
        rows_count INTEGER DEFAULT 0,
        elasticsearch_synced BOOLEAN DEFAULT FALSE,
        elasticsearch_sync_error VARCHAR(512),
        user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Queries table
    CREATE TABLE IF NOT EXISTS queries (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        question VARCHAR(2000) NOT NULL,
        response VARCHAR(8000) DEFAULT '',
        latency_ms INTEGER DEFAULT 0,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    
    -- File chunks table (for vector search)
    CREATE TABLE IF NOT EXISTS file_chunks (
        id SERIAL PRIMARY KEY,
        file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        content TEXT NOT NULL,
        metadata JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Sessions table (for user sessions)
    CREATE TABLE IF NOT EXISTS sessions (
        id SERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        session_token VARCHAR(255) UNIQUE NOT NULL,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    
    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    CREATE INDEX IF NOT EXISTS idx_files_filename ON files(filename);
    CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);
    CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
    CREATE INDEX IF NOT EXISTS idx_queries_user_id ON queries(user_id);
    CREATE INDEX IF NOT EXISTS idx_queries_created_at ON queries(created_at);
    CREATE INDEX IF NOT EXISTS idx_file_chunks_file_id ON file_chunks(file_id);
    CREATE INDEX IF NOT EXISTS idx_file_chunks_chunk_index ON file_chunks(chunk_index);
    CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
    CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);
    CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);
    """
    
    try:
        client = get_supabase_client()
        print("✅ Connected to Supabase!")
        
        # Execute the SQL using RPC call
        result = client.rpc("exec_sql", {"sql": create_tables_sql}).execute()
        print("✅ Tables and indexes created successfully!")
        
        # Verify tables were created by listing them
        tables_result = client.rpc("exec_sql", {
            "sql": """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            ORDER BY table_name;
            """
        }).execute()
        
        if hasattr(tables_result, 'data') and tables_result.data:
            tables = [row['table_name'] for row in tables_result.data]
            print(f"📋 Tables in database: {', '.join(tables)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        print("\n💡 This might be because the RPC function 'exec_sql' doesn't exist.")
        print("   Let's try the direct SQL approach instead...")
        return False

def test_connection():
    """Test the Supabase connection."""
    try:
        client = get_supabase_client()
        
        # Test with a simple query
        result = client.table('pg_tables').select('tablename').limit(1).execute()
        print("✅ Supabase connection test successful!")
        return True
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

def main():
    """Main function."""
    print("🚀 Setting up Supabase database tables...")
    
    # First test the connection
    if not test_connection():
        print("❌ Cannot connect to Supabase. Please check your credentials.")
        return
    
    # Try to create tables
    success = create_tables_with_supabase()
    
    if success:
        print("\n🎉 Database setup completed!")
        print("\nNext steps:")
        print("1. Your tables are ready to use")
        print("2. You can start uploading Excel files")
        print("3. Use the API endpoints to interact with the data")
    else:
        print("\n⚠️  RPC method didn't work. Please use the direct SQL script instead.")
        print("   Run: python scripts/setup/create_tables_supabase.py")

if __name__ == "__main__":
    main()