from app import db
from datetime import datetime, timedelta
from enum import Enum
import re
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import event

class TransactionType(Enum):
    DEPOSIT = 'deposit'
    WITHDRAWAL = 'withdrawal'
    TRANSFER = 'transfer'
    INTEREST = 'interest'
    FEE = 'fee'
    REFUND = 'refund'

class TransactionStatus(Enum):
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    REVERSED = 'reversed'

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Numeric(15, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default='USD')
    from_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    to_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(20), nullable=False, default=TransactionStatus.PENDING.value)
    reference_number = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    failure_reason = db.Column(db.String(200), nullable=True)
    metadata = db.Column(db.JSON, nullable=True)
    reversal_id = db.Column(db.Integer, db.ForeignKey('transaction.id'), nullable=True)
    reversed_by = db.relationship('Transaction', remote_side=[id], backref='reversal')

    def __init__(self, **kwargs):
        super(Transaction, self).__init__(**kwargs)
        # Generate reference number using the utility function
        from app.utils.account_utils import generate_reference_number
        self.reference_number = generate_reference_number(self.transaction_type)
        
        # Ensure amount is a Decimal
        if 'amount' in kwargs:
            self.amount = Decimal(str(kwargs['amount'])).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)

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
                
        # Validate status
        if self.status not in [s.value for s in TransactionStatus]:
            errors.append(f"Invalid transaction status: {self.status}")
            
        # Validate reference number
        if not self.reference_number:
            errors.append("Reference number is required")
            
        # Validate description length
        if self.description and len(self.description) > 200:
            errors.append("Description must be less than 200 characters")
            
        # Validate failure reason length
        if self.failure_reason and len(self.failure_reason) > 200:
            errors.append("Failure reason must be less than 200 characters")
            
        return errors

    def can_reverse(self):
        """Check if transaction can be reversed"""
        if self.status != TransactionStatus.COMPLETED.value:
            return False
        if self.transaction_type not in [TransactionType.TRANSFER.value, 
                                       TransactionType.DEPOSIT.value, 
                                       TransactionType.WITHDRAWAL.value]:
            return False
        if self.reversal_id is not None:
            return False
        # Check if transaction is too old to reverse (e.g., more than 30 days)
        if self.timestamp < datetime.utcnow() - timedelta(days=30):
            return False
        return True

    def reverse(self, reason=None):
        """Create a reversal transaction"""
        if not self.can_reverse():
            return None
            
        reversal = Transaction(
            transaction_type=self.transaction_type,
            amount=self.amount,
            currency=self.currency,
            from_account_id=self.to_account_id if self.transaction_type == TransactionType.TRANSFER.value else None,
            to_account_id=self.from_account_id,
            description=f"Reversal of {self.reference_number}",
            status=TransactionStatus.PENDING.value,
            metadata={'original_transaction_id': self.id, 'reason': reason}
        )
        
        self.reversal_id = reversal.id
        self.status = TransactionStatus.REVERSED.value
        db.session.add(reversal)
        db.session.commit()
        
        return reversal

    def to_dict(self):
        return {
            'id': self.id,
            'transaction_type': self.transaction_type,
            'amount': float(self.amount),
            'currency': self.currency,
            'from_account_id': self.from_account_id,
            'to_account_id': self.to_account_id,
            'timestamp': self.timestamp.isoformat(),
            'status': self.status,
            'reference_number': self.reference_number,
            'description': self.description,
            'failure_reason': self.failure_reason,
            'metadata': self.metadata,
            'reversal_id': self.reversal_id
        }

# Event listener to ensure currency is uppercase
@event.listens_for(Transaction, 'before_insert')
@event.listens_for(Transaction, 'before_update')
def uppercase_currency(mapper, connection, target):
    target.currency = target.currency.upper() 