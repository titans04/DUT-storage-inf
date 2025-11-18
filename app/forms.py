from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectMultipleField, SelectField, TextAreaField, DateField, validators, DecimalField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError, Optional
from wtforms.widgets import ListWidget, CheckboxInput 
from app.models import ItemStatus
from wtforms.validators import DataRequired, Length, Optional, NumberRange
import enum
from flask_login import current_user
from flask_wtf.file import FileField, FileAllowed
import re
from wtforms.validators import Regexp
from . import db
from datetime import date

# --------------------------------------------------------------------------
# --- GLOBAL IMPORTS AND CONSTANTS ---
# --------------------------------------------------------------------------

# Custom validator function for checkbox lists
def validate_at_least_one(form, field):
    """Ensures that a SelectMultipleField has at least one item selected."""
    if not field.data:  # Checks if the submitted list of keys is empty
        raise ValidationError('You must select at least one campus.')

# Helper to import all necessary models for form validation
def get_auth_models():
    """Locally imports models only when needed by a function."""
    from .models import db, Admin, DataCapturer, Campus
    return db, Admin, DataCapturer, Campus

STATIC_DUT_CAMPUSES = [
    ('Ritson', 'Ritson Campus'),
    ('SteveBiko', 'Steve Biko Campus'),
    ('MLSultan', 'ML Sultan Campus'),
    ('City', 'City Campus')
]

# --------------------------------------------------------------------------
# --- 1. Super Admin Setup Form ---
# --------------------------------------------------------------------------

