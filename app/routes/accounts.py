from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.account import Account
from app.models.user import User
from app.models.transaction import Transaction
from app.utils.validators import error_response
from app.utils.account_utils import generate_account_number
from datetime import datetime
from sqlalchemy import or_, text, and_
from werkzeug.exceptions import BadRequest
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
import hashlib
import uuid
import time
import random
import string

bp = Blueprint('accounts', __name__, url_prefix='/api/accounts')

MAX_ACCOUNTS = 2
MAX_BALANCE = Decimal('1000000.00')  # Maximum account balance
MIN_BALANCE = Decimal('-50.00')  # Minimum account balance

@bp.route('', methods=['GET'])
@jwt_required()
def get_accounts():
    try:
        user_id = int(get_jwt_identity())
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        account_type = request.args.get('type')
        
        # Validate pagination parameters
        if page < 1 or per_page < 1 or per_page > 100:
            return error_response('Invalid pagination parameters. Page and per_page must be positive, and per_page cannot exceed 100', 400)
        
        query = Account.query.filter(Account.user_id == user_id, Account.is_active == True)
        
        if account_type:
            if account_type not in Account.VALID_ACCOUNT_TYPES:
                return error_response(f'Invalid account type. Must be one of: {", ".join(Account.VALID_ACCOUNT_TYPES)}', 400)
            query = query.filter(Account.account_type == account_type)
        
        paginated_accounts = query.paginate(page=page, per_page=per_page, error_out=False)
        
        accounts_data = []
        for account in paginated_accounts.items:
            account_dict = account.to_dict()
            account_dict['category'] = account_dict.pop('account_type')
            account_dict['label'] = account_dict.pop('account_name')
            account_dict['balance'] = round(float(account_dict['balance']), 2)
            accounts_data.append(account_dict)
        
        return jsonify({
            'account_listing': accounts_data,
            'page': page,
            'per_page': per_page,
            'total': paginated_accounts.total
        })

    except Exception as e:
        current_app.logger.error(f"Error retrieving accounts: {str(e)}")
        return error_response("Failed to retrieve accounts", 500)

@bp.route('/<int:account_id>', methods=['GET'])
@jwt_required()
def get_account(account_id):
    try:
        user_id = int(get_jwt_identity())
        
        account = Account.query.filter(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.is_active == True
        ).first()
        
        if not account:
            return error_response('Account not found or access denied', 404)
        
        account_data = account.to_dict()
        return jsonify({
            'account_detail': account_data,
            'balance': round(float(account.balance), 2)
        })

    except Exception as e:
        current_app.logger.error(f"Error retrieving account: {str(e)}")
        return error_response("Failed to retrieve account", 500)

@bp.route('', methods=['POST'])
@jwt_required()
def create_account():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return error_response('Request body is required', 400)
        
        account_type = data.get('account_type') or data.get('type')
        if not account_type:
            return error_response('Account type is required', 400)
        
        if account_type not in Account.VALID_ACCOUNT_TYPES:
            return error_response(f'Invalid account type. Must be one of: {", ".join(Account.VALID_ACCOUNT_TYPES)}', 400)
        
        user = User.query.get(user_id)
        if not user:
            return error_response('User not found', 404)
        
        account_count = Account.query.filter_by(user_id=user_id, is_active=True).count()
        if account_count >= MAX_ACCOUNTS:
            return error_response(f'Maximum of {MAX_ACCOUNTS} accounts allowed per user', 400)
        
        account_name = data.get('account_name') or data.get('name')
        if account_name and (len(account_name) < 3 or len(account_name) > 100):
            return error_response('Account name must be between 3 and 100 characters', 400)
        
        initial_balance = data.get('initial_balance') or data.get('balance', 0.0)
        try:
            initial_balance = Decimal(str(initial_balance))
            if initial_balance < MIN_BALANCE:
                return error_response(f'Initial balance cannot be less than {MIN_BALANCE}', 400)
            if initial_balance > MAX_BALANCE:
                return error_response(f'Initial balance cannot exceed {MAX_BALANCE}', 400)
        except (ValueError, TypeError):
            return error_response('Initial balance must be a valid number', 400)
        
        # Generate unique account number
        timestamp = int(time.time() * 1000)
        random_suffix = ''.join(random.choices(string.digits, k=4))
        unique_suffix = str(uuid.uuid4().int)[-8:]
        account_prefix = "ACC" + str(user_id)[-3:].zfill(3)
        account_number = f"{account_prefix}{timestamp % 10000}{random_suffix}{unique_suffix[:4]}"
        
        new_account = Account(
            account_number=account_number,
            account_type=account_type,
            account_name=account_name,
            description=data.get('description'),
            balance=initial_balance,
            user_id=user_id
        )
        
        db.session.add(new_account)
        db.session.commit()
        
        account_data = new_account.to_dict()
        return jsonify({
            'message': 'Account created successfully',
            'account': account_data
        }), 201

    except IntegrityError:
        db.session.rollback()
        return error_response('Database error occurred', 500)
    except BadRequest as e:
        return error_response(str(e), 400)
    except Exception as e:
        current_app.logger.error(f"Error creating account: {str(e)}")
        return error_response("Failed to create account", 500)

