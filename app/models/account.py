from app import db
from datetime import datetime
from enum import Enum
import re
import uuid
from sqlalchemy import event
from decimal import Decimal, ROUND_HALF_UP

class AccountType(Enum):
    SAVINGS = 'savings'
    CHECKING = 'checking'
    BUSINESS = 'business'
    FIXED_DEPOSIT = 'fixed_deposit'

class AccountStatus(Enum):
    ACTIVE = 'active'
    FROZEN = 'frozen'
    CLOSED = 'closed'
    DORMANT = 'dormant'

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_number = db.Column(db.String(20), unique=True, nullable=False)
    account_type = db.Column(db.String(20), nullable=False)
    account_name = db.Column(db.String(100), nullable=True)
    description = db.Column(db.String(200), nullable=True)
    balance = db.Column(db.Numeric(15, 2), nullable=False, default=0.0)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    minimum_balance = db.Column(db.Numeric(15, 2), nullable=False, default=0.0)
    interest_rate = db.Column(db.Numeric(5, 4), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default=AccountStatus.ACTIVE.value)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    daily_withdrawal_limit = db.Column(db.Numeric(15, 2), nullable=True)
    monthly_withdrawal_limit = db.Column(db.Numeric(15, 2), nullable=True)
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
        # Generate account number using the utility function
        from app.utils.account_utils import generate_account_number
        self.account_number = generate_account_number(self.account_type)
        
        # Set default interest rate for savings accounts
        if self.account_type == AccountType.SAVINGS.value and self.interest_rate is None:
            self.interest_rate = Decimal('0.02')
            
        # Set default withdrawal limits based on account type
        if self.daily_withdrawal_limit is None:
            if self.account_type == AccountType.SAVINGS.value:
                self.daily_withdrawal_limit = Decimal('1000.00')
            elif self.account_type == AccountType.CHECKING.value:
                self.daily_withdrawal_limit = Decimal('5000.00')
            elif self.account_type == AccountType.BUSINESS.value:
                self.daily_withdrawal_limit = Decimal('10000.00')
                
        if self.monthly_withdrawal_limit is None:
            if self.account_type == AccountType.SAVINGS.value:
                self.monthly_withdrawal_limit = Decimal('10000.00')
            elif self.account_type == AccountType.CHECKING.value:
                self.monthly_withdrawal_limit = Decimal('50000.00')
            elif self.account_type == AccountType.BUSINESS.value:
                self.monthly_withdrawal_limit = Decimal('100000.00')

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
            if self.interest_rate < 0 or self.interest_rate > 1:
                errors.append("Interest rate must be between 0 and 1")
            elif self.account_type != AccountType.SAVINGS.value and self.account_type != AccountType.FIXED_DEPOSIT.value:
                errors.append("Interest rate can only be set for savings or fixed deposit accounts")
                
        # Validate account name
        if self.account_name and len(self.account_name) > 100:
            errors.append("Account name must be less than 100 characters")
            
        # Validate description
        if self.description and len(self.description) > 200:
            errors.append("Description must be less than 200 characters")
            
        # Validate withdrawal limits
        if self.daily_withdrawal_limit is not None and self.daily_withdrawal_limit < 0:
            errors.append("Daily withdrawal limit cannot be negative")
        if self.monthly_withdrawal_limit is not None and self.monthly_withdrawal_limit < 0:
            errors.append("Monthly withdrawal limit cannot be negative")
            
        return errors

    def can_withdraw(self, amount):
        """Check if withdrawal is possible"""
        if self.status != AccountStatus.ACTIVE.value:
            return False
        if not self.is_active:
            return False
            
        amount = Decimal(str(amount))
        if amount <= 0:
            return False
            
        # Check minimum balance
        if self.balance - amount < self.minimum_balance:
            return False
            
        # Check daily withdrawal limit
        if self.daily_withdrawal_limit is not None:
            today = datetime.utcnow().date()
            daily_withdrawals = sum(
                t.amount for t in self.transactions_from
                if t.transaction_type == 'withdrawal'
                and t.timestamp.date() == today
                and t.status == 'completed'
            )
            if daily_withdrawals + amount > self.daily_withdrawal_limit:
                return False
                
        # Check monthly withdrawal limit
        if self.monthly_withdrawal_limit is not None:
            current_month = datetime.utcnow().replace(day=1)
            monthly_withdrawals = sum(
                t.amount for t in self.transactions_from
                if t.transaction_type == 'withdrawal'
                and t.timestamp >= current_month
                and t.status == 'completed'
            )
            if monthly_withdrawals + amount > self.monthly_withdrawal_limit:
                return False
                
        return True

    def update_balance(self, amount, transaction_type):
        """Update account balance with proper decimal handling"""
        amount = Decimal(str(amount))
        if transaction_type == 'deposit':
            self.balance = (self.balance + amount).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        elif transaction_type == 'withdrawal':
            self.balance = (self.balance - amount).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        self.last_activity = datetime.utcnow()
        db.session.commit()

    def to_dict(self):
        return {
            'id': self.id,
            'account_number': self.account_number,
            'account_type': self.account_type,
            'account_name': self.account_name,
            'description': self.description,
            'balance': float(self.balance),
            'currency': self.currency,
            'minimum_balance': float(self.minimum_balance),
            'interest_rate': float(self.interest_rate) if self.interest_rate is not None else None,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat(),
            'last_activity': self.last_activity.isoformat(),
            'status': self.status,
            'is_active': self.is_active,
            'daily_withdrawal_limit': float(self.daily_withdrawal_limit) if self.daily_withdrawal_limit is not None else None,
            'monthly_withdrawal_limit': float(self.monthly_withdrawal_limit) if self.monthly_withdrawal_limit is not None else None
        }

# Event listener to ensure currency is uppercase
@event.listens_for(Account, 'before_insert')
@event.listens_for(Account, 'before_update')
def uppercase_currency(mapper, connection, target):
    target.currency = target.currency.upper() 