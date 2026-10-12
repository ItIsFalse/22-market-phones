from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import (
    Installment, InstallmentPayment,
    Phone, Customer, CashAccount, Currency,
)
from app.services.cash import apply_transaction, get_default_account


installments_bp = Blueprint("installments", __name__, url_prefix="/installments")


@installments_bp.route("/")
@login_required
def list_installments():
    """Список рассрочек с поиском, фильтрами и сортировкой."""
    q = (request.args.get("q") or "").strip()
    status = (request.args.get("status") or "").strip()
    currency = (request.args.get("currency") or "").strip()
    sort = (request.args.get("sort") or "date_desc").strip()

    query = (
        Installment.query
        .join(Phone, Installment.phone_id == Phone.id)
        .join(Customer, Installment.customer_id == Customer.id)
    )

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Phone.brand.ilike(like),
            Phone.model.ilike(like),
            Phone.imei.ilike(like),
            Customer.full_name.ilike(like),
            Customer.phone.ilike(like),
        ))

    if status == "active":
        query = query.filter(Installment.is_closed.is_(False))
    elif status == "closed":
        query = query.filter(Installment.is_closed.is_(True))

    if currency in Currency.CHOICES:
        query = query.filter(Installment.currency == currency)

    if sort == "price_asc":
        query = query.order_by(Installment.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Installment.price.desc())
    elif sort == "date_asc":
        query = query.order_by(Installment.started_at.asc())
    else:
        query = query.order_by(Installment.started_at.desc())

    installments = query.all()

    return render_template(
        "installments/list.html",
        installments=installments,
        filters={
            "q": q,
            "status": status,
            "currency": currency,
            "sort": sort,
        },
    )


@installments_bp.route("/summary/")
@login_required
def summary():
    """Сводка по рассрочкам: собрано, должны, просрочено, закрыто."""
    cur = (request.args.get("currency") or "USD").strip().upper()
    if cur not in ("USD", "UZS", "ALL"):
        cur = "USD"

    if cur == "ALL":
        usd = _calc_summary(Currency.USD)
        uzs = _calc_summary(Currency.UZS)
        collected_usd = usd["collected"]
        collected_uzs = uzs["collected"]
        pending_usd = usd["pending"]
        pending_uzs = uzs["pending"]
        overdue_usd = usd["overdue"]
        overdue_uzs = uzs["overdue"]
        closed_count = usd["closed"] + uzs["closed"]
        active_count = usd["active"] + uzs["active"]
        installments = (
            Installment.query
            .order_by(Installment.started_at.desc())
            .all()
        )
    else:
        data = _calc_summary(cur)
        collected_usd = data["collected"] if cur == Currency.USD else Decimal("0")
        collected_uzs = data["collected"] if cur == Currency.UZS else Decimal("0")
        pending_usd = data["pending"] if cur == Currency.USD else Decimal("0")
        pending_uzs = data["pending"] if cur == Currency.UZS else Decimal("0")
        overdue_usd = data["overdue"] if cur == Currency.USD else Decimal("0")
        overdue_uzs = data["overdue"] if cur == Currency.UZS else Decimal("0")
        closed_count = data["closed"]
        active_count = data["active"]
        installments = (
            Installment.query
            .filter_by(currency=cur)
            .order_by(Installment.started_at.desc())
            .all()
        )

    return render_template(
        "installments/summary.html",
        cur=cur,
        collected_usd=collected_usd,
        collected_uzs=collected_uzs,
        pending_usd=pending_usd,
        pending_uzs=pending_uzs,
        overdue_usd=overdue_usd,
        overdue_uzs=overdue_uzs,
        closed_count=closed_count,
        active_count=active_count,
        installments=installments,
    )


def _calc_summary(currency):
    """Считает 4 цифры для одной валюты."""
    installments = Installment.query.filter_by(currency=currency).all()

    collected = Decimal("0")
    for inst in installments:
        for p in inst.payments:
            collected += Decimal(p.amount)

    pending = Decimal("0")
    overdue = Decimal("0")
    closed_count = 0
    active_count = 0
    today = datetime.utcnow().date()

    for inst in installments:
        if inst.is_closed:
            closed_count += 1
        else:
            active_count += 1

        left = inst.debt_left
        if left > 0:
            pending += left

        schedule = inst.payment_schedule
        due_rows = [row for row in schedule if row["due_date"].date() < today]
        should_paid = sum((row["amount"] for row in due_rows), Decimal("0"))
        actually_paid = inst.paid_total - Decimal(inst.prepayment)
        diff = should_paid - actually_paid
        if diff > 0:
            overdue += diff

    return {
        "collected": collected,
        "pending": pending,
        "overdue": overdue,
        "closed": closed_count,
        "active": active_count,
    }