@bp.route('/<int:account_id>', methods=['PUT'])
@jwt_required(fresh=True)
def update_account(account_id):
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        if not data:
            return error_response('Request body is required', 400)
        
        account = Account.query.filter(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.is_active == True
        ).first()
        
        if not account:
            return error_response('Account not found or access denied', 404)
        
        if 'account_label' in data:
            account_name = data.get('account_label')
            if not account_name or len(account_name) < 3 or len(account_name) > 100:
                return error_response('Account name must be between 3 and 100 characters', 400)
            account.account_name = account_name
        
        if 'description' in data:
            description = data['description']
            if description and len(description) > 200:
                return error_response('Description must not exceed 200 characters', 400)
            account.description = description
        
        db.session.commit()
        
        return jsonify({
            'message': 'Account updated successfully',
            'account_detail': account.to_dict()
        })

    except IntegrityError:
        db.session.rollback()
        return error_response('Database error occurred', 500)
    except BadRequest as e:
        return error_response(str(e), 400)
    except Exception as e:
        current_app.logger.error(f"Error updating account: {str(e)}")
        return error_response("Failed to update account", 500)

@bp.route('/<int:account_id>', methods=['DELETE'])
@jwt_required(fresh=True)
def delete_account(account_id):
    try:
        user_id = int(get_jwt_identity())
        
        account = Account.query.filter(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.is_active == True
        ).first()
        
        if not account:
            return error_response('Account not found or access denied', 404)
        
        # Check if account has any pending transactions
        pending_transactions = Transaction.query.filter(
            or_(
                Transaction.from_account_id == account_id,
                Transaction.to_account_id == account_id
            ),
            Transaction.status == 'pending'
        ).first()
        
        if pending_transactions:
            return error_response('Cannot delete account with pending transactions', 400)
        
        account.deactivate()
        
        return jsonify({
            'message': 'Account deleted successfully'
        }), 200

    except Exception as e:
        current_app.logger.error(f"Error deleting account: {str(e)}")
        return error_response("Failed to delete account", 500)

@bp.route('/<int:account_id>/transactions', methods=['GET'])
@jwt_required()
def get_account_transactions(account_id):
    try:
        user_id = int(get_jwt_identity())
        
        account = Account.query.filter(
            Account.id == account_id,
            Account.user_id == user_id,
            Account.is_active == True
        ).first()
        
        if not account:
            return error_response('Account not found or access denied', 404)
        
        query = Transaction.query.filter(
            or_(
                Transaction.from_account_id == account_id,
                Transaction.to_account_id == account_id
            )
        )
        
        # Date range filtering
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
        
        # Transaction type filtering
        tx_type = request.args.get('type')
        if tx_type:
            if tx_type not in Transaction.VALID_TRANSACTION_TYPES:
                return error_response(f'Invalid transaction type. Must be one of: {", ".join(Transaction.VALID_TRANSACTION_TYPES)}', 400)
            
            if tx_type == 'deposit':
                query = query.filter(
                    Transaction.transaction_type == 'deposit',
                    Transaction.to_account_id == account_id
                )
            elif tx_type == 'withdrawal':
                query = query.filter(
                    Transaction.transaction_type == 'withdrawal',
                    Transaction.from_account_id == account_id
                )
            elif tx_type == 'transfer':
                query = query.filter(Transaction.transaction_type == 'transfer')
        
        # Search filtering
        search = request.args.get('search')
        if search:
            if len(search) < 2:
                return error_response('Search term must be at least 2 characters long', 400)
            search_term = f'%{search}%'
            query = query.filter(Transaction.description.ilike(search_term))
        
        # Pagination
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        if page < 1 or per_page < 1 or per_page > 100:
            return error_response('Invalid pagination parameters. Page and per_page must be positive, and per_page cannot exceed 100', 400)
        
        paginated_transactions = query.order_by(Transaction.timestamp.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        transactions = []
        for tx in paginated_transactions.items:
            tx_dict = tx.to_dict()
            tx_dict['amount'] = round(float(tx_dict['amount']), 2)
            transactions.append(tx_dict)
        
        return jsonify({
            'transactions': transactions,
            'page': page,
            'per_page': per_page,
            'total': paginated_transactions.total
        })

    except Exception as e:
        current_app.logger.error(f"Error retrieving transactions: {str(e)}")
        return error_response("Failed to retrieve transactions", 500)