from datetime import datetime, timedelta
from decimal import Decimal

from flask import Blueprint, render_template, request
from flask_login import login_required

from app.models import Sale, PhonePurchase, Currency, Installment

reports_bp = Blueprint("reports", __name__, url_prefix="/reports")


@reports_bp.route("/")
@login_required
def index():
    """Отчёт: закупки, продажи, наценка, рассрочки за период."""
    from app.models import InstallmentPayment
    from datetime import datetime, timedelta
    from decimal import Decimal
    from flask import render_template, request
    from app.models import Sale, PhonePurchase, Currency, Installment

    today = datetime.utcnow().date()
    default_from = today - timedelta(days=7)
    default_to = today

    date_from_raw = (request.args.get("from") or "").strip()
    date_to_raw = (request.args.get("to") or "").strip()

    try:
        date_from = datetime.strptime(date_from_raw, "%Y-%m-%d").date() if date_from_raw else default_from
    except ValueError:
        date_from = default_from

    try:
        date_to = datetime.strptime(date_to_raw, "%Y-%m-%d").date() if date_to_raw else default_to
    except ValueError:
        date_to = default_to

    date_to_end = date_to + timedelta(days=1)

    # ===== Закупки =====
    purchases = (
        PhonePurchase.query
        .filter(PhonePurchase.created_at >= date_from)
        .filter(PhonePurchase.created_at < date_to_end)
        .all()
    )
    purchases_usd = sum((Decimal(p.price) for p in purchases if p.currency == Currency.USD), Decimal("0"))
    purchases_uzs = sum((Decimal(p.price) for p in purchases if p.currency == Currency.UZS), Decimal("0"))
    purchases_count = len(purchases)

    # ===== Продажи =====
    sales = (
        Sale.query
        .filter(Sale.sold_at >= date_from)
        .filter(Sale.sold_at < date_to_end)
        .all()
    )
    sales_usd = sum((Decimal(s.price) for s in sales if s.currency == Currency.USD), Decimal("0"))
    sales_uzs = sum((Decimal(s.price) for s in sales if s.currency == Currency.UZS), Decimal("0"))
    sales_count = len(sales)

    # ===== Наценка =====
    margin_usd = Decimal("0")
    margin_uzs = Decimal("0")
    for s in sales:
        purchase = s.phone.purchase if s.phone else None
        if purchase is None or s.currency != purchase.currency:
            continue
        margin = Decimal(s.price) - Decimal(purchase.price)
        if s.currency == Currency.USD:
            margin_usd += margin
        elif s.currency == Currency.UZS:
            margin_uzs += margin

    # ===== Рассрочки (на основе фактических платежей за период) =====
    # Все платежи, которые были сделаны в выбранном диапазоне дат
    payments_in_period = (
        InstallmentPayment.query
        .filter(InstallmentPayment.paid_at >= date_from)
        .filter(InstallmentPayment.paid_at < date_to_end)
        .all()
    )

    paid_installments = Decimal("0")
    for p in payments_in_period:
        paid_installments += Decimal(p.amount)

    # Остаток по всем активным рассрочкам (на текущий момент)
    active_installments = Installment.query.filter_by(is_closed=False).all()
    pending_installments = Decimal("0")
    for inst in active_installments:
        pending_installments += inst.debt_left

    # "Всего" в рассрочке — это то, что мы получили за период + то, что осталось получить.
    total_installments = paid_installments + pending_installments

    return render_template(
        "reports/index.html",
        date_from=date_from,
        date_to=date_to,
        purchases_usd=purchases_usd,
        purchases_uzs=purchases_uzs,
        purchases_count=purchases_count,
        sales_usd=sales_usd,
        sales_uzs=sales_uzs,
        sales_count=sales_count,
        margin_usd=margin_usd,
        margin_uzs=margin_uzs,
        total_installments=total_installments,
        paid_installments=paid_installments,
        pending_installments=pending_installments,
    )
