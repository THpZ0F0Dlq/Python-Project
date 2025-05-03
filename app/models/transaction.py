from app import db
from datetime import datetime
from enum import Enum
import re

class TransactionType(Enum):
    DEPOSIT = 'deposit'
    WITHDRAWAL = 'withdrawal'
    TRANSFER = 'transfer'

class TransactionStatus(Enum):
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_type = db.Column(db.String(20), nullable=False)  # deposit, withdrawal, transfer
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    from_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    to_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default=TransactionStatus.PENDING.value)
    reference_number = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    failure_reason = db.Column(db.String(200), nullable=True)

    def __init__(self, **kwargs):
        super(Transaction, self).__init__(**kwargs)
        # Generate reference number without relying on id
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S%f')
        self.reference_number = f"TRX{timestamp}"

    def validate(self):
        """Validate transaction data"""
        errors = []
        
        # Validate transaction type
        if self.transaction_type not in [t.value for t in TransactionType]:
            errors.append(f"Invalid transaction type: {self.transaction_type}")
            
        # Validate amount
        if self.amount <= 0:
            errors.append("Amount must be positive")
            
        # Validate currency
        if not re.match(r'^[A-Z]{3}$', self.currency):
            errors.append("Invalid currency code")
            
        # Validate account references
        if self.transaction_type == TransactionType.TRANSFER.value:
            if not self.from_account_id or not self.to_account_id:
                errors.append("Both from_account_id and to_account_id are required for transfers")
            elif self.from_account_id == self.to_account_id:
                errors.append("Cannot transfer to the same account")
                
        elif self.transaction_type == TransactionType.DEPOSIT.value:
            if not self.to_account_id:
                errors.append("to_account_id is required for deposits")
                
        elif self.transaction_type == TransactionType.WITHDRAWAL.value:
            if not self.from_account_id:
                errors.append("from_account_id is required for withdrawals")
                
        return errors

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_type': self.transaction_type,
            'amount': self.amount,
            'currency': self.currency,
            'from_account_id': self.from_account_id,
            'to_account_id': self.to_account_id,
            'timestamp': self.timestamp.isoformat(),
            'status': self.status,
            'reference_number': self.reference_number,
            'description': self.description,
            'failure_reason': self.failure_reason
        } 