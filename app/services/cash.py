from decimal import Decimal

from app.extensions import db
from app.models import CashAccount, CashTransaction, Currency


def create_account(name, currency, initial_balance=0):
    """
    Создать новый счёт.
    При ненулевом начальном балансе сразу делаем приходную транзакцию,
    чтобы история была честной.
    """
    if currency not in Currency.CHOICES:
        raise ValueError(f"Неизвестная валюта: {currency}")

    account = CashAccount(
        name=name.strip(),
        currency=currency,
        balance=Decimal("0"),
    )
    db.session.add(account)
    db.session.flush()

    if initial_balance and Decimal(str(initial_balance)) != 0:
        apply_transaction(
            account=account,
            type_="income",
            amount=initial_balance,
            description="Начальный баланс",
            source_type="manual",
        )

    db.session.commit()
    return account


def apply_transaction(account, type_, amount, description="", source_type="manual", source_id=None, payment_id=None):
    """
    Провести операцию по счёту.
    type_ — 'income' или 'expense'.
    Баланс может уйти в минус — это допустимо.
    """
    if type_ not in ("income", "expense"):
        raise ValueError("type_ должен быть 'income' или 'expense'")

    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValueError("Сумма должна быть больше нуля")

    if type_ == "income":
        account.balance = Decimal(account.balance) + amount
    else:
        account.balance = Decimal(account.balance) - amount

    tx = CashTransaction(
        account=account,
        type=type_,
        amount=amount,
        currency=account.currency,
        description=description.strip() if description else "",
        source_type=source_type,
        source_id=source_id,
        payment_id=payment_id,
    )
    db.session.add(tx)
    db.session.flush()
    return tx


def get_default_account(currency):
    """
    Возвращает первый счёт нужной валюты (по id).
    Если счетов такой валюты нет — None.
    """
    if currency not in Currency.CHOICES:
        return None
    return (
        CashAccount.query
        .filter_by(currency=currency)
        .order_by(CashAccount.id)
        .first()
    )


def delete_account(account):
    """Удалить счёт вместе со всеми его транзакциями."""
    db.session.delete(account)
    db.session.commit()