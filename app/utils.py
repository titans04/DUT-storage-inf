from functools import wraps
from flask import flash, redirect, url_for, current_app
from flask_login import current_user
# NOTE: You do not need to import Admin or DataCapturer models here if their
# properties (is_admin, is_super_admin, etc.) are already set on the current_user object
# during Flask-Login's user loading process.


def capturer_required(f):
    """Decorator to restrict access only to Data Capturers."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # We check the 'is_data_capturer' property defined on the user model.
        if not hasattr(current_user, 'is_data_capturer') or not current_user.is_data_capturer:
            flash('Access denied. Only Data Capturers can view this page.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """
    Decorator to restrict access to Admins (including Super Admins).
    Requires the user to have the 'is_admin' property set to True.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Checks the 'is_admin' property defined on your Admin/DataCapturer models.
        if not hasattr(current_user, 'is_admin') or not current_user.is_admin:
            flash('Access denied. This action requires administrative privileges.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


def super_admin_required(f):
    """
    Decorator to restrict access only to Super Admins.
    Requires the user to have the 'is_super_admin' property set to True.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # We check for the explicit 'is_super_admin' property.
        if not (hasattr(current_user, 'is_super_admin') and current_user.is_super_admin):
            flash('Access denied. This action requires Super Administrator privileges.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function
