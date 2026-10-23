from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.models import Customer


customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.route("/")
@login_required
def list_customers():
    """Список покупателей с поиском, фильтрами и сортировкой."""
    q = (request.args.get("q") or "").strip()
    registration = (request.args.get("registration") or "").strip()
    sort = (request.args.get("sort") or "name_asc").strip()

    query = Customer.query

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Customer.full_name.ilike(like),
            Customer.phone.ilike(like),
            Customer.phone_extra.ilike(like),
            Customer.passport.ilike(like),
            Customer.pinfl.ilike(like),
            Customer.address.ilike(like),
        ))

    if registration == "yes":
        query = query.filter(Customer.has_permanent_registration.is_(True))
    elif registration == "no":
        query = query.filter(Customer.has_permanent_registration.is_(False))

    if sort == "date_desc":
        query = query.order_by(Customer.registered_at.desc())
    elif sort == "date_asc":
        query = query.order_by(Customer.registered_at.asc())
    else:
        query = query.order_by(Customer.full_name.asc())

    customers = query.all()

    return render_template(
        "customers/list.html",
        customers=customers,
        filters={
            "q": q,
            "registration": registration,
            "sort": sort,
        },
    )


@customers_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_customer():
    """Создание покупателя."""
    next_url = request.values.get("next", "")

    if request.method == "POST":
        form = _read_form(request.form)
        errors = _validate(form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "customers/form.html",
                customer=None,
                form_data=form,
                next_url=next_url,
            )

        customer = Customer(
            full_name=form["full_name"],
            phone=form["phone"],
            phone_extra=form["phone_extra"],
            passport=form["passport"],
            pinfl=form["pinfl"],
            address=form["address"],
            has_permanent_registration=form["has_permanent_registration"],
            salary_day=form["salary_day"],
            note=form["note"],
            latitude=form["latitude"],
            longitude=form["longitude"],
        )
        db.session.add(customer)
        db.session.commit()

        flash(f"Покупатель «{customer.full_name}» добавлен", "success")

        # Если передан next — возвращаемся туда, иначе в карточку
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("customers.customer_detail", customer_id=customer.id))

    return render_template(
        "customers/form.html",
        customer=None,
        form_data={},
        next_url=next_url,
    )


@customers_bp.route("/<int:customer_id>")
@login_required
def customer_detail(customer_id):
    """Карточка покупателя."""
    customer = Customer.query.get_or_404(customer_id)
    installments = (
        customer.installments
        .order_by(db.desc("started_at"))
        .all()
    ) if hasattr(customer.installments, "order_by") else customer.installments.all()
    return render_template(
        "customers/detail.html",
        customer=customer,
        installments=installments,
    )


@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit_customer(customer_id):
    """Редактирование покупателя."""
    customer = Customer.query.get_or_404(customer_id)

    if request.method == "POST":
        form = _read_form(request.form)
        errors = _validate(form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template(
                "customers/form.html",
                customer=customer,
                form_data=form,
                next_url="",
            )

        customer.full_name = form["full_name"]
        customer.phone = form["phone"]
        customer.phone_extra = form["phone_extra"]
        customer.passport = form["passport"]
        customer.pinfl = form["pinfl"]
        customer.address = form["address"]
        customer.has_permanent_registration = form["has_permanent_registration"]
        customer.salary_day = form["salary_day"]
        customer.note = form["note"]
        customer.latitude = form["latitude"]
        customer.longitude = form["longitude"]
        db.session.commit()

        flash("Данные обновлены", "success")
        return redirect(url_for("customers.customer_detail", customer_id=customer.id))

    form_data = {
        "full_name": customer.full_name or "",
        "phone": customer.phone or "",
        "phone_extra": customer.phone_extra or "",
        "passport": customer.passport or "",
        "pinfl": customer.pinfl or "",
        "address": customer.address or "",
        "has_permanent_registration": customer.has_permanent_registration,
        "salary_day": customer.salary_day,
        "note": customer.note or "",
        "latitude": customer.latitude,
        "longitude": customer.longitude,
    }
    return render_template(
        "customers/form.html",
        customer=customer,
        form_data=form_data,
        next_url="",
    )

@customers_bp.route("/<int:customer_id>/delete", methods=["POST"])
@login_required
def delete_customer(customer_id):
    """Удалить покупателя. Только если у него нет рассрочек."""
    customer = Customer.query.get_or_404(customer_id)

    # проверка — есть ли рассрочки
    if customer.installments.count() > 0:
        flash(
            "Нельзя удалить: у покупателя есть рассрочки. Сначала удалите их.",
            "danger",
        )
        return redirect(url_for("customers.customer_detail", customer_id=customer.id))

    name = customer.full_name
    db.session.delete(customer)
    db.session.commit()

    flash(f"Покупатель «{name}» удалён", "info")
    return redirect(url_for("customers.list_customers"))

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
            return None
        try:
            return Decimal(raw)
        except InvalidOperation:
            return None

    return {
        "full_name": val("full_name"),
        "phone": val("phone"),
        "phone_extra": val("phone_extra"),
        "passport": val("passport"),
        "pinfl": val("pinfl"),
        "address": val("address"),
        "has_permanent_registration": val("has_permanent_registration") == "on",
        "salary_day": to_int("salary_day"),
        "note": val("note"),
        "latitude": to_decimal("latitude"),
        "longitude": to_decimal("longitude"),
    }


def _validate(form):
    """Проверка формы."""
    errors = []
    if not form["full_name"]:
        errors.append("Укажите ФИО")
    if not form["phone"]:
        errors.append("Укажите телефон")

    if form["salary_day"] is not None:
        if form["salary_day"] < 0 or form["salary_day"] > 31:
            errors.append("День оплаты должен быть от 0 до 31")

    return errors