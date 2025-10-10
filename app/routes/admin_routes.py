from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import Admin, Campus, DataCapturer, db, Item, Room
from ..forms import AdminCreationForm, AdminEditForm, DataCapturerCreationForm, STATIC_DUT_CAMPUSES,RoomCreationForm

admin_bp = Blueprint('admin', __name__)

def super_admin_required():
    """Decorator to restrict access to Super Admins only."""
    if not current_user.is_super_admin:
        flash('Access denied. This feature is restricted to Super Administrators.', 'danger')
        return redirect(url_for('admin.admin_dashboard'))
    return None


def ensure_campuses_exist():
    """Ensures that all DUT campuses exist in the database."""
    for campus_key, campus_name in STATIC_DUT_CAMPUSES:
        # Check if campus exists by name
        existing = Campus.query.filter_by(name=campus_key).first()
        if not existing:
            new_campus = Campus(name=campus_key)
            db.session.add(new_campus)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error creating campuses: {e}")


@admin_bp.route('/')
@login_required
def admin_dashboard():
    total_capturers = DataCapturer.query.count()
    total_campuses = Campus.query.count()
    total_items = Item.query.count()

    return render_template('admin/admin_dashboard.html', 
                           total_capturers=total_capturers,
                           total_campuses=total_campuses,
                           total_items=total_items)


@admin_bp.route('/capturers')
@login_required
def manage_capturers():
    """Admin views the list of Data Capturers under their management scope."""
    
    # 1. Authorization/Scope Check
    if current_user.is_super_admin:
        # Super Admin sees ALL capturers (Query object, requires .all())
        capturer_list = DataCapturer.query.all()
    else:
        # Regular Admin sees only their assigned capturers
        # FIX: The current_user.data_capturers relationship is already a list (InstrumentedList)
        # when lazy=True. Remove the unnecessary .all().
        capturer_list = current_user.data_capturers
        
    return render_template('admin/manage_capturers.html', 
                            title='Manage Data Capturers',
                            capturer_list=capturer_list) 



