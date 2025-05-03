import random
import string
import re
from datetime import datetime

def generate_account_number(account_type='SAVINGS'):
    """
    Generate a unique account number based on account type and timestamp
    Format: TYPE-YYYYMMDD-XXXXXX
    """
    if not account_type or not isinstance(account_type, str):
        raise ValueError("Account type must be a non-empty string")
    
    # Get current date in YYYYMMDD format
    date_str = datetime.now().strftime('%Y%m%d')
    
    # Generate 6 random digits
    random_digits = ''.join(random.choices(string.digits, k=6))
    
    # Create account number
    account_number = f"{account_type[:3].upper()}-{date_str}-{random_digits}"
    
    return account_number

def validate_account_number(account_number):
    """
    Validate account number format
    Format: TYPE-YYYYMMDD-XXXXXX
    """
    if not account_number or not isinstance(account_number, str):
        return False
    
    pattern = r'^[A-Z]{3}-\d{8}-\d{6}$'
    if not re.match(pattern, account_number):
        return False
    
    # Extract date part and validate
    try:
        date_str = account_number.split('-')[1]
        datetime.strptime(date_str, '%Y%m%d')
    except (IndexError, ValueError):
        return False
    
    return True

def generate_reference_number(transaction_type):
    """
    Generate a unique reference number for transactions
    Format: TYPE-YYYYMMDDHHMMSS-XXXXXX
    """
    if not transaction_type or not isinstance(transaction_type, str):
        raise ValueError("Transaction type must be a non-empty string")
    
    # Get current timestamp
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    
    # Generate 6 random alphanumeric characters
    random_chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # Create reference number
    reference_number = f"{transaction_type[:3].upper()}-{timestamp}-{random_chars}"
    
    return reference_number

def validate_reference_number(reference_number):
    """
    Validate reference number format
    Format: TYPE-YYYYMMDDHHMMSS-XXXXXX
    """
    if not reference_number or not isinstance(reference_number, str):
        return False
    
    pattern = r'^[A-Z]{3}-\d{14}-[A-Z0-9]{6}$'
    if not re.match(pattern, reference_number):
        return False
    
    # Extract timestamp part and validate
    try:
        timestamp = reference_number.split('-')[1]
        datetime.strptime(timestamp, '%Y%m%d%H%M%S')
    except (IndexError, ValueError):
        return False
    
    return True 