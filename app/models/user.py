from app import db, bcrypt
from datetime import datetime, timedelta
import re
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    first_name = db.Column(db.String(50), nullable=True)
    last_name = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    role = db.Column(db.String(50), nullable=False, default='user')
    accounts = db.relationship('Account', backref='owner', lazy=True)
    last_login = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    # Email validation regex
    EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    # Username validation regex (alphanumeric and underscore, 3-20 chars)
    USERNAME_REGEX = re.compile(r'^[a-zA-Z0-9_]{3,20}$')

    def __init__(self, username, email, password, first_name=None, last_name=None):
        if not self.USERNAME_REGEX.match(username):
            raise BadRequest('Username must be 3-20 characters long and contain only letters, numbers, and underscores')
        
        if not self.EMAIL_REGEX.match(email):
            raise BadRequest('Invalid email format')
        
        if len(password) < 8:
            raise BadRequest('Password must be at least 8 characters long')
        
        self.username = username
        self.email = email
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        self.first_name = first_name
        self.last_name = last_name
    
    def check_password(self, password):
        if not self.is_active:
            raise BadRequest('Account is inactive')
        
        if self.locked_until and datetime.utcnow() < self.locked_until:
            raise BadRequest('Account is temporarily locked')
        
        if bcrypt.check_password_hash(self.password_hash, password):
            self.failed_login_attempts = 0
            self.last_login = datetime.utcnow()
            db.session.commit()
            return True
        
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=15)
        db.session.commit()
        return False
    
    @staticmethod
    def generate_password_hash(password):
        if len(password) < 8:
            raise BadRequest('Password must be at least 8 characters long')
        return bcrypt.generate_password_hash(password).decode('utf-8')
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'created_at': self.created_at.isoformat(),
            'role': self.role,
            'is_active': self.is_active
        }
    
    def activate(self):
        self.is_active = True
        self.failed_login_attempts = 0
        self.locked_until = None
        db.session.commit()
    
    def deactivate(self):
        self.is_active = False
        db.session.commit()
    
    def change_password(self, old_password, new_password):
        if not self.check_password(old_password):
            raise BadRequest('Current password is incorrect')
        
        if len(new_password) < 8:
            raise BadRequest('New password must be at least 8 characters long')
        
        self.password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit() 