class SuperAdminSetupForm(FlaskForm):
    """Form for initial creation of the Super Admin account."""
    
    name = StringField('First Name', validators=[DataRequired(), Length(max=100)]) 
    surname = StringField('Last Name', validators=[DataRequired(), Length(max=100)]) 
    username = StringField('Username (Admin Login ID)', validators=[DataRequired(), Length(min=4, max=10)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password_confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Complete Setup & Create Account')
    
    def validate_username(self, username):
        db, Admin, DataCapturer, Campus = get_auth_models() 
        if Admin.query.filter_by(username=username.data).first():
            raise ValidationError('This username is already taken. Please choose a different one.')

# --------------------------------------------------------------------------
# --- 2. Login Form ---
# --------------------------------------------------------------------------

class LoginForm(FlaskForm):
    """Form for logging in both Admins (by username) and Data Capturers (by student number)."""
    
    email_or_id = StringField('Username (Admin) or Student ID (Capturer)', validators=[DataRequired(), Length(min=1, max=23)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')



class AdminCreationForm(FlaskForm):
    """Form for creating a new regular Admin account by a Super Admin."""
    
    name = StringField('First Name', validators=[DataRequired(), Length(max=100)]) 
    surname = StringField('Last Name', validators=[DataRequired(), Length(max=100)]) 
    username = StringField('Username (Admin Login ID)', validators=[DataRequired(), Length(min=4, max=10)])
    
    # Campus Assignment Checklist (FIX APPLIED)
    campuses_assigned = SelectMultipleField(
        'Campuses to Manage (Check all that apply)',
        validators=[validate_at_least_one], # <- USING CUSTOM VALIDATOR
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput(),
        choices=STATIC_DUT_CAMPUSES
    )
    
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password_confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Create Admin Account')
    
    def validate_username(self, username):
        db, Admin, DataCapturer, Campus = get_auth_models()
        if Admin.query.filter_by(username=username.data).first():
            raise ValidationError('This username is already taken by another admin.')



class AdminEditForm(AdminCreationForm):
    """Form for editing an existing Admin (excluding password change by default)."""
    password = PasswordField('New Password (Leave blank to keep current)', validators=[Optional(), Length(min=8)])
    password_confirm = PasswordField('Confirm New Password', validators=[Optional(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Update Admin Details')

    def __init__(self, original_username, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            db, Admin, DataCapturer, Campus = get_auth_models() 
            if Admin.query.filter_by(username=username.data).first():
                raise ValidationError('This username is already taken by another admin.')
            



# Custom validator function for campus selection
def validate_at_least_one_campus(form, field):
    """Ensures that a SelectMultipleField has at least one campus selected."""
    if not field.data:
        raise ValidationError('Please select at least one campus where this capturer will work.')


class DataCapturerCreationForm(FlaskForm):
    """Form for creating a new Data Capturer account with flexible campus assignment."""
    
    full_name = StringField(
        'Full Name', 
        validators=[DataRequired(), Length(max=120)]
    )
    
    student_number = StringField(
        'Student Number', 
        validators=[DataRequired(), Length(min=8, max=8)]
    )
    
    campuses_assigned = SelectMultipleField(
        'Campuses Data Capturer will work at (Select one or more)',
        validators=[validate_at_least_one_campus],
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput(),
        description='Choose the specific campuses where this capturer is authorized to work.'
    )

    can_create_room = BooleanField('Can Create Rooms?')

    password = PasswordField(
        'Password', 
        validators=[DataRequired(), Length(min=8)]
    )
    
    password_confirm = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match')]
    )

    submit = SubmitField('Create Capturer Account')





# Custom validator function for checkbox lists
def validate_at_least_one(form, field):
    """Ensures that a SelectMultipleField has at least one item selected."""
    if not field.data:  # Checks if the submitted list of keys is empty
        raise ValidationError('You must select at least one campus.')

# Helper to import all necessary models for form validation
def get_auth_models():
    """Locally imports models only when needed by a function."""
    from .models import db, Admin, DataCapturer, Campus
    return db, Admin, DataCapturer, Campus

STATIC_DUT_CAMPUSES = [
    ('Ritson', 'Ritson Campus'),
    ('SteveBiko', 'Steve Biko Campus'),
    ('MLSultan', 'ML Sultan Campus'),
    ('City', 'City Campus')
]

# --------------------------------------------------------------------------
# --- 1. Super Admin Setup Form ---
# --------------------------------------------------------------------------

class SuperAdminSetupForm(FlaskForm):
    """Form for initial creation of the Super Admin account."""
    
    name = StringField('First Name', validators=[DataRequired(), Length(max=100)]) 
    surname = StringField('Last Name', validators=[DataRequired(), Length(max=100)]) 
    username = StringField('Username (Admin Login ID)', validators=[DataRequired(), Length(min=4, max=10)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password_confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Complete Setup & Create Account')
    
    def validate_username(self, username):
        db, Admin, DataCapturer, Campus = get_auth_models() 
        if Admin.query.filter_by(username=username.data).first():
            raise ValidationError('This username is already taken. Please choose a different one.')

# --------------------------------------------------------------------------
# --- 2. Login Form ---
# --------------------------------------------------------------------------

class LoginForm(FlaskForm):
    """Form for logging in both Admins (by username) and Data Capturers (by student number)."""
    
    email_or_id = StringField('Username (Admin) or Student ID (Capturer)', validators=[DataRequired(), Length(min=1, max=23)])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Login')



class AdminCreationForm(FlaskForm):
    """Form for creating a new regular Admin account by a Super Admin."""
    
    name = StringField('First Name', validators=[DataRequired(), Length(max=100)]) 
    surname = StringField('Last Name', validators=[DataRequired(), Length(max=100)]) 
    username = StringField('Username (Admin Login ID)', validators=[DataRequired(), Length(min=4, max=10)])
    
    # Campus Assignment Checklist (FIX APPLIED)
    campuses_assigned = SelectMultipleField(
        'Campuses to Manage (Check all that apply)',
        validators=[validate_at_least_one], # <- USING CUSTOM VALIDATOR
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput(),
        choices=STATIC_DUT_CAMPUSES
    )
    
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password_confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Create Admin Account')
    
    def validate_username(self, username):
        db, Admin, DataCapturer, Campus = get_auth_models()
        if Admin.query.filter_by(username=username.data).first():
            raise ValidationError('This username is already taken by another admin.')


class AdminEditForm(AdminCreationForm):
    """Form for editing an existing Admin (excluding password change by default)."""
    password = PasswordField('New Password (Leave blank to keep current)', validators=[Optional(), Length(min=8)])
    password_confirm = PasswordField('Confirm New Password', validators=[Optional(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Update Admin Details')

    def __init__(self, original_username, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.original_username = original_username

    def validate_username(self, username):
        if username.data != self.original_username:
            db, Admin, DataCapturer, Campus = get_auth_models() 
            if Admin.query.filter_by(username=username.data).first():
                raise ValidationError('This username is already taken by another admin.')
            



# Custom validator function for campus selection
def validate_at_least_one_campus(form, field):
    """Ensures that a SelectMultipleField has at least one campus selected."""
    if not field.data:
        raise ValidationError('Please select at least one campus where this capturer will work.')


class DataCapturerCreationForm(FlaskForm):
    """Form for creating a new Data Capturer account with flexible campus assignment."""
    
    full_name = StringField(
        'Full Name', 
        validators=[DataRequired(), Length(max=120)]
    )
    
    student_number = StringField(
        'Student Number', 
        validators=[DataRequired(), Length(min=8, max=8)]
    )
    
    campuses_assigned = SelectMultipleField(
        'Campuses Data Capturer will work at (Select one or more)',
        validators=[validate_at_least_one_campus],
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput(),
        description='Choose the specific campuses where this capturer is authorized to work.'
    )

    can_create_room = BooleanField('Can Create Rooms?')

    password = PasswordField(
        'Password', 
        validators=[DataRequired(), Length(min=8)]
    )
    
    password_confirm = PasswordField(
        'Confirm Password',
        validators=[DataRequired(), EqualTo('password', message='Passwords must match')]
    )

    submit = SubmitField('Create Capturer Account')


class ItemCreationForm(FlaskForm):
    """
    Form for capturing new inventory items.
    Prevents future dates for Procured and Allocated dates.
    """
    name = StringField('Item Name', validators=[DataRequired()])
    asset_tag = StringField('Asset Tag/Barcode', validators=[DataRequired()])

    brand = StringField('Brand / Manufacturer', validators=[Optional()])
    serial_number = StringField('Serial Number (Optional)', validators=[Optional()])
    description = TextAreaField('Description / Model', validators=[Optional()])
    color = StringField('Color', validators=[Optional()])

    # Prevent future dates
    def validate_future_date(form, field):
        if field.data and field.data > date.today():
            raise ValidationError('Future dates are not allowed.')

    procured_date = DateField(
        'Procured Date',
        format='%Y-%m-%d',
        validators=[DataRequired(), validate_future_date]
    )

    allocated_date = DateField(
        'Allocated Date (Optional)',
        format='%Y-%m-%d',
        validators=[Optional(), validate_future_date]
    )

    status = SelectField('Condition / Status', coerce=str, validators=[DataRequired()])
    submit = SubmitField('Capture Item')



# Replace ALL instances of LocationSelectionForm in your forms.py:

class LocationSelectionForm(FlaskForm):
    """Form for selecting campus and room location"""
    campus = SelectField(
        'Campus', 
        coerce=str,
        validators=[DataRequired(message='Please select a campus')],
        validate_choice=False  # ✅ Allow AJAX-populated choices
    )
    
    room = SelectField(
        'Room', 
        coerce=str,
        validators=[DataRequired(message='Please select a room')],
        validate_choice=False  # ✅ Allow AJAX-populated choices
    )
    
    staff_number = StringField('Staff Number', validators=[DataRequired(), Length(max=8)])
    staff_name = StringField('Staff Name', validators=[DataRequired(), Length(max=120)])
    
    submit = SubmitField('Proceed to Room Management')


#-----Move item to another room---------------#
class ItemMovementForm(FlaskForm):
    # Destination
    to_room = SelectField('Destination Room', coerce=int, validators=[validators.DataRequired()])
    
    # Information for the room the item is coming FROM (Current Room)
    source_staff_name = StringField('Staff Name (Source Room)', validators=[validators.Optional(), validators.Length(max=120)])
    source_staff_number = StringField('Staff No. (Source Room)', validators=[validators.Optional(), validators.Length(max=8)])
    
    # Information for the room the item is going TO (New Room)
    dest_staff_name = StringField('Staff Name (Destination Room)', validators=[validators.Optional(), validators.Length(max=120)])
    dest_staff_number = StringField('Staff No. (Destination Room)', validators=[validators.Optional(), validators.Length(max=8)])
 



# forms.py
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField, FileField
from wtforms.validators import DataRequired, Length, Optional, Regexp
from wtforms.widgets import html_params
from markupsafe import Markup


class RoomCreationForm(FlaskForm):
    campus = SelectField('Campus Location', coerce=int, validators=[DataRequired()])
    name = StringField('Room Name/Number', validators=[DataRequired(), Length(max=120)])
    description = TextAreaField('Description (Optional)', validators=[Optional()])

    # Faculty dropdown + "Other" with dynamic input
    faculty = SelectField('Faculty (Optional)', choices=[], coerce=str)
    faculty_other = StringField('Specify Faculty', validators=[Optional(), Length(max=150)])

    staff_name = StringField('Responsible Staff Name', validators=[Optional(), Length(max=120)])
    staff_number = StringField(
        'Staff Number',
        validators=[
            Optional(),
            Length(min=8, max=8, message='Staff number must be exactly 8 digits.'),
            Regexp(r'^\d{8}$', message='Staff number must contain only digits.')
        ]
    )

    room_picture = FileField(
        'Room Picture (Optional)',
        validators=[Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'Images only!')]
    )

    submit = SubmitField('Save Room Details')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate faculty choices from existing rooms
        from .models import Room
        faculties = db.session.query(Room.faculty).filter(Room.faculty != None).distinct().all()
        choices = [(f[0], f[0]) for f in faculties if f[0]]
        choices.append(('other', 'Other – specify...'))
        self.faculty.choices = choices


class EditItemForm(FlaskForm):
    """
    Form for editing an inventory item's details. 
    
    The 'price' field is set to read-only by default to restrict updates 
    by the Data Capturer role.
    """
    asset_number = StringField(
        'Asset Number',
        validators=[DataRequired(), Length(min=3, max=50)],
        # Asset number is generally fixed
        render_kw={'placeholder': 'e.g., DUTC00123', 'readonly': True} 
    )
    
    serial_number = StringField(
        'Serial Number (Optional)',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'e.g., SN-X1A2Y3B4'}
    )
    
    name = StringField(
        'Item Name',
        validators=[DataRequired(), Length(min=2, max=120)],
        render_kw={'placeholder': 'e.g., Dell Monitor 27-inch'}
    )
    
    brand = StringField(
        'Brand/Model',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'e.g., Lenovo, HP ZBook G7'}
    )
    
    color = StringField(
        'Color',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': 'e.g., Black, Silver'}
    )
    
    price = DecimalField(
        'Purchase Price (R)',
        validators=[
            Optional(), 
            NumberRange(min=0, message="Price cannot be negative.")
        ],
        places=2,
        # 🔒 READ-ONLY FOR DATA CAPTURER
        render_kw={'placeholder': 'e.g., 3500.50', 'step': '0.01', 'readonly': True} 
    )
    
    status = SelectField(
        'Status',
        choices=[], # Populated via ItemStatus.choices() in the view function
        validators=[DataRequired()]
    )

    allocated_date = DateField(
        'Date Allocated (Optional)',
        validators=[Optional()],
        format='%Y-%m-%d', 
        render_kw={'placeholder': 'YYYY-MM-DD'}
    )
    
    description = TextAreaField(
        'Description (Optional)', 
        validators=[Optional(), Length(max=500)],
        render_kw={'rows': 3}
    )

    submit = SubmitField('Update Item Details')


class SuperAdminProfileEditForm(FlaskForm):
    """Form for Super Admin to edit their profile."""
    name = StringField('First Name', validators=[DataRequired(), Length(max=100)])
    surname = StringField('Last Name', validators=[DataRequired(), Length(max=100)])
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=10)])
    
    current_password = PasswordField('Current Password (required to confirm changes)', validators=[DataRequired()])
    new_password = PasswordField('New Password (Leave blank to keep current)', validators=[Optional(), Length(min=8)])
    new_password_confirm = PasswordField(
        'Confirm New Password',
        validators=[Optional(), EqualTo('new_password', message='Passwords must match')]
    )
    
    submit = SubmitField('Update Profile')
    
    def validate_username(self, username):
        db, Admin, DataCapturer, Campus = get_auth_models()
        admin = Admin.query.filter_by(username=username.data).first()
        if admin and admin.admin_id != current_user.admin_id:
            raise ValidationError('This username is already taken.')


class AdminProfileEditForm(FlaskForm):
    """Form for regular Admin to edit their profile."""
    name = StringField('First Name', validators=[DataRequired(), Length(max=100)])
    surname = StringField('Last Name', validators=[DataRequired(), Length(max=100)])
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=10)])
    
    current_password = PasswordField('Current Password (required to confirm changes)', validators=[DataRequired()])
    new_password = PasswordField('New Password (Leave blank to keep current)', validators=[Optional(), Length(min=8)])
    new_password_confirm = PasswordField(
        'Confirm New Password',
        validators=[Optional(), EqualTo('new_password', message='Passwords must match')]
    )
    
    submit = SubmitField('Update Profile')
    
    def validate_username(self, username):
        db, Admin, DataCapturer, Campus = get_auth_models()
        admin = Admin.query.filter_by(username=username.data).first()
        if admin and admin.admin_id != current_user.admin_id:
            raise ValidationError('This username is already taken.')



class CampusRoomCreationForm(FlaskForm):
    """Form for Admin to select which campuses allow Data Capturers to create new rooms."""
    allowed_campuses = SelectMultipleField(
        'Campuses Allowed for Room Creation',
        coerce=int,
        validators=[DataRequired(message="You must select at least one campus.")],
        description='Select the campuses where Data Capturers under your supervision can create new rooms.'
    )
    submit = SubmitField('Update Room Creation Permissions')



class AdminEditItemForm(FlaskForm):
    """Admin version of item edit form - includes price/cost field."""
    
    asset_number = StringField(
        'Asset Number',
        validators=[DataRequired(), Length(min=3, max=100)],
        render_kw={'placeholder': 'e.g., DUTC00123'}
    )
    
    serial_number = StringField(
        'Serial Number (Optional)',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'e.g., SN-X1A2Y3B4'}
    )
    
    name = StringField(
        'Item Name',
        validators=[DataRequired(), Length(min=2, max=120)],
        render_kw={'placeholder': 'e.g., Dell Monitor 27-inch'}
    )
    
    brand = StringField(
        'Brand/Model',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': 'e.g., Lenovo, HP ZBook G7'}
    )
    
    color = StringField(
        'Color',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': 'e.g., Black, Silver'}
    )
    
    # ADD THIS FIELD
    capacity = StringField(
        'Capacity / Specifications',
        validators=[Optional(), Length(max=200)],
        render_kw={'placeholder': 'e.g., 1TB SSD, 16GB RAM, i7-12700H'}
    )
    
    # Admin can edit price
    cost = DecimalField(
        'Cost (R)',
        validators=[
            Optional(), 
            NumberRange(min=0, message="Price cannot be negative.")
        ],
        places=2,
        render_kw={'placeholder': 'e.g., 3500.50', 'step': '0.01'}
    )
    
    status = SelectField(
        'Status',
        choices=[],  # Populated in route
        validators=[DataRequired()]
    )

    procured_date = DateField(
        'Procurement Date',
        validators=[DataRequired()],
        format='%Y-%m-%d', 
        render_kw={'placeholder': 'YYYY-MM-DD'}
    )

    allocated_date = DateField(
        'Date Allocated (Optional)',
        validators=[Optional()],
        format='%Y-%m-%d', 
        render_kw={'placeholder': 'YYYY-MM-DD'}
    )
    
    description = TextAreaField(
        'Description (Optional)', 
        validators=[Optional(), Length(max=500)],
        render_kw={'rows': 3, 'placeholder': 'Additional details about the item'}
    )

    submit = SubmitField('Update Item Details')



class EditItemForm(FlaskForm):
    """
    Form for editing an inventory item's details by Data Capturers.
    
    Note: Price/cost field is NOT included - only admins can edit prices.
    """
    asset_number = StringField(
        'Asset Number',
        validators=[DataRequired(), Length(min=3, max=100)],
        render_kw={'placeholder': 'e.g., DUTC00123'}
    )
    
    serial_number = StringField(
        'Serial Number (Optional)',
        validators=[Optional(), Length(max=100)],
        render_kw={'placeholder': 'e.g., SN-X1A2Y3B4'}
    )
    
    name = StringField(
        'Item Name',
        validators=[DataRequired(), Length(min=2, max=120)],
        render_kw={'placeholder': 'e.g., Dell Monitor 27-inch'}
    )
    
    brand = StringField(
        'Brand/Model',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': 'e.g., Lenovo, HP ZBook G7'}
    )
    
    color = StringField(
        'Color',
        validators=[Optional(), Length(max=50)],
        render_kw={'placeholder': 'e.g., Black, Silver'}
    )
    
    status = SelectField(
        'Status',
        choices=[], # Populated dynamically in the route
        validators=[DataRequired()]
    )

    capacity = StringField(
        'Capacity / Specifications',
         validators=[Optional(), Length(max=200)],
         render_kw={'placeholder': 'e.g., 1TB SSD, 16GB RAM, i7-12700H'}
    )
    
    procured_date = DateField(
        'Procurement Date',
        validators=[DataRequired()],
        format='%Y-%m-%d', 
        render_kw={'placeholder': 'YYYY-MM-DD'}
    )

    allocated_date = DateField(
        'Date Allocated (Optional)',
        validators=[Optional()],
        format='%Y-%m-%d', 
        render_kw={'placeholder': 'YYYY-MM-DD'}
    )
    
    description = TextAreaField(
        'Description (Optional)', 
        validators=[Optional(), Length(max=500)],
        render_kw={'rows': 3, 'placeholder': 'Additional details about the item'}
    )

    submit = SubmitField('Update Item Details')




class SuperAdminProfileEditForm(FlaskForm):
    """Form for Super Admin to edit their profile."""
    name = StringField('First Name', validators=[DataRequired(), Length(max=100)])
    surname = StringField('Last Name', validators=[DataRequired(), Length(max=100)])
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=10)])
    
    current_password = PasswordField('Current Password (required to confirm changes)', validators=[DataRequired()])
    new_password = PasswordField('New Password (Leave blank to keep current)', validators=[Optional(), Length(min=8)])
    new_password_confirm = PasswordField(
        'Confirm New Password',
        validators=[Optional(), EqualTo('new_password', message='Passwords must match')]
    )
    
    submit = SubmitField('Update Profile')
    
    def validate_username(self, username):
        db, Admin, DataCapturer, Campus = get_auth_models()
        admin = Admin.query.filter_by(username=username.data).first()
        if admin and admin.admin_id != current_user.admin_id:
            raise ValidationError('This username is already taken.')


