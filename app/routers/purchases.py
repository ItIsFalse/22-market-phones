from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import PhonePurchase, Phone, CashAccount, Currency
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
    """Форма закупки телефона."""
    accounts = CashAccount.query.order_by(CashAccount.currency, CashAccount.name).all()

    default_usd_id = 1
    default_uzs_id = 2

    if request.method == "POST":
        form = _read_form(request.form)
        errors = _validate(form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "purchases/form.html",
                accounts=accounts,
                default_usd_id=default_usd_id,
                default_uzs_id=default_uzs_id,
                form_data=form,
            )

        account = CashAccount.query.get(form["cash_account_id"])
        if account is None:
            flash("Касса не найдена", "danger")
            return render_template(
                "purchases/form.html",
                accounts=accounts,
                default_usd_id=default_usd_id,
                default_uzs_id=default_uzs_id,
                form_data=form,
            )

        if account.currency != form["currency"]:
            flash(
                f"Валюта кассы ({account.currency}) не совпадает с валютой закупки ({form['currency']})",
                "danger",
            )
            return render_template(
                "purchases/form.html",
                accounts=accounts,
                default_usd_id=default_usd_id,
                default_uzs_id=default_uzs_id,
                form_data=form,
            )

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
                currency=form["currency"],
                note=form["note"],
                cash_account_id=account.id,
            )
            db.session.add(purchase)
            db.session.flush()

            phone = Phone(purchase=purchase, status="in_stock")
            db.session.add(phone)

            apply_transaction(
                account=account,
                type_="expense",
                amount=form["price"],
                description=f"Закупка: {form['brand']} {form['model']}",
                source_type="purchase",
                source_id=purchase.id,
            )

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка сохранения: {e}", "danger")
            return render_template(
                "purchases/form.html",
                accounts=accounts,
                default_usd_id=default_usd_id,
                default_uzs_id=default_uzs_id,
                form_data=form,
            )

        flash("Закупка сохранена", "success")
        return redirect(url_for("purchases.list_purchases"))

    return render_template(
        "purchases/form.html",
        accounts=accounts,
        default_usd_id=default_usd_id,
        default_uzs_id=default_uzs_id,
        form_data={},
    )


@purchases_bp.route("/<int:purchase_id>")
@login_required
def purchase_detail(purchase_id):
    """Детальная страница закупки/телефона."""
    purchase = PhonePurchase.query.get_or_404(purchase_id)
    return render_template("purchases/detail.html", purchase=purchase)


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
        "currency": val("currency"),
        "note": val("note"),
        "cash_account_id": cash_account_id,
        "cash_account_id_raw": cash_account_id_raw,
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
    if form["currency"] not in Currency.CHOICES:
        errors.append("Выберите валюту")
    if form["cash_account_id"] is None:
        errors.append("Выберите кассу")

    if form["imei"]:
        existing = PhonePurchase.query.filter_by(imei=form["imei"]).first()
        if existing:
            errors.append(f"IMEI {form['imei']} уже есть в базе")

    return errors