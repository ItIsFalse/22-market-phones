import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

os.makedirs(INSTANCE_DIR, exist_ok=True)

DB_PATH = os.path.join(INSTANCE_DIR, "database.db").replace("\\", "/")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-fallback")

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{DB_PATH}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SHOP_NAME = os.getenv("SHOP_NAME", "22 Market Phone")
    SHOP_PHONE = os.getenv("SHOP_PHONE", "")
    SHOP_ADDRESS = os.getenv("SHOP_ADDRESS", "")

    USD_RATE = int(os.getenv("USD_RATE", 12700))

    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    ADMIN_FULL_NAME = os.getenv("ADMIN_FULL_NAME")