from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import Phone, Sale, CashAccount, Currency, CashTransaction
from app.services.cash import apply_transaction

sales_bp = Blueprint("sales", __name__, url_prefix="/sales")


@sales_bp.route("/")
@login_required
def list_sales():
    """Список продаж с поиском, фильтрами и сортировкой."""
    q = (request.args.get("q") or "").strip()
    currency = (request.args.get("currency") or "").strip()
    account_id = (request.args.get("account_id") or "").strip()
    sort = (request.args.get("sort") or "date_desc").strip()

    query = Sale.query.join(Phone, Sale.phone_id == Phone.id)

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Phone.brand.ilike(like),
            Phone.model.ilike(like),
            Phone.imei.ilike(like),
            Sale.client_name.ilike(like),
            Sale.client_contact.ilike(like),
        ))

    if currency in Currency.CHOICES:
        query = query.filter(Sale.currency == currency)

    if account_id.isdigit():
        query = query.filter(Sale.cash_account_id == int(account_id))

    if sort == "price_asc":
        query = query.order_by(Sale.price.asc())
    elif sort == "price_desc":
        query = query.order_by(Sale.price.desc())
    else:
        query = query.order_by(Sale.sold_at.desc())

    sales = query.all()

    accounts = CashAccount.query.order_by(CashAccount.name).all()

    return render_template(
        "sales/list.html",
        sales=sales,
        accounts=accounts,
        filters={
            "q": q,
            "currency": currency,
            "account_id": account_id,
            "sort": sort,
        },
    )


@sales_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_sale():
    """Форма простой продажи. Всегда USD, касса — первая USD."""
    phones = (
        Phone.query
        .filter_by(status="in_stock")
        .join(Phone.purchase)
        .order_by(Phone.id.desc())
        .all()
    )

    # дефолтная USD-касса — первая по id
    default_account = (
        CashAccount.query
        .filter_by(currency=Currency.USD)
        .order_by(CashAccount.id)
        .first()
    )

    preselected_phone_id = request.args.get("phone_id", type=int)

    if request.method == "POST":
        form = _read_form(request.form)
        errors = _validate(form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "sales/form.html",
                phones=phones,
                form_data=form,
            )

        phone = Phone.query.get(form["phone_id"])
        if phone is None or phone.status != "in_stock":
            flash("Телефон не найден или уже продан", "danger")
            return render_template(
                "sales/form.html",
                phones=phones,
                form_data=form,
            )

        if default_account is None:
            flash("Нет USD-кассы. Создайте счёт в разделе «Касса».", "danger")
            return render_template(
                "sales/form.html",
                phones=phones,
                form_data=form,
            )

        account = default_account

        try:
            sale = Sale(
                phone_id=phone.id,
                client_name=form["client_name"],
                client_contact=form["client_contact"],
                price=form["price"],
                currency=Currency.USD,
                cash_account_id=account.id,
            )
            db.session.add(sale)
            db.session.flush()

            phone.status = "sold"

            apply_transaction(
                account=account,
                type_="income",
                amount=form["price"],
                description=f"Продажа: {phone.brand} {phone.model}",
                source_type="sale",
                source_id=sale.id,
            )

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка сохранения: {e}", "danger")
            return render_template(
                "sales/form.html",
                phones=phones,
                form_data=form,
            )

        flash("Продажа оформлена", "success")
        return redirect(url_for("sales.sale_detail", sale_id=sale.id))

    form_data = {}
    if preselected_phone_id:
        form_data["phone_id"] = preselected_phone_id

    return render_template(
        "sales/form.html",
        phones=phones,
        form_data=form_data,
    )


@sales_bp.route("/<int:sale_id>")
@login_required
def sale_detail(sale_id):
    """Детальная страница продажи."""
    sale = Sale.query.get_or_404(sale_id)
    return render_template("sales/detail.html", sale=sale)


