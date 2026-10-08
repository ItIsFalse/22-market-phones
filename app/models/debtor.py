from datetime import datetime
from decimal import Decimal

from app.extensions import db
from .cash import Currency


class Debtor(db.Model):
    __tablename__ = "debtors"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(128), nullable=False)
    phone = db.Column(db.String(32))
    loan_date = db.Column(db.Date, default=datetime.utcnow)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship(
        "DebtorTransaction",
        back_populates="debtor",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="DebtorTransaction.date.desc()",
    )

    @property
    def debt_uzs(self):
        total = Decimal("0")
        for t in self.transactions:
            if t.currency != Currency.UZS:
                continue
            total += t.amount if t.type == "borrow" else -t.amount
        return total

    @property
    def debt_usd(self):
        total = Decimal("0")
        for t in self.transactions:
            if t.currency != Currency.USD:
                continue
            total += t.amount if t.type == "borrow" else -t.amount
        return total

    def __repr__(self):
        return f"<Debtor {self.full_name}>"


class DebtorTransaction(db.Model):
    __tablename__ = "debtor_transactions"

    id = db.Column(db.Integer, primary_key=True)
    debtor_id = db.Column(db.Integer, db.ForeignKey("debtors.id"), nullable=False)
    type = db.Column(db.String(16), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), default=Currency.UZS, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    comment = db.Column(db.String(255))

    debtor = db.relationship("Debtor", back_populates="transactions")

    def __repr__(self):
        return f"<DebtorTransaction {self.type} {self.amount} {self.currency}>"
