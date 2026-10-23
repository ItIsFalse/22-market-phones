import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO

from docx import Document
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask import send_file
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

    from app.models import PhonePurchase

    query = (
        Installment.query
        .join(Phone, Installment.phone_id == Phone.id)
        .join(PhonePurchase, Phone.purchase_id == PhonePurchase.id)
        .join(Customer, Installment.customer_id == Customer.id)
    )

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            PhonePurchase.brand.ilike(like),
            PhonePurchase.model.ilike(like),
            PhonePurchase.imei.ilike(like),
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
    """Сводка по рассрочкам с поиском."""
    cur = (request.args.get("currency") or "USD").strip().upper()
    if cur not in ("USD", "UZS", "ALL"):
        cur = "USD"

    q = (request.args.get("q") or "").strip()

    if cur == "ALL":
        usd = _calc_summary(Currency.USD, q)
        uzs = _calc_summary(Currency.UZS, q)

        collected_usd = usd["collected"]
        collected_uzs = uzs["collected"]
        pending_usd = usd["pending"]
        pending_uzs = uzs["pending"]
        overdue_usd = usd["overdue"]
        overdue_uzs = uzs["overdue"]
        closed_count = usd["closed"] + uzs["closed"]
        active_count = usd["active"] + uzs["active"]
        installments = _filtered_installments(q, None)
    else:
        data = _calc_summary(cur, q)

        collected_usd = data["collected"] if cur == Currency.USD else Decimal("0")
        collected_uzs = data["collected"] if cur == Currency.UZS else Decimal("0")
        pending_usd = data["pending"] if cur == Currency.USD else Decimal("0")
        pending_uzs = data["pending"] if cur == Currency.UZS else Decimal("0")
        overdue_usd = data["overdue"] if cur == Currency.USD else Decimal("0")
        overdue_uzs = data["overdue"] if cur == Currency.UZS else Decimal("0")
        closed_count = data["closed"]
        active_count = data["active"]

        installments = _filtered_installments(q, cur)

    return render_template(
        "installments/summary.html",
        cur=cur,
        q=q,
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


def _filtered_installments(q, currency):
    """Возвращает отфильтрованный список рассрочек."""
    from app.models import PhonePurchase

    query = (
        Installment.query
        .join(Phone, Installment.phone_id == Phone.id)
        .join(PhonePurchase, Phone.purchase_id == PhonePurchase.id)
        .join(Customer, Installment.customer_id == Customer.id)
    )

    if currency in Currency.CHOICES:
        query = query.filter(Installment.currency == currency)

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            PhonePurchase.brand.ilike(like),
            PhonePurchase.model.ilike(like),
            PhonePurchase.imei.ilike(like),
            Customer.full_name.ilike(like),
            Customer.phone.ilike(like),
        ))

    return query.order_by(Installment.started_at.desc()).all()


def _calc_summary(currency, q=""):
    """Считает 4 цифры для одной валюты с учётом поиска."""
    installments = _filtered_installments(q, currency)

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
    # Сортируем по дате регистрации (сначала новые)
    customers = Customer.query.order_by(Customer.registered_at.desc()).all()
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
                started_at=form["started_at"],
                currency=Currency.USD,
            )
            db.session.add(installment)
            db.session.flush()

            if installment.prepayment > 0:
                payment = InstallmentPayment(
                    installment=installment,
                    amount=installment.prepayment,
                    currency=Currency.USD,
                    cash_account_id=account.id,
                    comment="Предоплата",
                )
                db.session.add(payment)
                db.session.flush()  # ← чтобы был payment.id

                apply_transaction(
                    account=account,
                    type_="income",
                    amount=installment.prepayment,
                    description=f"Предоплата по рассрочке #{installment.id}",
                    source_type="installment_prepayment",
                    source_id=installment.id,
                    payment_id=payment.id,  # ← привязка
                )

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
        # 1. Сначала создаём платёж, чтобы был payment.id
        payment = InstallmentPayment(
            installment=installment,
            amount=amount,
            currency=installment.currency,
            cash_account_id=account.id,
            comment=comment,
        )
        db.session.add(payment)
        db.session.flush()

        # 2. Потом создаём транзакцию с привязкой
        apply_transaction(
            account=account,
            type_="income",
            amount=amount,
            description=f"Платёж по рассрочке #{installment.id}",
            source_type="installment_payment",
            source_id=installment.id,
            payment_id=payment.id,
        )

        if installment.debt_left <= 0:
            installment.is_closed = True

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка сохранения: {e}", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    flash("Платёж внесён", "success")
    return redirect(url_for("installments.installment_detail", installment_id=installment.id))


