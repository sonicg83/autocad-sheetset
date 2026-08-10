import json
from pathlib import Path

import typer

from dst_manager.application.service import DstManagerService
from dst_manager.interfaces.api import _workspace_json

app = typer.Typer(help="DST Manager MVP 命令行")


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8000):
    """启动仅监听本机的Web API。"""
    if host != "127.0.0.1":
        raise typer.BadParameter("MVP只允许监听127.0.0.1")
    import uvicorn
    uvicorn.run("dst_manager.interfaces.api:app", host=host, port=port)


@app.command("open")
def open_workspace(dst_path: Path):
    """只读打开并输出结构报告。"""
    result = DstManagerService().open_workspace(dst_path)
    typer.echo(json.dumps(_workspace_json(result), ensure_ascii=False, indent=2, default=str))


@app.command("doctor")
def doctor():
    """检查AutoCAD 2016/2020显式配置。"""
    typer.echo(json.dumps(DstManagerService().capabilities(), ensure_ascii=False, indent=2))


@app.command("worker")
def worker(once: bool = typer.Option(False, help="没有任务时立即退出")):
    """运行同机CAD Worker；默认持续轮询SQLite任务队列。"""
    import time
    service = DstManagerService()
    while True:
        result = service.run_next_job()
        if result is not None:
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        elif once:
            return
        else:
            time.sleep(1)
