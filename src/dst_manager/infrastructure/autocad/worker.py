import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

_UNSAFE = re.compile(r"[\r\n\x00-\x1f\"]")


def encode_scr_argument(value: str) -> str:
    if not value or _UNSAFE.search(value):
        raise ValueError("SCR_ARGUMENT_UNSAFE")
    return f'"{value}"' if " " in value else value


class ScriptRenderer:
    def render_rebuild(self, plugin: Path, layouts: list[dict[str, str]]) -> str:
        lines = ["FILEDIA", "0", "SECURELOAD", "0", "CMDECHO", "0", "_.NETLOAD", encode_scr_argument(str(plugin)), "DstDeleteLayouts"]
        temporary_names = []
        for index, layout in enumerate(layouts):
            temporary_name = f"DST_TMP_{index:04d}"
            temporary_names.append(temporary_name)
            lines.extend(["_.-LAYOUT", "_Template", encode_scr_argument(layout["source_file"]), encode_scr_argument(layout["source_layout"])])
            lines.extend(["_.-LAYOUT", "_Rename", encode_scr_argument(layout["source_layout"]), temporary_name])
        for temporary_name, layout in zip(temporary_names, layouts, strict=True):
            lines.extend(["_.-LAYOUT", "_Rename", temporary_name, encode_scr_argument(layout["target_layout"])])
        if layouts:
            lines.extend(["_.-LAYOUT", "_Set", encode_scr_argument(layouts[0]["target_layout"])])
        lines.append("DstDeleteDefaultLayout")
        lines.extend(["CMDECHO", "1", "FILEDIA", "1", "_.QSAVE", "_.QUIT"])
        return "\n".join(lines) + "\n"

    def render_handles(self, plugin: Path) -> str:
        return "\n".join(["FILEDIA", "0", "SECURELOAD", "0", "CMDECHO", "0", "_.NETLOAD", encode_scr_argument(str(plugin)), "DstGetLayoutHandles", "_.QSAVE", "_.QUIT"]) + "\n"


def parse_handles(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        name, handle = (part.strip() for part in line.split("=", 1))
        if not name or not re.fullmatch(r"[0-9A-Fa-f]+", handle) or name in result or handle.upper() in {value.upper() for value in result.values()}:
            raise ValueError("HANDLE_OUTPUT_INVALID")
        result[name] = handle.upper()
    if not result:
        raise ValueError("HANDLE_OUTPUT_EMPTY")
    return result


@dataclass(slots=True)
class CadCapability:
    version: str
    console: Path | None
    plugin: Path | None

    @property
    def available(self) -> bool:
        return bool(self.console and self.console.is_file() and self.plugin and self.plugin.is_file())


class CoreConsoleExecutor:
    def run(self, capability: CadCapability, drawing: Path, script: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        if not capability.available:
            raise RuntimeError(f"CAD_CAPABILITY_UNAVAILABLE: {capability.version}")
        args = [str(capability.console), "/i", str(drawing), "/s", str(script), "/l", "zh-CN"]
        raw = subprocess.run(args, check=False, capture_output=True, timeout=timeout, shell=False)

        def decode(data: bytes) -> str:
            if data.startswith((b"\xff\xfe", b"\xfe\xff")):
                return data.decode("utf-16", errors="replace")
            if b"\x00" in data[:200]:
                return data.decode("utf-16-le", errors="replace")
            return data.decode("mbcs", errors="replace")

        completed = subprocess.CompletedProcess(args, raw.returncode, decode(raw.stdout), decode(raw.stderr))
        if completed.returncode:
            raise subprocess.CalledProcessError(completed.returncode, args, completed.stdout, completed.stderr)
        return completed
