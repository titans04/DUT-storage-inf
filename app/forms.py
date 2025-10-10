from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, SelectMultipleField, SelectField, TextAreaField
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError, Optional 
from wtforms.widgets import ListWidget, CheckboxInput 

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

# --------------------------------------------------------------------------
# --- 3. Admin Creation/Management Forms ---
# --------------------------------------------------------------------------

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
            
# --------------------------------------------------------------------------
# --- 4. Data Capturer Creation Form ---
# --------------------------------------------------------------------------
            
class DataCapturerCreationForm(FlaskForm):
    """Form for creating a new Data Capturer account."""
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=120)]) 
    student_number = StringField('Student Number', validators=[DataRequired(), Length(min=8, max=8)])
    
    # Campus Assignment (Scope for where they can capture data) (FIX APPLIED)
    campuses_assigned = SelectMultipleField(
        'Campuses Data Capturer will work at (Check all that apply)',
        validators=[validate_at_least_one], # <- USING CUSTOM VALIDATOR
        widget=ListWidget(prefix_label=False),
        option_widget=CheckboxInput()
    )

    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    password_confirm = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password', message='Passwords must match')])
    submit = SubmitField('Create Capturer Account')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Campus choices are dynamically set in the route function (add_capturer) 
        
    def validate_student_number(self, student_number):
        # Already fixed import issue previously
        db, Admin, DataCapturer, Campus = get_auth_models() 
        if DataCapturer.query.filter_by(student_number=student_number.data).first():
            raise ValidationError('This student number is already registered.')
        




class LocationSelectionForm(FlaskForm):
    """
    Form used on the capturer dashboard to select campus and room. 
    The choices for 'campus' are dynamically set in the route.
    The choices for 'room' are typically handled via JavaScript/AJAX after campus selection.
    """
    campus = SelectField('Campus', validators=[DataRequired()]) 
    room = SelectField('Room', validators=[DataRequired()])
    submit = SubmitField('Start Capturing Items')


class ItemCreationForm(FlaskForm):
    """
    Form used for rapidly capturing new inventory items. 
    It collects core data required for a new item entry, aligning with the Item model.
    """
    # Required fields based on Item model (name and asset_number)
    name = StringField('Item Name', validators=[DataRequired()])
    brand = StringField('Brand/Model', validators=[DataRequired()])
    # Renamed 'barcode' to 'asset_tag' to clearly map to Item.asset_number
    asset_tag = StringField('Asset Tag/Barcode', validators=[DataRequired()]) 

    # Optional fields based on Item model
    serial_number = StringField('Serial Number (Optional)', validators=[Optional()]) 
    description = StringField('Description (Optional)', validators=[Optional()])   

    submit = SubmitField('Capture Item')





class RoomCreationForm(FlaskForm):
    """Form for creating or editing a room within a campus."""
    # This field will be populated dynamically in the route (e.g., in add_room)
    campus = SelectField('Campus Location', coerce=int, validators=[DataRequired()])
    name = StringField('Room Name/Number', validators=[DataRequired(), Length(max=120)])
    # The routes requested adding 'description' and 'location' fields to the edit flow, 
    # so I've added a basic TextAreaField here for future use, although the Room model 
    # in your models.py doesn't currently have a description field.
    description = TextAreaField('Description (Optional)', validators=[Optional()])
    submit = SubmitField('Save Room Details')    