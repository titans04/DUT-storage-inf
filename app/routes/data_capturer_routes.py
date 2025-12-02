from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from ..forms import LocationSelectionForm, ItemCreationForm,EditItemForm,ItemMovementForm
from ..models import DataCapturer, Item, Campus, Room, db, ItemStatus,ItemMovement,ItemCategory
from ..utils import capturer_required
from datetime import datetime
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from sqlalchemy import func
from sqlalchemy import distinct, func 

data_capturer_bp = Blueprint('capturer', __name__, url_prefix='/capturer')



@data_capturer_bp.route('/', methods=['GET', 'POST'])
@data_capturer_bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
@capturer_required
def dashboard():
    """Data capturer dashboard with location selection."""
    form = LocationSelectionForm()
    assigned_campuses = current_user.assigned_campuses or []

    if not assigned_campuses:
        flash("You have not been assigned to any campuses. Contact your administrator.", "warning")

    # Populate campus choices
    form.campus.choices = [('', 'Select Campus')] + [(str(c.campus_id), c.name) for c in assigned_campuses]
    
    # Get selected campus from form submission or query param
    selected_campus_id = request.form.get('campus') or request.args.get('campus')
    
    print(f"🔍 Dashboard loaded - Selected campus: {selected_campus_id}")
    
    # Populate room choices based on selected campus
    if selected_campus_id and selected_campus_id != '':
        try:
            campus_id = int(selected_campus_id)
            
            # Security check
            allowed_campus_ids = [c.campus_id for c in assigned_campuses]
            if campus_id in allowed_campus_ids:
                # Fetch ACTIVE rooms for the selected campus
                rooms = Room.query.filter_by(
                    campus_id=campus_id,
                    is_active=True
                ).order_by(Room.name).all()
                
                print(f"📊 Found {len(rooms)} active rooms in campus {campus_id}")
                for room in rooms:
                    print(f"   - Room: {room.name} (ID: {room.room_id})")
                
                # Populate room choices
                form.room.choices = [('', 'Select Room')] + [
                    (str(r.room_id), r.name) for r in rooms
                ]
                
                # Pre-select campus in form
                form.campus.data = str(campus_id)
                
                # Get selected room
                selected_room_id = request.form.get('room')
                if selected_room_id and selected_room_id != '':
                    room = Room.query.get(int(selected_room_id))
                    if room:
                        # Pre-fill staff info from room ONLY if form fields are empty
                        if not form.staff_number.data:
                            form.staff_number.data = room.staff_number or ''
                        if not form.staff_name.data:
                            form.staff_name.data = room.staff_name or ''
                        print(f"✅ Pre-filled staff: {room.staff_name} ({room.staff_number})")
            else:
                print(f"❌ Unauthorized campus: {campus_id}")
                flash("Unauthorized campus selection.", "danger")
                form.room.choices = [('', 'Select a campus first')]
        except (ValueError, TypeError) as e:
            print(f"❌ Error processing campus selection: {e}")
            form.room.choices = [('', 'Select a campus first')]
    else:
        # No campus selected - show default message
        form.room.choices = [('', 'Select a campus first')]
        print("No campus selected")

    # Get stats
    captured_count = Item.query.filter_by(data_capturer_id=current_user.data_capturer_id).count()
    repair_count = Item.query.filter_by(
        data_capturer_id=current_user.data_capturer_id,
        status=ItemStatus.NEEDS_REPAIR
    ).count()

    # Handle final form submission (when both campus AND room are selected)
    if form.validate_on_submit():
        room_id = form.room.data
        print(f"📝 Form submitted - Room ID: {room_id}")
        
        if room_id and room_id != '':
            # Update room's staff info for future use
            room = Room.query.get(int(room_id))
            if room:
                # ✅ UPDATED: Always save the LATEST staff details from form
                # This ensures any changes made by the user are persisted
                new_staff_number = form.staff_number.data.strip() if form.staff_number.data else None
                new_staff_name = form.staff_name.data.strip() if form.staff_name.data else None
                
                # Only update if there are actual changes
                staff_updated = False
                
                if new_staff_number and new_staff_number != room.staff_number:
                    room.staff_number = new_staff_number
                    staff_updated = True
                    print(f"📝 Updated staff number: {room.staff_number}")
                
                if new_staff_name and new_staff_name != room.staff_name:
                    room.staff_name = new_staff_name
                    staff_updated = True
                    print(f"📝 Updated staff name: {room.staff_name}")
                
                try:
                    if staff_updated:
                        db.session.commit()
                        print(f"✅ Saved latest staff info for room {room.name}")
                        flash(f'Staff information updated for {room.name}.', 'info')
                    else:
                        print(f"ℹ️ No staff changes detected for room {room.name}")
                except Exception as e:
                    db.session.rollback()
                    print(f"❌ Error updating room: {e}")
                    flash(f'Warning: Could not save staff information: {str(e)}', 'warning')
            
                return redirect(url_for('capturer.manage_room_items', room_id=room_id))
        else:
            flash('Please select a room.', 'warning')

    return render_template(
        'data_capturer/data_capturer_dashboard.html',
        location_form=form,
        captured_count=captured_count,
        repair_count=repair_count,
        selected_campus_id=selected_campus_id
    )




