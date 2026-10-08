from datetime import datetime

from app.extensions import db


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(32), nullable=False, index=True)
    phone_extra = db.Column(db.String(32))
    passport = db.Column(db.String(64))
    pinfl = db.Column(db.String(32))
    address = db.Column(db.String(255))
    has_permanent_registration = db.Column(db.Boolean, default=False)
    salary_day = db.Column(db.Integer)
    note = db.Column(db.Text)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)

    latitude = db.Column(db.Numeric(10, 7))
    longitude = db.Column(db.Numeric(10, 7))

    installments = db.relationship(
        "Installment",
        back_populates="customer",
        lazy="dynamic",
    )

    def __repr__(self):
        return f"<Customer {self.full_name} {self.phone}>"