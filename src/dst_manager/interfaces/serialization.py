from dataclasses import asdict
from typing import Any


def workspace_json(workspace) -> dict[str, Any]:
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
                {
                    "id": subset.acsm_id,
                    "name": subset.name,
                    "order": subset.order,
                    "sheets": [
                        {
                            "id": sheet.acsm_id,
                            "number": sheet.number,
                            "title": sheet.title,
                            "custom_properties": sheet.custom_properties,
                            "layout": {
                                **asdict(sheet.layout),
                                "resolved_path": str(sheet.layout.resolved_path) if sheet.layout.resolved_path else None,
                            },
                        }
                        for sheet in subset.sheets
                    ],
                }
                for subset in workspace.document.subsets
            ],
        },
        "diagnostics": [asdict(issue) for issue in workspace.document.diagnostics],
        "unreferenced_dwgs": [str(path) for path in workspace.unreferenced_dwgs],
    }
