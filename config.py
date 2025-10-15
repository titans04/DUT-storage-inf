import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = None


class DevelopmentConfig(Config):
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(basedir, 'instance', 'app.db')}"


class ProductionConfig(Config):
    DATABASE_URL = os.environ.get('DATABASE_URL')

    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    # Add SSL parameters for Render PostgreSQL
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL + "?sslmode=require"
    else:
        SQLALCHEMY_DATABASE_URI = None
    
    # Additional SQLAlchemy engine options for SSL
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }


# Choose config based on environment variable
if os.environ.get('ENVIRONMENT') == 'production':
    config = ProductionConfig
else:
    config = DevelopmentConfig

