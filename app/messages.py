"""Разбор файла с обращениями: одно обращение на строку."""

import re

# «1) текст» или «2. текст» — нумерация из задания, к самому обращению не относится
_NUMBERING = re.compile(r"^\d+[).]\s+")


def parse_messages(raw: str) -> list[str]:
    messages = []
    for line in raw.splitlines():
        text = _NUMBERING.sub("", line.strip()).strip()
        if text:
            messages.append(text)
    return messages
