from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from ..forms import LocationSelectionForm, ItemCreationForm# Make sure to import this form
from ..models import DataCapturer, Item, Campus, Room, db, ItemStatus # <-- ADDED ItemStatus HERE
from functools import wraps # Import for decorators

data_capturer_bp = Blueprint('capturer', __name__)

def capturer_required(f):
    """Decorator to restrict access to Data Capturers."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # The user is logged in (due to @login_required), now check role
        if not current_user.is_data_capturer: 
            flash('Access denied. Only Data Capturers can view this page.', 'danger')
            return redirect(url_for('main.index')) # Redirect to a safe page
        return f(*args, **kwargs)
    return decorated_function

# FIX: Renaming the function to 'select_location' to match the endpoint
# expected by the HTML template for form submission.
@data_capturer_bp.route('/', methods=['GET', 'POST'])
@login_required
@capturer_required
def select_location():
    """Data capturer dashboard and location selection handler."""
    form = LocationSelectionForm()

    # Get stats for the dashboard display
    captured_count = Item.query.filter_by(data_capturer_id=current_user.data_capturer_id).count()
    
    # Needs Repair items captured by this user
    repair_count = Item.query.filter_by(
        data_capturer_id=current_user.data_capturer_id, 
        status=ItemStatus.NEEDS_REPAIR 
    ).count()

    # NOTE: In a real app, form.campus choices would be populated here 
    # based on current_user.assigned_campuses

    if form.validate_on_submit():
        # This branch handles the POST request from the form submission
        campus_id = form.campus.data
        room_id = form.room.data
        
        # Redirect to the item capture page, passing the selected room ID
        return redirect(url_for('capturer.start_capture', room_id=room_id))
    
    # On GET request or failed validation
    # NOTE: Assuming the template name 'capturer/dashboard.html' is correct based on prior context
    # but the traceback suggests 'data_capturer/data_capturer_dashboard.html'
    # I will stick to 'capturer/dashboard.html' for now, but if the error persists, 
    # you may need to update the template path here.
    return render_template('data_capturer/data_capturer_dashboard.html',
                           location_form=form,
                           captured_count=captured_count,
                           repair_count=repair_count)


@data_capturer_bp.route('/capture/<int:room_id>', methods=['GET', 'POST'])
@login_required
@capturer_required
def start_capture(room_id):
    """Item capture page for a specific room."""
    room = Room.query.get_or_404(room_id)
    # Optional: Check if the current user is assigned to this room's campus
    
    form = ItemCreationForm()
    if form.validate_on_submit():
        # Check for unique asset number *before* adding the item
        if Item.query.filter_by(asset_number=form.asset_tag.data).first():
            flash('An item with that Asset Tag/Barcode already exists.', 'danger')
            return render_template('capturer/capture_form.html', form=form, room=room)

        new_item = Item(
            asset_number=form.asset_tag.data,
            serial_number=form.serial_number.data,
            name=form.name.data,
            description=form.description.data,
            color=form.color.data,
            brand=form.brand.data,
            # Status defaults to ACTIVE in the model, but we use form data if provided
            status=ItemStatus[form.status.data], 
            room_id=room_id,
            data_capturer_id=current_user.data_capturer_id # Assign the capturer
        )
        db.session.add(new_item)
        db.session.commit()
        
        flash(f'Item "{new_item.name}" captured successfully in {room.name}!', 'success')
        # Redirect back to the capture page for the same room for quick, continuous entry
        return redirect(url_for('capturer.start_capture', room_id=room_id))

    return render_template('capturer/capture_form.html', form=form, room=room)

@data_capturer_bp.route('/my-items')
@login_required
@capturer_required
def my_items():
    """View items captured by this user (for review)."""
    # Fetch all items captured by the current user
    items = Item.query.filter_by(data_capturer_id=current_user.data_capturer_id).all()
    
    return render_template('capturer/my_items.html', items=items)

@data_capturer_bp.route('/item/update-status/<int:item_id>/<string:new_status>', methods=['POST'])
@login_required
@capturer_required
def update_item_status(item_id, new_status):
    """Allows the capturer to update the status of an item they captured."""
    item = Item.query.filter_by(
        item_id=item_id, 
        data_capturer_id=current_user.data_capturer_id # Only allow updates on their own items
    ).first_or_404()
    
    try:
        # Convert string status to the ItemStatus enum
        status_enum = ItemStatus[new_status.upper()] 
        item.status = status_enum
        db.session.commit()
        flash(f'Status for item "{item.name}" updated to {status_enum.value}.', 'success')
    except KeyError:
        flash(f'Invalid status requested: {new_status}.', 'danger')
        
    # Redirect back to the review page
    return redirect(url_for('capturer.my_items'))
 