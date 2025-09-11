import os
from datetime import datetime as dt
from dotenv import load_dotenv


def get_today() -> str:
    now = dt.now()
    today_formatted = now.strftime('%Y-%m-%d')
    return today_formatted


def get_env(var_name: str) -> str:
    load_dotenv()
    value = os.getenv(var_name)
    if value is None:
        raise EnvironmentError(f"Environment variable '{var_name}' not found.")
    return value
