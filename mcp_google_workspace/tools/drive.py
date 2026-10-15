from typing import Any
from ..server import mcp
from ..services.drive import DriveService

_drive = None


def _get_drive() -> DriveService:
    global _drive
    if _drive is None:
        _drive = DriveService()
    return _drive


@mcp.tool()
async def drive_search_files(query: str, page_size: int = 10, shared_drive_id: str | None = None) -> dict[str, Any]:
    """Vyhledej soubory na Google Drive. Pouzij Drive query syntax (name contains 'x', mimeType='...')."""
    return {"files": _get_drive().search_files(query, page_size, shared_drive_id)}


@mcp.tool()
async def drive_read_file_content(file_id: str) -> dict[str, Any]:
    """Precti obsah souboru z Google Drive. Google Docs se exportuji jako markdown, Sheets jako CSV."""
    return _get_drive().read_file_content(file_id)


@mcp.tool()
async def drive_create_folder(folder_name: str, parent_folder_id: str | None = None, shared_drive_id: str | None = None) -> dict[str, Any]:
    """Vytvor slozku na Google Drive."""
    return _get_drive().create_folder(folder_name, parent_folder_id, shared_drive_id)


@mcp.tool()
async def drive_upload_file(filename: str, content_base64: str, parent_folder_id: str | None = None, shared_drive_id: str | None = None) -> dict[str, Any]:
    """Nahraj soubor na Google Drive. Obsah musi byt base64 encoded."""
    return _get_drive().upload_file(filename, content_base64, parent_folder_id, shared_drive_id)


@mcp.tool()
async def drive_update_file_content(
    file_id: str,
    content: str,
    content_mime_type: str = "text/html",
    encoding: str = "utf-8",
    allow_type_change: bool = False,
    expected_modified_time: str | None = None,
) -> dict[str, Any]:
    """DESTRUKTIVNI: prepise CELY obsah existujiciho souboru na Google Drive; ID souboru i odkaz zustavaji.
    U Google dokumentu se nahrane HTML (vychozi) nebo text prevede a nahradi cely dokument: vsechno,
    co v nahranem obsahu neni (zahlavi, zapati, obrazky, navrhy, kotvy komentaru), se ztrati; predchozi
    obsah zustane v historii verzi. Pozor: drive_read_file_content vraci Docs jako markdown, pro zapis
    ho preved na HTML (nebo posli content_mime_type='text/plain'). Typ obsahu podle cile: Docs text/html
    nebo text/plain, Sheets text/csv, Slides pptx (base64). Pred zapisem over nazev souboru
    (vraci se v 'previous'). U obycejneho souboru musi content_mime_type odpovidat typu souboru, jinak
    je potreba allow_type_change=True. expected_modified_time (modifiedTime z drive_search_files)
    odmitne zapis, pokud soubor mezitim nekdo zmenil. encoding: 'utf-8' (content je text) nebo 'base64'."""
    return _get_drive().update_file_content(
        file_id, content, content_mime_type, encoding, allow_type_change, expected_modified_time
    )


@mcp.tool()
async def drive_delete_file(file_id: str) -> dict[str, Any]:
    """Smaz soubor z Google Drive."""
    return _get_drive().delete_file(file_id)


@mcp.tool()
async def drive_list_shared_drives(page_size: int = 100) -> dict[str, Any]:
    """Vypis sdilene disky na Google Drive."""
    return {"drives": _get_drive().list_shared_drives(page_size)}