@sales_bp.route("/<int:sale_id>/edit", methods=["GET", "POST"])
@login_required
def sale_edit(sale_id):
    """Редактирование продажи: клиент, контакт, цена (с пересчетом кассы)."""
    from app.models import CashTransaction

    sale = Sale.query.get_or_404(sale_id)

    if request.method == "POST":
        form = _read_form(request.form)

        errors = []
        if form["price"] is None or form["price"] <= 0:
            errors.append("Цена должна быть числом больше нуля")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("sales/edit.html", sale=sale, form_data=form)

        new_price = form["price"]
        old_price = Decimal(sale.price)

        # Если цена изменилась — пересчитываем кассу
        if new_price != old_price:
            account = sale.cash_account
            if account is None:
                flash("У продажи нет кассы — цена не может быть изменена", "danger")
                return redirect(url_for("sales.sale_detail", sale_id=sale.id))

            try:
                # Находим транзакцию по продаже
                tx = CashTransaction.query.filter_by(
                    source_type="sale",
                    source_id=sale.id,
                ).first()

                if tx:
                    diff = new_price - old_price
                    tx.amount = new_price
                    account.balance = Decimal(account.balance) + diff
                else:
                    # Если транзакции нет (старые данные) — создаём новую,
                    # apply_transaction сам зачислит сумму на баланс.
                    apply_transaction(
                        account=account,
                        type_="income",
                        amount=new_price,
                        description=f"Продажа: {sale.phone.brand} {sale.phone.model}",
                        source_type="sale",
                        source_id=sale.id,
                    )

                # Обновляем цену и данные клиента в самой продаже
                sale.price = new_price
                sale.client_name = form["client_name"]
                sale.client_contact = form["client_contact"]

                db.session.commit()
                flash("Продажа обновлена, касса пересчитана", "success")
                return redirect(url_for("sales.sale_detail", sale_id=sale.id))
            except Exception as e:
                db.session.rollback()
                flash(f"Ошибка сохранения: {e}", "danger")
                return redirect(url_for("sales.sale_detail", sale_id=sale.id))
        else:
            # Если цена не менялась, просто обновляем текстовые поля
            sale.client_name = form["client_name"]
            sale.client_contact = form["client_contact"]
            db.session.commit()
            flash("Данные обновлены", "success")
            return redirect(url_for("sales.sale_detail", sale_id=sale.id))

    # GET — заполняем форму
    form_data = {
        "client_name": sale.client_name or "",
        "client_contact": sale.client_contact or "",
        "price": sale.price,
        "price_raw": f"{Decimal(sale.price):.0f}",
    }
    return render_template("sales/edit.html", sale=sale, form_data=form_data)


