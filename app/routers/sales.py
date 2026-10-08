from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import Phone, Sale, CashAccount, Currency
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
    """Форма простой продажи."""
    phones = (
        Phone.query
        .filter_by(status="in_stock")
        .join(Phone.purchase)
        .order_by(Phone.id.desc())
        .all()
    )
    accounts = CashAccount.query.order_by(CashAccount.currency, CashAccount.name).all()

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
                accounts=accounts,
                form_data=form,
            )

        phone = Phone.query.get(form["phone_id"])
        if phone is None or phone.status != "in_stock":
            flash("Телефон не найден или уже продан", "danger")
            return render_template(
                "sales/form.html",
                phones=phones,
                accounts=accounts,
                form_data=form,
            )

        account = CashAccount.query.get(form["cash_account_id"])
        if account is None:
            flash("Касса не найдена", "danger")
            return render_template(
                "sales/form.html",
                phones=phones,
                accounts=accounts,
                form_data=form,
            )

        try:
            sale = Sale(
                phone_id=phone.id,
                client_name=form["client_name"],
                client_contact=form["client_contact"],
                price=form["price"],
                currency=form["currency"],
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
                accounts=accounts,
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
        accounts=accounts,
        form_data=form_data,
    )


@sales_bp.route("/<int:sale_id>")
@login_required
def sale_detail(sale_id):
    """Детальная страница продажи."""
    sale = Sale.query.get_or_404(sale_id)
    return render_template("sales/detail.html", sale=sale)


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
        "currency": val("currency"),
        "cash_account_id": to_int("cash_account_id"),
    }


def _validate(form):
    """Проверка формы."""
    errors = []

    if form["phone_id"] is None:
        errors.append("Выберите телефон")
    if form["price"] is None or form["price"] <= 0:
        errors.append("Цена должна быть числом больше нуля")
    if form["currency"] not in Currency.CHOICES:
        errors.append("Выберите валюту продажи")
    if form["cash_account_id"] is None:
        errors.append("Выберите кассу")

    return errors