import re

def optimize_text(text: str) -> str:
    """缩减 Prompt 中的重复空白字符。

    将连续重复的同类空白字符（空格、换行、制表符等）压缩为单个字符，
    并移除首尾空白。

    Args:
        text: 待优化文本。

    Returns:
        优化后的文本。
    """
    text = re.sub(r"(\s)\1+", r"\1", text)
    return text.strip()
