_ALLOWED_CONTROLS = {"\t", "\n", "\r"}


def sanitize_log_text(value: str) -> str:
    """把日志规范为可安全写入 UTF-8 文本文件的内容。"""
    output: list[str] = []
    for character in value:
        codepoint = ord(character)
        if codepoint < 32 and character not in _ALLOWED_CONTROLS:
            output.append(f"\\x{codepoint:02x}")
        elif codepoint == 127:
            output.append("\\x7f")
        else:
            output.append(character)
    return "".join(output)


def validate_log_bytes(data: bytes) -> None:
    """严格验证运行日志编码和控制字符协议。"""
    text = data.decode("utf-8", errors="strict")
    invalid = [character for character in text if (ord(character) < 32 and character not in _ALLOWED_CONTROLS) or ord(character) == 127]
    if invalid:
        raise ValueError(f"LOG_CONTROL_CHARACTER_INVALID: U+{ord(invalid[0]):04X}")