class AdminProfileEditForm(FlaskForm):
    """Form for regular Admin to edit their profile."""
    name = StringField('First Name', validators=[DataRequired(), Length(max=100)])
    surname = StringField('Last Name', validators=[DataRequired(), Length(max=100)])
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=10)])
    
    current_password = PasswordField('Current Password (required to confirm changes)', validators=[DataRequired()])
    new_password = PasswordField('New Password (Leave blank to keep current)', validators=[Optional(), Length(min=8)])
    new_password_confirm = PasswordField(
        'Confirm New Password',
        validators=[Optional(), EqualTo('new_password', message='Passwords must match')]
    )
    
    submit = SubmitField('Update Profile')
    
    def validate_username(self, username):
        db, Admin, DataCapturer, Campus = get_auth_models()
        admin = Admin.query.filter_by(username=username.data).first()
        if admin and admin.admin_id != current_user.admin_id:
            raise ValidationError('This username is already taken.')



class CampusRoomCreationForm(FlaskForm):
    """Form for Admin to select which campuses allow Data Capturers to create new rooms."""
    allowed_campuses = SelectMultipleField(
        'Campuses Allowed for Room Creation',
        coerce=int,
        validators=[DataRequired(message="You must select at least one campus.")],
        description='Select the campuses where Data Capturers under your supervision can create new rooms.'
    )
    submit = SubmitField('Update Room Creation Permissions')



# app/forms.py  ← Add or replace this class

from wtforms import StringField, PasswordField, BooleanField, SelectMultipleField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, EqualTo
from flask_wtf import FlaskForm

class DataCapturerEditForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=120)])
    student_number = StringField('Student Number', validators=[DataRequired(), Length(8, 8)])

    # This is the only extra permission field
    can_create_room = BooleanField('Can Create Rooms?')

    # Optional password change
    password = PasswordField('New Password (leave blank to keep current)', validators=[Optional(), Length(min=8)])
    password_confirm = PasswordField(
        'Confirm New Password',
        validators=[Optional(), EqualTo('password', message='Passwords must match')]
    )

    # Assigned campuses (many-to-many)
    campuses_assigned = SelectMultipleField(
        'Assigned Campuses',
        coerce=int,
        validators=[Optional()]
    )

    submit = SubmitField('Update Capturer')