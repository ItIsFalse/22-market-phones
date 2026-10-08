from datetime import datetime

from app.extensions import db
from .cash import Currency


class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    phone_id = db.Column(db.Integer, db.ForeignKey("phones.id"), unique=True, nullable=False)
    client_name = db.Column(db.String(128))
    client_contact = db.Column(db.String(64))
    price = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), default=Currency.UZS, nullable=False)
    cash_account_id = db.Column(db.Integer, db.ForeignKey("cash_accounts.id"))
    sold_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    phone = db.relationship("Phone", back_populates="sale")
    cash_account = db.relationship("CashAccount")

    def __repr__(self):
        return f"<Sale {self.phone_id} {self.price} {self.currency}>"