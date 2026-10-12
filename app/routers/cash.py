from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required

from app.extensions import db
from app.models import CashAccount, Currency
from app.services.cash import create_account, apply_transaction, delete_account


cash_bp = Blueprint("cash", __name__, url_prefix="/cash")


@cash_bp.route("/")
@login_required
def list_accounts():
    """Список всех счетов с итогами по валютам."""
    accounts = CashAccount.query.order_by(CashAccount.id).all()

    totals = {Currency.UZS: Decimal("0"), Currency.USD: Decimal("0")}
    for acc in accounts:
        totals[acc.currency] = totals.get(acc.currency, Decimal("0")) + Decimal(acc.balance)

    return render_template("cash/list.html", accounts=accounts, totals=totals)


@cash_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_account():
    """Создание нового счёта."""
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        currency = (request.form.get("currency") or "").strip()
        initial = (request.form.get("initial_balance") or "0").strip()

        errors = []
        if not name:
            errors.append("Введите название счёта")
        if currency not in Currency.CHOICES:
            errors.append("Выберите валюту")

        try:
            initial_value = Decimal(initial) if initial else Decimal("0")
        except InvalidOperation:
            errors.append("Начальный баланс должен быть числом")
            initial_value = Decimal("0")

        if initial_value < 0:
            errors.append("Начальный баланс не может быть отрицательным")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "cash/form.html",
                account=None,
                form_data={"name": name, "currency": currency, "initial_balance": initial},
            )

        create_account(name=name, currency=currency, initial_balance=initial_value)
        flash(f"Счёт «{name}» создан", "success")
        return redirect(url_for("cash.list_accounts"))

    return render_template("cash/form.html", account=None, form_data={})


@cash_bp.route("/<int:account_id>")
@login_required
def account_detail(account_id):
    """Страница счёта: баланс, история операций, форма ручной проводки."""
    account = CashAccount.query.get_or_404(account_id)
    transactions = account.transactions.limit(200).all()
    return render_template("cash/detail.html", account=account, transactions=transactions)


@cash_bp.route("/<int:account_id>/transaction", methods=["POST"])
@login_required
def add_transaction(account_id):
    """Ручная проводка прихода или расхода."""
    account = CashAccount.query.get_or_404(account_id)

    type_ = (request.form.get("type") or "").strip()
    amount_raw = (request.form.get("amount") or "").strip()
    description = (request.form.get("description") or "").strip()

    if type_ not in ("income", "expense"):
        flash("Выберите тип операции", "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    try:
        amount = Decimal(amount_raw)
    except InvalidOperation:
        flash("Сумма должна быть числом", "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    try:
        apply_transaction(
            account=account,
            type_=type_,
            amount=amount,
            description=description,
            source_type="manual",
        )
        db.session.commit()
    except ValueError as e:
        db.session.rollback()
        flash(str(e), "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    flash("Операция проведена", "success")
    return redirect(url_for("cash.account_detail", account_id=account.id))


@cash_bp.route("/<int:account_id>/delete", methods=["POST"])
@login_required
def account_delete(account_id):
    """Удаление счёта. Только если он не используется."""
    from app.models import Sale, PhonePurchase, CashTransaction

    account = CashAccount.query.get_or_404(account_id)

    if Sale.query.filter_by(cash_account_id=account.id).first():
        flash("Нельзя удалить счёт: на нём есть продажи", "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    if PhonePurchase.query.filter_by(cash_account_id=account.id).first():
        flash("Нельзя удалить счёт: на нём есть закупки телефонов", "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    if CashTransaction.query.filter_by(account_id=account.id).first():
        flash("Нельзя удалить счёт: на нём есть операции. Сначала удалите или перенесите их.", "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    name = account.name
    delete_account(account)
    flash(f"Счёт «{name}» удалён", "info")
    return redirect(url_for("cash.list_accounts"))