from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from ..forms import LocationSelectionForm, ItemCreationForm,EditItemForm,ItemMovementForm
from ..models import DataCapturer, Item, Campus, Room, db, ItemStatus,ItemMovement
from ..utils import capturer_required
from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy import or_


data_capturer_bp = Blueprint('capturer', __name__, url_prefix='/capturer')



@data_capturer_bp.route('/', methods=['GET', 'POST'])
@data_capturer_bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
@capturer_required
def dashboard():
    """Data capturer dashboard with location selection and staff info prefilling."""
    form = LocationSelectionForm()
    assigned_campuses = current_user.assigned_campuses or []

    if not assigned_campuses:
        flash("You have not been assigned to any campuses. Contact your administrator.", "warning")

    # Populate campus choices
    form.campus.choices = [('', 'Select Campus')] + [(str(c.campus_id), c.name) for c in assigned_campuses]
    form.room.choices = [('', 'Select a campus first')]

    # Get selected campus
    selected_campus_id = form.campus.data or request.args.get('campus')
    selected_room_id = form.room.data or request.args.get('room')

    # Populate rooms when campus is selected
    if selected_campus_id and selected_campus_id != '':
        try:
            campus_id = int(selected_campus_id)
            if campus_id in [c.campus_id for c in assigned_campuses]:
                rooms = Room.query.filter_by(campus_id=campus_id).order_by(Room.name).all()
                form.room.choices = [('', 'Choose a Room...')] + [(str(r.room_id), r.name) for r in rooms]
            else:
                flash('You are not assigned to that campus.', 'danger')
        except (ValueError, TypeError):
            flash('Invalid campus selection.', 'danger')

    # Prefill staff info based on selected room's last known staff
    if selected_room_id and selected_room_id != '':
        try:
            room_id = int(selected_room_id)
            room = Room.query.get(room_id)
            if room and room.staff_number:
                form.staff_number.data = room.staff_number
            if room and room.staff_name:
                form.staff_name.data = room.staff_name
        except (ValueError, TypeError):
            pass

    # Get stats
    captured_count = Item.query.filter_by(data_capturer_id=current_user.data_capturer_id).count()
    repair_count = Item.query.filter_by(
        data_capturer_id=current_user.data_capturer_id,
        status=ItemStatus.NEEDS_REPAIR
    ).count()

    # Handle form submission
    if form.validate_on_submit():
        room_id = form.room.data
        if room_id:
            # Update room's staff info for future prefilling
            room = Room.query.get(int(room_id))
            if room:
                room.staff_number = form.staff_number.data
                room.staff_name = form.staff_name.data
                db.session.commit()
            
            return redirect(url_for('capturer.manage_room_items', room_id=room_id))
        else:
            flash('Please select a room.', 'warning')

    return render_template(
        'data_capturer/data_capturer_dashboard.html',
        location_form=form,
        captured_count=captured_count,
        repair_count=repair_count,
        selected_room_id=form.room.data or 0
    )



@data_capturer_bp.route('/capture/<int:room_id>', methods=['GET', 'POST'])
@login_required
@capturer_required
def start_capture(room_id):
    """Item capture page for a specific room."""
    room = Room.query.get_or_404(room_id)
    
    # Security check: ensure the capturer is assigned to this campus
    assigned_campus_ids = [c.campus_id for c in current_user.assigned_campuses]
    if room.campus_id not in assigned_campus_ids:
        flash('Access denied. You are not assigned to this campus.', 'danger')
        return redirect(url_for('capturer.dashboard'))
    
    # Handle GET request - render the form page
    if request.method == 'GET':
        return render_template(
            'data_capturer/capture_form.html', 
            room=room,
            room_id=room_id,
            campus_name=room.campus.name
        )
    
    # Handle POST request - process the form submission
    if request.method == 'POST':
        # Extract form data
        asset_number = request.form.get('assetNumber', '').strip()
        serial_number = request.form.get('serialNumber', '').strip()
        item_type = request.form.get('itemType', '').strip()
        description = request.form.get('description', '').strip()
        color = request.form.get('color', '').strip()
        brand = request.form.get('brand', '').strip()
        capture_date_str = request.form.get('captureDate', '')
        allocation_date_str = request.form.get('allocationDate', '')
        
        # Validation
        errors = []
        
        if not asset_number:
            errors.append('Asset Number is required')
        elif Item.query.filter_by(asset_number=asset_number).first():
            errors.append('An item with that Asset Number already exists')
        
        if not item_type:
            errors.append('Item Type is required')
        
        if not capture_date_str:
            errors.append('Capture Date is required')
        
        if errors:
            return jsonify({'success': False, 'message': ' | '.join(errors)}), 400
        
        # Parse capture date (when item is scanned today)
        try:
            capture_date = datetime.strptime(capture_date_str, '%Y-%m-%d')
        except ValueError:
            return jsonify({'success': False, 'message': 'Invalid capture date format'}), 400
        
        # Parse allocation date (when item was originally allocated) - optional
        allocation_date = None
        if allocation_date_str:
            try:
                allocation_date = datetime.strptime(allocation_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid allocation date format'}), 400
        
        # Create new item
        try:
            new_item = Item(
                asset_number=asset_number,
                serial_number=serial_number if serial_number else None,
                name=item_type,  # Item Type is stored in the 'name' field
                description=description if description else None,
                brand=brand if brand else None,
                color=color if color else None,
                status=ItemStatus.ACTIVE,  # Default status for new items
                capture_date=capture_date,  # When item was captured/scanned (today)
                allocated_date=allocation_date,  # When item was originally allocated (optional, could be past)
                room_id=room_id,
                data_capturer_id=current_user.data_capturer_id
            )
            
            db.session.add(new_item)
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'message': f'Item "{new_item.name}" captured successfully in {room.name}!',
                'item_id': new_item.item_id
            }), 201
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating item: {str(e)}")
            return jsonify({
                'success': False, 
                'message': f'Error capturing item: {str(e)}'
            }), 500
 

 
