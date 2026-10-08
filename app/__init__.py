import os

from flask import Flask

from app.extensions import db, login_manager
from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)

    from app import models

    @login_manager.user_loader
    def load_user(user_id):
        return models.User.query.get(int(user_id))

    from app.routers.auth import auth_bp
    from app.routers.main import main_bp
    from app.routers.cash import cash_bp
    from app.routers.purchases import purchases_bp
    from app.routers.sales import sales_bp
    from app.routers.installments import installments_bp
    from app.routers.customers import customers_bp
    from app.routers.debtors import debtors_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(cash_bp)
    app.register_blueprint(purchases_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(installments_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(debtors_bp)

    with app.app_context():
        db.create_all()
        _bootstrap_admin(app)
        _bootstrap_cash_accounts(app)

    return app


def _bootstrap_admin(app):
    """Создаёт администратора, если база пустая."""
    from app import models

    if models.User.query.count() > 0:
        return

    admin = models.User(
        username=app.config["ADMIN_USERNAME"],
        full_name=app.config["ADMIN_FULL_NAME"],
        is_admin=True,
    )
    admin.set_password(app.config["ADMIN_PASSWORD"])

    db.session.add(admin)
    db.session.commit()


def _bootstrap_cash_accounts(app):
    """
    При первом запуске (пустая база) создаёт два дефолтных счёта:
    «Сейф USD» (id=1) и «Сейф UZS» (id=2).
    Если счета уже есть — ничего не делает.
    """
    from app import models
    from app.services.cash import create_account

    if models.CashAccount.query.count() > 0:
        return

    create_account(
        name="Сейф USD",
        currency=models.Currency.USD,
        initial_balance=0,
    )
    create_account(
        name="Сейф UZS",
        currency=models.Currency.UZS,
        initial_balance=0,
    )