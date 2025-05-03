from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from app import db
from app.models.account import Account
from app.models.transaction import Transaction
from app.utils.validators import validate_amount, error_response
from werkzeug.exceptions import BadRequest
from sqlalchemy.exc import IntegrityError
from decimal import Decimal
from datetime import datetime
from sqlalchemy import or_

bp = Blueprint('transactions', __name__, url_prefix='/api/transactions')

# Maximum transaction amount
MAX_TRANSACTION_AMOUNT = Decimal('100000.00')

@bp.route('', methods=['GET'])
@jwt_required()
def get_transactions():
    try:
        user_id = int(get_jwt_identity())
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        
        # Validate pagination parameters
        if page < 1 or per_page < 1 or per_page > 100:
            return error_response('Invalid pagination parameters. Page and per_page must be positive, and per_page cannot exceed 100', 400)
        
        # Get all user's accounts
        accounts = Account.query.filter_by(user_id=user_id, is_active=True).all()
        
        if not accounts:
            return jsonify({
                'transactions': [],
                'page': page,
                'per_page': per_page,
                'total': 0
            })
        
        account_ids = [account.id for account in accounts]
        
        # Build query
        query = Transaction.query.filter(
            (Transaction.from_account_id.in_(account_ids)) | 
            (Transaction.to_account_id.in_(account_ids))
        )
        
        # Add filters if provided
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
        
        # Add transaction type filter
        tx_type = request.args.get('type')
        if tx_type:
            if tx_type not in Transaction.VALID_TRANSACTION_TYPES:
                return error_response(f'Invalid transaction type. Must be one of: {", ".join(Transaction.VALID_TRANSACTION_TYPES)}', 400)
            query = query.filter(Transaction.transaction_type == tx_type)
        
        # Add search filter
        search = request.args.get('search')
        if search:
            if len(search) < 2:
                return error_response('Search term must be at least 2 characters long', 400)
            search_term = f'%{search}%'
            query = query.filter(Transaction.description.ilike(search_term))
        
        # Execute query with pagination
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

@bp.route('/deposit', methods=['POST'])
@jwt_required(fresh=True)
def deposit():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return error_response('Request body is required', 400)
        
        if not all(k in data for k in ('account_id', 'amount')):
            return error_response('Account ID and amount are required', 400)
        
        # Validate amount
        try:
            amount = Decimal(str(data['amount']))
            if amount <= 0:
                return error_response('Amount must be a positive number', 400)
            if amount > MAX_TRANSACTION_AMOUNT:
                return error_response(f'Amount cannot exceed {MAX_TRANSACTION_AMOUNT}', 400)
        except (ValueError, TypeError):
            return error_response('Amount must be a valid number', 400)
        
        # Get the account
        account = Account.query.filter_by(
            id=data['account_id'],
            user_id=user_id,
            is_active=True
        ).first()
        
        if not account:
            return error_response('Account not found or does not belong to you', 404)
        
        # Create transaction
        transaction = Transaction(
            transaction_type='deposit',
            amount=amount,
            to_account_id=account.id,
            description=data.get('description', 'Deposit')
        )
        
        # Process transaction
        transaction.process()
        
        return jsonify({
            'message': 'Deposit successful',
            'transaction': transaction.to_dict(),
            'new_balance': float(account.balance)
        })

    except BadRequest as e:
        return error_response(str(e), 400)
    except IntegrityError:
        db.session.rollback()
        return error_response('Database error occurred', 500)
    except Exception as e:
        current_app.logger.error(f"Error processing deposit: {str(e)}")
        return error_response("Failed to process deposit", 500)