@data_capturer_bp.route('/manage/<int:room_id>')
@login_required
@capturer_required
def manage_room_items(room_id):
    """Manage items in a specific room — view, update, or capture new."""
    room = Room.query.get_or_404(room_id)

    # Security: capturer can only manage rooms in their assigned campuses
    assigned_campus_ids = [c.campus_id for c in current_user.assigned_campuses]
    if room.campus_id not in assigned_campus_ids:
        flash('Access denied. You are not assigned to this campus.', 'danger')
        return redirect(url_for('capturer.dashboard'))

    # Fetch all items in the selected room
    items = Item.query.filter_by(room_id=room_id).order_by(Item.capture_date.desc()).all()

    # Stats summary for quick info
    total_items = len(items)
    repair_items = len([i for i in items if i.status == ItemStatus.NEEDS_REPAIR])

    return render_template(
        'data_capturer/manage_room_items.html',
        room=room,
        items=items,
        total_items=total_items,
        repair_items=repair_items
    )



@data_capturer_bp.route('/my-items')
@login_required
@capturer_required
def my_items():
    """View items captured by this user, including their Campus and Room details."""
    
    # Efficiently load the Room and Campus data to avoid N+1 queries.
    # The 'room' backref is on the Item model.
    # The 'campus' backref is on the Room model.
    items = Item.query.options(
        db.joinedload(Item.room).joinedload(Room.campus)
    ).filter(
        Item.data_capturer_id == current_user.data_capturer_id
    ).order_by(
        Item.capture_date.desc()
    ).all()
    
    # Note: Because the Item model has a 'room' attribute, and the Room model
    # has a 'campus' attribute, you can access the data in the template as:
    # item.room.name
    # item.room.campus.name
    
    return render_template('data_capturer/my_items.html', items=items)



@data_capturer_bp.route('/api/search-staff')
@login_required
@capturer_required
def search_staff():
    """
    API endpoint to search for unique staff number and name combinations.
    Returns results as JSON for autocomplete functionality.
    """
    # Get the search term from the query parameters (e.g., /api/search-staff?q=John)
    query_term = request.args.get('q', '').strip()

    # Don't search if the query is too short
    if len(query_term) < 2:
        return jsonify([])

    search_pattern = f"%{query_term}%"

    # Query the Room table for distinct staff_number and staff_name pairs
    # that match the search term.
    # We use distinct() to avoid sending duplicate staff details.
    staff_records = db.session.query(Room.staff_number, Room.staff_name)\
        .filter(
            Room.staff_number.isnot(None),  # Ensure we only get rooms with staff assigned
            Room.staff_name.isnot(None)
        )\
        .filter(
            or_(
                Room.staff_number.ilike(search_pattern),
                Room.staff_name.ilike(search_pattern)
            )
        )\
        .distinct()\
        .limit(10)\
        .all()

    # Format the results into a list of dictionaries for easy use in JavaScript
    results = [
        {'number': number, 'name': name}
        for number, name in staff_records
    ]

    return jsonify(results)


#--- ----#
# app/routes/data_capturer_routes.py
# app/routes/data_capturer_routes.py

