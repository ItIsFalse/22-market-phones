from datetime import datetime

from app.extensions import db


class Currency:
    UZS = "UZS"
    USD = "USD"
    CHOICES = (UZS, USD)


class CashAccount(db.Model):
    __tablename__ = "cash_accounts"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    balance = db.Column(db.Numeric(18, 2), default=0, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default=Currency.UZS)

    transactions = db.relationship(
        "CashTransaction",
        back_populates="account",
        lazy="dynamic",
        order_by="CashTransaction.created_at.desc()",
    )

    def __repr__(self):
        return f"<CashAccount {self.name} {self.balance} {self.currency}>"


class CashTransaction(db.Model):
    __tablename__ = "cash_transactions"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("cash_accounts.id"), nullable=False)
    type = db.Column(db.String(16), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), nullable=False, default=Currency.UZS)
    description = db.Column(db.String(255))
    source_type = db.Column(db.String(32))
    source_id = db.Column(db.Integer)
    payment_id = db.Column(db.Integer, index=True)  # ← новая строка
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    account = db.relationship("CashAccount", back_populates="transactions")

    def __repr__(self):
        return f"<CashTransaction {self.type} {self.amount} {self.currency}>"