"""
Database initialization script
Run once to create tables
"""

from database import init_db, engine
from models import Base

if __name__ == "__main__":
    print("Creating database tables...")
    
    # Drop all tables (careful in production!)
    # Base.metadata.drop_all(bind=engine)
    
    # Create all tables
    init_db()
    
    print("Database tables created successfully!")
    print("\nTables created:")
    print("- organizations")
    print("- users")
    print("- documents")
    print("- api_keys")