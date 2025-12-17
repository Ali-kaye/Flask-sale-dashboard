from flask import Blueprint, request, jsonify
from database import db
from backend.database import User
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity, JWTManager

auth_bp = Blueprint('auth', __name__)

# User Registration (Only for testing, restrict in production)
@auth_bp.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'message': 'Username already exists'}), 400

    user = User(username=data['username'], email=data['email'], role=data.get('role', 'user'))  # Default to 'user'
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'message': 'User registered successfully'}), 201

# User Login
@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = User.query.filter_by(username=data['username']).first()

    if user and user.check_password(data['password']):
        token = create_access_token(identity={'id': user.id, 'role': user.role})
        return jsonify({'token': token, 'role': user.role, 'message': 'Login successful'}), 200
    return jsonify({'message': 'Invalid credentials'}), 401

# Protected Route (Example)
@auth_bp.route('/admin', methods=['GET'])
@jwt_required()
def admin_only():
    user = get_jwt_identity()
    if user['role'] != 'admin':
        return jsonify({'message': 'Access forbidden: Admins only'}), 403
    return jsonify({'message': 'Welcome, Admin!'}), 200
