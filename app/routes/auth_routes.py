from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user, login_required
from ..forms import SuperAdminSetupForm, LoginForm,RoomCreationForm
# REMOVED TOP-LEVEL IMPORT: from ..models import db, Admin, DataCapturer 

# 1. Initialize the Blueprint (This MUST be the first thing defined)
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# Helper function to break circular import dependencies
def get_auth_models():
    """Locally imports models only when needed by a function."""
    from ..models import db, Admin, DataCapturer
    return db, Admin, DataCapturer


# In project/app/routes/auth_routes.py

@auth_bp.route('/setup', methods=['GET', 'POST'])
def setup_admin():
    db, Admin, DataCapturer = get_auth_models() 
    
    # Instantiate the form
    form = SuperAdminSetupForm() 

    """Handles the initial creation of the Super Admin account."""
    if Admin.query.count() > 0:
        flash('System setup is already complete.', 'warning')
        return redirect(url_for('auth.login'))

    # Use form.validate_on_submit() for POST handling and validation
    if form.validate_on_submit():
        # Data is valid, pull directly from form data
        username = form.username.data 
        password = form.password.data 
        name = form.name.data
        surname = form.surname.data
        
        # Create the Super Admin
        new_admin = Admin(
            username=username,
            # 👇 UPDATED: Use the collected form data instead of hardcoded strings
            name=name, 
            surname=surname,
            is_super_admin=True
        )
        new_admin.set_password(password)
        
        try:
            db.session.add(new_admin)
            db.session.commit()
            flash('Super Admin account created successfully! Please log in.', 'success')
            return redirect(url_for('auth.login'))
        except Exception as e:
            db.session.rollback()
            # Check for specific integrity errors if necessary
            flash(f'An error occurred during setup. Please try again. Error: {str(e)}', 'danger')
            # Fall through to render_template below, passing the form again

    # Render template, passing the form object
    return render_template('auth/setup_admin.html', title='System Setup', form=form)



# 3. Normal Login Route
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    db, Admin, DataCapturer = get_auth_models()
    
    
    form = LoginForm()

    # 1. Check if setup is needed
    if Admin.query.count() == 0:
        return redirect(url_for('auth.setup_admin'))

    # 2. Check if already authenticated
    # This logic prevents the infinite redirect loop
    if current_user.is_authenticated:
        if current_user.get_id().startswith('A-'):
            return redirect(url_for('admin.dashboard')) 
        elif current_user.get_id().startswith('D-'):
            return redirect(url_for('capturer.dashboard'))
            
    # 3. Handle login attempt (using form.validate_on_submit())
    if form.validate_on_submit(): # This handles the POST request and field validation
        # Data is valid, pull directly from form data
        email_or_id = form.email_or_id.data 
        password = form.password.data
        remember = form.remember_me.data # Boolean value

        # Attempt to find Admin by username
        user = Admin.query.filter_by(username=email_or_id).first()
        is_admin = True
        
        # If not found, attempt to find Data Capturer by student_number
        if not user:
            user = DataCapturer.query.filter_by(student_number=email_or_id).first()
            is_admin = False

        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f'{ "Admin" if is_admin else "Data Capturer"} login successful!', 'success')
            
            # The 'next' argument handles redirection after a @login_required page forces a login
            redirect_url = url_for('admin.dashboard') if is_admin else url_for('capturer.dashboard')
            return redirect(request.args.get('next') or redirect_url)

        # Login failed (Flask-WTF validation passed, but credentials failed)
        flash('Login failed. Check your username/ID and password.', 'danger')
        # Fall through to the return below

    # Render template, passing the form object
    return render_template('auth/login.html', title='Login', form=form)


# 4. Logout Route
@auth_bp.route('/logout')
@login_required 
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))