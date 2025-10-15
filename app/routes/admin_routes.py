from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import Admin, Campus, DataCapturer, db, Item, Room, ItemStatus
from ..forms import AdminCreationForm, AdminEditForm, DataCapturerCreationForm, STATIC_DUT_CAMPUSES,RoomCreationForm, EditItemForm, CampusRoomCreationForm
from ..forms import SuperAdminProfileEditForm,AdminProfileEditForm,DataCapturerEditForm
from flask import current_app
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError, Optional
import enum
from functools import wraps
from ..utils import admin_required, super_admin_required
# New imports needed for forms defined within this file (like CampusRoomCreationForm)
from flask_wtf import FlaskForm
from wtforms import SelectMultipleField, SubmitField
from sqlalchemy import or_ , func
from sqlalchemy.exc import IntegrityError


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
    
    if current_user.is_super_admin:
        # Super Admin: Global system statistics
        campus_count = Campus.query.count()
        room_count = Room.query.count()
        capturer_count = DataCapturer.query.count()
        item_count = Item.query.count()
        admin_count = Admin.query.filter(Admin.is_super_admin == False).count()
        
        # Items by status (for system health overview)
        active_items = Item.query.filter_by(status=ItemStatus.ACTIVE).count()
        inactive_items = Item.query.filter_by(status=ItemStatus.INACTIVE).count()
        needs_repair = Item.query.filter_by(status=ItemStatus.NEEDS_REPAIR).count()
        disposed_items = Item.query.filter_by(status=ItemStatus.DISPOSED).count()
        
        return render_template('admin/admin_dashboard.html',
                            campus_count=campus_count,
                            room_count=room_count,
                            capturer_count=capturer_count,
                            item_count=item_count,
                            admin_count=admin_count,
                            active_items=active_items,
                            inactive_items=inactive_items,
                            needs_repair=needs_repair,
                            disposed_items=disposed_items,
                            recent_items=None)
    else:
        # Normal Admin: Scoped to managed campuses
        managed_campus_ids = [c.campus_id for c in current_user.campuses]
        
        campus_count = len(managed_campus_ids)
        capturer_count = len(current_user.data_capturers)
        
        if managed_campus_ids:
            room_count = Room.query.filter(Room.campus_id.in_(managed_campus_ids)).count()
            
            scoped_room_ids = db.session.execute(
                db.select(Room.room_id).where(Room.campus_id.in_(managed_campus_ids))
            ).scalars().all()
            
            if scoped_room_ids:
                item_count = Item.query.filter(Item.room_id.in_(scoped_room_ids)).count()
                
                # Fetch recent items (last 10) for quick review
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
        
        return render_template('admin/admin_dashboard.html',
                            campus_count=campus_count,
                            room_count=room_count,
                            capturer_count=capturer_count,
                            item_count=item_count,
                            recent_items=recent_items)
    

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



#--------------------Edit Item(admin)
# app/routes/admin_routes.py (assuming this is where admin_bp is defined)

