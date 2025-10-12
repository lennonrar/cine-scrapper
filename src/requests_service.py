import json
import requests
from typing import Optional
from http import HTTPStatus
from requests.exceptions import RequestException


def get_html_page(url: str) -> str:
    print(f"Fetching HTML page from {url}")
    response = requests.get(url, timeout=10)
    if response.status_code == HTTPStatus.OK:
        return response.content
    raise Exception(response.reason)


def get_data(url: str, header: Optional[dict] = None) -> dict:
    print(f"Fetching {url}...")
    response = requests.get(url, headers=header, timeout=10)
    if response.status_code == HTTPStatus.OK:
        response_data = response.json()
        if type(response.json()) == str:
            response_data = json.loads(response_data)

        return response_data
    raise RequestException(response.reason)
