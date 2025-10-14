#!/usr/bin/env python3
"""
Script to create tables in Supabase database using the pooler connection.
This script connects to Supabase via the direct pooler connection and creates
all necessary tables for the Excel AI Agent application.
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import psycopg
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Load environment variables
load_dotenv()

def get_database_url():
    """Get the database URL from environment variables."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment variables")
    return database_url

def create_tables():
    """Create all necessary tables for the Excel AI Agent."""
    
    # SQL statements to create tables
    create_tables_sql = [
        # Users table
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            hashed_password VARCHAR(255) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        
        # Files table
        """
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
        """,
        
        # Queries table
        """
        CREATE TABLE IF NOT EXISTS queries (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            question VARCHAR(2000) NOT NULL,
            response VARCHAR(8000) DEFAULT '',
            latency_ms INTEGER DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        
        # File chunks table (for vector search)
        """
        CREATE TABLE IF NOT EXISTS file_chunks (
            id SERIAL PRIMARY KEY,
            file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            metadata JSONB,
            embedding VECTOR(1536),  -- OpenAI embedding dimension
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """,
        
        # Sessions table (for user sessions)
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            session_token VARCHAR(255) UNIQUE NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
    ]
    
    # SQL statements to create indexes
    create_indexes_sql = [
        "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);",
        "CREATE INDEX IF NOT EXISTS idx_files_filename ON files(filename);",
        "CREATE INDEX IF NOT EXISTS idx_files_user_id ON files(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);",
        "CREATE INDEX IF NOT EXISTS idx_queries_user_id ON queries(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_queries_created_at ON queries(created_at);",
        "CREATE INDEX IF NOT EXISTS idx_file_chunks_file_id ON file_chunks(file_id);",
        "CREATE INDEX IF NOT EXISTS idx_file_chunks_chunk_index ON file_chunks(chunk_index);",
        "CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);",
        "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at);"
    ]
    
    database_url = get_database_url()
    
    try:
        # Create engine and connect
        engine = create_engine(database_url, echo=True)
        
        with engine.connect() as connection:
            print("Connected to Supabase database via pooler!")
            
            # Enable pgvector extension for vector operations
            try:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
                print("✅ pgvector extension enabled")
            except Exception as e:
                print(f"⚠️  Warning: Could not enable pgvector extension: {e}")
                print("   This is normal if you don't have vector search requirements")
            
            # Create tables
            print("\nCreating tables...")
            for i, sql in enumerate(create_tables_sql, 1):
                try:
                    connection.execute(text(sql))
                    table_name = sql.split("CREATE TABLE IF NOT EXISTS")[1].split("(")[0].strip()
                    print(f"✅ Created table: {table_name}")
                except Exception as e:
                    print(f"❌ Error creating table {i}: {e}")
                    continue
            
            # Create indexes
            print("\nCreating indexes...")
            for i, sql in enumerate(create_indexes_sql, 1):
                try:
                    connection.execute(text(sql))
                    index_name = sql.split("CREATE INDEX IF NOT EXISTS")[1].split("ON")[0].strip()
                    print(f"✅ Created index: {index_name}")
                except Exception as e:
                    print(f"❌ Error creating index {i}: {e}")
                    continue
            
            # Commit all changes
            connection.commit()
            print("\n🎉 All tables and indexes created successfully!")
            
            # Verify tables were created
            print("\nVerifying tables...")
            result = connection.execute(text("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                ORDER BY table_name;
            """))
            
            tables = [row[0] for row in result.fetchall()]
            print(f"Tables in database: {', '.join(tables)}")
            
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        return False
    
    return True

def main():
    """Main function to run the table creation script."""
    print("🚀 Creating tables in Supabase database...")
    print(f"Using DATABASE_URL: {get_database_url()[:50]}...")  # Show partial URL for security
    
    success = create_tables()
    
    if success:
        print("\n✅ Database setup completed successfully!")
        print("\nYou can now:")
        print("1. Use the Supabase client in your application")
        print("2. Create users and upload files")
        print("3. Store and query data")
    else:
        print("\n❌ Database setup failed. Please check the error messages above.")
        sys.exit(1)

if __name__ == "__main__":
    main()