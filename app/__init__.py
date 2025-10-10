from flask import Flask, redirect, url_for, request, flash 
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config
from .models import db, Admin, DataCapturer 

# Initialize Login Manager
login_manager = LoginManager()
login_manager.login_view = 'auth.login' 

@login_manager.user_loader
def load_user(user_id):
    """
    Flask-Login user loader.
    Loads a user given the user_id. The ID is prefixed to distinguish
    between Admins ('A-') and DataCapturers ('D-').
    """
    user_type, _, user_actual_id = user_id.partition('-')
    if user_type == 'A':
        return Admin.query.get(int(user_actual_id))
    elif user_type == 'D':
        return DataCapturer.query.get(int(user_actual_id))
    return None

def create_app(config_class=Config):
    """
    Creates and configures an instance of the Flask application, 
    including a check for Super Admin setup.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Import and register blueprints
    from .routes.admin_routes import admin_bp
    from .routes.data_capturer_routes import data_capturer_bp
    from .routes.auth_routes import auth_bp 
    from .routes.main_routes import main_bp 

    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(data_capturer_bp, url_prefix='/capturer')
    app.register_blueprint(auth_bp, url_prefix='/auth') 
    app.register_blueprint(main_bp)

    with app.app_context():
        # Create database tables if they do not exist
        db.create_all()

        # Super Admin Setup Check - runs on EVERY request
        @app.before_request
        def check_admin_setup():
            # Check if any admin exists on each request
            if Admin.query.count() == 0:
                endpoint = request.endpoint
                # Allow access only to setup page and static files
                if (
                    endpoint and 
                    'static' not in endpoint and 
                    endpoint != 'auth.setup_admin'
                ):
                    if endpoint != 'auth.login':
                        flash("System setup required. Please create the Super Admin account.", "info")
                    return redirect(url_for('auth.setup_admin'))

    return app