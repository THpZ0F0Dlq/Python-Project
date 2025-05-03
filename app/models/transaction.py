from app import db
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import BadRequest
from decimal import Decimal

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    transaction_type = db.Column(db.String(20), nullable=False)  # deposit, withdrawal, transfer
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    from_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True, index=True)
    to_account_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=True, index=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    description = db.Column(db.String(200), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending')  # pending, completed, failed
    reference_number = db.Column(db.String(50), unique=True, nullable=True, index=True)

    # Transaction type validation
    VALID_TRANSACTION_TYPES = {'deposit', 'withdrawal', 'transfer'}
    VALID_STATUSES = {'pending', 'completed', 'failed'}

    def __init__(self, transaction_type, amount, from_account_id=None, to_account_id=None, description=None):
        if transaction_type not in self.VALID_TRANSACTION_TYPES:
            raise BadRequest(f'Invalid transaction type. Must be one of: {", ".join(self.VALID_TRANSACTION_TYPES)}')
        
        if amount <= 0:
            raise BadRequest('Transaction amount must be positive')
        
        if transaction_type == 'transfer' and (not from_account_id or not to_account_id):
            raise BadRequest('Transfer transactions require both from_account_id and to_account_id')
        
        if transaction_type == 'deposit' and not to_account_id:
            raise BadRequest('Deposit transactions require to_account_id')
        
        if transaction_type == 'withdrawal' and not from_account_id:
            raise BadRequest('Withdrawal transactions require from_account_id')
        
        self.transaction_type = transaction_type
        self.amount = Decimal(str(amount))
        self.from_account_id = from_account_id
        self.to_account_id = to_account_id
        self.description = description
        self.status = 'pending'
        self.reference_number = self._generate_reference_number()
    
    def _generate_reference_number(self):
        # Generate a unique reference number using timestamp and random component
        import random
        timestamp = int(datetime.utcnow().timestamp())
        random_component = random.randint(1000, 9999)
        return f"TXN{timestamp}{random_component}"
    
    def process(self):
        if self.status != 'pending':
            raise BadRequest('Transaction has already been processed')
        
        try:
            if self.transaction_type == 'deposit':
                from app.models.account import Account
                account = Account.query.get(self.to_account_id)
                if not account or not account.is_active:
                    raise BadRequest('Invalid or inactive account')
                account.deposit(self.amount)
            
            elif self.transaction_type == 'withdrawal':
                from app.models.account import Account
                account = Account.query.get(self.from_account_id)
                if not account or not account.is_active:
                    raise BadRequest('Invalid or inactive account')
                account.withdraw(self.amount)
            
            elif self.transaction_type == 'transfer':
                from app.models.account import Account
                from_account = Account.query.get(self.from_account_id)
                to_account = Account.query.get(self.to_account_id)
                
                if not from_account or not to_account:
                    raise BadRequest('Invalid account(s)')
                
                if not from_account.is_active or not to_account.is_active:
                    raise BadRequest('One or both accounts are inactive')
                
                from_account.transfer(to_account, self.amount)
            
            self.status = 'completed'
            db.session.commit()
            
        except BadRequest as e:
            self.status = 'failed'
            db.session.commit()
            raise e
    
    def to_dict(self):
        return {
            'id': self.id,
            'transaction_type': self.transaction_type,
            'amount': float(self.amount),
            'from_account_id': self.from_account_id,
            'to_account_id': self.to_account_id,
            'timestamp': self.timestamp.isoformat(),
            'description': self.description,
            'status': self.status,
            'reference_number': self.reference_number
        }
    
    def update_status(self, status):
        if status not in self.VALID_STATUSES:
            raise BadRequest(f'Invalid status. Must be one of: {", ".join(self.VALID_STATUSES)}')
        
        self.status = status
        db.session.commit()
    
    def update_description(self, description):
        self.description = description
        db.session.commit() 