@data_capturer_bp.route('/item/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@capturer_required
def edit_item(item_id):
    """Allows a data capturer to edit an existing item they captured, excluding price."""
    
    # 1. Fetch the item (securely checks ownership)
    item = Item.query.filter_by(
        item_id=item_id,
        data_capturer_id=current_user.data_capturer_id
    ).first_or_404()

    form = EditItemForm(obj=item)
    
    # --- FIX: Filter out the DISPOSED status ---
    # 1. Get all status choices
    all_choices = ItemStatus.choices() 
    
    # 2. Filter out the DISPOSED status from the list
    # Assuming ItemStatus.DISPOSED is represented by its enum name string 'DISPOSED'
    # The 'choices()' method likely returns a list of (value, label) tuples.
    filtered_choices = [
        (value, label) for value, label in all_choices if value != 'DISPOSED'
    ]
    
    # 3. Apply the filtered choices to the form field
    form.status.choices = filtered_choices 
    # ---------------------------------------------

    if form.validate_on_submit():
        # 2. Update all authorized fields:
        item.asset_number = form.asset_number.data
        item.serial_number = form.serial_number.data
        item.name = form.name.data
        item.description = form.description.data
        item.color = form.color.data
        item.brand = form.brand.data
        
        # NOTE: Status is updated here. If the form somehow submitted 'DISPOSED', 
        # it would still update the database, but this change prevents the user 
        # from selecting it via the dropdown.
        item.status = ItemStatus[form.status.data]
        item.allocated_date = form.allocated_date.data

        # 3. Commit changes
        db.session.commit()

        flash(f'Item "{item.name}" updated successfully.', 'success')
        # FIX: Ensure correct blueprint name 'capturer' is used (as discussed previously)
        return redirect(url_for('capturer.manage_room_items', room_id=item.room_id))

    return render_template('data_capturer/edit_item.html', form=form, item=item)


@data_capturer_bp.route('/item/move/<int:item_id>', methods=['GET', 'POST'])
@login_required
@capturer_required
def move_item(item_id):
    """
    Allows a data capturer to move an item to a different room, 
    updating staff details for both source and destination rooms.
    """
    
    item = Item.query.filter_by(item_id=item_id).first_or_404()
    current_room = item.room
    
    # 1. Authorization Check (Capturer must manage the item's current campus)
    assigned_campus_ids = [c.campus_id for c in current_user.assigned_campuses]
    if current_room.campus_id not in assigned_campus_ids:
        flash('Access denied. You are not assigned to the campus where this item is currently located.', 'danger')
        return redirect(url_for('capturer.my_items'))

    # 2. Setup Form (Assuming a comprehensive ItemMovementForm is available)
    # The form must include fields for: to_room, source_staff_name, source_staff_number, dest_staff_name, dest_staff_number
    from ..forms import ItemMovementForm
    form = ItemMovementForm() 

    # Populate Destination Room Choices (Scoped to all managed campuses)
    all_target_rooms = Room.query.filter(Room.campus_id.in_(assigned_campus_ids)).all()
    room_choices = [
        (str(r.room_id), f"{r.campus.name} - {r.name}") 
        for r in all_target_rooms if r.room_id != item.room_id
    ]
    form.to_room.choices = [(0, 'Select Destination Room')] + room_choices
    
    # 3. Handle GET Request (Prefill current/source room staff info)
    if request.method == 'GET':
        form.source_staff_name.data = current_room.staff_name
        form.source_staff_number.data = current_room.staff_number
        # Destination staff fields will remain blank or pre-filled if room_id is passed via args (advanced)

    # 4. Handle POST Request
    if form.validate_on_submit():
        to_room_id = int(form.to_room.data)
        from_room_id = current_room.room_id
        new_room = Room.query.get(to_room_id)
        
        if not new_room or to_room_id == from_room_id:
             flash('Invalid destination room selected.', 'danger')
             return redirect(url_for('capturer.move_item', item_id=item_id))

        # --- TRANSACTION ---

        # A. Update Staff info for the *Source* Room (The latest info from the field)
        current_room.staff_name = form.source_staff_name.data
        current_room.staff_number = form.source_staff_number.data
        
        # B. Update Staff info for the *Destination* Room
        new_room.staff_name = form.dest_staff_name.data
        new_room.staff_number = form.dest_staff_number.data

        # C. Record Movement in ItemMovement Table
        movement = ItemMovement(
            item_id=item.item_id,
            from_room_id=from_room_id,
            to_room_id=to_room_id,
            moved_by_id=current_user.data_capturer_id
        )
        db.session.add(movement)
        
        # D. Update Item's Location
        item.room_id = to_room_id
        
        try:
            db.session.commit()
            flash(
                f'Item "{item.name}" successfully moved to {new_room.name}. Movement logged.', 
                'success'
            )
            return redirect(url_for('capturer.manage_room_items', room_id=to_room_id))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred during item movement: {str(e)}', 'danger')
            
    return render_template(
        'data_capturer/move_item.html', 
        form=form, 
        item=item,
        current_room=current_room
    )