@admin_bp.route('/item/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
# Consider adding an @admin_required decorator for security
def edit_item(item_id):
    """Admin edits item details including price and status."""
    
    # 1. Fetch the item
    item = Item.query.get_or_404(item_id)
    form = EditItemForm(obj=item)
    
    # 2. Populate status choices with ALL options (including DISPOSED)
    # ItemStatus.choices() is often the preferred way if it returns (value, label)
    # The list comprehension provided is also correct if ItemStatus is a standard enum:
    form.status.choices = [
        (status.name, status.value) 
        for status in ItemStatus
    ]
    
    # 3. Pre-select current status on GET request
    if request.method == 'GET':
        # This line ensures the current status, e.g., 'DISPOSED', is shown
        form.status.data = item.status.name 

    if form.validate_on_submit():
        try:
            # 4. Update all item attributes, including the Admin-exclusive fields:
            item.name = form.name.data
            item.brand = form.brand.data
            item.asset_number = form.asset_number.data
            item.serial_number = form.serial_number.data # Ensure serial_number is also updated if available on the form
            item.description = form.description.data
            item.color = form.color.data or None
            
            #
            item.price = form.price.data
            
            
            item.status = ItemStatus[form.status.data]
            
            # If the form includes allocated_date, add it here too:
            # item.allocated_date = form.allocated_date.data

            # 5. Commit the changes
            db.session.commit()
            
            flash(f'Item "{item.name}" (Asset #{item.asset_number}) successfully updated.', 'success')
            # Assuming 'admin.view_inventory' is the correct redirect target
            return redirect(url_for('admin_bp.view_inventory')) 

        except Exception as e:
            db.session.rollback() 
            print(f"Database update failed: {e}") 
            flash('An unexpected error occurred while updating the item. Please check the server logs.', 'danger')
    
    # 6. Render the form
    return render_template(
        'admin/edit_item.html', 
        item=item, 
        form=form, 
        title=f'Edit Item: {item.asset_number}'
    )


#Edit capturers info 
# Edit capturer info
@admin_bp.route('/system/capturer/edit/<int:capturer_id>', methods=['GET', 'POST'])
@login_required
def edit_capturer(capturer_id):
    # 1. Fetch the capturer and perform authorization checks
    capturer = DataCapturer.query.get_or_404(capturer_id)
    
    # Ensure the current user has permission to edit this capturer
    if not current_user.is_super_admin and current_user.admin_id != capturer.admin_id:
        flash('You are not authorized to edit this data capturer.', 'danger')
        return redirect(url_for('admin.manage_capturers'))

    # Use DataCapturerEditForm and pass the required argument
    form = DataCapturerEditForm(original_student_number=capturer.student_number)  # Fix: Pass the original student number
    
    # Determine available campuses based on the admin's scope
    if current_user.is_super_admin:
        available_campuses = Campus.query.order_by(Campus.name).all()
    else:
        available_campuses = sorted(current_user.campuses, key=lambda c: c.name)
    
    form.campuses_assigned.choices = [
        (str(c.campus_id), c.name) for c in available_campuses
    ]
    
    if form.validate_on_submit():
        try:
            # Update basic fields
            capturer.full_name = form.full_name.data
            capturer.student_number = form.student_number.data  # This will be validated against original_student_number
            
            # Update password only if provided
            if form.password.data:  # Assuming the form has a password field that's optional
                capturer.set_password(form.password.data)
            
            # Update assigned campuses (similar to add_capturer)
            selected_campus_ids = [int(c_id) for c_id in form.campuses_assigned.data]
            assigned_campuses = Campus.query.filter(Campus.campus_id.in_(selected_campus_ids)).all()
            capturer.assigned_campuses = assigned_campuses  # This assumes a relationship like in your models
            
            # Update can_create_room if it's in the form
            if hasattr(form, 'can_create_room'):
                capturer.can_create_room = form.can_create_room.data
            
            db.session.commit()
            flash(f'Data Capturer {capturer.student_number} updated successfully.', 'success')
            return redirect(url_for('admin.manage_capturers'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating capturer: {str(e)}', 'danger')
    
    elif request.method == 'GET':
        # Populate form fields with current capturer data
        form.full_name.data = capturer.full_name
        form.student_number.data = capturer.student_number  # Pre-fill with current value
        
        # Pre-select current campuses
        current_campus_ids = [str(c.campus_id) for c in capturer.assigned_campuses]
        form.campuses_assigned.data = current_campus_ids  # This should pre-select the checkboxes or multi-select field
        
        # Pre-select can_create_room if applicable
        if hasattr(form, 'can_create_room'):
            form.can_create_room.data = capturer.can_create_room  # Assuming it's a boolean field
    
    return render_template('admin/edit_capturer.html', 
                            title=f'Edit Capturer: {capturer.student_number}', 
                            form=form, 
                            capturer=capturer)
#Bandile Cele


#---------For viewing rooms
@admin_bp.route('/rooms')
@login_required
def list_rooms():
    """Lists all rooms for the admin to manage (view/delete), scoped by assigned campus."""
    
    # Determine which campuses the user can access
    if current_user.is_super_admin:
        # Super Admin can see ALL rooms (not assigned to specific campuses)
        rooms_query = db.select(Room, Campus.name.label('campus_name')) \
                        .join(Campus) \
                        .order_by(Campus.name, Room.name)
    elif current_user.is_admin:
        # Regular Admin can only see rooms in their assigned campuses
        managed_campus_ids = [c.campus_id for c in current_user.campuses]
        
        if not managed_campus_ids:
            flash('You are not assigned to manage any campuses yet.', 'warning')
            return render_template('admin/list_rooms.html', rooms=[], title='Manage Rooms')
        
        rooms_query = db.select(Room, Campus.name.label('campus_name')) \
                        .join(Campus) \
                        .where(Room.campus_id.in_(managed_campus_ids)) \
                        .order_by(Campus.name, Room.name)
    elif current_user.is_data_capturer and getattr(current_user, 'can_create_room', False):
        # Data Capturer with permission can see rooms in their assigned campuses
        managed_campus_ids = [c.campus_id for c in current_user.assigned_campuses]
        
        if not managed_campus_ids:
            flash('You are not assigned to manage any campuses yet.', 'warning')
            return render_template('admin/list_rooms.html', rooms=[], title='Manage Rooms')
        
        rooms_query = db.select(Room, Campus.name.label('campus_name')) \
                        .join(Campus) \
                        .where(Room.campus_id.in_(managed_campus_ids)) \
                        .order_by(Campus.name, Room.name)
    else:
        # No permission to access rooms
        flash('Access denied. You do not have permission to manage rooms.', 'danger')
        return redirect(url_for('main.index'))

    rooms = db.session.execute(rooms_query).all()
    
    return render_template('admin/list_rooms.html', rooms=rooms, title='Manage Rooms')


#------------For regular admin to add rooms-----------------------#
@admin_bp.route('/room/add', methods=['GET', 'POST'])
@login_required
def add_room():
    """
    Allows Super Admin, Regular Admin, and Data Capturers (with permission) 
    to create rooms in their assigned campuses.
    """
    
    # 1. Access Control
    is_admin = getattr(current_user, 'is_admin', False)
    is_capturer_with_permission = (
        getattr(current_user, 'is_data_capturer', False) and 
        getattr(current_user, 'can_create_room', False)
    )
    
    if not (is_admin or is_capturer_with_permission):
        flash('Access denied. You do not have permission to create rooms.', 'danger')
        return redirect(url_for('main.home'))
    
    form = RoomCreationForm()

    # 2. Determine available campuses based on user scope
    is_super_admin = getattr(current_user, 'is_super_admin', False)
    
    if is_super_admin:
        campuses = Campus.query.order_by(Campus.name).all()
    elif is_admin:
        campuses = sorted(current_user.campuses, key=lambda c: c.name)
    else: # Data Capturer
        campuses = sorted(current_user.assigned_campuses, key=lambda c: c.name)
        # Make staff fields required for capturers
        form.staff_name.validators.append(DataRequired())
        form.staff_number.validators.append(DataRequired())
    
    form.campus.choices = [(c.campus_id, c.name) for c in campuses]
    
    # 3. Handle empty campus list
    if not campuses:
        flash('You are not assigned to manage any campuses. Contact your administrator.', 'warning')
        return redirect(url_for('admin.list_rooms'))

    # 4. Handle form submission
    if form.validate_on_submit():
        campus_id = int(form.campus.data)
        
        # Security: Verify the selected campus is in the user's scope
        if not is_super_admin:
            allowed_campus_ids = [c.campus_id for c in campuses]
            if campus_id not in allowed_campus_ids:
                flash('Unauthorized: You cannot create rooms in this campus.', 'danger')
                return redirect(url_for('admin.list_rooms'))
        
        # --- IMPROVED VALIDATION ---
        # Check if a room with the same name (case-insensitive) already exists in this campus.
        new_room_name_lower = form.name.data.lower()
        existing_room = Room.query.filter(
            func.lower(Room.name) == new_room_name_lower,
            Room.campus_id == campus_id
        ).first()
        
        if existing_room:
            flash(f'Validation Error: Room "{form.name.data}" already exists in this campus.', 'danger')
            # No redirect needed, just re-render the form with the error message
        else:
            # Create new room since validation passed
            new_room = Room(
                name=form.name.data.strip(), # Use .strip() to remove leading/trailing whitespace
                campus_id=campus_id,
                description=form.description.data
            )
            
            if form.staff_name.data or form.staff_number.data:
                new_room.staff_name = form.staff_name.data or None
                new_room.staff_number = form.staff_number.data or None

            try:
                db.session.add(new_room)
                db.session.commit()
                campus_name = next((c.name for c in campuses if c.campus_id == campus_id), 'Unknown')
                flash(f'Room "{new_room.name}" created successfully in {campus_name}.', 'success')
                return redirect(url_for('admin.list_rooms'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating room: {str(e)}', 'danger')

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
    
    # 1. Access Control Check: Ensure admin manages this room's campus
    managed_campus_ids = [c.campus_id for c in current_user.campuses]
    if room.campus_id not in managed_campus_ids:
        flash('Unauthorized: You do not manage the campus this room belongs to.', 'danger')
        return redirect(url_for('admin.list_rooms'))
        
    form = RoomCreationForm(obj=room)
    
    # 2. Populate form with ONLY managed campuses
    campuses = current_user.campuses
    form.campus.choices = [(c.campus_id, c.name) for c in campuses]

    if form.validate_on_submit():
        new_campus_id = form.campus.data
        new_room_name = form.name.data
        
        # Check if the new name is already taken by a DIFFERENT room on the NEW campus
        existing_room = Room.query.filter(
            Room.room_id != room_id, 
            Room.campus_id == new_campus_id,
            Room.name == new_room_name
        ).first()

        if existing_room:
            flash(f'Room "{new_room_name}" already exists on the selected campus.', 'danger')
        else:
            room.campus_id = new_campus_id
            room.name = new_room_name
            db.session.commit()
            flash(f'Room "{room.name}" updated successfully.', 'success')
            return redirect(url_for('admin.list_rooms'))

    # Populate form fields on GET request
    if form.campus.data is None:
        form.campus.data = room.campus_id
        
    return render_template('admin/edit_room.html', form=form, room=room, title='Edit Room')


#For the admin to delete the room
@admin_bp.route('/room/delete/<int:room_id>', methods=['POST'])
@login_required
@admin_required # CHANGED: Now allows Regular Admins and Super Admins to perform this deactivation/deletion action
def delete_room(room_id):
    """
    Soft-deletes (deactivates) a room and records the reason, 
    only if it contains no ACTIVE items.
    """
    room = Room.query.get_or_404(room_id)
    
    # 1. Get the deletion reason from the POST request form data
    # The form requesting deletion must include an input named 'deletion_reason'
    deletion_reason = request.form.get('deletion_reason', '').strip()
    
    if not deletion_reason:
        flash('Deactivation failed: A reason for closing the room is required.', 'danger')
        return redirect(url_for('admin.list_rooms')) # Assuming list_rooms is the redirect target

    # 2. Access Control Check: Ensure regular admin manages this room's campus
    # This check is crucial for Regular Admins, but Super Admins (who also pass @admin_required) 
    # bypass it due to the 'if not current_user.is_super_admin' condition being False for them.
    if not current_user.is_super_admin:
        managed_campus_ids = [c.campus_id for c in current_user.campuses]
        if room.campus_id not in managed_campus_ids:
            flash('Unauthorized: You do not manage the campus this room belongs to.', 'danger')
            return redirect(url_for('admin.list_rooms'))
        
    # 3. Deactivation Rule Check: Check for ACTIVE items only
    # We prevent deactivation if there are currently active inventory items in the room.
    active_item_count = Item.query.filter_by(
        room_id=room_id, 
        status=ItemStatus.ACTIVE
    ).count()

    if active_item_count > 0:
        flash(f'Cannot deactivate room "{room.name}". It still contains {active_item_count} active item(s). Please move or dispose of them first.', 'danger')
        return redirect(url_for('admin.list_rooms'))
    
    try:
        # --- SOFT DELETE (Deactivation and Reason Logging) ---
        room.is_active = False
        room.deletion_reason = deletion_reason
        
        db.session.commit()
        flash(f'Room "{room.name}" has been successfully **deactivated**. Reason recorded: "{deletion_reason}"', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'An unexpected database error occurred during room deactivation: {e}', 'danger')

    return redirect(url_for('admin.list_rooms'))


#---------------For the admin to export the data out--------------------------------#
@admin_bp.route('/items/export/<string:format>', methods=['GET'])
@login_required
def export_items(format):
    """Exports filtered items to Excel or PDF based on current filters."""
    query = Item.query.join(Room).join(Campus)

    # Filter by campus if user is not super admin
    if not current_user.is_super_admin:
        managed_campus_ids = [c.campus_id for c in current_user.campuses]
        query = query.filter(Room.campus_id.in_(managed_campus_ids))

    # Get filter parameters
    status = request.args.get("status", "").strip()
    room_id = request.args.get("room_id", "").strip()
    campus_id = request.args.get("campus_id", "").strip()
    brand = request.args.get("brand", "").strip()
    name = request.args.get("name", "").strip()

    # Apply filters
    if status and status.lower() != "all":
        try:
            query = query.filter(Item.status == ItemStatus[status.upper()])
        except KeyError:
            flash(f"Invalid status filter: {status}", "error")
            return redirect(url_for('admin.view_inventory'))
    
    if room_id and room_id.isdigit():
        query = query.filter(Item.room_id == int(room_id))
    
    if campus_id and campus_id.isdigit():
        query = query.filter(Room.campus_id == int(campus_id))
    
    if brand:
        query = query.filter(Item.brand.ilike(f"%{brand}%"))
    
    if name:
        query = query.filter(Item.name.ilike(f"%{name}%"))

    items = query.all()
    
    # Handle empty result set
    if not items:
        flash("No items found matching the current filters. Export canceled.", "warning")
        return redirect(url_for('admin.view_inventory'))

    import pandas as pd
    from io import BytesIO
    from flask import send_file
    
    # Build data structure with clean formatting
    data = [
        {
            "Item ID": item.item_id,
            "Asset No.": item.asset_number or "N/A",
            "Serial No.": item.serial_number or "N/A",
            "Item Name": item.name,
            "Brand": item.brand or "N/A",
            "Color": item.color or "N/A",
            "Price (R)": item.price if item.price else 0,
            "Status": item.status.value,
            "Captured By": item.data_capturer.full_name if item.data_capturer else "Unknown",
            "Room": item.room.name,
            "Campus": item.room.campus.name,
            "Capture Date": item.capture_date.strftime("%Y-%m-%d") if item.capture_date else "N/A",
            "Alloc. Date": item.allocated_date.strftime("%Y-%m-%d") if item.allocated_date else "N/A",
            "Disposed By": f"{item.disposed_by_admin.name} {item.disposed_by_admin.surname}".strip() if item.disposed_by_admin else "N/A",
            "Disposal Reason": item.disposal_reason or "N/A",
            "Description": item.description or "N/A",
        }
        for item in items
    ]
    df = pd.DataFrame(data)

    # Generate summary data
    df_summary = df.groupby(['Item Name', 'Status']).size().reset_index(name='Count')
    df_summary = df_summary.sort_values(by=['Item Name', 'Count'], ascending=[True, False])

    if format == "xlsx":
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            workbook = writer.book
            header_format = workbook.add_format({
                'bg_color': '#2196F3',
                'font_color': 'white',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })
            
            summary_format = workbook.add_format({
                'bg_color': '#64B5F6',
                'font_color': 'white',
                'bold': True,
                'border': 1,
                'align': 'center'
            })
            
            cell_format = workbook.add_format({
                'border': 1,
                'align': 'left',
                'valign': 'vcenter'
            })
            
            money_format = workbook.add_format({
                'border': 1,
                'align': 'right',
                'num_format': 'R#,##0.00'
            })

            # Sheet 1: Summary
            df_summary.to_excel(writer, index=False, sheet_name="Item Status Summary", startrow=0)
            summary_sheet = writer.sheets["Item Status Summary"]
            for col_num, value in enumerate(df_summary.columns.values):
                summary_sheet.write(0, col_num, value, summary_format)
            summary_sheet.set_column('A:A', 20)
            summary_sheet.set_column('B:B', 15)
            summary_sheet.set_column('C:C', 10)

            # Sheet 2: Detailed Inventory
            df.to_excel(writer, index=False, sheet_name="Detailed Inventory", startrow=0)
            inventory_sheet = writer.sheets["Detailed Inventory"]
            
            for col_num, value in enumerate(df.columns.values):
                inventory_sheet.write(0, col_num, value, header_format)
            
            # Set column widths for better readability
            col_widths = {
                'A': 8,   # Item ID
                'B': 12,  # Asset No.
                'C': 12,  # Serial No.
                'D': 18,  # Item Name
                'E': 12,  # Brand
                'F': 10,  # Color
                'G': 12,  # Price (R)
                'H': 12,  # Status
                'I': 15,  # Captured By
                'J': 12,  # Room
                'K': 12,  # Campus
                'L': 12,  # Capture Date
                'M': 12,  # Alloc. Date
                'N': 15,  # Disposed By
                'O': 15,  # Disposal Reason
                'P': 25,  # Description
            }
            
            for col, width in col_widths.items():
                inventory_sheet.set_column(f'{col}:{col}', width)
            
            # Format data rows
            for row_num in range(1, len(df) + 1):
                for col_num in range(len(df.columns)):
                    if df.columns[col_num] == 'Price (R)':
                        inventory_sheet.write(row_num, col_num, df.iloc[row_num - 1, col_num], money_format)
                    else:
                        inventory_sheet.write(row_num, col_num, df.iloc[row_num - 1, col_num], cell_format)
        
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name="filtered_items.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    elif format == "pdf":
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(A4),
            leftMargin=0.4*inch,
            rightMargin=0.4*inch,
            topMargin=0.4*inch,
            bottomMargin=0.4*inch
        )
        styles = getSampleStyleSheet()
        elements = []

        # Custom heading style
        title_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1565C0'),
            spaceAfter=12,
            spaceBefore=6
        )

        # Summary Section
        elements.append(Paragraph("Inventory Status Summary", title_style))

        summary_col_widths = [3.5*inch, 1.2*inch, 0.8*inch]
        summary_data = [list(df_summary.columns)] + df_summary.values.tolist()
        summary_table = Table(summary_data, colWidths=summary_col_widths)

        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor('#64B5F6')),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 11),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 1), (0, -1), "LEFT"),
            ("ALIGN", (1, 1), (-1, -1), "CENTER"),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.HexColor('#CCCCCC')),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor('#EEEEEE')])
        ]))

        elements.append(summary_table)
        elements.append(Spacer(1, 0.3*inch))

        # Detailed List Section
        elements.append(Paragraph("Detailed Inventory List", title_style))

        # Dynamic column widths based on data
        col_widths = [
            0.35*inch, 0.55*inch, 0.55*inch, 0.75*inch, 0.55*inch,
            0.4*inch, 0.5*inch, 0.6*inch, 0.7*inch, 0.5*inch,
            0.5*inch, 0.6*inch, 0.6*inch, 0.65*inch, 0.65*inch, 1.5*inch
        ]

        detail_data = [list(df.columns)] + df.values.tolist()
        detail_table = Table(detail_data, colWidths=col_widths, repeatRows=1)

        detail_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor('#2196F3')),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),
            ("FONTSIZE", (0, 1), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor('#DDDDDD')),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9F9F9')]),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        elements.append(detail_table)

        doc.build(elements)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name="filtered_items.pdf", mimetype="application/pdf")

    else:
        flash("Invalid export format. Please choose 'xlsx' or 'pdf'.", "error")
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


