from app import create_app, db
from sqlalchemy import text
import os

# Force production config to connect to PostgreSQL
os.environ['ENVIRONMENT'] = 'production'

app = create_app()

with app.app_context():
    print(f"Connected to: {app.config['SQLALCHEMY_DATABASE_URI']}")
    
    # PostgreSQL syntax
    db.session.execute(text("ALTER TABLE admin ALTER COLUMN password_hash TYPE VARCHAR(256)"))
    print("✓ Updated admin table")
    
    db.session.execute(text("ALTER TABLE data_capturer ALTER COLUMN password_hash TYPE VARCHAR(256)"))
    print("✓ Updated data_capturer table")
    
    db.session.commit()
    
    print("\n✓✓✓ PostgreSQL database fixed! ✓✓✓")