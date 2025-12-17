from flask import Blueprint, request, jsonify
from database import db
from models.customers import Customer

customers_bp = Blueprint('customers', __name__)

@customers_bp.route('/customers', methods=['GET'])
def get_customers():
    customers = Customer.query.all()
    return jsonify([{ 'id': c.id, 'name': c.name, 'email': c.email, 'phone': c.phone, 'location': c.location } for c in customers])

@customers_bp.route('/customers', methods=['POST'])
def add_customer():
    data = request.get_json()
    new_customer = Customer(name=data['name'], email=data['email'], phone=data['phone'], location=data['location'])
    db.session.add(new_customer)
    db.session.commit()
    return jsonify({'message': 'Customer added successfully'})