@data_capturer_bp.route('/api/get-rooms/<int:campus_id>')
@login_required
@capturer_required
def get_rooms_for_campus(campus_id):
    """API endpoint to get rooms and staff info for a specific campus."""
    
    allowed_campus_ids = [c.campus_id for c in current_user.assigned_campuses]
    
    if campus_id not in allowed_campus_ids:
        return jsonify({"error": "Unauthorized campus"}), 403

    rooms = Room.query.filter_by(
        campus_id=campus_id, 
        is_active=True
    ).order_by(Room.name).all()

    room_list = [{
        "id": room.room_id, 
        "name": room.name,
        "staff_name": room.staff_name or "",
        "staff_number": room.staff_number or "",
        "description": room.description or "",
        "room_picture": room.room_picture or ""  # 
    } for room in rooms]
    
    return jsonify(rooms=room_list)


from flask import jsonify, request

@data_capturer_bp.route('/autocomplete/item-types')
def autocomplete_item_types():
    q = request.args.get('q', '').strip()
    # Query your DB for item types containing q
    suggestions = db.session.query(Item.type).filter(Item.type.ilike(f'%{q}%')).distinct().limit(10).all()
    return jsonify([s[0] for s in suggestions])

@data_capturer_bp.route('/autocomplete/brands')
def autocomplete_brands():
    q = request.args.get('q', '').strip()
    suggestions = db.session.query(Item.brand).filter(Item.brand.ilike(f'%{q}%')).distinct().limit(10).all()
    return jsonify([s[0] for s in suggestions])

@data_capturer_bp.route('/autocomplete/colors')
def autocomplete_colors():
    q = request.args.get('q', '').strip()
    suggestions = db.session.query(Item.color).filter(Item.color.ilike(f'%{q}%')).distinct().limit(10).all()
    return jsonify([s[0] for s in suggestions])