@bp.route('/withdraw', methods=['POST'])
@jwt_required(fresh=True)
def withdraw():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return error_response('Request body is required', 400)
        
        if not all(k in data for k in ('account_id', 'amount')):
            return error_response('Account ID and amount are required', 400)
        
        # Validate amount
        try:
            amount = Decimal(str(data['amount']))
            if amount <= 0:
                return error_response('Amount must be a positive number', 400)
            if amount > MAX_TRANSACTION_AMOUNT:
                return error_response(f'Amount cannot exceed {MAX_TRANSACTION_AMOUNT}', 400)
        except (ValueError, TypeError):
            return error_response('Amount must be a valid number', 400)
        
        # Get the account
        account = Account.query.filter_by(
            id=data['account_id'],
            user_id=user_id,
            is_active=True
        ).first()
        
        if not account:
            return error_response('Account not found or does not belong to you', 404)
        
        # Create transaction
        transaction = Transaction(
            transaction_type='withdrawal',
            amount=amount,
            from_account_id=account.id,
            description=data.get('description', 'Withdrawal')
        )
        
        # Process transaction
        transaction.process()
        
        return jsonify({
            'message': 'Withdrawal successful',
            'transaction': transaction.to_dict(),
            'new_balance': float(account.balance)
        })

    except BadRequest as e:
        return error_response(str(e), 400)
    except IntegrityError:
        db.session.rollback()
        return error_response('Database error occurred', 500)
    except Exception as e:
        current_app.logger.error(f"Error processing withdrawal: {str(e)}")
        return error_response("Failed to process withdrawal", 500)

@bp.route('/transfer', methods=['POST'])
@jwt_required(fresh=True)
def transfer():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return error_response('Request body is required', 400)
        
        if not all(k in data for k in ('from_account_id', 'to_account_id', 'amount')):
            return error_response('From account ID, to account ID, and amount are required', 400)
        
        # Validate amount
        try:
            amount = Decimal(str(data['amount']))
            if amount <= 0:
                return error_response('Amount must be a positive number', 400)
            if amount > MAX_TRANSACTION_AMOUNT:
                return error_response(f'Amount cannot exceed {MAX_TRANSACTION_AMOUNT}', 400)
        except (ValueError, TypeError):
            return error_response('Amount must be a valid number', 400)
        
        # Check if accounts are different
        if data['from_account_id'] == data['to_account_id']:
            return error_response('Cannot transfer to the same account', 400)
        
        # Get the from account and verify ownership
        from_account = Account.query.filter_by(
            id=data['from_account_id'],
            user_id=user_id,
            is_active=True
        ).first()
        
        if not from_account:
            return error_response('Source account not found or does not belong to you', 404)
        
        # Get the to account
        to_account = Account.query.filter_by(
            id=data['to_account_id'],
            is_active=True
        ).first()
        
        if not to_account:
            return error_response('Destination account not found', 404)
        
        # Create transaction
        transaction = Transaction(
            transaction_type='transfer',
            amount=amount,
            from_account_id=from_account.id,
            to_account_id=to_account.id,
            description=data.get('description', f'Transfer from {from_account.account_number} to {to_account.account_number}')
        )
        
        # Process transaction
        transaction.process()
        
        return jsonify({
            'message': 'Transfer successful',
            'transaction': transaction.to_dict(),
            'from_account_balance': float(from_account.balance),
            'to_account_balance': float(to_account.balance)
        })

    except BadRequest as e:
        return error_response(str(e), 400)
    except IntegrityError:
        db.session.rollback()
        return error_response('Database error occurred', 500)
    except Exception as e:
        current_app.logger.error(f"Error processing transfer: {str(e)}")
        return error_response("Failed to process transfer", 500)

@bp.route('/transfer-advanced', methods=['POST'])
@jwt_required()
def transfer_advanced():
    try:
        user_id = int(get_jwt_identity())
        data = request.get_json()
        
        # Validate required fields
        if not data:
            return error_response('Request body is required', 400)
        
        if not all(k in data for k in ('from_account_id', 'to_account_id', 'amount')):
            return error_response('From account ID, to account ID, and amount are required', 400)
        
        # Validate amount
        try:
            amount = Decimal(str(data['amount']))
            if amount <= 0:
                return error_response('Amount must be a positive number', 400)
            if amount > MAX_TRANSACTION_AMOUNT:
                return error_response(f'Amount cannot exceed {MAX_TRANSACTION_AMOUNT}', 400)
        except (ValueError, TypeError):
            return error_response('Amount must be a valid number', 400)
        
        # Get the accounts
        from_account = Account.query.filter_by(
            id=data['from_account_id'],
            user_id=user_id,
            is_active=True
        ).first()
        
        if not from_account:
            return error_response('Source account not found or does not belong to you', 404)
        
        to_account = Account.query.filter_by(
            id=data['to_account_id'],
            is_active=True
        ).first()
        
        if not to_account:
            return error_response('Destination account not found', 404)
        
        # Check if accounts are different
        if from_account.id == to_account.id:
            return error_response('Cannot transfer to the same account', 400)
        
        # Create transaction
        transaction = Transaction(
            transaction_type='transfer',
            amount=amount,
            from_account_id=from_account.id,
            to_account_id=to_account.id,
            description=data.get('description', f'Transfer from {from_account.account_number} to {to_account.account_number}')
        )
        
        # Process transaction
        transaction.process()
        
        return jsonify({
            'message': 'Transfer successful',
            'transaction': transaction.to_dict(),
            'from_account_balance': float(from_account.balance),
            'to_account_balance': float(to_account.balance)
        })

    except BadRequest as e:
        return error_response(str(e), 400)
    except IntegrityError:
        db.session.rollback()
        return error_response('Database error occurred', 500)
    except Exception as e:
        current_app.logger.error(f"Error processing transfer: {str(e)}")
        return error_response("Failed to process transfer", 500)

