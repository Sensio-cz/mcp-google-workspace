from typing import Any
from ..server import mcp
from ..services.sheets import SheetsService

_sheets = None


def _get_sheets() -> SheetsService:
    global _sheets
    if _sheets is None:
        _sheets = SheetsService()
    return _sheets


@mcp.tool()
async def sheets_create_spreadsheet(title: str) -> dict[str, Any]:
    """Vytvor novy Google Spreadsheet."""
    return _get_sheets().create_spreadsheet(title)


@mcp.tool()
async def sheets_read_range(spreadsheet_id: str, range_notation: str) -> dict[str, Any]:
    """Precti data z Google Sheetu. Pouzij A1 notaci (napr. 'Sheet1!A1:B5')."""
    return _get_sheets().read_range(spreadsheet_id, range_notation)


@mcp.tool()
async def sheets_write_range(spreadsheet_id: str, range_notation: str, values: list[list]) -> dict[str, Any]:
    """Zapis data do Google Sheetu. Pouzij A1 notaci."""
    return _get_sheets().write_range(spreadsheet_id, range_notation, values)


@mcp.tool()
async def sheets_append_rows(spreadsheet_id: str, range_notation: str, values: list[list]) -> dict[str, Any]:
    """Pridej radky na konec Google Sheetu."""
    return _get_sheets().append_rows(spreadsheet_id, range_notation, values)


@mcp.tool()
async def sheets_clear_range(spreadsheet_id: str, range_notation: str) -> dict[str, Any]:
    """Vymaz data v rozsahu Google Sheetu."""
    return _get_sheets().clear_range(spreadsheet_id, range_notation)


@mcp.tool()
async def sheets_add_sheet(spreadsheet_id: str, title: str) -> dict[str, Any]:
    """Pridej novy list do Google Sheetu."""
    return _get_sheets().add_sheet(spreadsheet_id, title)


@mcp.tool()
async def sheets_delete_sheet(spreadsheet_id: str, sheet_id: int) -> dict[str, Any]:
    """Smaz list z Google Sheetu."""
    return _get_sheets().delete_sheet(spreadsheet_id, sheet_id)
