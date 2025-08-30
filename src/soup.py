from bs4 import BeautifulSoup as bs


def get_soup(html_content: str):
    return bs(html_content, 'html.parser')
