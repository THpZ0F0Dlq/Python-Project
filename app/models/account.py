from app import db
from datetime import datetime
import re
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest
from decimal import Decimal

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), unique=True, nullable=False, index=True)
    account_type = db.Column(db.String(20), nullable=False)  # savings, checking, etc.
    account_name = db.Column(db.String(100), nullable=True)  # Optional name for the account
    description = db.Column(db.String(200), nullable=True)  # Optional description
    balance = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, nullable=False, default=True)  # For soft delete
    transactions_from = db.relationship('Transaction', 
                                      foreign_keys='Transaction.from_account_id',
                                      backref='from_account', 
                                      lazy=True)
    transactions_to = db.relationship('Transaction', 
                                    foreign_keys='Transaction.to_account_id',
                                    backref='to_account', 
                                    lazy=True)

    # Account type validation
    VALID_ACCOUNT_TYPES = {'savings', 'checking', 'investment', 'credit'}
    # Account number validation (10-20 digits)
    ACCOUNT_NUMBER_REGEX = re.compile(r'^\d{10,20}$')

    def __init__(self, account_number, account_type, user_id, account_name=None, description=None):
        if not self.ACCOUNT_NUMBER_REGEX.match(account_number):
            raise BadRequest('Account number must be 10-20 digits')
        
        if account_type not in self.VALID_ACCOUNT_TYPES:
            raise BadRequest(f'Invalid account type. Must be one of: {", ".join(self.VALID_ACCOUNT_TYPES)}')
        
        self.account_number = account_number
        self.account_type = account_type
        self.user_id = user_id
        self.account_name = account_name
        self.description = description
        self.balance = Decimal('0.00')
    
    def deposit(self, amount):
        if not self.is_active:
            raise BadRequest('Account is inactive')
        
        if amount <= 0:
            raise BadRequest('Deposit amount must be positive')
        
        self.balance += Decimal(str(amount))
        db.session.commit()
    
    def withdraw(self, amount):
        if not self.is_active:
            raise BadRequest('Account is inactive')
        
        if amount <= 0:
            raise BadRequest('Withdrawal amount must be positive')
        
        if self.balance < Decimal(str(amount)):
            raise BadRequest('Insufficient funds')
        
        self.balance -= Decimal(str(amount))
        db.session.commit()
    
    def transfer(self, to_account, amount):
        if not self.is_active or not to_account.is_active:
            raise BadRequest('One or both accounts are inactive')
        
        if amount <= 0:
            raise BadRequest('Transfer amount must be positive')
        
        if self.balance < Decimal(str(amount)):
            raise BadRequest('Insufficient funds')
        
        self.balance -= Decimal(str(amount))
        to_account.balance += Decimal(str(amount))
        db.session.commit()
    
    def to_dict(self):
        return {
            'id': self.id,
            'account_number': self.account_number,
            'account_type': self.account_type,
            'account_name': self.account_name,
            'description': self.description,
            'balance': float(self.balance),
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'is_active': self.is_active
        }
    
    def activate(self):
        self.is_active = True
        db.session.commit()
    
    def deactivate(self):
        self.is_active = False
        db.session.commit()
    
    def update_details(self, account_name=None, description=None):
        if account_name is not None:
            self.account_name = account_name
        if description is not None:
            self.description = description
        db.session.commit() 