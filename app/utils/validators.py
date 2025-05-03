import re
from flask import jsonify

def validate_email(email):
    """Validate email format with stricter rules"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(pattern, email) is None:
        return False
    return True

def validate_password(password):
    """Password must be at least 8 characters and maximum 128 characters"""
    if len(password) < 8 or len(password) > 128:
        return False
    return True

def validate_amount(amount):
    """Amount must be positive and within reasonable limits"""
    try:
        amount = float(amount)
        if amount <= 0 or amount > 1000000:  # Maximum limit of 1 million
            return False
        return True
    except (ValueError, TypeError):
        return False

def error_response(message, status_code=400):
    """Return a standardized error response"""
    response = jsonify({'error': message})  # Always use 'error' key
    response.status_code = status_code
    return response 