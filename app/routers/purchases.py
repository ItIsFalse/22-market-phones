from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import PhonePurchase, Phone, CashAccount, Currency, CashTransaction
from app.services.cash import apply_transaction


purchases_bp = Blueprint("purchases", __name__, url_prefix="/purchases")


PRESET_BRANDS = ["Apple", "Samsung", "Xiaomi", "Huawei", "Oppo"]
PRESET_STORAGE = ["16", "32", "64", "128", "256", "512", "1024"]


@purchases_bp.route("/")
@login_required
def list_purchases():
    """Список закупок в наличии с поиском, фильтрами и сортировкой."""
    q = (request.args.get("q") or "").strip()
    brand = (request.args.get("brand") or "").strip()
    color = (request.args.get("color") or "").strip()
    storage = (request.args.get("storage") or "").strip()
    battery = (request.args.get("battery") or "").strip()
    has_box = (request.args.get("has_box") or "").strip()
    sort = (request.args.get("sort") or "date_desc").strip()

    query = (
        PhonePurchase.query
        .join(Phone, Phone.purchase_id == PhonePurchase.id)
        .filter(Phone.status == "in_stock")
    )

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            PhonePurchase.brand.ilike(like),
            PhonePurchase.model.ilike(like),
            PhonePurchase.color.ilike(like),
            PhonePurchase.storage.ilike(like),
            PhonePurchase.imei.ilike(like),
            PhonePurchase.client_name.ilike(like),
            PhonePurchase.client_contact.ilike(like),
        ))

    if brand:
        query = query.filter(PhonePurchase.brand.ilike(brand))

    if color:
        query = query.filter(PhonePurchase.color.ilike(f"%{color}%"))

    if storage:
        query = query.filter(PhonePurchase.storage == storage)

    if battery:
        query = query.filter(PhonePurchase.battery.ilike(f"%{battery}%"))

    if has_box == "1":
        query = query.filter(PhonePurchase.has_box.is_(True))
    elif has_box == "0":
        query = query.filter(PhonePurchase.has_box.is_(False))

    if sort == "price_asc":
        query = query.order_by(PhonePurchase.price.asc())
    elif sort == "price_desc":
        query = query.order_by(PhonePurchase.price.desc())
    else:
        query = query.order_by(PhonePurchase.created_at.desc())

    purchases = query.all()

    db_brands = [
        b[0] for b in
        PhonePurchase.query
        .join(Phone, Phone.purchase_id == PhonePurchase.id)
        .filter(Phone.status == "in_stock")
        .with_entities(PhonePurchase.brand)
        .distinct()
        .order_by(PhonePurchase.brand)
        .all()
        if b[0]
    ]

    brand_options = []
    for b in PRESET_BRANDS + db_brands:
        if b and b not in brand_options:
            brand_options.append(b)

    return render_template(
        "purchases/list.html",
        purchases=purchases,
        brand_options=brand_options,
        storage_options=PRESET_STORAGE,
        filters={
            "q": q,
            "brand": brand,
            "color": color,
            "storage": storage,
            "battery": battery,
            "has_box": has_box,
            "sort": sort,
        },
    )