@data_capturer_bp.route('/bulk-capture/<int:room_id>', methods=['GET', 'POST'])
@login_required
@capturer_required
def bulk_capture(room_id):
    """Capture multiple items at once using a dynamic form."""
    room = Room.query.get_or_404(room_id)

    # Security check
    if room.campus_id not in [c.campus_id for c in current_user.assigned_campuses]:
        flash('Access denied. You are not assigned to this campus.', 'danger')
        return redirect(url_for('capturer.dashboard'))

    if request.method == 'GET':
        # Fetch suggestions for autocomplete
        item_type_suggestions = [
            r[0] for r in db.session.query(distinct(Item.name))
            .filter(Item.name.isnot(None), Item.name != '')
            .order_by(Item.name).all()
        ]
        brand_suggestions = [
            r[0] for r in db.session.query(distinct(Item.brand))
            .filter(Item.brand.isnot(None), Item.brand != '')
            .order_by(Item.brand).all()
        ]
        color_suggestions = [
            r[0] for r in db.session.query(distinct(Item.color))
            .filter(Item.color.isnot(None), Item.color != '')
            .order_by(Item.color).all()
        ]
        
        # Get last captured item in this room for default values (including status)
        last_item = Item.query.filter_by(
            room_id=room_id,
            data_capturer_id=current_user.data_capturer_id
        ).order_by(Item.capture_date.desc()).first()
        
        last_item_data = {
            'itemType': '',
            'description': '',
            'brand': '',
            'color': '',
            'capacity': '',
            'category': 'TEACHING_LEARNING',
            'procuredDate': datetime.today().strftime('%Y-%m-%d'),
            'status': 'ACTIVE'  # default fallback
        }

        if last_item:
            last_item_data.update({
                'itemType': last_item.name or '',
                'description': last_item.description or '',
                'brand': last_item.brand or '',
                'color': last_item.color or '',
                'capacity': last_item.capacity or '',
                'category': last_item.category.name if last_item.category else 'TEACHING_LEARNING',
                'procuredDate': last_item.Procured_date.strftime('%Y-%m-%d') if last_item.Procured_date else datetime.today().strftime('%Y-%m-%d'),
                'status': last_item.status.name  # This is now included!
            })

        return render_template(
            'data_capturer/capture_form.html',
            room=room,
            room_id=room_id,
            item_type_suggestions=item_type_suggestions,
            brand_suggestions=brand_suggestions,
            color_suggestions=color_suggestions,
            last_item_data=last_item_data
        )

    # POST: Save multiple items
    if request.method == 'POST':
        items_data = request.get_json()
        
        if not items_data or not isinstance(items_data, list):
            return jsonify({'success': False, 'message': 'Invalid data format'}), 400

        errors = []
        success_count = 0
        duplicate_assets = []

        for idx, item_data in enumerate(items_data, 1):
            try:
                asset_number = item_data.get('assetNumber', '').strip()
                
                # Required field checks
                if not asset_number:
                    errors.append(f'Row {idx}: Asset Number is required')
                    continue
                
                if not item_data.get('itemType', '').strip():
                    errors.append(f'Row {idx}: Item Type is required')
                    continue
                
                if not item_data.get('procuredDate'):
                    errors.append(f'Row {idx}: Procurement Date is required')
                    continue

                # Check for duplicate asset number (case-insensitive)
                if Item.query.filter(func.lower(Item.asset_number) == asset_number.lower()).first():
                    duplicate_assets.append(asset_number)
                    continue

                # Parse dates
                try:
                    procured_date = datetime.strptime(item_data['procuredDate'], '%Y-%m-%d').date()
                except ValueError:
                    errors.append(f'Row {idx}: Invalid procurement date')
                    continue

                allocated_date = None
                if item_data.get('allocationDate'):
                    try:
                        allocated_date = datetime.strptime(item_data['allocationDate'], '%Y-%m-%d').date()
                    except ValueError:
                        errors.append(f'Row {idx}: Invalid allocation date')
                        continue

                # Parse category (safe fallback)
                category_str = item_data.get('category', 'TEACHING_LEARNING')
                category = ItemCategory.TEACHING_LEARNING
                if category_str in ItemCategory.__members__:
                    category = ItemCategory[category_str]

                # Parse status — now fully dynamic!
                status_str = item_data.get('status', 'ACTIVE').upper()
                allowed_statuses = {'ACTIVE', 'INACTIVE', 'NEEDS_REPAIR','STOLEN'}  # Data capturers can only set these
                if status_str in allowed_statuses:
                    status = ItemStatus[status_str]
                else:
                    status = ItemStatus.ACTIVE  # Fallback if invalid

                # Create item
                new_item = Item(
                    asset_number=asset_number,
                    serial_number=item_data.get('serialNumber', '').strip() or None,
                    name=item_data.get('itemType', '').strip(),
                    description=item_data.get('description', '').strip() or None,
                    brand=item_data.get('brand', '').strip() or None,
                    color=item_data.get('color', '').strip() or None,
                    capacity=item_data.get('capacity', '').strip() or None,
                    status=status,  # Now dynamic!
                    Procured_date=procured_date,
                    allocated_date=allocated_date,
                    cost=0,
                    category=category,
                    room_id=room_id,
                    data_capturer_id=current_user.data_capturer_id
                )
                db.session.add(new_item)
                success_count += 1

            except Exception as e:
                errors.append(f'Row {idx}: Unexpected error - {str(e)}')
                continue

        # Commit all successful items
        try:
            if success_count > 0:
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            return jsonify({
                'success': False,
                'message': f'Database error: {str(e)}'
            }), 500

        # Build response message
        message_parts = []
        if success_count > 0:
            message_parts.append(f'Successfully captured {success_count} item(s)')
        if duplicate_assets:
            message_parts.append(f'Skipped {len(duplicate_assets)} duplicate(s): {", ".join(duplicate_assets[:5])}')
            if len(duplicate_assets) > 5:
                message_parts[-1] += f' and {len(duplicate_assets) - 5} more'
        if errors:
            message_parts.append(f'{len(errors)} error(s): {" | ".join(errors[:3])}')
            if len(errors) > 3:
                message_parts[-1] += f' and {len(errors) - 3} more'

        return jsonify({
            'success': success_count > 0,
            'message': ' | '.join(message_parts),
            'success_count': success_count,
            'duplicate_count': len(duplicate_assets),
            'error_count': len(errors)
        }), 200 if success_count > 0 else 400
    
        
 
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