@sales_bp.route("/<int:sale_id>/price", methods=["POST"])
@login_required
def sale_price(sale_id):
    """Изменение цены продажи. Пересоздаёт кассовую транзакцию."""
    sale = Sale.query.get_or_404(sale_id)

    price_raw = (request.form.get("new_price") or "").strip()
    try:
        new_price = Decimal(price_raw)
    except InvalidOperation:
        flash("Цена должна быть числом", "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale.id))

    if new_price <= 0:
        flash("Цена должна быть больше нуля", "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale.id))

    account = sale.cash_account
    if account is None:
        flash("У продажи нет кассы — цена не может быть изменена", "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale.id))

    try:
        # откат старой транзакции
        old_tx = CashTransaction.query.filter_by(
            source_type="sale",
            source_id=sale.id,
        ).first()

        if old_tx:
            if old_tx.type == "income":
                account.balance = Decimal(account.balance) - Decimal(old_tx.amount)
            else:
                account.balance = Decimal(account.balance) + Decimal(old_tx.amount)
            tx_date = old_tx.created_at
            db.session.delete(old_tx)
        else:
            tx_date = sale.sold_at or datetime.utcnow()

        # обновляем цену
        sale.price = new_price

        # новая транзакция
        new_tx = apply_transaction(
            account=account,
            type_="income",
            amount=new_price,
            description=f"Продажа: {sale.phone.brand} {sale.phone.model}",
            source_type="sale",
            source_id=sale.id,
        )
        new_tx.created_at = tx_date

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка сохранения: {e}", "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale.id))

    flash("Цена обновлена, касса пересчитана", "success")
    return redirect(url_for("sales.sale_detail", sale_id=sale.id))


@sales_bp.route("/<int:sale_id>/delete", methods=["POST"])
@login_required
def sale_delete(sale_id):
    """Удалить продажу: вернуть телефон в наличие, откатить доход из кассы."""
    sale = Sale.query.get_or_404(sale_id)
    phone = sale.phone
    account = sale.cash_account

    try:
        if account:
            apply_transaction(
                account=account,
                type_="expense",
                amount=sale.price,
                description=f"Отмена продажи: {phone.brand} {phone.model}",
                source_type="sale_cancel",
                source_id=sale.id,
            )

        if phone:
            phone.status = "in_stock"

        db.session.delete(sale)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Не удалось удалить: {e}", "danger")
        return redirect(url_for("sales.sale_detail", sale_id=sale.id))

    flash("Продажа отменена, телефон возвращён в наличие", "info")
    return redirect(url_for("sales.list_sales"))


@sales_bp.route("/summary/")
@login_required
def summary():
    """Сводка по простым продажам."""
    from datetime import datetime, timedelta
    from decimal import Decimal

    # 1. Получаем параметры фильтров
    q = (request.args.get("q") or "").strip()
    date_from_raw = (request.args.get("from") or "").strip()
    date_to_raw = (request.args.get("to") or "").strip()

    # 2. Дефолтные даты (текущий сезон)
    today = datetime.utcnow().date()
    year = today.year
    month = today.month

    if 6 <= month <= 8:  # Лето
        default_from = datetime(year, 6, 1).date()
        default_to = datetime(year, 8, 31).date()
    elif 9 <= month <= 11:  # Осень
        default_from = datetime(year, 9, 1).date()
        default_to = datetime(year, 11, 30).date()
    elif month == 12:  # Зима (начало)
        default_from = datetime(year, 12, 1).date()
        default_to = datetime(year + 1, 2, 28).date()
    elif month in (1, 2):  # Зима (конец)
        default_from = datetime(year - 1, 12, 1).date()
        default_to = datetime(year, 2, 28).date()
    else:  # Весна (3, 4, 5)
        default_from = datetime(year, 3, 1).date()
        default_to = datetime(year, 5, 31).date()

    try:
        date_from = datetime.strptime(date_from_raw, "%Y-%m-%d").date() if date_from_raw else default_from
    except ValueError:
        date_from = default_from

    try:
        date_to = datetime.strptime(date_to_raw, "%Y-%m-%d").date() if date_to_raw else default_to
    except ValueError:
        date_to = default_to

    # Конец дня
    date_to_end = datetime.combine(date_to, datetime.max.time())

    # 3. Строим запрос
    query = Sale.query.join(Phone, Sale.phone_id == Phone.id)

    # Фильтр по датам
    query = query.filter(Sale.sold_at >= datetime.combine(date_from, datetime.min.time()))
    query = query.filter(Sale.sold_at <= date_to_end)

    # Поиск
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Phone.brand.ilike(like),
            Phone.model.ilike(like),
            Phone.imei.ilike(like),
            Sale.client_name.ilike(like),
            Sale.client_contact.ilike(like),
        ))

    # Сортировка (новые сначала)
    sales = query.order_by(Sale.sold_at.desc()).all()

    # 4. Считаем статистику
    total_sales_usd = Decimal("0")
    total_margin_usd = Decimal("0")
    total_purchase_usd = Decimal("0")  # <--- Новая переменная
    sales_count = len(sales)

    for s in sales:
        total_sales_usd += Decimal(s.price)

        # Считаем закупку и наценку
        purchase = s.phone.purchase if s.phone else None
        if purchase:
            total_purchase_usd += Decimal(purchase.price)  # <--- Суммируем закупку
            if s.currency == purchase.currency:
                margin = Decimal(s.price) - Decimal(purchase.price)
                total_margin_usd += margin

    return render_template(
        "sales/summary.html",
        sales=sales,
        q=q,
        date_from=date_from,
        date_to=date_to,
        total_sales_usd=total_sales_usd,
        total_margin_usd=total_margin_usd,
        total_purchase_usd=total_purchase_usd, # <--- Добавить
        sales_count=sales_count,
    )


def _read_form(form):
    """Считать данные формы."""

    def val(key, default=""):
        return (form.get(key) or default).strip()

    price_raw = val("price")
    try:
        price = Decimal(price_raw) if price_raw else None
    except InvalidOperation:
        price = None

    def to_int(key):
        raw = val(key)
        try:
            return int(raw) if raw else None
        except ValueError:
            return None

    return {
        "phone_id": to_int("phone_id"),
        "client_name": val("client_name"),
        "client_contact": val("client_contact"),
        "price": price,
        "price_raw": price_raw,
        "currency": val("currency") or Currency.USD,
        "cash_account_id": to_int("cash_account_id"),
    }


def _validate(form):
    """Проверка формы."""
    errors = []

    if form["phone_id"] is None:
        errors.append("Выберите телефон")
    if form["price"] is None or form["price"] <= 0:
        errors.append("Цена должна быть числом больше нуля")

    return errors
