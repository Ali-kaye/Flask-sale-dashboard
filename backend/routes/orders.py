from flask import Blueprint, request, jsonify
from database import db
from models.orders import Order

orders_bp = Blueprint('orders', __name__)

@orders_bp.route('/orders', methods=['POST'])
def add_order():
    data = request.get_json()
    new_order = Order(customer_id=data['customer_id'], product_id=data['product_id'], amount=data['amount'])
    db.session.add(new_order)
    db.session.commit()
    return jsonify({'message': 'Order placed successfully'})

@orders_bp.route('/orders', methods=['GET'])
def get_orders():
    orders = Order.query.all()
    return jsonify([{ 'id': o.id, 'customer_id': o.customer_id, 'product_id': o.product_id, 'amount': o.amount, 'order_date': o.order_date } for o in orders])