# --- Inventory View Route with Filtering ---
@admin_bp.route('/inventory')
@login_required
def view_inventory():
    """
    Admin views all items, filtered by their scope (managed campuses/capturers) 
    and request arguments.
    """
    
    # 1. Initialize Base Query and Scope
    query = db.select(Item) \
        .join(Room, Item.room_id == Room.room_id) \
        .join(Campus, Room.campus_id == Campus.campus_id) \
        .join(DataCapturer, Item.data_capturer_id == DataCapturer.data_capturer_id)
    
    # Context variables for the filter forms
    managed_campuses = []
    managed_capturers = []
    managed_campus_ids = []
    managed_capturer_ids = []

    if current_user.is_super_admin:
        # Super Admin: All data
        managed_campuses = Campus.query.order_by(Campus.name).all()
        managed_capturers = DataCapturer.query.order_by(DataCapturer.full_name).all()
        managed_campus_ids = [c.campus_id for c in managed_campuses]
        managed_capturer_ids = [dc.data_capturer_id for dc in managed_capturers]
    else:
        # Regular Admin: Scoped data
        managed_campuses = current_user.campuses
        managed_capturers = current_user.data_capturers
        managed_campus_ids = [c.campus_id for c in managed_campuses]
        managed_capturer_ids = [dc.data_capturer_id for dc in managed_capturers]
        
        # Apply scope filtering to the query
        query = query.where(Room.campus_id.in_(managed_campus_ids))
        query = query.where(Item.data_capturer_id.in_(managed_capturer_ids))

    # 2. Apply Request Filters (from URL query parameters)
    
    current_filters = {}

    # Filter 1: Campus
    campus_id_filter = request.args.get("campus_id")
    if campus_id_filter and campus_id_filter.isdigit():
        campus_id_filter = int(campus_id_filter)
        if campus_id_filter in managed_campus_ids: 
            query = query.where(Room.campus_id == campus_id_filter)
            current_filters['campus_id'] = campus_id_filter

    # Filter 2: Room
    room_id_filter = request.args.get("room_id")
    if room_id_filter and room_id_filter.isdigit():
        room_id_filter = int(room_id_filter)
        query = query.where(Item.room_id == room_id_filter)
        current_filters['room_id'] = room_id_filter

    # Filter 3: Item Status
    status_filter = request.args.get("status")
    if status_filter and status_filter != "all":
        try:
            # ItemStatus is an Enum; get the member by name
            status_enum = ItemStatus[status_filter.upper()]
            query = query.where(Item.status == status_enum)
            current_filters['status'] = status_filter
        except KeyError:
            flash(f"Invalid status filter '{status_filter}' ignored.", 'warning')

    # Filter 4: Data Capturer (by full_name or student_number)
    capturer_identifier = request.args.get("capturer")
    if capturer_identifier:
        # Find matching Data Capturer IDs based on the search string
        capturer_search = db.select(DataCapturer.data_capturer_id).where(
            or_(
                DataCapturer.full_name.ilike(f"%{capturer_identifier}%"),
                DataCapturer.student_number.ilike(f"%{capturer_identifier}%")
            )
        )
        matching_capturer_ids = db.session.execute(capturer_search).scalars().all()
        
        # Filter the item query by the matching capturers (respecting the Admin's scope)
        query = query.where(Item.data_capturer_id.in_(matching_capturer_ids))
        current_filters['capturer'] = capturer_identifier
        
    # 3. Final Execution
    query = query.order_by(Campus.name, Room.name, Item.capture_date.desc())
    items = db.session.execute(query).scalars().all()
    
    # Get all possible rooms for the dropdown (only rooms in managed campuses)
    all_managed_rooms = Room.query \
        .filter(Room.campus_id.in_(managed_campus_ids)) \
        .order_by(Room.name).all()
        
    # Get all possible status choices for the filter dropdown
    status_choices = [
        (status.name.lower(), status.value.replace('_', ' ').title()) 
        for status in ItemStatus
    ]

    return render_template(
        'admin/view_inventory.html',
        title='View All Inventory',
        items=items,
        managed_campuses=managed_campuses,
        managed_rooms=all_managed_rooms,
        managed_capturers=managed_capturers,
        status_choices=status_choices,
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