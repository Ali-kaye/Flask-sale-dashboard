from flask import Blueprint, request, jsonify
from database import db
from models.products import Product
from flask_jwt_extended import jwt_required, get_jwt_identity

products_bp = Blueprint('products', __name__)

@products_bp.route('/products', methods=['POST'])
@jwt_required()
def add_product():
    user = get_jwt_identity()
    if user['role'] != 'admin':
        return jsonify({'message': 'Access forbidden: Admins only'}), 403

    data = request.get_json()
    new_product = Product(name=data['name'], category=data['category'], price=data['price'])
    db.session.add(new_product)
    db.session.commit()
    return jsonify({'message': 'Product added successfully'}), 201

@products_bp.route('/products', methods=['GET'])
def get_products():
    products = Product.query.all()
    return jsonify([{ 'id': p.id, 'name': p.name, 'category': p.category, 'price': p.price } for p in products])
