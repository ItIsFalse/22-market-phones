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
    from datetime import datetime, timedelta
    from decimal import Decimal
    from app.models import Sale, CashTransaction

    account = CashAccount.query.get_or_404(account_id)

    # === Фильтры ===
    tx_type = (request.args.get("tx_type") or "").strip()      # income / expense / ""
    tx_source = (request.args.get("tx_source") or "").strip()  # manual / purchase / sale / installment / ""

    query = CashTransaction.query.filter_by(account_id=account.id)

    if tx_type in ("income", "expense"):
        query = query.filter(CashTransaction.type == tx_type)

    if tx_source == "manual":
        query = query.filter(CashTransaction.source_type == "manual")

    elif tx_source == "purchase":
        query = query.filter(CashTransaction.source_type == "purchase")

    elif tx_source == "sale":
        query = query.filter(CashTransaction.source_type.in_(["sale", "sale_cancel"]))

    elif tx_source == "installment":
        query = query.filter(
            CashTransaction.source_type.in_(
                ["installment_prepayment", "installment_payment"]
            )
        )

    transactions = (
        query
        .order_by(CashTransaction.created_at.desc())
        .limit(200)
        .all()
    )

    # === Наценка за выбранный период ===
    period = (request.args.get("period") or "7d").strip()
    today = datetime.utcnow().date()

    if period == "month":
        date_from = today.replace(day=1)
    elif period == "all":
        date_from = None
    else:
        period = "7d"
        date_from = today - timedelta(days=7)

    date_to_end = today + timedelta(days=1)

    sales_q = Sale.query.filter(Sale.sold_at < date_to_end)
    if date_from is not None:
        sales_q = sales_q.filter(Sale.sold_at >= date_from)

    sales = sales_q.all()

    margin_usd = Decimal("0")
    margin_uzs = Decimal("0")
    for s in sales:
        purchase = s.phone.purchase if s.phone else None
        if purchase is None:
            continue
        if s.currency != purchase.currency:
            continue
        margin = Decimal(s.price) - Decimal(purchase.price)
        if s.currency == "USD":
            margin_usd += margin
        elif s.currency == "UZS":
            margin_uzs += margin

    return render_template(
        "cash/detail.html",
        account=account,
        transactions=transactions,
        margin_usd=margin_usd,
        margin_uzs=margin_uzs,
        filters={
            "tx_type": tx_type,
            "tx_source": tx_source,
            "period": period,
        },
    )


@cash_bp.route("/<int:account_id>/transaction/<int:tx_id>/delete", methods=["POST"])
@login_required
def delete_transaction(account_id, tx_id):
    """Удаление ручной транзакции. Пересчитывает баланс счёта."""
    from app.models import CashTransaction

    account = CashAccount.query.get_or_404(account_id)
    tx = CashTransaction.query.filter_by(id=tx_id, account_id=account.id).first_or_404()

    # разрешаем удалять только ручные операции
    if tx.source_type != "manual":
        flash(
            "Эту операцию нельзя удалить здесь. Она создана автоматически "
            "(закупка / продажа / рассрочка). Удалите её через соответствующий раздел.",
            "danger",
        )
        return redirect(url_for("cash.account_detail", account_id=account.id))

    # откат баланса
    if tx.type == "income":
        account.balance = Decimal(account.balance) - Decimal(tx.amount)
    else:
        account.balance = Decimal(account.balance) + Decimal(tx.amount)

    db.session.delete(tx)
    db.session.commit()

    flash("Операция удалена, баланс обновлён", "success")
    return redirect(url_for("cash.account_detail", account_id=account.id))


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
    """Удаление счёта. Только если он пустой и пароль верный."""
    from flask import current_app
    from app.models import Sale, PhonePurchase, CashTransaction

    account = CashAccount.query.get_or_404(account_id)

    # проверка пароля
    password = (request.form.get("password") or "").strip()
    expected = current_app.config.get("DELETE_PASSWORD", "")

    if not password or password != expected:
        flash("Неверный пароль. Счёт не удалён.", "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    # защита от удаления используемых счетов
    if Sale.query.filter_by(cash_account_id=account.id).first():
        flash("Нельзя удалить счёт: на нём есть продажи", "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    if PhonePurchase.query.filter_by(cash_account_id=account.id).first():
        flash("Нельзя удалить счёт: на нём есть закупки телефонов", "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    if CashTransaction.query.filter_by(account_id=account.id).first():
        flash("Нельзя удалить счёт: на нём есть операции.", "danger")
        return redirect(url_for("cash.account_detail", account_id=account.id))

    name = account.name
    delete_account(account)
    flash(f"Счёт «{name}» удалён", "info")
    return redirect(url_for("cash.list_accounts"))