@installments_bp.route("/<int:installment_id>/payment/<int:payment_id>/edit", methods=["POST"])
@login_required
def edit_payment(installment_id, payment_id):
    """Редактирование суммы и комментария платежа с защитой от переплаты."""
    from app.models import CashTransaction

    installment = Installment.query.get_or_404(installment_id)
    payment = InstallmentPayment.query.filter_by(id=payment_id, installment_id=installment.id).first_or_404()

    amount_raw = (request.form.get("amount") or "").strip()
    comment = (request.form.get("comment") or "").strip()

    try:
        new_amount = Decimal(amount_raw)
    except InvalidOperation:
        flash("Сумма должна быть числом", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    if new_amount <= 0:
        flash("Сумма должна быть больше нуля", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    old_amount = Decimal(payment.amount)
    account = payment.cash_account

    if account is None:
        flash("У платежа нет привязанной кассы", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    # === ПРОВЕРКА НА ПЕРЕПЛАТУ ===
    # 1. Вычисляем, какой будет долг, если мы применим новую сумму
    # Текущий paid_total включает старую сумму платежа
    temp_paid_total = installment.paid_total - old_amount + new_amount
    # Итоговая сумма к оплате с процентами (без учета предоплаты, так как она уже в paid_total)
    temp_debt_left = installment.total_with_percent - (temp_paid_total - Decimal(installment.prepayment))

    if temp_debt_left < 0:
        flash(f"Нельзя внести больше остатка. Максимальная сумма к оплате: ${installment.debt_left + old_amount}",
              "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment.id))

    # Если это предоплата — обновляем и ее
    is_prepayment = (payment.comment == "Предоплата")

    try:
        # 1. Находим транзакцию в кассе по payment.id
        tx = CashTransaction.query.filter_by(payment_id=payment.id).first()

        if tx:
            diff = new_amount - old_amount
            tx.amount = new_amount
            account.balance = Decimal(account.balance) + diff
        else:
            account.balance = Decimal(account.balance) - old_amount
            account.balance = Decimal(account.balance) + new_amount
            apply_transaction(
                account=account,
                type_="income",
                amount=new_amount,
                description=f"Платёж по рассрочке #{installment.id}",
                source_type="installment_payment",
                source_id=installment.id,
                payment_id=payment.id,
            )

        # 2. Обновляем сам платёж
        payment.amount = new_amount
        payment.comment = comment

        # 3. Если это была предоплата, обновляем поле в самой рассрочке
        if is_prepayment:
            installment.prepayment = new_amount

        # 4. Пересчитываем закрытие (temp_debt_left уже проверен выше)
        if temp_debt_left <= 0:
            installment.is_closed = True
        else:
            installment.is_closed = False

        db.session.commit()
        flash("Платёж обновлён, касса пересчитана", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка сохранения: {e}", "danger")

    return redirect(url_for("installments.installment_detail", installment_id=installment.id))


@installments_bp.route("/<int:installment_id>/contract")
@login_required
def contract(installment_id):
    """Просмотр договора рассрочки."""
    from datetime import datetime

    installment = Installment.query.get_or_404(installment_id)
    customer = installment.customer
    phone = installment.phone
    purchase = phone.purchase
    schedule = installment.payment_schedule

    # дата договора — сегодня
    today = datetime.utcnow()

    # первая и последняя даты платежей
    first_payment_date = schedule[0]["due_date"] if schedule else None
    last_payment_date = schedule[-1]["due_date"] if schedule else None

    # день месяца для оплаты — из salary_day клиента, если есть, иначе из первой даты
    if customer.salary_day:
        salary_day = customer.salary_day
    elif first_payment_date:
        salary_day = first_payment_date.day
    else:
        salary_day = ""

    return render_template(
        "installments/contract.html",
        installment=installment,
        customer=customer,
        phone=phone,
        purchase=purchase,
        today=today,
        today_str=today.strftime('%d.%m.%Y'),
        first_payment_date=first_payment_date,
        last_payment_date=last_payment_date,
        salary_day=salary_day,
        shop_name=current_app.config.get("SHOP_NAME", "22 Market Phone"),
        shop_phone=current_app.config.get("SHOP_PHONE", ""),
        shop_address=current_app.config.get("SHOP_ADDRESS", ""),
        shop_seller_name=current_app.config.get("ADMIN_FULL_NAME", "Владелец магазина"),
    )


@installments_bp.route("/<int:installment_id>/contract.docx")
@login_required
def contract_docx(installment_id):
    """Скачать договор в .docx."""
    installment = Installment.query.get_or_404(installment_id)
    customer = installment.customer
    phone = installment.phone
    schedule = installment.payment_schedule

    today = datetime.utcnow()
    today_str = today.strftime('%d.%m.%Y')

    first_payment_date = schedule[0]["due_date"] if schedule else None
    last_payment_date = schedule[-1]["due_date"] if schedule else None

    if customer.salary_day:
        salary_day = customer.salary_day
    elif first_payment_date:
        salary_day = first_payment_date.day
    else:
        salary_day = ""

    replacements = {
        "{customer_full_name}": customer.full_name or "",
        "{customer_address}": customer.address or "",
        "{customer_phone}": customer.phone or "",
        "{today_str}": today_str,
        "{phone_brand}": phone.brand or "",
        "{phone_model}": phone.model or "",
        "{phone_imei}": phone.imei or "",
        "{monthly_payment}": f"{installment.monthly_payment:,.0f}".replace(",", " "),
        "{salary_day}": str(salary_day),
        "{first_payment_date}": first_payment_date.strftime('%d.%m.%Y') if first_payment_date else "",
        "{last_payment_date}": last_payment_date.strftime('%d.%m.%Y') if last_payment_date else "",
        "{shop_phone}": current_app.config.get("SHOP_PHONE", ""),
        "{admin_full_name}": current_app.config.get("ADMIN_FULL_NAME", ""),
        "{has_box}": "bor" if phone.purchase.has_box else "yo‘q",
    }

    template_path = os.path.join(
        current_app.root_path, "static", "contracts", "example.docx"
    )

    if not os.path.exists(template_path):
        flash("Шаблон договора не найден (example.docx)", "danger")
        return redirect(url_for("installments.installment_detail", installment_id=installment_id))

    doc = Document(template_path)

    # замена в параграфах
    for paragraph in doc.paragraphs:
        _replace_in_paragraph(paragraph, replacements)

    # замена в таблицах
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _replace_in_paragraph(paragraph, replacements)

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    # безопасное имя файла
    safe_name = (customer.full_name or f"installment_{installment.id}").replace("/", "_").replace("\\", "_")
    filename = f"shartnoma_{installment.id}_{safe_name}.docx"

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


def _replace_in_paragraph(paragraph, replacements):
    """Заменяет текст в параграфе целиком, собирая все runs."""
    # собираем весь текст параграфа
    full_text = "".join(run.text for run in paragraph.runs)

    if not any(key in full_text for key in replacements):
        return

    new_text = full_text
    for key, val in replacements.items():
        new_text = new_text.replace(key, val)

    # пишем в первый run, остальные очищаем
    if paragraph.runs:
        paragraph.runs[0].text = new_text
        for run in paragraph.runs[1:]:
            run.text = ""


def _parse_start_date(raw):
    if not raw:
        return datetime.combine(
            datetime.utcnow().date(),
            datetime.min.time()
        )

    try:
        return datetime.combine(
            datetime.strptime(raw, "%Y-%m-%d").date(),
            datetime.min.time()
        )
    except ValueError:
        return None


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
        "started_at": _parse_start_date(val("started_at")),
        "started_at_raw": val("started_at") or datetime.utcnow().date().isoformat(),
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
    if form["started_at"] is None:
        errors.append("Выберите корректную дату начала рассрочки")
    return errors
