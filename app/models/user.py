from app import db, bcrypt
from datetime import datetime, timedelta
from enum import Enum
import re
import secrets

class UserRole(Enum):
    USER = 'user'
    ADMIN = 'admin'
    MANAGER = 'manager'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    address = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(50), nullable=True)
    country = db.Column(db.String(50), nullable=True)
    postal_code = db.Column(db.String(20), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    role = db.Column(db.String(50), nullable=False, default=UserRole.USER.value)
    is_verified = db.Column(db.Boolean, nullable=False, default=False)
    verification_token = db.Column(db.String(100), nullable=True)
    verification_token_expires = db.Column(db.DateTime, nullable=True)
    accounts = db.relationship('Account', backref='owner', lazy=True)

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if 'password' in kwargs:
            self.password_hash = bcrypt.generate_password_hash(kwargs['password']).decode('utf-8')
        if not self.role:
            self.role = UserRole.USER.value

    def validate(self):
        """Validate user data"""
        errors = []
        
        # Validate username
        if not re.match(r'^[a-zA-Z0-9_]{3,20}$', self.username):
            errors.append("Username must be 3-20 characters long and contain only letters, numbers, and underscores")
            
        # Validate email
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', self.email):
            errors.append("Invalid email format")
            
        # Validate phone number if provided
        if self.phone_number and not re.match(r'^\+?[1-9]\d{1,14}$', self.phone_number):
            errors.append("Invalid phone number format")
            
        # Validate role
        if self.role not in [r.value for r in UserRole]:
            errors.append(f"Invalid role: {self.role}")
            
        # Validate name fields
        if self.first_name and len(self.first_name) > 50:
            errors.append("First name must be less than 50 characters")
        if self.last_name and len(self.last_name) > 50:
            errors.append("Last name must be less than 50 characters")
            
        # Validate address fields
        if self.address and len(self.address) > 200:
            errors.append("Address must be less than 200 characters")
        if self.city and len(self.city) > 50:
            errors.append("City must be less than 50 characters")
        if self.country and len(self.country) > 50:
            errors.append("Country must be less than 50 characters")
        if self.postal_code and len(self.postal_code) > 20:
            errors.append("Postal code must be less than 20 characters")
            
        return errors

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)
    
    @staticmethod
    def generate_password_hash(password):
        return bcrypt.generate_password_hash(password).decode('utf-8')
    
    def update_last_login(self):
        self.last_login = datetime.utcnow()
        db.session.commit()
    
    def generate_verification_token(self, expires_in=3600):
        """Generate a verification token that expires in the specified time (in seconds)"""
        self.verification_token = secrets.token_urlsafe(32)
        self.verification_token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
        db.session.commit()
        return self.verification_token
    
    def verify_token(self, token):
        """Verify if the provided token is valid and not expired"""
        if not self.verification_token or not self.verification_token_expires:
            return False
        if self.verification_token != token:
            return False
        if datetime.utcnow() > self.verification_token_expires:
            return False
        self.is_verified = True
        self.verification_token = None
        self.verification_token_expires = None
        db.session.commit()
        return True
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'phone_number': self.phone_number,
            'address': self.address,
            'city': self.city,
            'country': self.country,
            'postal_code': self.postal_code,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'role': self.role,
            'is_verified': self.is_verified
        } 