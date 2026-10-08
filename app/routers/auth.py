from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user

from app.models import User


auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Страница входа.
    Если пользователь уже авторизован — сразу редиректим на главную.
    """
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    error = None
    username = ""

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            error = "Введите логин и пароль"
        else:
            user = User.query.filter_by(username=username).first()

            if user is None or not user.check_password(password):
                error = "Неверный логин или пароль"
            else:
                login_user(user)
                flash(f"Добро пожаловать, {user.full_name or user.username}!", "success")

                next_page = request.args.get("next")
                if next_page and next_page.startswith("/"):
                    return redirect(next_page)
                return redirect(url_for("main.index"))

    return render_template("auth/login.html", error=error, username=username)


@auth_bp.route("/logout")
@login_required
def logout():
    """Выход из системы."""
    logout_user()
    flash("Вы вышли из системы", "info")
    return redirect(url_for("auth.login"))