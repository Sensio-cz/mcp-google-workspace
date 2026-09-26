"""
Cache místností (Directory) patří přihlášenému uživateli.

PROČ TENHLE TEST EXISTUJE. `CalendarService._rooms_cache` je na úrovni třídy
a byla pod pevným klíčem "all". Kdo se zeptal první, tomu se místnosti
načetly - a všichni další uživatelé (i z jiné domény, i bez práv do Directory)
pak 24 hodin dostávali jeho seznam. Nález revize 26. 9. 2026.

Spuštění: python -m pytest tests/test_mistnosti_podle_uzivatele.py -q
"""

from unittest.mock import MagicMock, patch

from mcp_google_workspace.services import calendar as cal


def _directory_s_mistnosti(nazev: str) -> MagicMock:
    api = MagicMock()
    api.resources().calendars().list().execute.return_value = {
        "items": [{"resourceEmail": f"{nazev}@resource", "resourceName": nazev}]
    }
    return api


def test_kazdy_uzivatel_vidi_sve_mistnosti():
    cal.CalendarService._rooms_cache.clear()
    sluzba = cal.CalendarService()
    with patch.object(cal, "current_user_key", return_value="a@firma-a.cz"), \
         patch.object(cal.CalendarService, "directory", new=_directory_s_mistnosti("Sal A")):
        assert [m["name"] for m in sluzba.list_room_resources()] == ["Sal A"]
    with patch.object(cal, "current_user_key", return_value="b@firma-b.cz"), \
         patch.object(cal.CalendarService, "directory", new=_directory_s_mistnosti("Sal B")):
        assert [m["name"] for m in sluzba.list_room_resources()] == ["Sal B"]
