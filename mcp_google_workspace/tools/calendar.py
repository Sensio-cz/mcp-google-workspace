"""MCP tools pro Google Calendar.

Tools odpovídají Phase 2 z welcome-board plánu (Sensio-os#70, mcp-google-workspace#1).
Sdílejí auth context s Gmail / Drive / Sheets tools (per-request credentials).
"""

from typing import Any, Optional

from ..server import mcp
from ..services.calendar import CalendarService

_calendar = None


def _get_calendar() -> CalendarService:
    global _calendar
    if _calendar is None:
        _calendar = CalendarService()
    return _calendar


@mcp.tool()
async def calendar_list_events(
    calendar_id: str = "primary",
    time_min: Optional[str] = None,
    time_max: Optional[str] = None,
    q: Optional[str] = None,
    max_results: int = 50,
) -> dict[str, Any]:
    """List events v kalendari. Defaultne primary kalendar od ted (time_min=now).

    Args:
        calendar_id: 'primary' nebo Calendar ID (napr. 'sensio.cz_xxx@group.calendar.google.com')
        time_min: ISO 8601 zacatek okna (default = ted, UTC)
        time_max: ISO 8601 konec okna (default = otevreny)
        q: full-text search query (napr. 'Karel')
        max_results: max pocet (default 50, Google max 2500)

    Vrati: {ok, count, events: [normalized event s welcome-board tagy], next_page_token?}
    """
    return _get_calendar().list_events(
        calendar_id=calendar_id,
        time_min=time_min,
        time_max=time_max,
        q=q,
        max_results=max_results,
    )


@mcp.tool()
async def calendar_create_event(
    calendar_id: str,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: Optional[str] = None,
    timezone_str: str = "Europe/Prague",
    attendees: Optional[list[str]] = None,
    location: Optional[str] = None,
    auto_attach_room: bool = False,
    room_name_match: str = "zasedací místnost",
    send_updates: str = "none",
) -> dict[str, Any]:
    """Vytvor event v kalendari.

    Pro welcome-board pouziti:
        - calendar_id = 'sensio.cz_ar5pmceb233tndhaj0aghkjt6c@group.calendar.google.com'
          (kalendar 'Sensio - pro vsechny')
        - attendees = ['welcome@sensio.cz', + interni @sensio.cz, + externi hoste]
        - auto_attach_room = True (auto pripoji 'Zasedaci mistnost 116b' jako resource)
        - description: muze obsahovat tagy:
            Welcome: Jmeno Hosta
            Company: Firma s.r.o.
            Photo: https://...
            Sound: birthday-song
            Greeting: Vitej!  (nebo 'none' pro skryti uvitani)
            Background: true   (pro narozeniny - neprebije visit)
        - send_updates = 'externalOnly' aby externi hoste dostali pozvanku

    Args:
        calendar_id: cilovy kalendar
        summary: nazev udalosti
        start_iso, end_iso: ISO 8601 zacatek/konec
        description: tělo události (volitelne welcome-board tagy)
        timezone_str: napr. 'Europe/Prague'
        attendees: list emailu
        location: textova adresa
        auto_attach_room: pridat resource attendee podle room_name_match
        room_name_match: substring match na resource name (default 'zasedaci mistnost')
        send_updates: 'none' / 'all' / 'externalOnly'

    Vrati: {ok, event_id, html_link, calendar_id, summary, attendees: [...]}
    """
    return _get_calendar().create_event(
        calendar_id=calendar_id,
        summary=summary,
        start_iso=start_iso,
        end_iso=end_iso,
        description=description,
        timezone_str=timezone_str,
        attendees=attendees,
        location=location,
        auto_attach_room=auto_attach_room,
        room_name_match=room_name_match,
        send_updates=send_updates,
    )


@mcp.tool()
async def calendar_patch_event(
    calendar_id: str,
    event_id: str,
    patches: dict[str, Any],
    send_updates: str = "none",
) -> dict[str, Any]:
    """Uprav existujici event (partial update).

    Args:
        patches: dict s field => new value (napr. {'start': {'dateTime': '...'}, 'summary': '...'})
        send_updates: 'none' / 'all' / 'externalOnly'

    Pouziti: posunout cas, zmenit jmeno hosta, pridat/odebrat attendees, zmenit popis.
    Pro nejcastejsi pripady:
        - posun zacatku: patches = {'start': {'dateTime': '2026-05-01T15:00:00+02:00'}, 'end': {...}}
        - pridat hosta: patches = {'attendees': [...stávající + novy]}  (nutno cele pole, ne append)
    """
    return _get_calendar().patch_event(
        calendar_id=calendar_id,
        event_id=event_id,
        patches=patches,
        send_updates=send_updates,
    )


@mcp.tool()
async def calendar_delete_event(
    calendar_id: str,
    event_id: str,
    send_updates: str = "none",
    fallback_calendars: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Smaz event s multi-calendar fallback.

    Pokud event neni na primarnim kalendari (404), zkousi vsechny fallback_calendars.
    204/410 z kterehokoli = uspech. 404 ze vsech = uspech (event nikde neni).

    Args:
        calendar_id: primarni cil pro delete
        event_id: ID udalosti
        send_updates: 'none' (default - tichy smaz) / 'all' / 'externalOnly'
        fallback_calendars: dalsi kalendare k vyzkouseni; pro welcome-board pouzij
            ['sensio.cz_ar5pmceb233tndhaj0aghkjt6c@group.calendar.google.com', 'primary']

    Vrati: {ok, deleted_id, calendar_id (kde se smazalo), attempts: [...]}
        nebo {ok: false, error: 'calendar_api_failed', attempts, last_error}
    """
    return _get_calendar().delete_event(
        calendar_id=calendar_id,
        event_id=event_id,
        send_updates=send_updates,
        fallback_calendars=fallback_calendars,
    )


@mcp.tool()
async def calendar_list_rooms(force_refresh: bool = False) -> dict[str, Any]:
    """List Workspace Room Resources (zasedacky, ucebny, ...).

    Vyzaduje DwD scope:
        https://www.googleapis.com/auth/admin.directory.resource.calendar.readonly

    Cache: 24 hodin v pameti (per CalendarService instance). force_refresh=True
    cache obejde a znovu volá Directory API.

    Vrati: {ok, count, rooms: [{email, name, generated_name, capacity, building_id, floor_name, category}, ...]}
    """
    rooms = _get_calendar().list_room_resources(force_refresh=force_refresh)
    return {"ok": True, "count": len(rooms), "rooms": rooms}


@mcp.tool()
async def calendar_find_room_email(name_match: str) -> dict[str, Any]:
    """Najdi email Workspace mistnosti, jejiz nazev obsahuje name_match (case-insensitive).

    Args:
        name_match: napr. 'zasedaci mistnost' najde 'Zasedaci mistnost 116b'

    Vrati: {ok: true, email: '...@resource.calendar.google.com'}
        nebo {ok: false, error: 'not_found'} pokud nic nesedi
    """
    email = _get_calendar().find_room_email(name_match)
    if email:
        return {"ok": True, "email": email}
    return {"ok": False, "error": "not_found", "name_match": name_match}
