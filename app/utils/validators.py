import re
from flask import jsonify
from datetime import datetime

def validate_email(email):
    """Validate email format"""
    if not email or not isinstance(email, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(pattern, email) is None:
        return False
    return True

def validate_password(password):
    """Password must be at least 8 characters with at least one uppercase, one lowercase, one number and one special character"""
    if not password or not isinstance(password, str):
        return False
    if len(password) < 8:
        return False
    if not re.search(r'[A-Z]', password):
        return False
    if not re.search(r'[a-z]', password):
        return False
    if not re.search(r'\d', password):
        return False
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False
    return True

def validate_amount(amount):
    """Amount must be positive and have at most 2 decimal places"""
    try:
        amount = float(amount)
        if amount <= 0:
            return False
        # Check for more than 2 decimal places
        if not re.match(r'^\d+(\.\d{1,2})?$', str(amount)):
            return False
        return True
    except (ValueError, TypeError):
        return False

def validate_currency(currency):
    """Validate currency code (ISO 4217 format)"""
    if not currency or not isinstance(currency, str):
        return False
    pattern = r'^[A-Z]{3}$'
    return bool(re.match(pattern, currency))

def validate_date(date_str, format='%Y-%m-%d'):
    """Validate date string format"""
    if not date_str or not isinstance(date_str, str):
        return False
    try:
        datetime.strptime(date_str, format)
        return True
    except ValueError:
        return False

def validate_phone(phone):
    """Validate phone number format"""
    if not phone or not isinstance(phone, str):
        return False
    # Remove any non-digit characters
    phone = re.sub(r'\D', '', phone)
    # Check if it's a valid length (between 10 and 15 digits)
    return 10 <= len(phone) <= 15

def validate_name(name):
    """Validate name format (letters, spaces, hyphens, and apostrophes only)"""
    if not name or not isinstance(name, str):
        return False
    pattern = r'^[a-zA-Z\s\'-]+$'
    return bool(re.match(pattern, name))

def error_response(message, status_code=400, details=None):
    """Return a standardized error response with optional details"""
    response_data = {'error': message}
    if details:
        response_data['details'] = details
    response = jsonify(response_data)
    response.status_code = status_code
    return response 