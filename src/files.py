
def get_file(file_path: str) -> str:
    with open(file_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    return html_content
