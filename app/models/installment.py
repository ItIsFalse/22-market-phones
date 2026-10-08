from datetime import datetime
from decimal import Decimal, ROUND_DOWN

from dateutil.relativedelta import relativedelta

from app.extensions import db
from .cash import Currency


class Installment(db.Model):
    __tablename__ = "installments"

    id = db.Column(db.Integer, primary_key=True)
    phone_id = db.Column(db.Integer, db.ForeignKey("phones.id"), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=False)

    price = db.Column(db.Numeric(18, 2), nullable=False)
    prepayment = db.Column(db.Numeric(18, 2), default=0)
    percent = db.Column(db.Numeric(5, 2), default=0)
    months = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), default=Currency.USD, nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    is_closed = db.Column(db.Boolean, default=False)

    phone = db.relationship("Phone", back_populates="installment")
    customer = db.relationship("Customer", back_populates="installments")
    payments = db.relationship(
        "InstallmentPayment",
        back_populates="installment",
        cascade="all, delete-orphan",
        lazy="dynamic",
        order_by="InstallmentPayment.paid_at",
    )

    @property
    def remaining_after_prepayment(self):
        return Decimal(self.price) - Decimal(self.prepayment)

    @property
    def total_with_percent(self):
        percent = Decimal(self.percent or 0)
        return self.remaining_after_prepayment * (Decimal("1") + percent / Decimal("100"))

    @property
    def monthly_payment(self):
        """Базовый месячный платёж — целое, округление вниз."""
        if self.months <= 0:
            return Decimal("0")
        return (self.total_with_percent / self.months).quantize(
            Decimal("1"), rounding=ROUND_DOWN
        )

    @property
    def payment_schedule(self):
        """График: целые суммы, остаток от деления в последний платёж."""
        if self.months <= 0:
            return []

        total = self.total_with_percent
        base = (total / self.months).quantize(Decimal("1"), rounding=ROUND_DOWN)
        schedule = [base] * self.months

        diff = total - base * self.months
        schedule[-1] = schedule[-1] + diff

        result = []
        start = self.started_at or datetime.utcnow()
        for i, amount in enumerate(schedule):
            due = start + relativedelta(months=i + 1)
            result.append({"index": i + 1, "due_date": due, "amount": amount})
        return result

    @property
    def paid_total(self):
        """Все внесённые платежи, включая предоплату."""
        total = Decimal("0")
        for p in self.payments:
            total += Decimal(p.amount)
        return total

    @property
    def debt_left(self):
        """Остаток к оплате (без учёта предоплаты, она уже в paid_total)."""
        return self.total_with_percent - (self.paid_total - Decimal(self.prepayment))

    def __repr__(self):
        return f"<Installment {self.phone_id} {self.months}м>"


class InstallmentPayment(db.Model):
    __tablename__ = "installment_payments"

    id = db.Column(db.Integer, primary_key=True)
    installment_id = db.Column(db.Integer, db.ForeignKey("installments.id"), nullable=False)
    amount = db.Column(db.Numeric(18, 2), nullable=False)
    currency = db.Column(db.String(3), default=Currency.USD, nullable=False)
    cash_account_id = db.Column(db.Integer, db.ForeignKey("cash_accounts.id"))
    paid_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    comment = db.Column(db.String(255))

    installment = db.relationship("Installment", back_populates="payments")
    cash_account = db.relationship("CashAccount")

    def __repr__(self):
        return f"<InstallmentPayment {self.amount} {self.paid_at}>"