@data_capturer_bp.route('/my-items', methods=['GET'])
@login_required
@capturer_required
def my_items():
    """View items captured by this user, with search and filter options."""

    # Base query: items captured by current user
    query = Item.query.options(
        db.joinedload(Item.room).joinedload(Room.campus)
    ).filter(
        Item.data_capturer_id == current_user.data_capturer_id
    )

    # Get search/filter params from query string
    asset_number = request.args.get('asset_number', '').strip()
    item_name = request.args.get('item_name', '').strip()
    status = request.args.get('status', '').strip()
    campus_id = request.args.get('campus_id', '').strip()
    room_id = request.args.get('room_id', '').strip()
    procured_date_from = request.args.get('procured_date_from', '').strip()
    procured_date_to = request.args.get('procured_date_to', '').strip()

    # Apply filters if provided
    if asset_number:
        query = query.filter(Item.asset_number.ilike(f"%{asset_number}%"))

    if item_name:
        query = query.filter(Item.name.ilike(f"%{item_name}%"))

    if status:
         status = status.strip().upper()
    
    # Allow ANY valid status EXCEPT "DISPOSED" for data capturers
    if status == "DISPOSED":
        # Data capturers are not allowed to filter by "Disposed" → silently ignore
        pass
    else:
        try:
            status_enum = ItemStatus[status]
            query = query.filter(Item.status == status_enum)
        except KeyError:
            # Invalid status (e.g. "BLAHBLAH", "123") → ignore silently
            pass

    if campus_id:
        query = query.join(Item.room).filter(Room.campus_id == int(campus_id))

    if room_id:
        query = query.filter(Item.room_id == int(room_id))

    if procured_date_from:
        try:
            date_from = datetime.strptime(procured_date_from, "%Y-%m-%d").date()
            query = query.filter(Item.Procured_date >= date_from)
        except ValueError:
            pass

    if procured_date_to:
        try:
            date_to = datetime.strptime(procured_date_to, "%Y-%m-%d").date()
            query = query.filter(Item.Procured_date <= date_to)
        except ValueError:
            pass

    # Execute query
    items = query.order_by(Item.capture_date.desc()).all()

    # Assigned campuses for dropdown
    assigned_campuses = current_user.assigned_campuses or []

    # Build JSON-serializable rooms structure for dynamic filtering
    rooms_json = {}
    for campus in assigned_campuses:
        rooms_json[str(campus.campus_id)] = [
            {"room_id": r.room_id, "name": r.name} for r in campus.rooms
        ]

    # Pass the rooms of the selected campus for initial rendering
    rooms = rooms_json.get(campus_id, []) if campus_id else []

    # Filters dict for template
    filters = {
        'asset_number': asset_number,
        'item_name': item_name,
        'status': status,
        'campus_id': campus_id,
        'room_id': room_id,
        'procured_date_from': procured_date_from,
        'procured_date_to': procured_date_to
    }

    return render_template(
        'data_capturer/my_items.html',
        items=items,
        assigned_campuses=assigned_campuses,
        rooms=rooms,
        rooms_json=rooms_json,  # JSON-safe rooms for JS
        filters=filters,
        ItemStatus=ItemStatus
    )




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



