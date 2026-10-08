from datetime import datetime

from app.extensions import db
from .cash import Currency


class PhonePurchase(db.Model):
    __tablename__ = "phone_purchases"

    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(128))
    client_contact = db.Column(db.String(64))
    brand = db.Column(db.String(64), nullable=False)
    model = db.Column(db.String(64), nullable=False)
    color = db.Column(db.String(64))
    storage = db.Column(db.String(32))
    battery = db.Column(db.String(32))
    imei = db.Column(db.String(32), unique=True, index=True)
    has_box = db.Column(db.Boolean, default=False)
    price = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), default=Currency.USD, nullable=False)
    note = db.Column(db.Text)
    cash_account_id = db.Column(db.Integer, db.ForeignKey("cash_accounts.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    cash_account = db.relationship("CashAccount")
    phone = db.relationship("Phone", back_populates="purchase", uselist=False)

    def __repr__(self):
        return f"<PhonePurchase {self.brand} {self.model} {self.imei}>"


class Phone(db.Model):
    __tablename__ = "phones"

    id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("phone_purchases.id"), unique=True)
    status = db.Column(db.String(16), default="in_stock")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    purchase = db.relationship("PhonePurchase", back_populates="phone")
    sale = db.relationship("Sale", back_populates="phone", uselist=False)
    installment = db.relationship("Installment", back_populates="phone", uselist=False)

    @property
    def brand(self):
        return self.purchase.brand

    @property
    def model(self):
        return self.purchase.model

    @property
    def imei(self):
        return self.purchase.imei

    @property
    def purchase_price(self):
        return self.purchase.price

    @property
    def purchase_currency(self):
        return self.purchase.currency

    def __repr__(self):
        return f"<Phone {self.brand} {self.model} [{self.status}]>"