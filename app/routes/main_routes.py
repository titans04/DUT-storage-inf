from flask import Blueprint, redirect, url_for
from flask_login import current_user
from ..models import Admin

# Initialize the Blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """
    The main landing page. 
    Redirects based on setup status and user authentication.
    """
    # Check if Super Admin setup is required
    if Admin.query.count() == 0:
        return redirect(url_for('auth.setup_admin'))

    # If setup is complete, check if user is logged in
    if current_user.is_authenticated:
        if current_user.get_id().startswith('A-'):
            # Logged in as Admin
            return redirect(url_for('admin.dashboard'))
        elif current_user.get_id().startswith('D-'):
            # Logged in as Data Capturer
            return redirect(url_for('capturer.dashboard'))
    
    # If not logged in and setup is complete, redirect to the login page
    return redirect(url_for('auth.login'))

# You can add other simple pages here, like @main_bp.route('/about')