@bp.route('/accounts/<int:account_id>/transactions', methods=['POST', 'GET'])
@jwt_required(fresh=True)
def account_transactions(account_id):
    try:
        user_id = int(get_jwt_identity())
        
        # Verify account ownership
        account = Account.query.filter_by(
            id=account_id,
            user_id=user_id,
            is_active=True
        ).first()
        
        if not account:
            return error_response('Account not found or does not belong to you', 404)
        
        if request.method == 'GET':
            # Get pagination parameters
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 20, type=int)
            
            # Validate pagination parameters
            if page < 1 or per_page < 1 or per_page > 100:
                return error_response('Invalid pagination parameters. Page and per_page must be positive, and per_page cannot exceed 100', 400)
            
            # Build query
            query = Transaction.query.filter(
                or_(
                    Transaction.from_account_id == account_id,
                    Transaction.to_account_id == account_id
                )
            )
            
            # Add filters if provided
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
            
            # Add transaction type filter
            tx_type = request.args.get('type')
            if tx_type:
                if tx_type not in Transaction.VALID_TRANSACTION_TYPES:
                    return error_response(f'Invalid transaction type. Must be one of: {", ".join(Transaction.VALID_TRANSACTION_TYPES)}', 400)
                query = query.filter(Transaction.transaction_type == tx_type)
            
            # Add search filter
            search = request.args.get('search')
            if search:
                if len(search) < 2:
                    return error_response('Search term must be at least 2 characters long', 400)
                search_term = f'%{search}%'
                query = query.filter(Transaction.description.ilike(search_term))
            
            # Execute query with pagination
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
        
        elif request.method == 'POST':
            data = request.get_json()
            
            # Validate required fields
            if not data:
                return error_response('Request body is required', 400)
            
            if not all(k in data for k in ('amount', 'type')):
                return error_response('Amount and transaction type are required', 400)
            
            # Validate transaction type
            tx_type = data['type']
            if tx_type not in Transaction.VALID_TRANSACTION_TYPES:
                return error_response(f'Invalid transaction type. Must be one of: {", ".join(Transaction.VALID_TRANSACTION_TYPES)}', 400)
            
            # Validate amount
            try:
                amount = Decimal(str(data['amount']))
                if amount <= 0:
                    return error_response('Amount must be a positive number', 400)
                if amount > MAX_TRANSACTION_AMOUNT:
                    return error_response(f'Amount cannot exceed {MAX_TRANSACTION_AMOUNT}', 400)
            except (ValueError, TypeError):
                return error_response('Amount must be a valid number', 400)
            
            # Create transaction based on type
            if tx_type == 'deposit':
                transaction = Transaction(
                    transaction_type='deposit',
                    amount=amount,
                    to_account_id=account_id,
                    description=data.get('description', 'Deposit')
                )
            elif tx_type == 'withdrawal':
                transaction = Transaction(
                    transaction_type='withdrawal',
                    amount=amount,
                    from_account_id=account_id,
                    description=data.get('description', 'Withdrawal')
                )
            else:
                return error_response('Invalid transaction type for this endpoint', 400)
            
            # Process transaction
            transaction.process()
            
            return jsonify({
                'message': f'{tx_type.capitalize()} successful',
                'transaction': transaction.to_dict(),
                'new_balance': float(account.balance)
            })

    except BadRequest as e:
        return error_response(str(e), 400)
    except IntegrityError:
        db.session.rollback()
        return error_response('Database error occurred', 500)
    except Exception as e:
        current_app.logger.error(f"Error processing account transactions: {str(e)}")
        return error_response("Failed to process account transactions", 500) 