@data_capturer_bp.route('/item/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@capturer_required
def edit_item(item_id):
    """Allows a data capturer to edit an existing item they captured (excludes price and sensitive statuses)."""
    
    # 1. Fetch the item and verify ownership
    item = Item.query.filter_by(
        item_id=item_id,
        data_capturer_id=current_user.data_capturer_id
    ).first_or_404()

    form = EditItemForm(obj=item)
    
    # 2. Filter status choices - exclude DISPOSED and STOLEN (admin-only statuses)
    all_choices = ItemStatus.choices() 
    filtered_choices = [
        (value, label) for value, label in all_choices 
        if value not in ['DISPOSED']
    ]
    form.status.choices = filtered_choices

    if form.validate_on_submit():
        # 3. Security: Double-check status is not DISPOSED or STOLEN
        selected_status = form.status.data
        if selected_status in ['DISPOSED', 'STOLEN']:
            flash('You do not have permission to set that status.', 'danger')
            return redirect(url_for('capturer.edit_item', item_id=item_id))
        
        # 4. Check for duplicate asset number (case-insensitive, excluding current item)
        new_asset_number = form.asset_number.data.strip()
        existing_item = Item.query.filter(
            Item.item_id != item_id,
            func.lower(Item.asset_number) == new_asset_number.lower()
        ).first()
        
        if existing_item:
            flash(f'An item with Asset Number "{new_asset_number}" already exists.', 'danger')
        else:
            # 5. Update all authorized fields (price/cost is NOT included)
            item.asset_number = new_asset_number
            item.serial_number = form.serial_number.data.strip() if form.serial_number.data else None
            item.name = form.name.data.strip()
            item.description = form.description.data.strip() if form.description.data else None
            item.color = form.color.data.strip() if form.color.data else None
            item.brand = form.brand.data.strip() if form.brand.data else None
            item.capacity = form.capacity.data.strip() if form.capacity.data else None
            item.status = ItemStatus[selected_status]
            item.Procured_date = form.procured_date.data
            item.allocated_date = form.allocated_date.data
            
            # Note: cost/price is intentionally NOT updated - data capturers cannot modify it

            try:
                db.session.commit()
                flash(f'Item "{item.name}" updated successfully.', 'success')
                return redirect(url_for('capturer.manage_room_items', room_id=item.room_id))
            except Exception as e:
                db.session.rollback()
                flash(f'Error updating item: {str(e)}', 'danger')

    # 6. Pre-populate form on GET request
    if request.method == 'GET':
        form.asset_number.data = item.asset_number
        form.serial_number.data = item.serial_number
        form.name.data = item.name
        form.description.data = item.description
        form.color.data = item.color
        form.brand.data = item.brand
        form.capacity.data = item.capacity
        form.status.data = item.status.name
        form.procured_date.data = item.Procured_date
        form.allocated_date.data = item.allocated_date

    return render_template('data_capturer/edit_item.html', form=form, item=item)




@data_capturer_bp.route('/item/move/<int:item_id>', methods=['GET', 'POST'])
@login_required
@capturer_required
def move_item(item_id):
    """
    Move an item to a new room, updating staff ownership for both rooms.
    WARNING: This updates room-level staff, affecting ALL items in those rooms.
    """
    item = Item.query.filter_by(item_id=item_id).first_or_404()
    current_room = item.room
    from_room_id = current_room.room_id

    # Authorization check
    assigned_campus_ids = [c.campus_id for c in current_user.assigned_campuses]
    if current_room.campus_id not in assigned_campus_ids:
        flash('Access denied: You are not assigned to this campus.', 'danger')
        return redirect(url_for('capturer.my_items'))

    from ..forms import ItemMovementForm
    form = ItemMovementForm()

    # Populate destination room choices
    all_target_rooms = Room.query.filter(Room.campus_id.in_(assigned_campus_ids)).all()
    room_choices = [
        (str(r.room_id), f"{r.campus.name} - {r.name}")
        for r in all_target_rooms if r.room_id != from_room_id
    ]
    form.to_room.choices = [(0, 'Select Destination Room')] + room_choices

    # GET: Prefill source room staff
    if request.method == 'GET':
        form.source_staff_name.data = current_room.staff_name or ''
        form.source_staff_number.data = current_room.staff_number or ''

    # POST: Process move
    if form.validate_on_submit():
        to_room_id = int(form.to_room.data)
        if to_room_id == 0 or to_room_id == from_room_id:
            flash('Please select a valid destination room.', 'danger')
            return redirect(url_for('capturer.move_item', item_id=item_id))

        new_room = Room.query.get(to_room_id)
        if not new_room:
            flash('Selected destination room not found.', 'danger')
            return redirect(url_for('capturer.move_item', item_id=item_id))

        try:
            # Count items affected by staff changes
            source_items_affected = len(current_room.items)
            dest_items_affected = len(new_room.items)
            
            # Only update if staff details were actually changed
            source_changed = False
            dest_changed = False
            
            new_source_name = form.source_staff_name.data.strip() or None
            new_source_number = form.source_staff_number.data.strip() or None
            new_dest_name = form.dest_staff_name.data.strip() or None
            new_dest_number = form.dest_staff_number.data.strip() or None
            
            # Update source room staff ONLY if changed
            if (new_source_name != current_room.staff_name or 
                new_source_number != current_room.staff_number):
                current_room.staff_name = new_source_name
                current_room.staff_number = new_source_number
                source_changed = True

            # Update destination room staff ONLY if changed
            if (new_dest_name != new_room.staff_name or 
                new_dest_number != new_room.staff_number):
                new_room.staff_name = new_dest_name
                new_room.staff_number = new_dest_number
                dest_changed = True

            # Record Movement
            movement = ItemMovement(
                item_id=item.item_id,
                from_room_id=from_room_id,
                to_room_id=to_room_id,
                moved_by_id=current_user.data_capturer_id
            )
            db.session.add(movement)

            # Update Item Location
            item.room_id = to_room_id
            db.session.commit()

            # Build detailed success message
            msg = f'Item <strong>{item.name}</strong> moved from <strong>{current_room.name}</strong> to <strong>{new_room.name}</strong>.'
            
            warnings = []
            if source_changed:
                warnings.append(f'⚠️ Source room staff updated - affects <strong>{source_items_affected} items</strong>')
            if dest_changed:
                warnings.append(f'⚠️ Destination room staff updated - affects <strong>{dest_items_affected} items</strong>')
            
            if warnings:
                msg += '<br>' + '<br>'.join(warnings)
            
            flash(msg, 'success' if not warnings else 'warning')
            
            return redirect(url_for('capturer.manage_room_items', room_id=from_room_id))

        except Exception as e:
            db.session.rollback()
            flash(f'Move failed: {str(e)}', 'danger')
            return redirect(url_for('capturer.move_item', item_id=item_id))

    # Pass item counts to template
    return render_template(
        'data_capturer/move_item.html',
        form=form,
        item=item,
        current_room=current_room
    )