@admin_bp.route('/capturers/add', methods=['GET', 'POST'])
@login_required
def add_capturer():
    """Admin creates a new Data Capturer account and assigns their scope."""
    form = DataCapturerCreationForm()
    
    if current_user.is_super_admin:
        available_campuses = Campus.query.order_by(Campus.name).all()
    else:
        available_campuses = sorted(current_user.campuses, key=lambda c: c.name)

    form.campuses_assigned.choices = [
        (str(c.campus_id), c.name) for c in available_campuses
    ]
    
    if form.validate_on_submit():
        if DataCapturer.query.filter_by(student_number=form.student_number.data).first():
            flash('Creation failed: Student number is already registered.', 'danger')
            return redirect(url_for('admin.add_capturer'))
        
        new_capturer = DataCapturer(
            full_name=form.full_name.data,
            student_number=form.student_number.data,
            admin_id=current_user.admin_id 
        )
        new_capturer.set_password(form.password.data)
        
        selected_campus_ids = [int(c_id) for c_id in form.campuses_assigned.data]
        assigned_campuses = Campus.query.filter(Campus.campus_id.in_(selected_campus_ids)).all()
        new_capturer.assigned_campuses = assigned_campuses
        
        try:
            db.session.add(new_capturer)
            db.session.commit()
            flash(f'Data Capturer "{new_capturer.full_name}" created successfully and assigned to {len(assigned_campuses)} campuses.', 'success')
            return redirect(url_for('admin.manage_capturers'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating capturer: {str(e)}', 'danger')
            
    return render_template('admin/add_capturer.html', 
                           title='Add Data Capturer',
                           form=form)



#----EDIT CAPTURER ROUTE (BASIC STRUCTURE)----
 
@admin_bp.route('/system/capturer/edit/<int:capturer_id>', methods=['GET', 'POST'])
@login_required
def edit_capturer(capturer_id):
    """Handles viewing and editing a specific Data Capturer's details."""
    
    # 1. Fetch the capturer and perform authorization checks
    capturer = DataCapturer.query.get_or_404(capturer_id)
    
    # Ensure the current user has permission to edit this capturer
    if not current_user.is_super_admin and current_user.admin_id != capturer.admin_id:
        flash('You are not authorized to edit this data capturer.', 'danger')
        return redirect(url_for('admin.manage_capturers'))

    # Initialize the form, passing the original username for validation
    form = DataCapturerCreationForm() # Note: You'll likely need an EditCapturerForm later
    
    # Logic to populate the form and handle updates will go here:
    if form.validate_on_submit():
        # Update logic...
        
        # Example of dynamic campus update logic (similar to admin update)
        # selected_campus_keys = form.campuses_assigned.data
        # campus_names_to_query = [key for key, label in STATIC_DUT_CAMPUSES if key in selected_campus_keys]
        # capturer.assigned_campuses = Campus.query.filter(Campus.name.in_(campus_names_to_query)).all()
        
        # db.session.commit()
        flash(f'Data Capturer {capturer.student_number} updated successfully.', 'success')
        return redirect(url_for('admin.manage_capturers'))

    elif request.method == 'GET':
        # Populate form fields with current capturer data
        form.full_name.data = capturer.full_name
        form.student_number.data = capturer.student_number
        # Need to select current campuses on the form
        # selected_keys = [key for key, label in STATIC_DUT_CAMPUSES if label in [c.name for c in capturer.assigned_campuses]]
        # form.campuses_assigned.data = selected_keys 
        
    return render_template('admin/edit_capturer.html', 
                           title=f'Edit Capturer: {capturer.student_number}', 
                           form=form, 
                           capturer=capturer)





@admin_bp.route('/rooms')
@login_required

def list_rooms():
    """Lists all rooms for the admin to manage (view/delete)."""
    # Fetch all rooms along with their parent campus names
    rooms = db.session.execute(
        db.select(Room, Campus.name.label('campus_name'))
        .join(Campus)
        .order_by(Campus.name, Room.name)
    ).all()
    
    return render_template('admin/list_rooms.html', rooms=rooms, title='Manage Rooms')


@admin_bp.route('/room/add', methods=['GET', 'POST'])
@login_required

def add_room():
    """Route for adding a new room to an existing campus."""
    form = RoomCreationForm()
    
    # Dynamically populate the campus selection field
    campuses = Campus.query.all()
    if not campuses:
        flash('No campuses found. Please add a campus first.', 'warning')
        return redirect(url_for('admin.add_campus'))

    form.campus.choices = [(c.campus_id, c.name) for c in campuses]
    
    if form.validate_on_submit():
        campus_id = form.campus.data
        room_name = form.name.data
        
        # Check if a room with the same name already exists on that campus
        existing_room = Room.query.filter_by(campus_id=campus_id, name=room_name).first()

        if existing_room:
            flash(f'Room "{room_name}" already exists on this campus.', 'danger')
        else:
            new_room = Room(name=room_name, campus_id=campus_id)
            db.session.add(new_room)
            db.session.commit()
            flash(f'Room "{new_room.name}" added successfully to Campus ID {campus_id}.', 'success')
            return redirect(url_for('admin.list_rooms')) # Redirect to the room list


    return render_template('admin/add_room.html', form=form, title='Add New Room')


@admin_bp.route('/room/edit/<int:room_id>', methods=['GET', 'POST'])
@login_required

def edit_room(room_id):
    """Route for editing an existing room's details."""
    room = Room.query.get_or_404(room_id)
    form = RoomCreationForm(obj=room) # Populate form with existing data
    
    # Dynamically populate the campus selection field (same as add_room)
    campuses = Campus.query.all()
    form.campus.choices = [(c.campus_id, c.name) for c in campuses]

    if form.validate_on_submit():
        new_campus_id = form.campus.data
        new_room_name = form.name.data
        
        # Check if the new name is already taken by a different room on the NEW campus
        existing_room = Room.query.filter(
            Room.room_id != room_id, # Exclude the current room
            Room.campus_id == new_campus_id,
            Room.name == new_room_name
        ).first()

        if existing_room:
            flash(f'Room "{new_room_name}" already exists on the selected campus.', 'danger')
        else:
            room.campus_id = new_campus_id
            room.name = new_room_name
            
            # Note: The form doesn't have a separate description/location field, 
            # so we only update what's in the form.
            # If you add description to Room model/form, update here.

            db.session.commit()
            flash(f'Room "{room.name}" updated successfully.', 'success')
            return redirect(url_for('admin.list_rooms'))

    # Populate form fields on GET request
    if form.campus.data is None:
        form.campus.data = room.campus_id
        
    return render_template('admin/edit_room.html', form=form, room=room, title='Edit Room')


@admin_bp.route('/campuses')
@login_required
def manage_campuses():
    return render_template('admin/manage_campuses.html', title='Manage Campuses')


@admin_bp.route('/inventory')
@login_required
def view_inventory():
    return render_template('admin/view_inventory.html', title='View All Inventory')


@admin_bp.route('/reports')
@login_required
def run_report():
    return render_template('admin/run_report.html', title='Generate Inventory Report')


# --- FIXED: Super Admin Manage Admins Route ---
@admin_bp.route('/system/admins', methods=['GET', 'POST'])
@login_required
def manage_admins():
    guard = super_admin_required()
    if guard:
        return guard
    
    # CRITICAL FIX: Ensure campuses exist before anything else
    ensure_campuses_exist()
    
    form = AdminCreationForm()
    admin_list = Admin.query.filter(Admin.is_super_admin == False).all() 
    
    if form.validate_on_submit():
        new_admin = Admin(
            username=form.username.data,
            name=form.name.data,
            surname=form.surname.data,
            is_super_admin=False 
        )
        new_admin.set_password(form.password.data)
        
        # FIXED: Get selected campus keys from form (e.g., ['Ritson', 'City'])
        selected_campus_keys = form.campuses_assigned.data
        
        # Query Campus objects where name matches the selected keys
        selected_campuses = Campus.query.filter(
            Campus.name.in_(selected_campus_keys)
        ).all()
        
        # Debug: Check if campuses were found
        if not selected_campuses:
            flash('Warning: No campuses were assigned. Please try again.', 'warning')
        
        new_admin.campuses = selected_campuses
        
        try:
            db.session.add(new_admin)
            db.session.commit()
            flash(f'New Admin account "{new_admin.username}" created and assigned to {len(selected_campuses)} campuses.', 'success')
            return redirect(url_for('admin.manage_admins'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating admin: {str(e)}', 'danger')
            
    return render_template('admin/manage_admins.html', 
                           title='Manage Administrators',
                           form=form,
                           admin_list=admin_list)


@admin_bp.route('/system/admins/edit/<int:admin_id>', methods=['GET', 'POST'])
@login_required
def edit_admin(admin_id):
    guard = super_admin_required()
    if guard:
        return guard

    admin_to_edit = Admin.query.get_or_404(admin_id)
    form = AdminEditForm(original_username=admin_to_edit.username)
    
    if form.validate_on_submit():
        admin_to_edit.name = form.name.data
        admin_to_edit.surname = form.surname.data
        admin_to_edit.username = form.username.data
        
        if form.password.data:
            admin_to_edit.set_password(form.password.data)
            
        # Update campus assignments
        selected_campus_keys = form.campuses_assigned.data
        selected_campuses = Campus.query.filter(Campus.name.in_(selected_campus_keys)).all()
        admin_to_edit.campuses = selected_campuses
            
        try:
            db.session.commit()
            flash(f'Admin "{admin_to_edit.username}" updated successfully.', 'success')
            return redirect(url_for('admin.manage_admins'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating admin: {str(e)}', 'danger')
            
    elif request.method == 'GET':
        form.name.data = admin_to_edit.name
        form.surname.data = admin_to_edit.surname
        form.username.data = admin_to_edit.username
        # Pre-select assigned campuses
        form.campuses_assigned.data = [c.name for c in admin_to_edit.campuses]
        
    return render_template('admin/edit_admin.html', 
                           title='Edit Administrator', 
                           form=form, 
                           admin=admin_to_edit)


@admin_bp.route('/system/admins/delete/<int:admin_id>', methods=['POST'])
@login_required
def delete_admin(admin_id):
    guard = super_admin_required()
    if guard:
        return guard

    if current_user.admin_id == admin_id:
        flash("You cannot delete your own account!", 'danger')
        return redirect(url_for('admin.manage_admins'))
        
    admin_to_delete = Admin.query.get_or_404(admin_id)
    
    if admin_to_delete.is_super_admin:
         flash("Cannot delete the primary Super Admin account.", 'danger')
         return redirect(url_for('admin.manage_admins'))

    try:
        db.session.delete(admin_to_delete)
        db.session.commit()
        flash(f'Admin "{admin_to_delete.username}" deleted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting admin: {str(e)}', 'danger')
        
    return redirect(url_for('admin.manage_admins'))


@admin_bp.route('/system/settings')
@login_required
def system_settings():
    guard = super_admin_required()
    if guard:
        return guard
        
    return render_template('admin/system_settings.html', title='System Settings')


@admin_bp.route('add-campus', methods=['GET', 'POST'])
@login_required 
def add_campus():
    guard = super_admin_required()
    if guard:
        return guard
    
    if request.method == 'POST':
        campus_name = request.form.get('campus_name')
        if campus_name:
            if Campus.query.filter_by(name=campus_name).first():
                flash('Campus already exists.', 'danger')
            else:
                new_campus = Campus(name=campus_name)
                try:
                    db.session.add(new_campus)
                    db.session.commit()
                    flash(f'Campus "{campus_name}" added successfully.', 'success')
                    return redirect(url_for('admin.manage_campuses'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'Error adding campus: {str(e)}', 'danger')
        else:
            flash('Campus name cannot be empty.', 'danger')
    
    return render_template('admin/add_campus.html', title='Add New Campus')




@admin_bp.route('/capturer/delete/<int:capturer_id>', methods=['POST'])
@login_required# Assuming you have a decorator to restrict access to admins
def delete_capturer(capturer_id):
    """Handles deletion (or deactivation) of a Data Capturer."""
    capturer = DataCapturer.query.get_or_404(capturer_id)
    
    # 1. Decide if you are *deleting* or *deactivating*
    
    # Simple Deletion:
    # db.session.delete(capturer)
    # flash(f"Data Capturer {capturer.full_name} deleted.", 'success')
    
    # Recommended: Deactivate (by changing an 'is_active' field in the DataCapturer model)
    # capturer.is_active = False
    # db.session.commit()
    # flash(f"Data Capturer {capturer.full_name} has been deactivated.", 'warning')

    db.session.commit() # Commit changes
    return redirect(url_for('admin.list_capturers')) # Redirect back to the list