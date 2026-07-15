from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db # Assuming circular import is handled or db is passed

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False) # NEW FIELD
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    estimates = db.relationship('Estimate', backref='user', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Estimate(db.Model):
    __tablename__ = 'estimates'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    brand = db.Column(db.String(50), nullable=False)
    model = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    fuel = db.Column(db.String(20), nullable=False)
    transmission = db.Column(db.String(20), nullable=False)
    predicted_price = db.Column(db.Float, nullable=False)
    min_price = db.Column(db.Float, nullable=True) # NEW FIELD
    max_price = db.Column(db.Float, nullable=True) # NEW FIELD
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

