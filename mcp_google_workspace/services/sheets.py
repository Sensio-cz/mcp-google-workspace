from typing import Any
from googleapiclient.discovery import build
from ..auth.context import get_current_google_credentials


class SheetsService:
    def __init__(self):
        pass

    @property
    def service(self):
        """Build a Sheets service using the current user's credentials (per-request)."""
        creds = get_current_google_credentials()
        return build("sheets", "v4", credentials=creds)

    def create_spreadsheet(self, title: str) -> dict:
        body = {"properties": {"title": title}}
        result = self.service.spreadsheets().create(body=body).execute()
        return {"spreadsheet_id": result["spreadsheetId"], "url": result["spreadsheetUrl"]}

    def read_range(self, spreadsheet_id: str, range_notation: str) -> dict:
        result = self.service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=range_notation
        ).execute()
        return {"values": result.get("values", []), "range": result.get("range", "")}

    def write_range(self, spreadsheet_id: str, range_notation: str, values: list[list]) -> dict:
        body = {"values": values}
        result = self.service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=range_notation,
            valueInputOption="USER_ENTERED", body=body,
        ).execute()
        return {"updated_cells": result.get("updatedCells", 0), "updated_range": result.get("updatedRange", "")}

    def append_rows(self, spreadsheet_id: str, range_notation: str, values: list[list]) -> dict:
        body = {"values": values}
        result = self.service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range=range_notation,
            valueInputOption="USER_ENTERED", body=body,
        ).execute()
        updates = result.get("updates", {})
        return {"updated_cells": updates.get("updatedCells", 0), "updated_range": updates.get("updatedRange", "")}

    def clear_range(self, spreadsheet_id: str, range_notation: str) -> dict:
        self.service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id, range=range_notation, body={}
        ).execute()
        return {"success": True, "cleared_range": range_notation}

    def add_sheet(self, spreadsheet_id: str, title: str) -> dict:
        body = {"requests": [{"addSheet": {"properties": {"title": title}}}]}
        result = self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body=body
        ).execute()
        props = result["replies"][0]["addSheet"]["properties"]
        return {"sheet_id": props["sheetId"], "title": props["title"]}

    def delete_sheet(self, spreadsheet_id: str, sheet_id: int) -> dict:
        body = {"requests": [{"deleteSheet": {"sheetId": sheet_id}}]}
        self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body=body
        ).execute()
        return {"success": True}