@purchases_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_purchase():
    """Форма закупки телефона. Валюта всегда USD."""
    accounts = (
        CashAccount.query
        .filter_by(currency=Currency.USD)
        .order_by(CashAccount.id)
        .all()
    )
    default_account_id = accounts[0].id if accounts else None
    today_str = datetime.utcnow().strftime("%Y-%m-%d")

    if request.method == "POST":
        form = _read_form(request.form)
        errors = _validate(form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "purchases/form.html",
                accounts=accounts,
                form_data=form,
                today_str=today_str,
                default_account_id=default_account_id,
            )

        account = CashAccount.query.get(form["cash_account_id"])
        if account is None or account.currency != Currency.USD:
            flash("Выберите USD-кассу", "danger")
            return render_template(
                "purchases/form.html",
                accounts=accounts,
                form_data=form,
                today_str=today_str,
                default_account_id=default_account_id,
            )

        purchased_at_raw = form["purchased_at_raw"]
        if purchased_at_raw:
            try:
                purchased_at = datetime.strptime(purchased_at_raw, "%Y-%m-%d")
            except ValueError:
                purchased_at = datetime.utcnow()
        else:
            purchased_at = datetime.utcnow()

        try:
            purchase = PhonePurchase(
                client_name=form["client_name"],
                client_contact=form["client_contact"],
                brand=form["brand"],
                model=form["model"],
                color=form["color"],
                storage=form["storage"],
                battery=form["battery"],
                imei=form["imei"] or None,
                has_box=form["has_box"],
                price=form["price"],
                currency=Currency.USD,
                note=form["note"],
                cash_account_id=account.id,
                created_at=purchased_at,
            )
            db.session.add(purchase)
            db.session.flush()

            phone = Phone(purchase=purchase, status="in_stock")
            db.session.add(phone)

            tx = apply_transaction(
                account=account,
                type_="expense",
                amount=form["price"],
                description=f"Закупка: {form['brand']} {form['model']}",
                source_type="purchase",
                source_id=purchase.id,
            )
            tx.created_at = purchased_at

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка сохранения: {e}", "danger")
            return render_template(
                "purchases/form.html",
                accounts=accounts,
                form_data=form,
                today_str=today_str,
                default_account_id=default_account_id,
            )

        flash("Закупка сохранена", "success")
        return redirect(url_for("purchases.list_purchases"))

    return render_template(
        "purchases/form.html",
        accounts=accounts,
        form_data={},
        today_str=today_str,
        default_account_id=default_account_id,
    )


@purchases_bp.route("/<int:purchase_id>")
@login_required
def purchase_detail(purchase_id):
    """Детальная страница закупки/телефона."""
    purchase = PhonePurchase.query.get_or_404(purchase_id)
    return render_template("purchases/detail.html", purchase=purchase)


@purchases_bp.route("/<int:purchase_id>/edit", methods=["GET", "POST"])
@login_required
def purchase_edit(purchase_id):
    """Редактирование закупки. Без цены, кассы, валюты, даты."""
    purchase = PhonePurchase.query.get_or_404(purchase_id)
    phone = purchase.phone

    if phone and phone.status != "in_stock":
        flash(
            "Телефон уже продан или в рассрочке. Сначала удалите продажу / рассрочку.",
            "danger",
        )
        return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))

    if request.method == "POST":
        form = _read_form(request.form)
        errors = []

        if not form["brand"]:
            errors.append("Укажите бренд")
        if not form["model"]:
            errors.append("Укажите модель")

        # проверка уникальности IMEI, исключая текущую закупку
        if form["imei"]:
            existing = PhonePurchase.query.filter(
                PhonePurchase.imei == form["imei"],
                PhonePurchase.id != purchase.id,
            ).first()
            if existing:
                errors.append(f"IMEI {form['imei']} уже есть в другой закупке")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "purchases/edit.html",
                purchase=purchase,
                form_data=form,
            )

        purchase.client_name = form["client_name"]
        purchase.client_contact = form["client_contact"]
        purchase.brand = form["brand"]
        purchase.model = form["model"]
        purchase.color = form["color"]
        purchase.storage = form["storage"]
        purchase.battery = form["battery"]
        purchase.imei = form["imei"] or None
        purchase.has_box = form["has_box"]
        purchase.note = form["note"]

        db.session.commit()

        flash("Закупка обновлена", "success")
        return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))

    form_data = {
        "client_name": purchase.client_name or "",
        "client_contact": purchase.client_contact or "",
        "brand": purchase.brand or "",
        "model": purchase.model or "",
        "color": purchase.color or "",
        "storage": purchase.storage or "",
        "battery": purchase.battery or "",
        "imei": purchase.imei or "",
        "has_box": purchase.has_box,
        "note": purchase.note or "",
    }
    return render_template(
        "purchases/edit.html",
        purchase=purchase,
        form_data=form_data,
    )


