from database import db

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    location = db.Column(db.String(50), nullable=False)
    registration_date = db.Column(db.DateTime, default=db.func.current_timestamp())
