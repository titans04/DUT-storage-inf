from flask import Blueprint, render_template, redirect, url_for, flash, request,send_file
from flask_login import login_required, current_user
from ..models import Admin, Campus, DataCapturer, db, Item, Room, ItemStatus,ItemCategory
from ..forms import AdminCreationForm, AdminEditForm, DataCapturerCreationForm, STATIC_DUT_CAMPUSES,RoomCreationForm, EditItemForm, CampusRoomCreationForm
from ..forms import SuperAdminProfileEditForm,AdminProfileEditForm,DataCapturerEditForm,AdminEditItemForm
from flask import current_app
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError, Optional
import enum
from functools import wraps
from ..utils import admin_required, super_admin_required
# New imports needed for forms defined within this file (like CampusRoomCreationForm)
from flask_wtf import FlaskForm
from wtforms import SelectMultipleField, SubmitField
from sqlalchemy import or_ , func, and_
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename
import os
from datetime import datetime
import pandas as pd
from io import BytesIO
from sqlalchemy import func, case, literal_column, select

admin_bp = Blueprint('admin', __name__)



#---------------Super admin required----------------#
def super_admin_required():
    """Decorator to restrict access to Super Admins only."""
    if not current_user.is_super_admin:
        flash('Access denied. This feature is restricted to Super Administrators.', 'danger')
        return redirect(url_for('admin.dashboard'))
    return None

#--------------
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
def dashboard():
    """Admin dashboard showing relevant stats and management links."""

    # --- Super Admin ---
    if getattr(current_user, 'is_super_admin', False):
        campus_count = Campus.query.count()
        room_count = Room.query.count()
        capturer_count = DataCapturer.query.count()
        item_count = Item.query.count()
        admin_count = Admin.query.filter(Admin.is_super_admin == False).count()

        # Items by status
        active_items = Item.query.filter_by(status=ItemStatus.ACTIVE).count()
        inactive_items = Item.query.filter_by(status=ItemStatus.INACTIVE).count()
        needs_repair = Item.query.filter_by(status=ItemStatus.NEEDS_REPAIR).count()
        disposed_items = Item.query.filter_by(status=ItemStatus.DISPOSED).count()

        return render_template(
            'admin/admin_dashboard.html',
            campus_count=campus_count,
            room_count=room_count,
            capturer_count=capturer_count,
            item_count=item_count,
            admin_count=admin_count,
            active_items=active_items,
            inactive_items=inactive_items,
            needs_repair=needs_repair,
            disposed_items=disposed_items,
            recent_items=None
        )

    # --- Normal Admin ---
    elif getattr(current_user, 'is_admin', False):
        # Safe: only access .campuses for Admin
        managed_campuses = getattr(current_user, 'campuses', [])
        managed_campus_ids = [c.campus_id for c in managed_campuses]

        campus_count = len(managed_campus_ids)
        capturer_count = len(getattr(current_user, 'data_capturers', []))

        if managed_campus_ids:
            room_count = Room.query.filter(Room.campus_id.in_(managed_campus_ids)).count()

            scoped_room_ids = db.session.execute(
                db.select(Room.room_id).where(Room.campus_id.in_(managed_campus_ids))
            ).scalars().all()

            if scoped_room_ids:
                item_count = Item.query.filter(Item.room_id.in_(scoped_room_ids)).count()

                # Fetch last 10 items
                recent_items = Item.query.filter(
                    Item.room_id.in_(scoped_room_ids)
                ).order_by(Item.capture_date.desc()).limit(10).all()
            else:
                item_count = 0
                recent_items = []
        else:
            room_count = 0
            item_count = 0
            recent_items = []

        return render_template(
            'admin/admin_dashboard.html',
            campus_count=campus_count,
            room_count=room_count,
            capturer_count=capturer_count,
            item_count=item_count,
            recent_items=recent_items
        )

    # --- Non-admins (e.g., Data Capturers) ---
    else:
        flash('Access denied: Admins only.', 'danger')
        return redirect(url_for('main.index'))

    

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
        capturer_list = current_user.data_capturers
        
    return render_template('admin/manage_capturers.html', 
                            title='Manage Data Capturers',
                            capturer_list=capturer_list) 


