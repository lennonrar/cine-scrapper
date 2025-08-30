from typing import Optional
import requests
from http import HTTPStatus


def get_html_page(url: str) -> str:
    print(f"Fetching HTML page from {url}")
    response = requests.get(url)
    if response.status_code == HTTPStatus.OK:
        return response.content
    raise Exception(response.reason)


def get_data(url: str, header: Optional[dict] = None) -> dict:
    print(f"Fetching {url}...")
    response = requests.get(url, headers=header)
    if response.status_code == HTTPStatus.OK:
        return response.json()
    raise Exception(response.reason)
