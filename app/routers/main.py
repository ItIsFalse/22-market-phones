from datetime import datetime
from decimal import Decimal

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models import (
    CashAccount, Currency,
    Phone, Installment, Debtor,
)


main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
def index():
    """Дашборд."""
    accounts = CashAccount.query.all()

    totals = {Currency.UZS: Decimal("0"), Currency.USD: Decimal("0")}
    for acc in accounts:
        totals[acc.currency] = totals.get(acc.currency, Decimal("0")) + Decimal(acc.balance)

    default_cash_usd = (
        CashAccount.query
        .filter_by(currency=Currency.USD)
        .order_by(CashAccount.id)
        .first()
    )
    default_cash_uzs = (
        CashAccount.query
        .filter_by(currency=Currency.UZS)
        .order_by(CashAccount.id)
        .first()
    )

    phones_in_stock = Phone.query.filter_by(status="in_stock").count()
    installments_active = Installment.query.filter_by(is_closed=False).count()

    debtors_count = 0
    for d in Debtor.query.all():
        if d.debt_uzs > 0 or d.debt_usd > 0:
            debtors_count += 1

    due_installments = _due_installments()

    return render_template(
        "index.html",
        user=current_user,
        totals=totals,
        default_cash_usd=default_cash_usd,
        default_cash_uzs=default_cash_uzs,
        phones_in_stock=phones_in_stock,
        installments_active=installments_active,
        debtors_count=debtors_count,
        due_installments=due_installments,
    )


def _due_installments():
    """Активные рассрочки, у которых наступил срок платежа и он не покрыт."""
    today = datetime.utcnow().date()
    result = []

    installments = Installment.query.filter_by(is_closed=False).all()

    for inst in installments:
        schedule = inst.payment_schedule
        if not schedule:
            continue

        due_rows = [row for row in schedule if row["due_date"].date() <= today]
        if not due_rows:
            continue

        should_paid = sum((row["amount"] for row in due_rows), Decimal("0"))
        actually_paid = inst.paid_total - inst.prepayment

        overdue = should_paid - actually_paid
        if overdue <= 0:
            continue

        next_due = due_rows[-1]["due_date"]
        result.append({
            "installment": inst,
            "next_due": next_due,
            "overdue": overdue,
            "should_paid": should_paid,
            "actually_paid": actually_paid,
        })

    result.sort(key=lambda r: r["next_due"])
    return result