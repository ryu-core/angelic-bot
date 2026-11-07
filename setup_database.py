"""
Automatic Database Setup Script
This script runs automatically on bot startup to ensure database is ready
"""
import os
import sys

def setup_database():
    """Initialize database automatically"""
    print("\n" + "="*60)
    print("🔧 Checking Database Setup...")
    print("="*60 + "\n")
    
    # Add database directory to path
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'database'))
    
    try:
        from database.models import Database, db
        
        # Initialize database
        print("📦 Initializing database tables...")
        print(f"   Database file: {db.engine.url}")
        db.create_tables()
        driver_name = db.engine.url.drivername
        if driver_name.startswith('sqlite'):
            print("Using local SQLite dashboard database because MySQL env is missing")
            print("MySQL-backed cogs still need MYSQL_HOST, MYSQL_USER, MYSQL_PASSWORD, and MYSQL_DATABASE")
            print("="*60 + "\n")
            return True
        print("✅ Database tables ready!\n")
        
        # Initialize economy database
        try:
            from utils.economy_db import economy_db
            print("💰 Initializing economy database...")
            economy_db.init_database()
        except Exception as e:
            print(f"⚠️  Economy database initialization warning: {e}")
        
        # Initialize auto-role database
        try:
            from utils.autorole_db import autorole_db
            print("🎭 Initializing auto-role database...")
            autorole_db.init_database()
        except Exception as e:
            print(f"⚠️  Auto-role database initialization warning: {e}")
        
        print("✅ Using MySQL database")
        print("="*60 + "\n")
        return True
        
    except Exception as e:
        print(f"⚠️  Database setup warning: {e}")
        print("   Bot will continue, but dashboard may have limited functionality")
        print("="*60 + "\n")
        return False

if __name__ == '__main__':
    setup_database()
