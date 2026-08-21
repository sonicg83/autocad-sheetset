import json
import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

import pytest

from dst_manager.infrastructure.logging_text import validate_log_bytes

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "scripts" / "start.ps1"
POWERSHELL = shutil.which("powershell")
POWERSHELLS = [path for path in (POWERSHELL, shutil.which("pwsh")) if path]


def _run_script(*arguments: str, check: bool = True, executable: str | None = None) -> subprocess.CompletedProcess[str]:
    command = [executable or POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SCRIPT), *arguments]
    # 后台 Python 子进程在 Windows 上可能继承 PowerShell 的标准句柄；使用普通文件避免 PIPE 等待 EOF。
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as stdout_file, tempfile.TemporaryFile(
        mode="w+", encoding="utf-8", errors="replace"
    ) as stderr_file:
        result = subprocess.run(command, cwd=ROOT, text=True, stdout=stdout_file, stderr=stderr_file, check=False, timeout=90)
        stdout_file.seek(0)
        stderr_file.seek(0)
        completed = subprocess.CompletedProcess(command, result.returncode, stdout_file.read(), stderr_file.read())
    if check and completed.returncode:
        raise AssertionError(completed.stdout + completed.stderr)
    return completed


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@pytest.mark.parametrize("shell", POWERSHELLS)
@pytest.mark.skipif(not POWERSHELLS, reason="需要 Windows PowerShell 或 PowerShell 7")
def test_start_script_is_utf8_bom_and_parses_in_powershell(shell):
    assert SCRIPT.read_bytes().startswith(b"\xef\xbb\xbf")
    command = (
        "$tokens=$null;$errors=$null;"
        f"[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT}',[ref]$tokens,[ref]$errors)|Out-Null;"
        "if($errors.Count){$errors|ForEach-Object{$_.Message};exit 1}"
    )
    completed = subprocess.run(
        [shell, "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.parametrize("shell", POWERSHELLS)
@pytest.mark.skipif(not POWERSHELLS, reason="需要 Windows PowerShell 或 PowerShell 7")
def test_web_dependency_check_reuses_matching_lockfile_installation(shell, tmp_path):
    web_root = tmp_path / "web"
    node_modules = web_root / "node_modules"
    node_modules.mkdir(parents=True)
    (node_modules / ".dst-manager-package-lock.sha256").write_text("matching-lock-hash\n", encoding="utf-8")
    npm = tmp_path / "npm.cmd"
    npm.write_text("@echo off\r\nif \"%1\"==\"ls\" exit /b 0\r\nexit /b 1\r\n", encoding="ascii")

    command = f"""
$tokens=$null;$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile('{SCRIPT}',[ref]$tokens,[ref]$errors)
$functions=@($ast.FindAll({{param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Test-WebDependenciesCurrent'}}, $true))
if($functions.Count -ne 1){{throw '未找到 Web 依赖复用检查函数'}}
Invoke-Expression $functions[0].Extent.Text
if(-not (Test-WebDependenciesCurrent '{npm}' '{web_root}' 'matching-lock-hash')){{throw '匹配的锁文件依赖应被复用'}}
if(Test-WebDependenciesCurrent '{npm}' '{web_root}' 'changed-lock-hash'){{throw '锁文件变化后不得复用依赖'}}
"""
    completed = subprocess.run(
        [shell, "-NoProfile", "-Command", command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr


@pytest.mark.skipif(os.environ.get("DST_MANAGER_RUN_LIFECYCLE") != "1", reason="真实进程生命周期测试需显式启用")
@pytest.mark.parametrize("shell", POWERSHELLS)
@pytest.mark.skipif(not POWERSHELLS, reason="需要 Windows PowerShell 或 PowerShell 7")
def test_cold_start_duplicate_start_missing_state_logs_and_stop(shell):
    port = _free_port()
    runtime_root = ROOT / ".dst-manager-data" / "runtime"
    state_path = runtime_root / "processes.json"
    _run_script("-Action", "Stop", "-Port", str(port), check=False, executable=shell)
    try:
        for index in range(22):
            old_run = runtime_root / f"retention-test-{index:02d}"
            old_run.mkdir(parents=True, exist_ok=True)
            (old_run / "old.log").write_text("old", encoding="utf-8")
            timestamp = 1_600_000_000 + index
            os.utime(old_run, (timestamp, timestamp))
        (runtime_root / "legacy-mixed.log").write_bytes("中文错误".encode("mbcs") + b"\x00")
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps(
                {
                    "run_id": "stale",
                    "port": port,
                    "server": {"process_id": 999999, "started_at_utc": "2000-01-01T00:00:00Z", "command_type": "server"},
                    "worker": {"process_id": 999998, "started_at_utc": "2000-01-01T00:00:00Z", "command_type": "worker"},
                }
            ),
            encoding="utf-8",
        )
        started = _run_script("-Action", "Start", "-NoBrowser", "-SkipSync", "-SkipWebBuild", "-Port", str(port), executable=shell)
        assert "已启动" in started.stdout
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        assert Path(state["run_dir"]).is_dir()
        assert not (runtime_root / "retention-test-00").exists()
        converted_legacy = list(runtime_root.glob("legacy-*/legacy-mixed.log"))
        assert converted_legacy
        validate_log_bytes(converted_legacy[-1].read_bytes())
        assert "中文错误" in converted_legacy[-1].read_text(encoding="utf-8-sig")
        assert converted_legacy[-1].with_name("legacy-mixed.log.legacy.bin").is_file()
        first_pids = (state["server"]["process_id"], state["worker"]["process_id"])
        repeated = _run_script("-Action", "Start", "-NoBrowser", "-SkipSync", "-SkipWebBuild", "-Port", str(port), executable=shell)
        assert "不创建新进程" in repeated.stdout
        repeated_state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        assert (repeated_state["server"]["process_id"], repeated_state["worker"]["process_id"]) == first_pids
        logs = _run_script("-Action", "Logs", "-LogTail", "5", executable=shell)
        assert "server.stdout.log" in logs.stdout and "worker.stdout.log" in logs.stdout

        state_path.unlink()
        missing_state = _run_script("-Action", "Start", "-NoBrowser", "-SkipSync", "-SkipWebBuild", "-Port", str(port), check=False, executable=shell)
        assert missing_state.returncode != 0
        assert "状态文件缺失" in missing_state.stdout + missing_state.stderr
        stopped = _run_script("-Action", "Stop", "-Port", str(port), executable=shell)
        assert "已清空" in stopped.stdout

        for path in state["logs"].values():
            if path:
                validate_log_bytes(Path(path).read_bytes())
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
    finally:
        _run_script("-Action", "Stop", "-Port", str(port), check=False, executable=shell)
        for old_run in runtime_root.glob("retention-test-*"):
            shutil.rmtree(old_run)


@pytest.mark.skipif(os.environ.get("DST_MANAGER_RUN_LIFECYCLE") != "1", reason="真实进程生命周期测试需显式启用")
@pytest.mark.skipif(POWERSHELL is None, reason="需要 Windows PowerShell")
def test_unknown_port_owner_is_not_terminated():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        completed = _run_script("-Action", "Start", "-NoWorker", "-NoBrowser", "-SkipSync", "-SkipWebBuild", "-Port", str(port), check=False)
        assert completed.returncode != 0
        assert "未知进程占用" in completed.stdout + completed.stderr
        assert "startup.log" in completed.stdout + completed.stderr
        listener.settimeout(0.01)
        assert listener.fileno() >= 0


@pytest.mark.skipif(os.environ.get("DST_MANAGER_RUN_LIFECYCLE") != "1", reason="真实进程生命周期测试需显式启用")
@pytest.mark.skipif(POWERSHELL is None, reason="需要 Windows PowerShell")
def test_worker_start_failure_rolls_back_api_and_releases_port(monkeypatch):
    port = _free_port()
    monkeypatch.setenv("DST_MANAGER_TEST_FAIL_BEFORE_WORKER", "1")

    completed = _run_script("-Action", "Start", "-NoBrowser", "-SkipSync", "-SkipWebBuild", "-Port", str(port), check=False)

    assert completed.returncode != 0
    assert "TEST_WORKER_START_FAILURE" in completed.stdout + completed.stderr
    assert not (ROOT / ".dst-manager-data" / "runtime" / "processes.json").exists()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))
