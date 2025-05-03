from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.account import Account, AccountStatus
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.utils.validators import validate_amount, error_response
from datetime import datetime, timedelta
from sqlalchemy import or_, and_, func
import uuid

bp = Blueprint('transactions', __name__, url_prefix='/api/transactions')

@bp.route('', methods=['GET'])
@jwt_required()
def get_transactions():
    """Get transaction history for user accounts with filtering and pagination"""
    user_id = int(get_jwt_identity())
    
    # Get query parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    tx_type = request.args.get('type')
    status = request.args.get('status')
    search = request.args.get('search')
    account_id = request.args.get('account_id')
    min_amount = request.args.get('min_amount')
    max_amount = request.args.get('max_amount')
    
    # Get all user's accounts
    accounts = Account.query.filter_by(user_id=user_id).all()
    if not accounts:
        return jsonify({'transactions': [], 'page': page, 'per_page': per_page, 'total': 0})
    
    account_ids = [account.id for account in accounts]
    
    # Build query
    query = Transaction.query.filter(
        or_(
            Transaction.from_account_id.in_(account_ids),
            Transaction.to_account_id.in_(account_ids)
        )
    )
    
    # Filter by specific account if provided
    if account_id:
        try:
            account_id = int(account_id)
            if account_id not in account_ids:
                return error_response('Account not found or access denied', 404)
            query = query.filter(
                or_(
                    Transaction.from_account_id == account_id,
                    Transaction.to_account_id == account_id
                )
            )
        except ValueError:
            return error_response('Invalid account ID', 400)
    
    # Filter by date range
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Transaction.timestamp >= start_date)
        except ValueError:
            return error_response('Invalid start_date format. Use YYYY-MM-DD', 400)
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
            query = query.filter(Transaction.timestamp <= end_date)
        except ValueError:
            return error_response('Invalid end_date format. Use YYYY-MM-DD', 400)
    
    # Filter by amount range
    if min_amount:
        try:
            min_amount = float(min_amount)
            if min_amount < 0:
                return error_response('Minimum amount cannot be negative', 400)
            query = query.filter(Transaction.amount >= min_amount)
        except ValueError:
            return error_response('Invalid minimum amount', 400)
    
    if max_amount:
        try:
            max_amount = float(max_amount)
            if max_amount < 0:
                return error_response('Maximum amount cannot be negative', 400)
            query = query.filter(Transaction.amount <= max_amount)
        except ValueError:
            return error_response('Invalid maximum amount', 400)
    
    # Filter by transaction type
    if tx_type:
        if tx_type not in [t.value for t in TransactionType]:
            return error_response('Invalid transaction type', 400)
        query = query.filter(Transaction.transaction_type == tx_type)
    
    # Filter by status
    if status:
        if status not in [s.value for s in TransactionStatus]:
            return error_response('Invalid transaction status', 400)
        query = query.filter(Transaction.status == status)
    
    # Search in description
    if search:
        search_term = f'%{search}%'
        query = query.filter(Transaction.description.ilike(search_term))
    
    # Pagination
    if page < 1 or per_page < 1 or per_page > 100:
        return error_response('Invalid pagination parameters', 400)
    
    paginated_transactions = query.order_by(Transaction.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Calculate summary statistics
    total_transactions = query.count()
    total_amount = db.session.query(func.sum(Transaction.amount)).scalar() or 0
    avg_amount = total_amount / total_transactions if total_transactions > 0 else 0
    
    transactions = []
    for tx in paginated_transactions.items:
        tx_dict = tx.to_dict()
        # Add account details for from and to accounts
        if tx.from_account_id:
            from_account = Account.query.get(tx.from_account_id)
            if from_account:
                tx_dict['from_account'] = {
                    'id': from_account.id,
                    'account_number': from_account.account_number,
                    'account_name': from_account.account_name,
                    'currency': from_account.currency
                }
        if tx.to_account_id:
            to_account = Account.query.get(tx.to_account_id)
            if to_account:
                tx_dict['to_account'] = {
                    'id': to_account.id,
                    'account_number': to_account.account_number,
                    'account_name': to_account.account_name,
                    'currency': to_account.currency
                }
        transactions.append(tx_dict)
    
    return jsonify({
        'transactions': transactions,
        'page': page,
        'per_page': per_page,
        'total': paginated_transactions.total,
        'summary': {
            'total_transactions': total_transactions,
            'total_amount': total_amount,
            'average_amount': avg_amount
        }
    })

@bp.route('/deposit', methods=['POST'])
@jwt_required(fresh=True)
def deposit():
    """Deposit funds to an account"""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    # Validate required fields
    if not all(k in data for k in ('account_id', 'amount')):
        return error_response('Account ID and amount are required')
    
    # Validate amount
    if not validate_amount(data['amount']):
        return error_response('Amount must be a positive number')
    
    amount = float(data['amount'])
    
    # Get the account
    account = Account.query.filter_by(id=data['account_id'], user_id=user_id).first()
    
    if not account:
        return error_response('Account not found or does not belong to you', 404)
    
    if account.status != AccountStatus.ACTIVE.value:
        return error_response('Account is not active', 400)
    
    try:
        # Update account balance
        account.balance += amount
        
        # Generate reference number
        timestamp = int(datetime.now().timestamp() * 1000)
        unique_suffix = str(uuid.uuid4().int)[-8:]
        reference_number = f"DEP{timestamp}{unique_suffix}"
        
        # Create transaction record
        transaction = Transaction(
            transaction_type=TransactionType.DEPOSIT.value,
            amount=amount,
            to_account_id=account.id,
            description=data.get('description', 'Deposit'),
            status=TransactionStatus.COMPLETED.value,
            reference_number=reference_number,
            currency=account.currency
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({
            'message': 'Deposit successful',
            'transaction': transaction.to_dict(),
            'new_balance': account.balance,
            'id': transaction.id
        })
    except Exception as e:
        db.session.rollback()
        return error_response(f'Deposit failed: {str(e)}', 500)

@bp.route('/withdraw', methods=['POST'])
@jwt_required(fresh=True)
def withdraw():
    """Withdraw funds from an account"""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    # Validate required fields
    if not all(k in data for k in ('account_id', 'amount')):
        return error_response('Account ID and amount are required')
    
    # Validate amount
    if not validate_amount(data['amount']):
        return error_response('Amount must be a positive number')
    
    amount = float(data['amount'])
    
    # Get the account
    account = Account.query.filter_by(id=data['account_id'], user_id=user_id).first()
    
    if not account:
        return error_response('Account not found or does not belong to you', 404)
    
    if account.status != AccountStatus.ACTIVE.value:
        return error_response('Account is not active', 400)
    
    # Check sufficient balance
    if not account.can_withdraw(amount):
        return error_response('Insufficient funds or below minimum balance')
    
    try:
        # Update account balance
        account.balance -= amount
        
        # Generate reference number
        timestamp = int(datetime.now().timestamp() * 1000)
        unique_suffix = str(uuid.uuid4().int)[-8:]
        reference_number = f"WDR{timestamp}{unique_suffix}"
        
        # Create transaction record
        transaction = Transaction(
            transaction_type=TransactionType.WITHDRAWAL.value,
            amount=amount,
            from_account_id=account.id,
            description=data.get('description', 'Withdrawal'),
            status=TransactionStatus.COMPLETED.value,
            reference_number=reference_number,
            currency=account.currency
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({
            'message': 'Withdrawal successful',
            'transaction': transaction.to_dict(),
            'new_balance': account.balance,
            'id': transaction.id
        })
    except Exception as e:
        db.session.rollback()
        return error_response(f'Withdrawal failed: {str(e)}', 500)

@bp.route('/transfer', methods=['POST'])
@jwt_required(fresh=True)
def transfer():
    """Transfer funds between accounts"""
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    # Validate required fields
    if not all(k in data for k in ('from_account_id', 'to_account_id', 'amount')):
        return error_response('From account ID, to account ID, and amount are required')
    
    # Validate amount
    if not validate_amount(data['amount']):
        return error_response('Amount must be a positive number')
    
    amount = float(data['amount'])
    
    # Check if accounts are different
    if data['from_account_id'] == data['to_account_id']:
        return error_response('Cannot transfer to the same account')
    
    # Get the from account and verify ownership
    from_account = Account.query.filter_by(id=data['from_account_id'], user_id=user_id).first()
    
    if not from_account:
        return error_response('Source account not found or does not belong to you', 404)
    
    if from_account.status != AccountStatus.ACTIVE.value:
        return error_response('Source account is not active', 400)
    
    # Check sufficient balance
    if not from_account.can_withdraw(amount):
        return error_response('Insufficient funds or below minimum balance')
    
    # Get the to account
    to_account = Account.query.get(data['to_account_id'])
    
    if not to_account:
        return error_response('Destination account not found', 404)
    
    if to_account.status != AccountStatus.ACTIVE.value:
        return error_response('Destination account is not active', 400)
    
    # Check currency compatibility
    if from_account.currency != to_account.currency:
        return error_response('Cannot transfer between accounts with different currencies', 400)
    
    try:
        # Update account balances
        from_account.balance -= amount
        to_account.balance += amount
        
        # Generate reference number
        timestamp = int(datetime.now().timestamp() * 1000)
        unique_suffix = str(uuid.uuid4().int)[-8:]
        reference_number = f"TRF{timestamp}{unique_suffix}"
        
        # Create transaction record
        transaction = Transaction(
            transaction_type=TransactionType.TRANSFER.value,
            amount=amount,
            from_account_id=from_account.id,
            to_account_id=to_account.id,
            description=data.get('description', f'Transfer from {from_account.account_number} to {to_account.account_number}'),
            status=TransactionStatus.COMPLETED.value,
            reference_number=reference_number,
            currency=from_account.currency
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        return jsonify({
            'message': 'Transfer successful',
            'transaction': transaction.to_dict(),
            'from_account_balance': from_account.balance,
            'to_account_balance': to_account.balance,
            'id': transaction.id
        })
    except Exception as e:
        db.session.rollback()
        return error_response(f'Transfer failed: {str(e)}', 500)

@bp.route('/<int:transaction_id>', methods=['GET'])
@jwt_required()
def get_transaction(transaction_id):
    """Get details of a specific transaction"""
    user_id = int(get_jwt_identity())
    
    # Get user's accounts
    accounts = Account.query.filter_by(user_id=user_id).all()
    account_ids = [account.id for account in accounts]
    
    # Get transaction
    transaction = Transaction.query.filter(
        Transaction.id == transaction_id,
        or_(
            Transaction.from_account_id.in_(account_ids),
            Transaction.to_account_id.in_(account_ids)
        )
    ).first()
    
    if not transaction:
        return error_response('Transaction not found or access denied', 404)
    
    tx_dict = transaction.to_dict()
    
    # Add account details
    if transaction.from_account_id:
        from_account = Account.query.get(transaction.from_account_id)
        if from_account:
            tx_dict['from_account'] = {
                'id': from_account.id,
                'account_number': from_account.account_number,
                'account_name': from_account.account_name,
                'currency': from_account.currency
            }
    if transaction.to_account_id:
        to_account = Account.query.get(transaction.to_account_id)
        if to_account:
            tx_dict['to_account'] = {
                'id': to_account.id,
                'account_number': to_account.account_number,
                'account_name': to_account.account_name,
                'currency': to_account.currency
            }
    
    return jsonify(tx_dict)

@bp.route('/<int:transaction_id>/cancel', methods=['POST'])
@jwt_required(fresh=True)
def cancel_transaction(transaction_id):
    """Cancel a pending transaction"""
    user_id = int(get_jwt_identity())
    
    # Get user's accounts
    accounts = Account.query.filter_by(user_id=user_id).all()
    account_ids = [account.id for account in accounts]
    
    # Get transaction
    transaction = Transaction.query.filter(
        Transaction.id == transaction_id,
        or_(
            Transaction.from_account_id.in_(account_ids),
            Transaction.to_account_id.in_(account_ids)
        )
    ).first()
    
    if not transaction:
        return error_response('Transaction not found or access denied', 404)
    
    if transaction.status != TransactionStatus.PENDING.value:
        return error_response('Only pending transactions can be cancelled', 400)
    
    # Check if transaction is too old to cancel (e.g., more than 24 hours)
    if transaction.timestamp < datetime.now() - timedelta(hours=24):
        return error_response('Cannot cancel transactions older than 24 hours', 400)
    
    try:
        # Update transaction status
        transaction.status = TransactionStatus.CANCELLED.value
        db.session.commit()
        
        return jsonify({
            'message': 'Transaction cancelled successfully',
            'transaction': transaction.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return error_response(f'Failed to cancel transaction: {str(e)}', 500)

@bp.route('/accounts/<int:account_id>/transactions', methods=['GET'])
@jwt_required()
def account_transactions(account_id):
    """Get transactions for a specific account"""
    user_id = int(get_jwt_identity())
    
    # Verify account ownership
    account = Account.query.filter_by(id=account_id, user_id=user_id).first()
    if not account:
        return error_response('Account not found or does not belong to you', 404)
    
    # Get query parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    tx_type = request.args.get('type')
    status = request.args.get('status')
    search = request.args.get('search')
    min_amount = request.args.get('min_amount')
    max_amount = request.args.get('max_amount')
    
    # Build query
    query = Transaction.query.filter(
        or_(
            Transaction.from_account_id == account_id,
            Transaction.to_account_id == account_id
        )
    )
    
    # Filter by date range
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d')
            query = query.filter(Transaction.timestamp >= start_date)
        except ValueError:
            return error_response('Invalid start_date format. Use YYYY-MM-DD', 400)
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
            query = query.filter(Transaction.timestamp <= end_date)
        except ValueError:
            return error_response('Invalid end_date format. Use YYYY-MM-DD', 400)
    
    # Filter by amount range
    if min_amount:
        try:
            min_amount = float(min_amount)
            if min_amount < 0:
                return error_response('Minimum amount cannot be negative', 400)
            query = query.filter(Transaction.amount >= min_amount)
        except ValueError:
            return error_response('Invalid minimum amount', 400)
    
    if max_amount:
        try:
            max_amount = float(max_amount)
            if max_amount < 0:
                return error_response('Maximum amount cannot be negative', 400)
            query = query.filter(Transaction.amount <= max_amount)
        except ValueError:
            return error_response('Invalid maximum amount', 400)
    
    # Filter by transaction type
    if tx_type:
        if tx_type not in [t.value for t in TransactionType]:
            return error_response('Invalid transaction type', 400)
        query = query.filter(Transaction.transaction_type == tx_type)
    
    # Filter by status
    if status:
        if status not in [s.value for s in TransactionStatus]:
            return error_response('Invalid transaction status', 400)
        query = query.filter(Transaction.status == status)
    
    # Search in description
    if search:
        search_term = f'%{search}%'
        query = query.filter(Transaction.description.ilike(search_term))
    
    # Pagination
    if page < 1 or per_page < 1 or per_page > 100:
        return error_response('Invalid pagination parameters', 400)
    
    paginated_transactions = query.order_by(Transaction.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Calculate summary statistics
    total_transactions = query.count()
    total_amount = db.session.query(func.sum(Transaction.amount)).scalar() or 0
    avg_amount = total_amount / total_transactions if total_transactions > 0 else 0
    
    transactions = []
    for tx in paginated_transactions.items:
        tx_dict = tx.to_dict()
        # Add account details for from and to accounts
        if tx.from_account_id:
            from_account = Account.query.get(tx.from_account_id)
            if from_account:
                tx_dict['from_account'] = {
                    'id': from_account.id,
                    'account_number': from_account.account_number,
                    'account_name': from_account.account_name,
                    'currency': from_account.currency
                }
        if tx.to_account_id:
            to_account = Account.query.get(tx.to_account_id)
            if to_account:
                tx_dict['to_account'] = {
                    'id': to_account.id,
                    'account_number': to_account.account_number,
                    'account_name': to_account.account_name,
                    'currency': to_account.currency
                }
        transactions.append(tx_dict)
    
    return jsonify({
        'transactions': transactions,
        'page': page,
        'per_page': per_page,
        'total': paginated_transactions.total,
        'summary': {
            'total_transactions': total_transactions,
            'total_amount': total_amount,
            'average_amount': avg_amount
        }
    }) 