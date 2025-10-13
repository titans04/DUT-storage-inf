from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ..models import Admin, Campus, DataCapturer, db, Item, Room, ItemStatus
from ..forms import AdminCreationForm, AdminEditForm, DataCapturerCreationForm, STATIC_DUT_CAMPUSES,RoomCreationForm, EditItemForm, CampusRoomCreationForm
from flask import current_app
from wtforms.validators import DataRequired, EqualTo, Length, ValidationError, Optional 
import enum
from functools import wraps
from ..utils import admin_required, super_admin_required
# New imports needed for forms defined within this file (like CampusRoomCreationForm)
from flask_wtf import FlaskForm
from wtforms import SelectMultipleField, SubmitField
from sqlalchemy import or_