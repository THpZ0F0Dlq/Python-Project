from app import db
from datetime import datetime
from enum import Enum
import re
import uuid

class AccountType(Enum):
    SAVINGS = 'savings'
    CHECKING = 'checking'
    BUSINESS = 'business'

class AccountStatus(Enum):
    ACTIVE = 'active'
    FROZEN = 'frozen'
    CLOSED = 'closed'

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), unique=True, nullable=False)
    account_type = db.Column(db.String(20), nullable=False)  # savings, checking, etc.
    account_name = db.Column(db.String(100), nullable=True)  # Optional name for the account
    description = db.Column(db.String(200), nullable=True)  # Optional description
    balance = db.Column(db.Float, nullable=False, default=0.0)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    minimum_balance = db.Column(db.Float, nullable=False, default=0.0)
    interest_rate = db.Column(db.Float, nullable=True)  # For savings accounts
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default=AccountStatus.ACTIVE.value)
    is_active = db.Column(db.Boolean, nullable=False, default=True)  # For soft delete
    transactions_from = db.relationship('Transaction', 
                                      foreign_keys='Transaction.from_account_id',
                                      backref='from_account', 
                                      lazy=True)
    transactions_to = db.relationship('Transaction', 
                                    foreign_keys='Transaction.to_account_id',
                                    backref='to_account', 
                                    lazy=True)

    def __init__(self, **kwargs):
        super(Account, self).__init__(**kwargs)
        # Generate account number without relying on id
        timestamp = datetime.utcnow().strftime('%Y%m%d')
        unique_id = str(uuid.uuid4().int)[:8]
        self.account_number = f"ACC{timestamp}{unique_id}"
        
        # Set default interest rate for savings accounts
        if self.account_type == AccountType.SAVINGS.value and self.interest_rate is None:
            self.interest_rate = 0.02  # Default 2% interest for savings accounts

    def validate(self):
        """Validate account data"""
        errors = []
        
        # Validate account type
        if self.account_type not in [t.value for t in AccountType]:
            errors.append(f"Invalid account type: {self.account_type}")
            
        # Validate currency
        if not re.match(r'^[A-Z]{3}$', self.currency):
            errors.append("Invalid currency code")
            
        # Validate minimum balance
        if self.minimum_balance < 0:
            errors.append("Minimum balance cannot be negative")
            
        # Validate interest rate
        if self.interest_rate is not None:
            if self.interest_rate < 0 or self.interest_rate > 1:  # 0% to 100%
                errors.append("Interest rate must be between 0 and 1")
            elif self.account_type != AccountType.SAVINGS.value:
                errors.append("Interest rate can only be set for savings accounts")
                
        # Validate account name
        if self.account_name and len(self.account_name) > 100:
            errors.append("Account name must be less than 100 characters")
            
        # Validate description
        if self.description and len(self.description) > 200:
            errors.append("Description must be less than 200 characters")
            
        return errors

    def can_withdraw(self, amount):
        """Check if withdrawal is possible"""
        if self.status != AccountStatus.ACTIVE.value:
            return False
        if not self.is_active:
            return False
        return self.balance - amount >= self.minimum_balance

    def to_dict(self):
        return {
            'id': self.id,
            'account_number': self.account_number,
            'account_type': self.account_type,
            'account_name': self.account_name,
            'description': self.description,
            'balance': self.balance,
            'currency': self.currency,
            'minimum_balance': self.minimum_balance,
            'interest_rate': self.interest_rate,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'status': self.status,
            'is_active': self.is_active
        } 