#------------For regular admin to add data capturers
@admin_bp.route('/capturers/add', methods=['GET', 'POST'])
@login_required
def add_capturer():
    """Admin creates a new Data Capturer account and assigns their scope."""
    form = DataCapturerCreationForm()
    
    # Determine campuses this admin can assign
    if current_user.is_super_admin:
        available_campuses = Campus.query.order_by(Campus.name).all()
    else:
        available_campuses = sorted(current_user.campuses, key=lambda c: c.name)

    form.campuses_assigned.choices = [
        (str(c.campus_id), c.name) for c in available_campuses
    ]
    
    if form.validate_on_submit():
        # Check if student number already exists
        if DataCapturer.query.filter_by(student_number=form.student_number.data).first():
            flash('Creation failed: Student number is already registered.', 'danger')
            return redirect(url_for('admin.add_capturer'))
        
        # Create new Data Capturer instance
        new_capturer = DataCapturer(
            full_name=form.full_name.data,
            student_number=form.student_number.data,
            admin_id=current_user.admin_id,
            can_create_room=form.can_create_room.data
        )
        new_capturer.set_password(form.password.data)
        
        # Assign only the SELECTED campuses (not all available ones)
        selected_campus_ids = [int(c_id) for c_id in form.campuses_assigned.data]
        assigned_campuses = Campus.query.filter(Campus.campus_id.in_(selected_campus_ids)).all()
        new_capturer.assigned_campuses = assigned_campuses
        
        try:
            db.session.add(new_capturer)
            db.session.commit()
            
            campus_names = ', '.join([c.name for c in assigned_campuses])
            flash(
                f'Data Capturer "{new_capturer.full_name}" created successfully and assigned to: {campus_names}',
                'success'
            )
            return redirect(url_for('admin.manage_capturers'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating capturer: {str(e)}', 'danger')
            
    return render_template(
        'admin/add_capturer.html', 
        title='Add Data Capturer',
        form=form
    )



# app/routes/admin_routes.py (assuming this is where admin_bp is defined)
# app/routes/admin_routes.py
from flask import render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from sqlalchemy import func
from app.forms import AdminEditItemForm
from app.models import Item, ItemStatus
from app import db


@admin_bp.route('/item/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_item(item_id):
    """Admin edits any item — including cost, capacity, status, and dates."""
    
    item = Item.query.get_or_404(item_id)

    # === Security: Only super admin or admins managing this campus ===
    if not current_user.is_super_admin:
        managed_campus_ids = [c.campus_id for c in current_user.campuses]
        if item.room.campus_id not in managed_campus_ids:
            flash('Access denied: You do not manage this campus.', 'danger')
            return redirect(url_for('admin.view_inventory'))

    # Use the correct form with 'cost' field
    form = AdminEditItemForm(obj=item)

    # Populate status dropdown
    form.status.choices = [(s.name, s.value) for s in ItemStatus]

    # === GET: Pre-fill form ===
    if request.method == 'GET':
        form.status.data = item.status.name
        form.asset_number.data = item.asset_number
        form.serial_number.data = item.serial_number
        form.name.data = item.name
        form.brand.data = item.brand
        form.color.data = item.color
        form.capacity.data = item.capacity
        form.cost.data = item.cost  # ← CORRECT: cost → cost
        form.procured_date.data = item.Procured_date
        form.allocated_date.data = item.allocated_date
        form.description.data = item.description

    # === POST: Save changes ===
    if form.validate_on_submit():
        new_asset_number = form.asset_number.data.strip().upper()

        # Prevent duplicate asset number (except current item)
        duplicate = Item.query.filter(
            Item.item_id != item_id,
            func.lower(Item.asset_number) == new_asset_number.lower()
        ).first()

        if duplicate:
            flash(f'Asset number "{new_asset_number}" already exists.', 'danger')
            return render_template('admin/edit_item.html', item=item, form=form, title=f'Edit Item')

        try:
            # Update all fields cleanly
            item.asset_number = new_asset_number
            item.serial_number = form.serial_number.data.strip() or None
            item.name = form.name.data.strip()
            item.brand = form.brand.data.strip() or None
            item.color = form.color.data.strip() or None
            item.capacity = form.capacity.data.strip() or None
            item.description = form.description.data.strip() or None
            item.cost = form.cost.data or 0  # ← CORRECT: cost from form
            item.status = ItemStatus[form.status.data]
            item.Procured_date = form.procured_date.data
            item.allocated_date = form.allocated_date.data or None

            db.session.commit()
            flash(f'Item "{item.name}" ({item.asset_number}) updated successfully!', 'success')
            return redirect(url_for('admin.view_inventory'))

        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Item update failed: {e}")
            flash('Database error. Please try again.', 'danger')

    # === Render form ===
    return render_template(
        'admin/edit_item.html',
        title=f'Edit Item • {item.asset_number}',
        item=item,
        form=form
    )


# Edit capturer info
@admin_bp.route('/system/capturer/edit/<int:capturer_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_capturer(capturer_id):
    capturer = DataCapturer.query.get_or_404(capturer_id)

    # AUTHORIZATION: Super admin = full access
    if not current_user.is_super_admin:
        # Regular admin can only edit:
        # 1. Capturers they created (via admin_id), OR
        # 2. Capturers working in their campuses
        if capturer.admin_id != current_user.admin_id:
            user_campus_ids = {c.campus_id for c in current_user.campuses}
            capturer_campus_ids = {c.campus_id for c in capturer.assigned_campuses}
            if user_campus_ids.isdisjoint(capturer_campus_ids):
                flash('You are not authorized to edit this data capturer.', 'danger')
                return redirect(url_for('admin.manage_capturers'))

    form = DataCapturerEditForm()

    # Set campus choices
    if current_user.is_super_admin:
        campuses = Campus.query.order_by(Campus.name).all()
    else:
        campuses = current_user.campuses

    form.campuses_assigned.choices = [(c.campus_id, c.name) for c in campuses]

    if form.validate_on_submit():
        capturer.full_name = form.full_name.data
        capturer.student_number = form.student_number.data
        capturer.can_create_room = form.can_create_room.data

        if form.password.data:
            capturer.set_password(form.password.data)

        # Update assigned campuses
        selected_ids = [int(x) for x in form.campuses_assigned.data]
        capturer.assigned_campuses = Campus.query.filter(Campus.campus_id.in_(selected_ids)).all()

        db.session.commit()
        flash('Data capturer updated successfully!', 'success')
        return redirect(url_for('admin.manage_capturers'))

    elif request.method == 'GET':
        form.full_name.data = capturer.full_name
        form.student_number.data = capturer.student_number
        form.can_create_room.data = capturer.can_create_room
        form.campuses_assigned.data = [campus.campus_id for campus in capturer.assigned_campuses]

    return render_template('admin/edit_capturer.html', form=form, capturer=capturer)


@admin_bp.route('/rooms')
@login_required
def list_rooms():
    """
    List rooms with optional filters: search, campus, status.
    Returns (Room, campus_name, active_item_count)
    """
    # --- Get all campuses for dropdown (scoped to user) ---
    if current_user.is_super_admin:
        campuses = Campus.query.order_by(Campus.name).all()
    elif current_user.is_admin:
        campuses = current_user.campuses
    elif current_user.is_data_capturer and getattr(current_user, 'can_create_room', False):
        campuses = current_user.assigned_campuses
    else:
        flash('Access denied. You do not have permission to manage rooms.', 'danger')
        return redirect(url_for('main.index'))

    # --- Build base query ---
    active_count_sub = (
        func.coalesce(
            func.count(
                case((Item.status == ItemStatus.ACTIVE, Item.item_id))
            ), 0
        ).label('active_item_count')
    )

    base_select = (
        select(Room, Campus.name.label('campus_name'), active_count_sub)
        .join(Campus, Room.campus_id == Campus.campus_id)
        .outerjoin(Item, (Item.room_id == Room.room_id) & (Item.status == ItemStatus.ACTIVE))
        .group_by(Room.room_id, Campus.name)
    )

    # --- Apply user scope ---
    if not current_user.is_super_admin:
        managed_ids = [c.campus_id for c in campuses]
        if not managed_ids:
            flash('You are not assigned to manage any campuses yet.', 'warning')
            return render_template('admin/list_rooms.html', rooms=[], campuses=[], title='Manage Rooms')
        base_select = base_select.where(Room.campus_id.in_(managed_ids))

    # --- Apply filters ---
    query = base_select

    # 1. Search by room name
    search_q = request.args.get('q', '').strip()
    if search_q:
        query = query.where(Room.name.ilike(f"%{search_q}%"))

    # 2. Filter by campus
    campus_filter = request.args.get('campus_id')
    if campus_filter:
        query = query.where(Room.campus_id == int(campus_filter))

    # 3. Filter by status
    status_filter = request.args.get('status')
    if status_filter == 'active':
        query = query.where(Room.is_active == True)
    elif status_filter == 'inactive':
        query = query.where(Room.is_active == False)

    # --- Final order ---
    query = query.order_by(Campus.name, Room.name)

    # --- Execute ---
    rooms = db.session.execute(query).all()

    return render_template(
        'admin/list_rooms.html',
        rooms=rooms,
        campuses=campuses,
        title='Manage Rooms'
    )


#------------For regular admin to add rooms-----------------------#
@admin_bp.route('/room/add', methods=['GET', 'POST'])
@login_required
def add_room():
    # --- ACCESS CONTROL ---
    is_admin = getattr(current_user, 'is_admin', False)
    is_super_admin = getattr(current_user, 'is_super_admin', False)
    is_capturer_with_permission = (
        getattr(current_user, 'is_data_capturer', False) and
        getattr(current_user, 'can_create_room', False)
    )

    if not (is_super_admin or is_admin or is_capturer_with_permission):
        flash('Access denied. You do not have permission to create rooms.', 'danger')
        return redirect(url_for('main.home'))

    # --- CRITICAL: Ensure campuses exist in database ---
    ensure_campuses_exist()

    form = RoomCreationForm()

    # --- Campus choices ---
    if is_super_admin:
        # Super admin sees ALL campuses
        campuses = Campus.query.order_by(Campus.name).all()
    elif is_admin:
        # Regular admin sees only their assigned campuses
        campuses = sorted(current_user.campuses, key=lambda c: c.name)
    else:
        # Data capturer sees their assigned campuses
        campuses = sorted(current_user.assigned_campuses, key=lambda c: c.name)
        # Data capturers must provide staff info
        if not form.staff_name.validators:
            form.staff_name.validators = []
        if not form.staff_number.validators:
            form.staff_number.validators = []
        form.staff_name.validators.append(DataRequired())
        form.staff_number.validators.append(DataRequired())

    form.campus.choices = [(c.campus_id, c.name) for c in campuses]
    
    # Only check for empty campuses if NOT super admin
    if not campuses and not is_super_admin:
        flash('You are not assigned to manage any campuses.', 'warning')
        return redirect(url_for('capturer.dashboard') if is_capturer_with_permission else url_for('admin.list_rooms'))
    
    # If super admin has no campuses, something is wrong with database
    if not campuses and is_super_admin:
        flash('No campuses found in the system. Please contact support.', 'danger')
        return redirect(url_for('admin.dashboard'))

    if form.validate_on_submit():
        campus_id = int(form.campus.data)

        # --- Security check (skip for super admin) ---
        if not is_super_admin and campus_id not in [c.campus_id for c in campuses]:
            flash('Unauthorized campus selection.', 'danger')
            return redirect(url_for('admin.add_room'))

        # --- Duplicate room name check ---
        new_room_name = form.name.data.strip()
        if Room.query.filter(
            func.lower(Room.name) == new_room_name.lower(),
            Room.campus_id == campus_id
        ).first():
            campus_name = next((c.name for c in campuses if c.campus_id == campus_id), 'Unknown')
            flash(f'A room named "{new_room_name}" already exists in {campus_name}.', 'danger')
            return redirect(url_for('admin.add_room'))

        # --- Determine final faculty value ---
        faculty_value = None
        if form.faculty.data and form.faculty.data != 'other':
            faculty_value = form.faculty.data
        elif form.faculty.data == 'other' and form.faculty_other.data and form.faculty_other.data.strip():
            faculty_value = form.faculty_other.data.strip()

        # --- Create room ---
        new_room = Room(
            name=new_room_name,
            campus_id=campus_id,
            description=form.description.data.strip() if form.description.data else None,
            faculty=faculty_value,
            staff_name=form.staff_name.data.strip() if form.staff_name.data else None,
            staff_number=form.staff_number.data.strip() if form.staff_number.data else None,
            is_active=True
        )

        # --- Picture upload ---
        if 'room_picture' in request.files:
            file = request.files['room_picture']
            if file and file.filename:
                allowed = {'png', 'jpg', 'jpeg', 'gif'}
                ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
                if ext in allowed:
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"room_{timestamp}_{filename}"
                    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'rooms')
                    os.makedirs(upload_folder, exist_ok=True)
                    filepath = os.path.join(upload_folder, filename)
                    try:
                        file.save(filepath)
                        new_room.room_picture = f'/static/uploads/rooms/{filename}'
                    except Exception as e:
                        flash(f'Picture upload failed: {str(e)}', 'warning')

        try:
            db.session.add(new_room)
            db.session.commit()
            campus_name = next((c.name for c in campuses if c.campus_id == campus_id), 'Unknown')
            flash(f'Room "{new_room.name}" created in {campus_name}.', 'success')
            return redirect(url_for('capturer.dashboard') if current_user.is_data_capturer else url_for('admin.list_rooms'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error: {str(e)}', 'danger')

    return render_template(
        'admin/add_room.html',
        form=form,
        title='Add New Room',
        campuses=campuses
    )

#----------------For admin t
@admin_bp.route('/room/edit/<int:room_id>', methods=['GET', 'POST'])
@login_required
def edit_room(room_id):
    """Route for editing an existing room's details, scoped to managed campuses."""
    room = Room.query.get_or_404(room_id)
    
    # 1. Access Control Check
    is_super_admin = getattr(current_user, 'is_super_admin', False)
    
    if is_super_admin:
        managed_campus_ids = [c.campus_id for c in Campus.query.all()]
    else:
        managed_campus_ids = [c.campus_id for c in current_user.campuses]
    
    if room.campus_id not in managed_campus_ids:
        flash('Unauthorized: You do not manage the campus this room belongs to.', 'danger')
        return redirect(url_for('admin.list_rooms'))
        
    form = RoomCreationForm(obj=room)
    
    # 2. Populate form with managed campuses
    if is_super_admin:
        campuses = Campus.query.order_by(Campus.name).all()
    else:
        campuses = sorted(current_user.campuses, key=lambda c: c.name)
    
    form.campus.choices = [(c.campus_id, c.name) for c in campuses]

    if form.validate_on_submit():
        new_campus_id = int(form.campus.data)
        new_room_name = form.name.data.strip()
        
        # Check if the new name is already taken by a DIFFERENT room on the NEW campus (case-insensitive)
        existing_room = Room.query.filter(
            Room.room_id != room_id, 
            Room.campus_id == new_campus_id,
            func.lower(Room.name) == new_room_name.lower()
        ).first()

        if existing_room:
            campus_name = next((c.name for c in campuses if c.campus_id == new_campus_id), 'Unknown Campus')
            flash(f'A room named "{new_room_name}" already exists in {campus_name}. Please use a different name.', 'danger')
        else:
            # Update basic fields
            room.campus_id = new_campus_id
            room.name = new_room_name
            room.description = form.description.data.strip() if form.description.data else None
            room.staff_name = form.staff_name.data.strip() if form.staff_name.data else None
            room.staff_number = form.staff_number.data.strip() if form.staff_number.data else None
            
            # Handle room picture upload
            if 'room_picture' in request.files:
                file = request.files['room_picture']
                if file and file.filename:
                    # Delete old picture if it exists
                    if room.room_picture:
                        old_file_path = os.path.join(current_app.root_path, 'static', room.room_picture)
                        if os.path.exists(old_file_path):
                            try:
                                os.remove(old_file_path)
                            except Exception as e:
                                print(f"Could not delete old file: {e}")
                    
                    # Save new picture
                    filename = secure_filename(file.filename)
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"room_{timestamp}_{filename}"
                    
                    upload_folder = os.path.join(current_app.root_path, 'static', 'uploads', 'rooms')
                    os.makedirs(upload_folder, exist_ok=True)
                    
                    filepath = os.path.join(upload_folder, filename)
                    file.save(filepath)
                    
                    room.room_picture = f'uploads/rooms/{filename}'
            
            try:
                db.session.commit()
                flash(f'Room "{room.name}" updated successfully.', 'success')
                return redirect(url_for('admin.list_rooms'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating room: {str(e)}', 'danger')

    # Populate form fields on GET request
    if request.method == 'GET':
        form.campus.data = room.campus_id
        form.name.data = room.name
        form.description.data = room.description
        form.staff_name.data = room.staff_name
        form.staff_number.data = room.staff_number
        
    return render_template(
        'admin/edit_room.html', 
        form=form, 
        room=room, 
        title='Edit Room'
    )


#For the admin to delete the room
@admin_bp.route('/room/delete/<int:room_id>', methods=['POST'])
@login_required
@admin_required
def delete_room(room_id):
    """
    Soft-delete (deactivate) a room if it has no active items.
    Records reason for deactivation.
    """
    room = Room.query.get_or_404(room_id)
    
    deletion_reason = request.form.get('deletion_reason', '').strip()
    if not deletion_reason:
        flash('Deactivation failed: Reason is required.', 'danger')
        return redirect(url_for('admin.list_rooms'))

    # Regular admin must manage this room's campus
    if not current_user.is_super_admin:
        if room.campus_id not in [c.campus_id for c in current_user.campuses]:
            flash('Unauthorized: You do not manage this campus.', 'danger')
            return redirect(url_for('admin.list_rooms'))

    # Check for active items
    active_count = Item.query.filter_by(room_id=room_id, status=ItemStatus.ACTIVE).count()
    if active_count > 0:
        flash(f'Cannot deactivate "{room.name}". It has {active_count} active item(s).', 'danger')
        return redirect(url_for('admin.list_rooms'))

    # Soft delete
    try:
        room.is_active = False
        room.deletion_reason = deletion_reason
        db.session.commit()
        flash(f'Room "{room.name}" deactivated. Reason: {deletion_reason}', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Database error: {e}', 'danger')

    return redirect(url_for('admin.list_rooms'))



#---------------For the admin to export the data out--------------------------------#
@admin_bp.route('/items/export/<string:format>', methods=['GET'])
@login_required
@admin_required
def export_items(format):
    """Export filtered inventory — Excel & PDF — FINAL & ERROR-FREE"""
    from datetime import datetime
    from sqlalchemy import and_
    from io import BytesIO
    import pandas as pd

    # === BUILD QUERY ===
    query = db.select(Item).join(Room).join(Campus).outerjoin(DataCapturer)
    if not current_user.is_super_admin:
        query = query.where(Room.campus_id.in_([c.campus_id for c in current_user.campuses]))

    # Allocated Date filter
    alloc_filters = []
    if alloc_from := request.args.get("alloc_from"):
        try:
            alloc_filters.append(Item.allocated_date >= datetime.strptime(alloc_from, "%Y-%m-%d").date())
        except:
            pass
    if alloc_to := request.args.get("alloc_to"):
        try:
            alloc_filters.append(Item.allocated_date <= datetime.strptime(alloc_to, "%Y-%m-%d").date())
        except:
            pass
    if alloc_filters:
        query = query.where(and_(*alloc_filters))

    items = db.session.execute(query).scalars().all()
    if not items:
        flash("No items match your filters to export.", "info")
        return redirect(url_for('admin.view_inventory'))

    # === BUILD DATAFRAME ===
    data = []
    for i in items:
        data.append({
            "Asset No.": i.asset_number or "",
            "Serial No.": i.serial_number or "",
            "Name": i.name,
            "Brand": i.brand or "",
            "Color": i.color or "",
            "Capacity/Specs": i.capacity or "",
            "Category": i.category.value if i.category else "",
            "Cost (R)": float(i.cost) if i.cost else 0.00,
            "Status": i.status.value,
            "Captured By": i.data_capturer.full_name if i.data_capturer else "",
            "Room": i.room.name,
            "Campus": i.room.campus.name,
            "Room Staff": i.room.staff_name or "",
            "Staff ID": i.room.staff_number or "",
            "Procured Date": i.Procured_date.strftime("%Y-%m-%d") if i.Procured_date else "",
            "Allocated Date": i.allocated_date.strftime("%Y-%m-%d") if i.allocated_date else "Not Allocated",
            "Captured Date": i.capture_date.strftime("%Y-%m-%d") if i.capture_date else "",
        })

    df_full = pd.DataFrame(data)

    # === COLUMN SELECTION ===
    selected_columns = request.args.getlist('columns')
    if not selected_columns:
        selected_columns = [
            "Asset No.", "Serial No.", "Name", "Brand", "Color",
            "Capacity/Specs", "Category", "Cost (R)", "Status",
            "Room", "Campus", "Room Staff", "Staff ID",
            "Procured Date", "Allocated Date", "Captured Date"
        ]

    df_export = df_full[selected_columns].copy()

    # Always include Name & Status for summary
    if 'Name' not in df_export.columns:
        df_export.insert(0, 'Name', df_full['Name'])
    if 'Status' not in df_export.columns:
        df_export.insert(1 if 'Name' in df_export.columns else 0, 'Status', df_full['Status'])

    df_summary = df_export.groupby(['Name', 'Status']).size().reset_index(name='Count')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    # =============================================
    # EXCEL EXPORT — PERFECT, NO DUPLICATES
    # =============================================
    if format == "xlsx":
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            navy = '#001F3F'

            header_fmt = workbook.add_format({
                'bg_color': navy, 'font_color': 'white', 'bold': True, 'border': 1,
                'align': 'center', 'valign': 'vcenter', 'text_wrap': True, 'font_size': 11
            })
            money_fmt = workbook.add_format({'num_format': 'R#,##0.00', 'border': 1})
            date_fmt = workbook.add_format({'num_format': 'yyyy-mm-dd', 'border': 1})

            # Inventory Sheet
            df_export.to_excel(writer, sheet_name='Inventory', index=False, startrow=1, header=False)
            sheet = writer.sheets['Inventory']

            for col_num, value in enumerate(df_export.columns):
                sheet.write(0, col_num, value, header_fmt)

            col_widths = {
                "Asset No.": 18, "Serial No.": 25, "Name": 35, "Brand": 16, "Color": 12,
                "Capacity/Specs": 28, "Category": 20, "Cost (R)": 15, "Status": 14,
                "Captured By": 22, "Room": 20, "Campus": 18, "Room Staff": 22,
                "Staff ID": 14, "Procured Date": 15, "Allocated Date": 16, "Captured Date": 15
            }
            for i, col in enumerate(df_export.columns):
                sheet.set_column(i, i, col_widths.get(col, 18))

            sheet.freeze_panes(1, 0)

            # Summary Sheet
            df_summary.to_excel(writer, sheet_name='Summary', index=False, startrow=4, header=False)
            s = writer.sheets['Summary']
            big_title = workbook.add_format({'bold': True, 'font_size': 18, 'font_color': navy, 'align': 'center'})
            s.merge_range('A1:C1', 'SUMMARY BY ITEM & STATUS', big_title)
            s.set_row(0, 35)
            for c, h in enumerate(["Item Name", "Status", "Total Count"]):
                s.write(4, c, h, header_fmt)
            s.set_row(4, 28)
            for r, row in enumerate(df_summary.itertuples(index=False), start=5):
                s.write(r, 0, row.Name)
                s.write(r, 1, row.Status)
                s.write(r, 2, row.Count)
            s.set_column('A:A', 50); s.set_column('B:B', 22); s.set_column('C:C', 18)

        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"DUT_Inventory_{timestamp}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # =============================================
    # PDF EXPORT — CLEAN & BEAUTIFUL
    # =============================================
    elif format == "pdf":
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A3, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib.enums import TA_CENTER

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(A3),
                                topMargin=1.5*cm, bottomMargin=1.5*cm,
                                leftMargin=1*cm, rightMargin=1*cm)
        styles = getSampleStyleSheet()

        # Custom styles
        styles.add(ParagraphStyle(name='BigTitle', parent=styles['Title'], fontSize=26, textColor=colors.HexColor('#001F3F'), alignment=TA_CENTER, spaceAfter=30))
        styles.add(ParagraphStyle(name='Heading', parent=styles['Heading2'], fontSize=18, textColor=colors.HexColor('#001F3F'), spaceAfter=15))
        styles.add(ParagraphStyle(name='SumCell', fontSize=15, alignment=TA_CENTER, leading=18))
        styles.add(ParagraphStyle(name='Hdr', fontSize=10.5, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_CENTER, leading=13))
        styles.add(ParagraphStyle(name='Cell', fontSize=9.5, alignment=TA_CENTER, leading=12))

        elements = []

        elements.append(Paragraph("DUT INVENTORY REPORT", styles["BigTitle"]))
        elements.append(Paragraph(f"Generated: {datetime.now().strftime('%d %B %Y at %H:%M')} • Total Items: {len(df_export)}", styles["Normal"]))
        elements.append(Spacer(1, 1*cm))

        # Summary
        elements.append(Paragraph("SUMMARY BY ITEM & STATUS", styles["Heading"]))
        sum_data = [[Paragraph("<b>Item Name</b>", styles["SumCell"]),
                     Paragraph("<b>Status</b>", styles["SumCell"]),
                     Paragraph("<b>Total Count</b>", styles["SumCell"])]]
        for _, r in df_summary.iterrows():
            sum_data.append([Paragraph(str(r['Name']), styles["SumCell"]),
                             Paragraph(str(r['Status']), styles["SumCell"]),
                             Paragraph(str(r['Count']), styles["SumCell"])])

        sum_table = Table(sum_data, colWidths=[11*cm, 8*cm, 6*cm])
        sum_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#001F3F')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 2.5, colors.black),
            ('BOX', (0,0), (-1,-1), 3, colors.black),
            ('FONTSIZE', (0,0), (-1,-1), 16),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f0f4f8')]),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
        ]))
        elements.append(sum_table)
        elements.append(PageBreak())

        # Detailed Table
        elements.append(Paragraph("DETAILED INVENTORY LISTING", styles["Heading"]))
        detail_data = [[Paragraph(col, styles["Hdr"]) for col in df_export.columns]]
        for _, row in df_export.iterrows():
            detail_data.append([Paragraph(str(val) if val not in ['', None] else '-', styles["Cell"]) for val in row])

        num_cols = len(df_export.columns)
        col_width = 37.0 / num_cols
        col_widths = [col_width * cm for _ in range(num_cols)]

        detail_table = Table(detail_data, colWidths=col_widths, repeatRows=1)
        detail_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#001F3F')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 1.2, colors.black),
            ('BOX', (0,0), (-1,-1), 2.8, colors.black),
            ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f8f9fa')]),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('FONTSIZE', (0,0), (-1,0), 10.5),
            ('FONTSIZE', (0,1), (-1,-1), 9.5),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('RIGHTPADDING', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ]))
        elements.append(detail_table)

        doc.build(elements)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True,
                         download_name=f"DUT_Inventory_{timestamp}.pdf",
                         mimetype="application/pdf")

    flash("Invalid format. Use 'xlsx' or 'pdf'.", "danger")
    return redirect(url_for('admin.view_inventory'))


# ------------------Manage Campuses Route ----------------#
@admin_bp.route('/campuses', methods=['GET', 'POST'])
@login_required
def manage_campuses():
    """
    Allows Admin to view their managed campuses and set room creation privileges 
    for Data Capturers.
    """
    
    # 1. Determine Scope: Get all available campuses for this Admin
    if current_user.is_super_admin:
        # Super Admin sees and configures all (Query object needs .all())
        managed_campuses = Campus.query.order_by(Campus.name).all()
    else:
        # Regular Admin only sees and configures their assigned campuses
        # FIX: The relationship property returns a list-like object, NOT a Query object.
        managed_campuses = current_user.campuses 
    
    form = CampusRoomCreationForm()
    
    # 2. Populate choices dynamically with (value, display_text)
    form.allowed_campuses.choices = [
        (c.campus_id, c.name) 
        for c in managed_campuses
    ]

    # --- Handle POST (Form Submission) ---
    if form.validate_on_submit():
        selected_ids = [int(id) for id in form.allowed_campuses.data]
        
        try:
            # Step A: Disable room creation for all currently managed campuses
            # This ensures unselected campuses are properly disabled.
            for campus in managed_campuses:
                # Assuming the Campus model has 'room_creation_enabled' field
                campus.room_creation_enabled = False
            
            # Step B: Re-enable creation for only the selected campuses
            for campus_id in selected_ids:
                # Find the specific campus object in the list for update
                campus_to_update = next((c for c in managed_campuses if c.campus_id == campus_id), None)
                if campus_to_update:
                    campus_to_update.room_creation_enabled = True
            
            db.session.commit()
            flash('Campus room creation privileges updated successfully!', 'success')
            return redirect(url_for('admin.manage_campuses'))

        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred while updating permissions: {str(e)}', 'danger')

    # --- Handle GET (Initial Page Load) ---
    else:
        # Pre-select checkboxes based on current DB state
        # The managed_campuses list is used here, which is the output of the 'if/else' above.
        enabled_ids = [c.campus_id for c in managed_campuses if hasattr(c, 'room_creation_enabled') and c.room_creation_enabled]
        form.allowed_campuses.data = enabled_ids

    return render_template(
        'admin/manage_campuses.html', 
        title='Manage Campuses & Privileges',
        campuses=managed_campuses,
        form=form # Pass the form to the template
    )



#------------------View Inventory Route ----------------#
@admin_bp.route('/inventory')
@login_required
@admin_required
def view_inventory():
    """
    Ultimate Admin Inventory Dashboard
    Now with Allocated Date filter + display
    """
    from datetime import datetime
    from sqlalchemy import and_, or_

    # === 1. Base Query ===
    query = db.select(Item) \
        .join(Room, Item.room_id == Room.room_id) \
        .join(Campus, Room.campus_id == Campus.campus_id) \
        .outerjoin(DataCapturer, Item.data_capturer_id == DataCapturer.data_capturer_id)

    # === 2. Admin Scope ===
    if current_user.is_super_admin:
        managed_campuses = Campus.query.order_by(Campus.name).all()
        managed_capturers = DataCapturer.query.order_by(DataCapturer.full_name).all()
    else:
        managed_campuses = current_user.campuses
        managed_capturers = current_user.data_capturers
        query = query.where(Room.campus_id.in_([c.campus_id for c in managed_campuses]))

    managed_campus_ids = [c.campus_id for c in managed_campuses]
    current_filters = {}

    # === 3. ALL FILTERS (including new Allocated Date range) ===

    # Campus
    if (campus_id := request.args.get("campus_id")) and campus_id.isdigit():
        campus_id = int(campus_id)
        if current_user.is_super_admin or campus_id in managed_campus_ids:
            query = query.where(Room.campus_id == campus_id)
            current_filters['campus_id'] = campus_id

    # Room
    if (room_id := request.args.get("room_id")) and room_id.isdigit():
        query = query.where(Item.room_id == int(room_id))
        current_filters['room_id'] = int(room_id)

    # Status
    if (status := request.args.get("status")) and status != "all":
        try:
            query = query.where(Item.status == ItemStatus[status.upper()])
            current_filters['status'] = status
        except KeyError:
            flash("Invalid status filter.", "warning")

    # Category
    if (category := request.args.get("category")) and category != "all":
        try:
            query = query.where(Item.category == ItemCategory[category.upper()])
            current_filters['category'] = category
        except KeyError:
            flash("Invalid category selected.", "warning")

    # Data Capturer
    if capturer := request.args.get("capturer"):
        subq = db.select(DataCapturer.data_capturer_id).where(
            or_(
                DataCapturer.full_name.ilike(f"%{capturer}%"),
                DataCapturer.student_number.ilike(f"%{capturer}%")
            )
        ).scalar_subquery()
        query = query.where(Item.data_capturer_id.in_(subq))
        current_filters['capturer'] = capturer

    # Responsible Staff
    if staff := request.args.get("staff"):
        query = query.where(
            or_(
                Room.staff_name.ilike(f"%{staff}%"),
                Room.staff_number.ilike(f"%{staff}%")
            )
        )
        current_filters['staff'] = staff

    # Cost Range
    if min_cost := request.args.get("min_cost"):
        try:
            query = query.where(Item.cost >= float(min_cost))
            current_filters['min_cost'] = min_cost
        except (ValueError, TypeError):
            flash("Invalid minimum cost.", "warning")

    if max_cost := request.args.get("max_cost"):
        try:
            query = query.where(Item.cost <= float(max_cost))
            current_filters['max_cost'] = max_cost
        except (ValueError, TypeError):
            flash("Invalid maximum cost.", "warning")

    # Procurement Date Range
    if date_from := request.args.get("date_from"):
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d").date()
            query = query.where(Item.Procured_date >= start)
            current_filters['date_from'] = date_from
        except ValueError:
            flash("Invalid 'From' procurement date.", "warning")

    if date_to := request.args.get("date_to"):
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d").date()
            query = query.where(Item.Procured_date <= end)
            current_filters['date_to'] = date_to
        except ValueError:
            flash("Invalid 'To' procurement date.", "warning")

    # === NEW: Allocated Date Range Filter ===
    if alloc_from := request.args.get("alloc_from"):
        try:
            start = datetime.strptime(alloc_from, "%Y-%m-%d").date()
            query = query.where(Item.allocated_date >= start)
            current_filters['alloc_from'] = alloc_from
        except ValueError:
            flash("Invalid 'Allocated From' date.", "warning")

    if alloc_to := request.args.get("alloc_to"):
        try:
            end = datetime.strptime(alloc_to, "%Y-%m-%d").date()
            query = query.where(Item.allocated_date <= end)
            current_filters['alloc_to'] = alloc_to
        except ValueError:
            flash("Invalid 'Allocated To' date.", "warning")

    # === 4. Execute Query ===
    query = query.order_by(
        Campus.name,
        Room.name,
        Item.capture_date.desc()
    )

    items = db.session.execute(query).scalars().all()

    # === 5. Dropdown Data ===
    all_managed_rooms = Room.query.filter(
        Room.campus_id.in_(managed_campus_ids)
    ).order_by(Room.name).all()

    status_choices = [(s.name.lower(), s.value.replace(" ", " ").title()) for s in ItemStatus]
    category_choices = [(c.name.lower(), c.value) for c in ItemCategory]

    return render_template(
        'admin/view_inventory.html',
        title='Inventory Dashboard',
        items=items,
        managed_campuses=managed_campuses,
        managed_rooms=all_managed_rooms,
        managed_capturers=managed_capturers,
        status_choices=status_choices,
        category_choices=category_choices,
        current_filters=current_filters
    )

@admin_bp.route('/reports')
@login_required
def run_report():
    return render_template('admin/run_report.html', title='Generate Inventory Report')


# --- Super Admin Manage Admins Route --------------------#
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

#-------------------Super admin can updated or edit the regular admin------------------------#
@admin_bp.route('/system/admins/edit/<int:admin_id>', methods=['GET', 'POST'])
@login_required
def edit_admin(admin_id):
    """Edit an existing admin's details and campus assignments."""
    admin = Admin.query.get_or_404(admin_id)
    form = AdminEditForm(original_username=admin.username)

    # Load campus choices dynamically
    campuses = Campus.query.all()
    form.campuses_assigned.choices = [(c.name, c.name) for c in campuses]

    # Pre-fill form fields on GET
    if request.method == 'GET':
        form.name.data = admin.name
        form.surname.data = admin.surname
        form.username.data = admin.username
        form.campuses_assigned.data = [c.name for c in admin.campuses]

    if form.validate_on_submit():
        # Update basic info
        admin.name = form.name.data
        admin.surname = form.surname.data
        admin.username = form.username.data

        # Update password if provided
        if form.password.data:
            admin.set_password(form.password.data)

        # Update campuses
        selected_names = form.campuses_assigned.data
        selected_campuses = Campus.query.filter(Campus.name.in_(selected_names)).all()
        admin.campuses = selected_campuses

        db.session.commit()
        flash('Admin details updated successfully.', 'success')
        return redirect(url_for('admin.manage_admins'))

    return render_template('admin/edit_admin.html', form=form, admin=admin)



#-------------------Super Admin can delete the regular admin
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



#-------------------Admin Delete the Data Capturer--------------------#
@admin_bp.route('/capturer/delete/<int:capturer_id>', methods=['POST'])
@login_required
def delete_capturer(capturer_id):
    """
    Handles permanent deletion of a Data Capturer.
    NOTE: Permanent deletion is used because the DataCapturer model does not 
    contain an 'is_active' field for simple deactivation.
    """
    capturer = DataCapturer.query.get_or_404(capturer_id)
    
    try:
        # Action: Permanent Deletion (matches model structure)
        # SQLAlchemy will automatically handle cascading deletes if configured, 
        # or raise an error if foreign key constraints are violated (e.g., if items are linked).
        db.session.delete(capturer)
        
        db.session.commit()
        
        # Use capturer.full_name for the message
        flash(f"Data Capturer **{capturer.full_name}** deleted permanently. All associated items remain.", 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting capturer: {e}")
        
        # Check for Foreign Key errors often caused by permanent deletion
        if "ForeignKeyConstraint" in str(e) or "IntegrityError" in str(e):
             flash('Cannot delete capturer: items or other records are still linked. Please update their associated items before deleting this account, or consider adding an "is_active" field to the DataCapturer model for deactivation.', 'danger')
        else:
             flash('An unexpected error occurred during deletion. Please check the server logs.', 'danger')
        
    # Redirect back to the list after the action
    return redirect(url_for('admin.manage_capturers'))



@admin_bp.route('/system/settings', methods=['GET', 'POST'])
@login_required
def system_settings():
    from app.forms import SuperAdminProfileEditForm, AdminProfileEditForm
    
    if current_user.is_super_admin:
        form = SuperAdminProfileEditForm()
    else:
        form = AdminProfileEditForm()
    
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash('Current password is incorrect.', 'error')
            return redirect(url_for('admin.system_settings'))
        
        current_user.name = form.name.data
        current_user.surname = form.surname.data
        current_user.username = form.username.data
        
        if form.new_password.data:
            current_user.set_password(form.new_password.data)
        
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('admin.system_settings'))
    
    elif request.method == 'GET':
        form.name.data = current_user.name
        form.surname.data = current_user.surname
        form.username.data = current_user.username
    
    return render_template('admin/system_settings.html', form=form, title='Settings')