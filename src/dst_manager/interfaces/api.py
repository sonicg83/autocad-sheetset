import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from dst_manager.application.service import ApplicationError, DstManagerService
from dst_manager.config import Settings


class OpenRequest(BaseModel):
    dst_path: Path
    root_override: Path | None = None


class ChangeRequest(BaseModel):
    base_revision_id: str
    commands: list[dict[str, Any]] = Field(default_factory=list)
    cad_version: str = "2020"


class XmlRequest(BaseModel):
    base_revision_id: str
    xml: str
    destination: Path | None = None


class TemplateRequest(BaseModel):
    template_path: Path
    cad_version: str = "2020"


def _workspace_json(workspace) -> dict[str, Any]:
    return {
        "id": workspace.id,
        "root": str(workspace.root),
        "dst_path": str(workspace.dst_path),
        "revision_id": workspace.revision_id,
        "sheet_set": {
            "database_id": workspace.document.database_id,
            "name": workspace.document.name,
            "custom_properties": workspace.document.custom_properties,
            "sheet_count": len(workspace.document.sheets),
            "subset_count": len(workspace.document.subsets),
            "subsets": [
                {"id": subset.acsm_id, "name": subset.name, "order": subset.order, "sheets": [{"id": sheet.acsm_id, "number": sheet.number, "title": sheet.title, "custom_properties": sheet.custom_properties, "layout": {**asdict(sheet.layout), "resolved_path": str(sheet.layout.resolved_path) if sheet.layout.resolved_path else None}} for sheet in subset.sheets]}
                for subset in workspace.document.subsets
            ],
        },
        "diagnostics": [asdict(issue) for issue in workspace.document.diagnostics],
        "unreferenced_dwgs": [str(path) for path in workspace.unreferenced_dwgs],
    }


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="DST Manager MVP", version="0.1.0")
    service = DstManagerService(settings)
    app.state.service = service

    @app.exception_handler(ApplicationError)
    async def application_error(_, exc: ApplicationError):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "message": str(exc)})

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/workspaces/open")
    def open_workspace(request: OpenRequest):
        return _workspace_json(service.open_workspace(request.dst_path, request.root_override))

    @app.get("/api/workspaces/{workspace_id}")
    def get_workspace(workspace_id: str):
        return _workspace_json(service.get_workspace(workspace_id))

    @app.post("/api/workspaces/{workspace_id}/changes/preview")
    def preview(workspace_id: str, request: ChangeRequest):
        return service.preview_changes(workspace_id, request.base_revision_id, request.commands)

    @app.post("/api/workspaces/{workspace_id}/changes/execute")
    def execute(workspace_id: str, request: ChangeRequest):
        if request.cad_version not in {"2016", "2020"}:
            raise HTTPException(422, "cad_version必须为2016或2020")
        return service.execute_changes(workspace_id, request.base_revision_id, request.commands, request.cad_version)

    @app.post("/api/workspaces/{workspace_id}/xml/import/preview")
    def preview_xml(workspace_id: str, request: XmlRequest):
        return service.preview_xml(workspace_id, request.base_revision_id, request.xml.encode("utf-8"))

    @app.post("/api/workspaces/{workspace_id}/xml/export-dst")
    def export_dst(workspace_id: str, request: XmlRequest):
        if request.destination is None:
            raise HTTPException(422, "destination不能为空")
        return service.export_xml_to_dst(workspace_id, request.base_revision_id, request.xml.encode("utf-8"), request.destination)

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str):
        result = service.database.get_job(job_id)
        if result is None:
            raise HTTPException(404, "任务不存在")
        return result

    @app.get("/api/jobs/{job_id}/events")
    async def job_events(job_id: str):
        async def events():
            previous = None
            while True:
                result = service.database.get_job(job_id)
                if result is None:
                    yield "event: error\ndata: {\"code\":\"JOB_NOT_FOUND\"}\n\n"
                    return
                current = json.dumps(result, ensure_ascii=False)
                if current != previous:
                    yield f"data: {current}\n\n"
                    previous = current
                if result["status"] in {"SUCCEEDED", "FAILED", "ROLLED_BACK", "BLOCKED_FILE_LOCK"}:
                    return
                await asyncio.sleep(0.5)
        return StreamingResponse(events(), media_type="text/event-stream")

    @app.get("/api/revisions")
    def revisions():
        return service.database.list_revisions()

    @app.get("/api/system/cad-capabilities")
    def capabilities():
        return service.capabilities()

    @app.post("/api/templates/inspect")
    def inspect_template(request: TemplateRequest):
        return service.inspect_template(request.template_path, request.cad_version)

    web_dist = Path(__file__).parents[3] / "web" / "dist"
    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app


app = create_app()