@purchases_bp.route("/<int:purchase_id>/price", methods=["POST"])
@login_required
def purchase_price(purchase_id):
    """Изменение цены закупки. Пересоздаёт кассовую транзакцию."""
    purchase = PhonePurchase.query.get_or_404(purchase_id)
    phone = purchase.phone

    if phone and phone.status != "in_stock":
        flash(
            "Телефон уже продан или в рассрочке. Сначала удалите продажу / рассрочку.",
            "danger",
        )
        return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))

    price_raw = (request.form.get("new_price") or "").strip()
    try:
        new_price = Decimal(price_raw)
    except InvalidOperation:
        flash("Цена должна быть числом", "danger")
        return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))

    if new_price <= 0:
        flash("Цена должна быть больше нуля", "danger")
        return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))

    account = purchase.cash_account
    if account is None:
        flash("У закупки нет кассы — цена не может быть изменена", "danger")
        return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))

    try:
        # 1. откат старой транзакции
        old_tx = CashTransaction.query.filter_by(
            source_type="purchase",
            source_id=purchase.id,
        ).first()

        if old_tx:
            if old_tx.type == "expense":
                account.balance = Decimal(account.balance) + Decimal(old_tx.amount)
            else:
                account.balance = Decimal(account.balance) - Decimal(old_tx.amount)
            tx_date = old_tx.created_at
            db.session.delete(old_tx)
        else:
            tx_date = purchase.created_at or datetime.utcnow()

        # 2. обновляем цену
        purchase.price = new_price

        # 3. создаём новую транзакцию
        new_tx = apply_transaction(
            account=account,
            type_="expense",
            amount=new_price,
            description=f"Закупка: {purchase.brand} {purchase.model}",
            source_type="purchase",
            source_id=purchase.id,
        )
        new_tx.created_at = tx_date

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка сохранения: {e}", "danger")
        return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))

    flash("Цена обновлена, касса пересчитана", "success")
    return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))


@purchases_bp.route("/<int:purchase_id>/delete", methods=["POST"])
@login_required
def purchase_delete(purchase_id):
    """Удаление закупки. Только если телефон в наличии."""
    purchase = PhonePurchase.query.get_or_404(purchase_id)
    phone = purchase.phone

    if phone and phone.status != "in_stock":
        flash("Нельзя удалить: телефон продан или в рассрочке", "danger")
        return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))

    account = purchase.cash_account

    try:
        old_tx = CashTransaction.query.filter_by(
            source_type="purchase",
            source_id=purchase.id,
        ).first()

        if old_tx and account:
            if old_tx.type == "expense":
                account.balance = Decimal(account.balance) + Decimal(old_tx.amount)
            else:
                account.balance = Decimal(account.balance) - Decimal(old_tx.amount)
            db.session.delete(old_tx)

        if phone:
            db.session.delete(phone)
        db.session.delete(purchase)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка удаления: {e}", "danger")
        return redirect(url_for("purchases.purchase_detail", purchase_id=purchase.id))

    flash(f"Закупка «{purchase.brand} {purchase.model}» удалена", "info")
    return redirect(url_for("purchases.list_purchases"))


def _read_form(form):
    """Считать данные формы в обычный dict."""
    def val(key, default=""):
        return (form.get(key) or default).strip()

    price_raw = val("price")
    try:
        price = Decimal(price_raw) if price_raw else Decimal("0")
    except InvalidOperation:
        price = None

    cash_account_id_raw = val("cash_account_id")
    try:
        cash_account_id = int(cash_account_id_raw) if cash_account_id_raw else None
    except ValueError:
        cash_account_id = None

    return {
        "client_name": val("client_name"),
        "client_contact": val("client_contact"),
        "brand": val("brand"),
        "model": val("model"),
        "color": val("color"),
        "storage": val("storage"),
        "battery": val("battery"),
        "imei": val("imei"),
        "has_box": val("has_box") == "on",
        "price": price,
        "price_raw": price_raw,
        "currency": Currency.USD,
        "note": val("note"),
        "cash_account_id": cash_account_id,
        "cash_account_id_raw": cash_account_id_raw,
        "purchased_at_raw": val("purchased_at"),
    }


def _validate(form):
    """Проверка данных формы. Возвращает список ошибок."""
    errors = []

    if not form["brand"]:
        errors.append("Укажите бренд")
    if not form["model"]:
        errors.append("Укажите модель")
    if form["price"] is None or form["price"] <= 0:
        errors.append("Цена должна быть числом больше нуля")
    if form["cash_account_id"] is None:
        errors.append("Выберите кассу")

    if form["imei"]:
        existing = PhonePurchase.query.filter_by(imei=form["imei"]).first()
        if existing:
            errors.append(f"IMEI {form['imei']} уже есть в базе")

    return errors