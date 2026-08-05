import json
import requests
from typing import Optional
from http import HTTPStatus
from requests.exceptions import RequestException


def get_html_page(url: str, timeout: int = 10) -> str:
    response = requests.get(url, timeout=timeout)
    if response.status_code == HTTPStatus.OK:
        return response.content
    raise Exception(response.reason)


def get_data(url: str, header: Optional[dict] = None, timeout: int = 10) -> dict:
    response = requests.get(url, headers=header, timeout=timeout)
    if response.status_code == HTTPStatus.OK:
        response_data = response.json()
        if type(response.json()) == str:
            response_data = json.loads(response_data)

        return response_data
    raise RequestException(response.reason)
