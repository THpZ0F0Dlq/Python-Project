from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.account import Account, AccountType, AccountStatus
from app.models.user import User
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.utils.validators import error_response
from app.utils.account_utils import generate_account_number
from datetime import datetime
from sqlalchemy import or_, text, and_
import hashlib
import uuid

bp = Blueprint('accounts', __name__, url_prefix='/api/accounts')

MAX_ACCOUNTS = 5  # Increased from 2 to 5

@bp.route('', methods=['GET'])
@jwt_required()
def get_accounts():
    user_id = int(get_jwt_identity())
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    account_type = request.args.get('type')
    status = request.args.get('status')
    
    query = Account.query.filter(Account.user_id == user_id)
    
    if account_type:
        if account_type not in [t.value for t in AccountType]:
            return error_response('Invalid account type', 400)
        query = query.filter(Account.account_type == account_type)
    
    if status:
        if status not in [s.value for s in AccountStatus]:
            return error_response('Invalid account status', 400)
        query = query.filter(Account.status == status)
    else:
        query = query.filter(Account.is_active == True)
    
    paginated_accounts = query.paginate(page=page, per_page=per_page, error_out=False)
    
    accounts_data = []
    for account in paginated_accounts.items:
        account_dict = account.to_dict()
        accounts_data.append(account_dict)
    
    return jsonify({
        'accounts': accounts_data,
        'page': page,
        'per_page': per_page,
        'total': paginated_accounts.total
    })

@bp.route('/<int:account_id>', methods=['GET'])
@jwt_required()
def get_account(account_id):
    user_id = int(get_jwt_identity())
    
    account = Account.query.filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    
    if not account:
        return error_response('Account not found', 404)
    
    return jsonify(account.to_dict())

@bp.route('', methods=['POST'])
@jwt_required()
def create_account():
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    # Validate user exists
    user = User.query.get(user_id)
    if not user:
        return error_response('User not found', 404)
    
    # Check account limit
    account_count = Account.query.filter_by(user_id=user_id, is_active=True).count()
    if account_count >= MAX_ACCOUNTS:
        return error_response(f'Maximum of {MAX_ACCOUNTS} accounts allowed per user', 400)
    
    # Validate account type
    account_type = data.get('account_type')
    if account_type not in [t.value for t in AccountType]:
        return error_response('Invalid account type', 400)
    
    # Validate account name
    account_name = data.get('account_name')
    if account_name and (len(account_name) < 3 or len(account_name) > 100):
        return error_response('Account name must be between 3 and 100 characters', 400)
    
    # Validate initial balance
    initial_balance = data.get('initial_balance', 0.0)
    try:
        initial_balance = float(initial_balance)
        if initial_balance < 0:
            return error_response('Initial balance cannot be negative', 400)
    except (ValueError, TypeError):
        return error_response('Initial balance must be a valid number', 400)
    
    # Create new account
    new_account = Account(
        account_type=account_type,
        account_name=account_name,
        description=data.get('description'),
        balance=initial_balance,
        currency=data.get('currency', 'USD'),
        minimum_balance=data.get('minimum_balance', 0.0),
        user_id=user_id
    )
    
    # Validate account data
    errors = new_account.validate()
    if errors:
        return error_response(errors[0], 400)
    
    db.session.add(new_account)
    db.session.commit()
    
    return jsonify({
        'message': 'Account created successfully',
        'account': new_account.to_dict()
    }), 201

@bp.route('/<int:account_id>', methods=['PUT'])
@jwt_required()
def update_account(account_id):
    user_id = int(get_jwt_identity())
    data = request.get_json()
    
    account = Account.query.filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    
    if not account:
        return error_response('Account not found', 404)
    
    # Update allowed fields
    if 'account_name' in data:
        if len(data['account_name']) < 3 or len(data['account_name']) > 100:
            return error_response('Account name must be between 3 and 100 characters', 400)
        account.account_name = data['account_name']
    
    if 'description' in data:
        account.description = data['description']
    
    if 'minimum_balance' in data:
        try:
            minimum_balance = float(data['minimum_balance'])
            if minimum_balance < 0:
                return error_response('Minimum balance cannot be negative', 400)
            account.minimum_balance = minimum_balance
        except (ValueError, TypeError):
            return error_response('Minimum balance must be a valid number', 400)
    
    # Validate account data
    errors = account.validate()
    if errors:
        return error_response(errors[0], 400)
    
    db.session.commit()
    
    return jsonify({
        'message': 'Account updated successfully',
        'account': account.to_dict()
    })

@bp.route('/<int:account_id>', methods=['DELETE'])
@jwt_required()
def delete_account(account_id):
    user_id = int(get_jwt_identity())
    
    account = Account.query.filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    
    if not account:
        return error_response('Account not found', 404)
    
    # Check if account has any pending transactions
    pending_transactions = Transaction.query.filter(
        or_(
            Transaction.from_account_id == account_id,
            Transaction.to_account_id == account_id
        ),
        Transaction.status == TransactionStatus.PENDING.value
    ).first()
    
    if pending_transactions:
        return error_response('Cannot delete account with pending transactions', 400)
    
    # Soft delete the account
    account.is_active = False
    account.status = AccountStatus.CLOSED.value
    db.session.commit()
    
    return jsonify({
        'message': 'Account deleted successfully'
    })

@bp.route('/<int:account_id>/transactions', methods=['GET'])
@jwt_required()
def get_account_transactions(account_id):
    user_id = int(get_jwt_identity())
    
    account = Account.query.filter(
        Account.id == account_id,
        Account.user_id == user_id
    ).first()
    
    if not account:
        return error_response('Account not found', 404)
    
    query = Transaction.query.filter(
        or_(
            Transaction.from_account_id == account_id,
            Transaction.to_account_id == account_id
        )
    )
    
    # Filter by date range
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
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
    
    # Filter by transaction type
    tx_type = request.args.get('type')
    if tx_type:
        if tx_type not in [t.value for t in TransactionType]:
            return error_response('Invalid transaction type', 400)
        query = query.filter(Transaction.transaction_type == tx_type)
    
    # Filter by status
    status = request.args.get('status')
    if status:
        if status not in [s.value for s in TransactionStatus]:
            return error_response('Invalid transaction status', 400)
        query = query.filter(Transaction.status == status)
    
    # Search in description
    search = request.args.get('search')
    if search:
        search_term = f'%{search}%'
        query = query.filter(Transaction.description.ilike(search_term))
    
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    if page < 1 or per_page < 1 or per_page > 100:
        return error_response('Invalid pagination parameters', 400)
    
    paginated_transactions = query.order_by(Transaction.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    transactions = []
    for tx in paginated_transactions.items:
        tx_dict = tx.to_dict()
        transactions.append(tx_dict)
    
    return jsonify({
        'transactions': transactions,
        'page': page,
        'per_page': per_page,
        'total': paginated_transactions.total
    })