@installments_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_installment():
    """Создание рассрочки."""
    phones = (
        Phone.query
        .filter_by(status="in_stock")
        .join(Phone.purchase)
        .order_by(Phone.id.desc())
        .all()
    )
    phones_json = [
        {
            "id": p.id,
            "brand": p.brand,
            "model": p.model,
            "imei": p.imei or "",
            "storage": p.purchase.storage or "",
            "color": p.purchase.color or "",
        }
        for p in phones
    ]
    customers = Customer.query.order_by(Customer.full_name).all()
    customers_json = [
        {"id": c.id, "full_name": c.full_name, "phone": c.phone or ""}
        for c in customers
    ]
    usd_accounts = (
        CashAccount.query
        .filter_by(currency=Currency.USD)
        .order_by(CashAccount.id)
        .all()
    )
    default_account = usd_accounts[0] if usd_accounts else None

    preselected_phone_id = request.args.get("phone_id", type=int)

    ctx = dict(
        phones=phones,
        phones_json=phones_json,
        customers_json=customers_json,
        usd_accounts=usd_accounts,
        default_account=default_account,
    )

    if request.method == "POST":
        form = _read_form(request.form)
        errors = _validate(form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("installments/form.html", form_data=form, **ctx)

        phone = Phone.query.get(form["phone_id"])
        if phone is None or phone.status != "in_stock":
            flash("Телефон не найден или уже продан", "danger")
            return render_template("installments/form.html", form_data=form, **ctx)

        customer = Customer.query.get(form["customer_id"])
        if customer is None:
            flash("Покупатель не найден", "danger")
            return render_template("installments/form.html", form_data=form, **ctx)

        if form["prepayment"] > form["price"]:
            flash("Предоплата не может быть больше цены", "danger")
            return render_template("installments/form.html", form_data=form, **ctx)

        if form["cash_account_id"]:
            account = CashAccount.query.get(form["cash_account_id"])
        else:
            account = default_account

        if account is None:
            flash("Нет USD-кассы для зачисления предоплаты", "danger")
            return render_template("installments/form.html", form_data=form, **ctx)

        if account.currency != Currency.USD:
            flash("Касса для рассрочки должна быть в USD", "danger")
            return render_template("installments/form.html", form_data=form, **ctx)

        try:
            installment = Installment(
                phone_id=phone.id,
                customer_id=customer.id,
                price=form["price"],
                prepayment=form["prepayment"],
                percent=form["percent"],
                months=form["months"],
                currency=Currency.USD,
            )
            db.session.add(installment)
            db.session.flush()

            if installment.prepayment > 0:
                apply_transaction(
                    account=account,
                    type_="income",
                    amount=installment.prepayment,
                    description=f"Предоплата по рассрочке #{installment.id}",
                    source_type="installment_prepayment",
                    source_id=installment.id,
                )
                payment = InstallmentPayment(
                    installment=installment,
                    amount=installment.prepayment,
                    currency=Currency.USD,
                    cash_account_id=account.id,
                    comment="Предоплата",
                )
                db.session.add(payment)

            phone.status = "installment"
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка сохранения: {e}", "danger")
            return render_template("installments/form.html", form_data=form, **ctx)

        flash("Рассрочка оформлена", "success")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    form_data = {}
    if preselected_phone_id:
        form_data["phone_id"] = preselected_phone_id
        # для отображения в автокомплите
        preselected = Phone.query.get(preselected_phone_id)
        if preselected:
            extra = " · ".join(filter(None, [preselected.purchase.storage, preselected.purchase.color]))
            form_data["phone_display"] = f"{preselected.brand} {preselected.model}"
            if extra:
                form_data["phone_display"] += f" · {extra}"

    return render_template("installments/form.html", form_data=form_data, **ctx)


@installments_bp.route("/<int:installment_id>")
@login_required
def installment_detail(installment_id):
    """Карточка рассрочки: график, платежи, форма внесения."""
    installment = Installment.query.get_or_404(installment_id)
    payments = installment.payments.all()

    usd_accounts = (
        CashAccount.query
        .filter_by(currency=installment.currency)
        .order_by(CashAccount.id)
        .all()
    )
    default_account = usd_accounts[0] if usd_accounts else None

    # --- Прогресс оплаты ---
    total = installment.total_with_percent
    paid = installment.paid_total - Decimal(installment.prepayment)  # без предоплаты
    if total and total > 0:
        progress = int((paid / total) * 100)
        if progress > 100:
            progress = 100
        if progress < 0:
            progress = 0
    else:
        progress = 0

    # --- Статусы графика ---
    schedule = installment.payment_schedule
    today = datetime.utcnow().date()

    # сколько уже оплачено (без предоплаты)
    paid_so_far = Decimal("0")
    schedule_with_status = []
    next_payment = None

    for row in schedule:
        due_date = row["due_date"].date()
        amount = row["amount"]

        # сколько нужно было бы оплатить к этому платежу включительно
        cumulative_target = paid_so_far + amount
        is_paid = paid >= cumulative_target
        is_partial = (not is_paid) and (paid > paid_so_far)
        is_overdue = (not is_paid) and (due_date < today)

        if is_paid:
            status = "paid"
            icon = "✅"
        elif is_overdue:
            status = "overdue"
            icon = "🔴"
        elif is_partial:
            status = "partial"
            icon = "🟡"
        else:
            status = "future"
            icon = "⚪"
            if next_payment is None:
                next_payment = row

        schedule_with_status.append({
            "index": row["index"],
            "due_date": row["due_date"],
            "amount": amount,
            "status": status,
            "icon": icon,
        })
        paid_so_far = cumulative_target

    return render_template(
        "installments/detail.html",
        installment=installment,
        payments=payments,
        usd_accounts=usd_accounts,
        default_account=default_account,
        progress=progress,
        schedule_with_status=schedule_with_status,
        next_payment=next_payment,
    )


@installments_bp.route("/<int:installment_id>/pay", methods=["POST"])
@login_required
def add_payment(installment_id):
    """Внести платёж по рассрочке."""
    installment = Installment.query.get_or_404(installment_id)

    if installment.is_closed:
        flash("Рассрочка уже закрыта", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    amount_raw = (request.form.get("amount") or "").strip()
    comment = (request.form.get("comment") or "").strip()
    account_id_raw = (request.form.get("cash_account_id") or "").strip()

    try:
        amount = Decimal(amount_raw)
    except InvalidOperation:
        flash("Сумма должна быть числом", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    if amount <= 0:
        flash("Сумма должна быть больше нуля", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    left = installment.debt_left
    if left <= 0:
        installment.is_closed = True
        db.session.commit()
        flash("Рассрочка уже закрыта", "info")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    if amount > left:
        amount = left
        suffix = "Сумма скорректирована до остатка"
        comment = f"{comment} ({suffix})" if comment else suffix

    if account_id_raw.isdigit():
        account = CashAccount.query.get(int(account_id_raw))
    else:
        account = get_default_account(installment.currency)

    if account is None:
        flash("Не найдена касса для зачисления платежа", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    if account.currency != installment.currency:
        flash("Валюта кассы не совпадает с валютой рассрочки", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    try:
        apply_transaction(
            account=account,
            type_="income",
            amount=amount,
            description=f"Платёж по рассрочке #{installment.id}",
            source_type="installment_payment",
            source_id=installment.id,
        )

        payment = InstallmentPayment(
            installment=installment,
            amount=amount,
            currency=installment.currency,
            cash_account_id=account.id,
            comment=comment,
        )
        db.session.add(payment)
        db.session.flush()

        if installment.debt_left <= 0:
            installment.is_closed = True

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка сохранения: {e}", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    flash("Платёж внесён", "success")
    return redirect(url_for("installments.installment_detail", installment_id=installment.id))


def _read_form(form):
    """Считать данные формы."""
    def val(key, default=""):
        return (form.get(key) or default).strip()

    def to_int(key):
        raw = val(key)
        try:
            return int(raw) if raw else None
        except ValueError:
            return None

    def to_decimal(key):
        raw = val(key)
        if not raw:
            return Decimal("0")
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None

    return {
        "phone_id": to_int("phone_id"),
        "customer_id": to_int("customer_id"),
        "phone_display": val("phone_display"),
        "customer_display": val("customer_display"),
        "price": to_decimal("price"),
        "prepayment": to_decimal("prepayment"),
        "percent": to_decimal("percent"),
        "months": to_int("months"),
        "cash_account_id": to_int("cash_account_id"),
        "price_raw": val("price"),
        "prepayment_raw": val("prepayment"),
        "percent_raw": val("percent"),
        "months_raw": val("months"),
    }


def _validate(form):
    """Проверка формы."""
    errors = []

    if form["phone_id"] is None:
        errors.append("Выберите телефон")
    if form["customer_id"] is None:
        errors.append("Выберите покупателя")
    if form["price"] is None or form["price"] <= 0:
        errors.append("Цена должна быть числом больше нуля")
    if form["prepayment"] is None or form["prepayment"] < 0:
        errors.append("Предоплата должна быть числом ≥ 0")
    if form["percent"] is None or form["percent"] < 0:
        errors.append("Процент должен быть числом ≥ 0")
    if form["months"] is None or form["months"] < 1:
        errors.append("Срок рассрочки — целое число месяцев ≥ 1")

    return errors