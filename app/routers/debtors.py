from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import or_
from app.extensions import db
from app.models import Debtor, DebtorTransaction, Currency


debtors_bp = Blueprint("debtors", __name__, url_prefix="/debtors")


@debtors_bp.route("/")
@login_required
def list_debtors():
    """Список должников с поиском и сортировкой."""
    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "name_asc").strip()

    query = Debtor.query

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Debtor.full_name.ilike(like),
            Debtor.phone.ilike(like),
            Debtor.note.ilike(like),
        ))

    if sort == "date_desc":
        query = query.order_by(Debtor.loan_date.desc().nullslast())
    elif sort == "date_asc":
        query = query.order_by(Debtor.loan_date.asc().nullsfirst())
    else:
        query = query.order_by(Debtor.full_name.asc())

    debtors = query.all()

    return render_template(
        "debtors/list.html",
        debtors=debtors,
        filters={"q": q, "sort": sort},
    )


@debtors_bp.route("/new", methods=["GET", "POST"])
@login_required
def new_debtor():
    """Создание должника."""
    if request.method == "POST":
        form = _read_debtor_form(request.form)
        errors = _validate_debtor(form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("debtors/form.html", debtor=None, form_data=form)

        debtor = Debtor(
            full_name=form["full_name"],
            phone=form["phone"],
            loan_date=form["loan_date"],
            note=form["note"],
        )
        db.session.add(debtor)
        db.session.commit()

        flash(f"Должник «{debtor.full_name}» добавлен", "success")
        return redirect(url_for("debtors.debtor_detail", debtor_id=debtor.id))

    return render_template("debtors/form.html", debtor=None, form_data={})


@debtors_bp.route("/<int:debtor_id>")
@login_required
def debtor_detail(debtor_id):
    """Карточка должника: инфо, история, форма операции."""
    debtor = Debtor.query.get_or_404(debtor_id)
    transactions = debtor.transactions.limit(200).all()
    return render_template("debtors/detail.html", debtor=debtor, transactions=transactions)


@debtors_bp.route("/<int:debtor_id>/edit", methods=["GET", "POST"])
@login_required
def edit_debtor(debtor_id):
    """Редактирование данных должника."""
    debtor = Debtor.query.get_or_404(debtor_id)

    if request.method == "POST":
        form = _read_debtor_form(request.form)
        errors = _validate_debtor(form)

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("debtors/form.html", debtor=debtor, form_data=form)

        debtor.full_name = form["full_name"]
        debtor.phone = form["phone"]
        debtor.loan_date = form["loan_date"]
        debtor.note = form["note"]
        db.session.commit()

        flash("Данные обновлены", "success")
        return redirect(url_for("debtors.debtor_detail", debtor_id=debtor.id))

    form_data = {
        "full_name": debtor.full_name,
        "phone": debtor.phone or "",
        "loan_date": debtor.loan_date.strftime("%Y-%m-%d") if debtor.loan_date else "",
        "note": debtor.note or "",
    }
    return render_template("debtors/form.html", debtor=debtor, form_data=form_data)


@debtors_bp.route("/<int:debtor_id>/transaction", methods=["POST"])
@login_required
def add_transaction(debtor_id):
    """Добавить операцию: borrow (взять) или repay (вернуть)."""
    debtor = Debtor.query.get_or_404(debtor_id)

    type_ = (request.form.get("type") or "").strip()
    amount_raw = (request.form.get("amount") or "").strip()
    currency = (request.form.get("currency") or "").strip()
    comment = (request.form.get("comment") or "").strip()

    if type_ not in ("borrow", "repay"):
        flash("Выберите тип операции", "danger")
        return redirect(url_for("debtors.debtor_detail", debtor_id=debtor.id))

    if currency not in Currency.CHOICES:
        flash("Выберите валюту", "danger")
        return redirect(url_for("debtors.debtor_detail", debtor_id=debtor.id))

    try:
        amount = Decimal(amount_raw)
    except InvalidOperation:
        flash("Сумма должна быть числом", "danger")
        return redirect(url_for("debtors.debtor_detail", debtor_id=debtor.id))

    if amount <= 0:
        flash("Сумма должна быть больше нуля", "danger")
        return redirect(url_for("debtors.debtor_detail", debtor_id=debtor.id))

    if type_ == "repay":
        debt = debtor.debt_uzs if currency == Currency.UZS else debtor.debt_usd
        if amount > debt:
            if currency == Currency.USD:
                debt_str = f"$ {debt:,.0f}".replace(",", " ")
            else:
                debt_str = f"{debt:,.0f} сум".replace(",", " ")
            flash(
                f"Нельзя вернуть больше, чем должны. Текущий долг: {debt_str}. "
                f"Если хотите дать ещё в долг — создайте отдельную запись долга.",
                "danger",
            )
            return redirect(url_for("debtors.debtor_detail", debtor_id=debtor.id))

    tx = DebtorTransaction(
        debtor=debtor,
        type=type_,
        amount=amount,
        currency=currency,
        comment=comment,
        date=datetime.utcnow(),
    )
    db.session.add(tx)
    db.session.commit()

    flash("Операция добавлена", "success")
    return redirect(url_for("debtors.debtor_detail", debtor_id=debtor.id))


@debtors_bp.route("/<int:debtor_id>/delete", methods=["POST"])
@login_required
def delete_debtor(debtor_id):
    """Удалить должника вместе со всей историей."""
    debtor = Debtor.query.get_or_404(debtor_id)
    name = debtor.full_name
    db.session.delete(debtor)
    db.session.commit()
    flash(f"Должник «{name}» удалён", "info")
    return redirect(url_for("debtors.list_debtors"))


def _read_debtor_form(form):
    """Считать данные формы должника."""
    loan_date_raw = (form.get("loan_date") or "").strip()
    loan_date = None
    if loan_date_raw:
        try:
            loan_date = datetime.strptime(loan_date_raw, "%Y-%m-%d").date()
        except ValueError:
            loan_date = None

    return {
        "full_name": (form.get("full_name") or "").strip(),
        "phone": (form.get("phone") or "").strip(),
        "loan_date": loan_date,
        "note": (form.get("note") or "").strip(),
        "loan_date_raw": loan_date_raw,
    }


def _validate_debtor(form):
    """Проверка формы должника."""
    errors = []
    if not form["full_name"]:
        errors.append("Укажите ФИО")
    if form["loan_date_raw"] and form["loan_date"] is None:
        errors.append("Дата займа указана неверно (нужен формат ГГГГ-ММ-ДД)")
    return errors