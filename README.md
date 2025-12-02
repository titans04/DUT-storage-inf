# DUT-storage-inf

Overview
The DUT Inventory Management System is a full-stack web application designed to streamline asset tracking across multiple campuses. Built with Flask and PostgreSQL, it implements advanced role-based access control (RBAC), real-time data validation, and comprehensive reporting capabilities.

Business Problem Solved
Educational institutions struggle with tracking thousands of assets across multiple campuses, rooms, and departments. This system provides:

Centralized asset tracking with real-time updates
Role-based workflows preventing unauthorized access
Audit trails for asset movements and status changes
Professional reporting in PDF and Excel formats


 Key Features
 Multi-Level Authentication & Authorization

Super Admin: Full system control, manage all admins and campuses
Campus Admin: Manage specific campuses, data capturers, and inventory
Data Capturer: Add/edit items, move assets between rooms

Advanced Inventory Management

Smart asset tracking with unique asset numbers and serial numbers
Comprehensive item details: brand, color, capacity, procurement dates
Status management: Active, Inactive, Needs Repair, Stolen, Disposed
Category classification: Teaching & Learning, Projects/Research, Commercial

Multi-Campus Architecture

Hierarchical structure: Campus → Room → Item
Dynamic room management with staff assignments
Cross-campus item movement tracking with audit logs
Soft deletion with reason tracking for rooms

Powerful Reporting & Export

Multi-format exports: Excel (.xlsx) with formatted headers and summary sheets, PDF with landscape A3 layout
Advanced filtering: Date ranges (procurement & allocation), status, category, campus, room, staff, cost ranges
Custom column selection for tailored reports
Summary statistics by item name and status

Smart Search & Filtering

Real-time autocomplete for item types, brands, and colors
Case-insensitive search across all fields
Multi-criteria filtering with dynamic dropdowns
AJAX-powered room selection based on campus


Tech Stack

Backend

Framework: Flask 3.0 (Python 3.9+)
ORM: SQLAlchemy 2.0 with relationship management
Authentication: Flask-Login with Werkzeug password hashing
Database: PostgreSQL (production-ready with migrations)
Forms: WTForms with custom validators

Frontend

Template Engine: Jinja2
Styling: Custom CSS with responsive design
JavaScript: Vanilla JS for dynamic interactions
Icons: Modern UI/UX with intuitive navigation

Security Features

Password hashing: Werkzeug's generate_password_hash (SHA-256)
CSRF protection: Flask-WTF tokens on all forms
SQL injection prevention: SQLAlchemy parameterized queries
Role-based decorators: Custom @admin_required, @super_admin_required

Data Export Libraries

Excel: XlsxWriter with advanced formatting
PDF: ReportLab with custom table styling
Date handling: Python datetime with timezone support


Project Structure
dut-inventory/
├── app/
│   ├── __init__.py              # App factory pattern
│   ├── models.py                # SQLAlchemy models (Admin, DataCapturer, Item, Room, Campus)
│   ├── forms.py                 # WTForms with custom validators
│   ├── utils.py                 # Role decorators and helpers
│   ├── routes/
│   │   ├── auth_routes.py       # Login, logout, setup
│   │   ├── admin_routes.py      # Admin dashboard, inventory, exports
│   │   └── data_capturer_routes.py  # Item capture, editing, movement
│   ├── templates/
│   │   ├── auth/                # Login, setup pages
│   │   ├── admin/               # Admin dashboards, forms
│   │   └── data_capturer/       # Capturer workflows
│   └── static/
│       ├── css/                 # Custom stylesheets
│       ├── js/                  # Dynamic interactions
│       └── uploads/rooms/       # Room images
├── migrations/                  # Alembic database migrations
├── config.py                    # Environment configurations
├── requirements.txt             # Python dependencies
└── run.py                       # Application entry point

Installation
Prerequisites

Python 3.9 or higher
PostgreSQL 12+ (or SQLite for development)
pip package manager

Setup Steps

Clone the repository

bashgit clone https://github.com/yourusername/dut-inventory.git
cd dut-inventory

Create virtual environment

bashpython -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

Install dependencies

bashpip install -r requirements.txt

Configure environment variables

bash# Create .env file
echo "SECRET_KEY=your-secret-key-here" > .env
echo "DATABASE_URL=postgresql://user:password@localhost/dut_inventory" >> .env

Initialize database

bashflask db upgrade

Run the application

bashpython run.py

Access the system


Open browser: http://localhost:5000
First-time setup will prompt for Super Admin creation


Usage
Initial Setup

Navigate to /auth/setup to create the Super Admin account
Log in with Super Admin credentials
Add campuses and create Campus Admins
Campus Admins create Data Capturers and assign them to rooms

Daily Workflows
Data Capturer:

Select campus and room from dashboard
Capture new items with asset numbers
Edit item details (excludes cost/price)
Move items between rooms with audit trail

Campus Admin:

View inventory dashboard with filters
Edit items including cost and sensitive statuses (Disposed, Stolen)
Manage data capturers and room assignments
Export reports with custom date ranges and columns

Super Admin:

Create/edit/delete Campus Admins
View system-wide statistics
Access all campuses and data
Generate comprehensive reports


Database Schema Highlights
Core Models
pythonAdmin          # System administrators with campus assignments
DataCapturer   # Staff capturing inventory data
Campus         # Physical campus locations
Room           # Rooms within campuses (with staff details)
Item           # Individual inventory items
ItemMovement   # Audit trail for item relocations
Key Relationships

Many-to-Many: Admin ↔ Campus, DataCapturer ↔ Campus
One-to-Many: Room → Item, Campus → Room
Foreign Keys: Item.disposed_by_admin_id tracks disposal authorization


Screenshots
Super Admin Dashboard
System-wide statistics with campus, room, item, and admin counts
Inventory Export (Excel)

Inventory Sheet: Detailed item listing with formatted headers
Summary Sheet: Items grouped by name and status

Item Movement Tracking
Complete audit trail with source/destination rooms and staff details

Security Considerations

Authentication: Session-based with Flask-Login
Authorization: Custom decorators enforce role boundaries
Data Validation: Server-side WTForms validation + client-side checks
Audit Logging: ItemMovement table tracks all asset relocations
Soft Deletion: Rooms marked inactive instead of deleted


Future Enhancements

 QR code generation for asset tags
 Email notifications for status changes
 Mobile-responsive PWA
 Advanced analytics dashboard
 Bulk import via CSV/Excel
 API for third-party integrations


License
This project is licensed under the MIT License - see the LICENSE file for details.

Developer
Your Name
Email: bandilecele18@gmail.com
LinkedIn: www.linkedin.com/in/bandile-cele-92796a2b5
GitHub: @titans04

Acknowledgments

Built for Durban University of Technology (DUT)
Inspired by enterprise asset management systems
Special thanks to the Flask and SQLAlchemy communities
