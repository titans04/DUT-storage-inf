from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Enum as SQLAlchemyEnum
from datetime import datetime
import enum
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize the SQLAlchemy object (this needs to be passed to init_app later)
db = SQLAlchemy()

# --- Updated Enumerations for Status and Format ---
class ItemStatus(enum.Enum):
    """Enumerates the possible statuses of an inventory item based on the web flow."""
    ACTIVE = 'Active'
    INACTIVE = 'Inactive'
    NEEDS_REPAIR = 'Needs Repair'
    STOLEN  = "Stolen"
    DISPOSED = 'Disposed'
    
    @classmethod
    def choices(cls):
        """Returns a list of tuples for use in forms/templates."""
        return [(status.name, status.value) for status in cls]


class ExportFormat(enum.Enum):
    """Enumerates the possible formats for an inventory export."""
    CSV = 'CSV'
    PDF = 'PDF'
    EXCEL = 'Excel'


# --- Association Tables for Many-to-Many Relationships ---

admin_campus_association = db.Table('admin_campus_association',
    db.Column('admin_id', db.Integer, db.ForeignKey('admin.admin_id'), primary_key=True),
    db.Column('campus_id', db.Integer, db.ForeignKey('campus.campus_id'), primary_key=True)
)

capturer_campus_association = db.Table('capturer_campus_association',
    db.Column('data_capturer_id', db.Integer, db.ForeignKey('data_capturer.data_capturer_id'), primary_key=True),
    db.Column('campus_id', db.Integer, db.ForeignKey('campus.campus_id'), primary_key=True)
)


# --------------------------------------------------------
# --- Database Models ---
# --------------------------------------------------------

class Admin(db.Model, UserMixin):
    """Represents an administrator who manages data capturers and campuses."""
    __tablename__ = 'admin'
    admin_id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True) 
    surname = db.Column(db.String(100), nullable=True)
    password_hash = db.Column(db.String(128), nullable=False)
    is_super_admin = db.Column(db.Boolean, default=False, nullable=False)

    data_capturers = db.relationship(
        'DataCapturer', backref='admin', lazy=True, cascade="all, delete-orphan", foreign_keys='DataCapturer.admin_id'
    )
    campuses = db.relationship('Campus', secondary=admin_campus_association, lazy='subquery',
                              backref=db.backref('admins', lazy=True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        # Crucial for Flask-Login to distinguish users
        return f"A-{self.admin_id}"
    
    # --- FIX: Role properties for authorization checks ---
    @property
    def is_admin(self):
        """Check used in routes to verify admin status."""
        return True
    
    @property
    def is_data_capturer(self):
        """Admins are not capturers (unless explicit role-switching is implemented)."""
        return False
    # ---------------------------------------------------

    def __repr__(self):
        return f'<Admin(ID={self.admin_id}, Username={self.username})>'


class DataCapturer(db.Model, UserMixin):
    """Represents a data capturer who adds and manages items."""
    __tablename__ = 'data_capturer'
    data_capturer_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    student_number = db.Column(db.String(8), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    can_create_room = db.Column(db.Boolean, default=False)

    admin_id = db.Column(db.Integer, db.ForeignKey('admin.admin_id'), nullable=True) 

    items = db.relationship('Item', backref='data_capturer', lazy=True)
    exports = db.relationship('InventoryExport', backref='data_capturer', lazy=True)
    assigned_campuses = db.relationship('Campus', secondary=capturer_campus_association, lazy='subquery',
                                         backref=db.backref('data_capturers', lazy=True))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return f"D-{self.data_capturer_id}"
    
    
    @property
    def is_super_admin(self):
        """A DataCapturer is never a super admin."""
        return False
    
    @property
    def is_data_capturer(self):
        """Check used in routes to verify data capturer status."""
        return True

    @property
    def is_admin(self):
        """Capturers are not admins."""
        return False
    # ---------------------------------------------------------------------------

    def __repr__(self):
        return f'<DataCapturer(ID={self.data_capturer_id}, Name={self.full_name})>'


class Campus(db.Model):
    """Represents a university campus."""
    __tablename__ = 'campus'
    campus_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    rooms = db.relationship('Room', backref='campus', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Campus(ID={self.campus_id}, Name={self.name})>'


class Room(db.Model):
    """Represents a physical room within a campus where items are stored."""
    __tablename__ = 'room'
    room_id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    
    staff_number = db.Column(db.String(8), nullable=True)  # DUT staff number (8 digits)
    staff_name = db.Column(db.String(120), nullable=True) 
    description = db.Column(db.Text, nullable=True)
    campus_id = db.Column(db.Integer, db.ForeignKey('campus.campus_id'), nullable=False)
    items = db.relationship('Item', backref='room', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f'<Room(ID={self.room_id}, Name={self.name}, Campus ID={self.campus_id})>'


class Item(db.Model):
    """Represents a single item in the inventory."""
    __tablename__ = 'item'
    item_id = db.Column(db.Integer, primary_key=True)
    asset_number = db.Column(db.String(100), unique=True, nullable=False)
    serial_number = db.Column(db.String(100), nullable=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    color = db.Column(db.String(50), nullable=True)
    brand = db.Column(db.String(50), nullable=True)
    status = db.Column(SQLAlchemyEnum(ItemStatus), default=ItemStatus.ACTIVE, nullable=False)
    capture_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    disposal_reason = db.Column(db.Text, nullable=True)
    allocated_date = db.Column(db.Date, nullable=True)
    
    price = db.Column(db.Numeric(12, 2), nullable=True) 

    data_capturer_id = db.Column(db.Integer, db.ForeignKey('data_capturer.data_capturer_id'), nullable=True)
    room_id = db.Column(db.Integer, db.ForeignKey('room.room_id'), nullable=False)
    
    disposed_by_admin_id = db.Column(db.Integer, db.ForeignKey('admin.admin_id'), nullable=True)
    disposed_by_admin = db.relationship('Admin', foreign_keys=[disposed_by_admin_id], backref='disposed_items')


    def __repr__(self):
        return f'<Item(ID={self.item_id}, Name={self.name}, Status={self.status.value})>'


class InventoryExport(db.Model):
    """Represents a record of an inventory data export."""
    __tablename__ = 'inventory_export'
    export_id = db.Column(db.Integer, primary_key=True)
    export_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    export_format = db.Column(SQLAlchemyEnum(ExportFormat), nullable=False)

    data_capturer_id = db.Column(db.Integer, db.ForeignKey('data_capturer.data_capturer_id'), nullable=True)
    
    def __repr__(self):
        return f'<InventoryExport(ID={self.export_id}, Format={self.export_format.value}, Date={self.export_date.date()})>'



class ItemMovement(db.Model):
    __tablename__ = 'item_movement'
    movement_id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item.item_id'), nullable=False)
    from_room_id = db.Column(db.Integer, db.ForeignKey('room.room_id'), nullable=True)
    to_room_id = db.Column(db.Integer, db.ForeignKey('room.room_id'), nullable=False)
    moved_by_id = db.Column(db.Integer, db.ForeignKey('data_capturer.data_capturer_id'), nullable=False)
    move_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
