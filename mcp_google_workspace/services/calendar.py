"""Google Calendar service vrstva.

Port logiky z welcome-board-sensio/backend/lib/calendar.php a lib/rooms.php.

Poskytuje:
- list / create / patch / delete events
- multi-calendar fallback při delete (pro events které mohou být na primary/sdíleném)
- room resource auto-attach via Directory API (cache 24h)
- parse welcome-board tagů (Welcome:, Company:, Photo:, Sound:, Greeting:, Background:)
- normalize event do compact dictu
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..auth.context import get_current_google_credentials


# ---------------------------------------------------------------------------
# Welcome-board tag parsing (port z calendar.php calendar_parse_welcome)
# ---------------------------------------------------------------------------

_RE_WELCOME = re.compile(r"^[\s>]*Welcome:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_RE_COMPANY = re.compile(r"^[\s>]*Company:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_RE_GREETING = re.compile(r"^[\s>]*Greeting:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_RE_PHOTO = re.compile(r"^[\s>]*Photo:\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
_RE_SOUND = re.compile(r"^[\s>]*Sound:\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)
_RE_BACKGROUND = re.compile(r"^[\s>]*Background:\s*(true|1|ano|yes)\s*$", re.IGNORECASE | re.MULTILINE)
_RE_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Approximate strip_tags() z PHP."""
    return _RE_HTML_TAG.sub("", text or "")


def _split_names(raw: str) -> list[str]:
    """„Karel | Marie | Petr" → ['Karel', 'Marie', 'Petr']. Max 3 jména."""
    names = [n.strip() for n in re.split(r"\s*[|;]\s*", raw or "") if n.strip()]
    return names[:3]


def parse_welcome_tags(summary: str, description: str = "") -> dict[str, Any]:
    """Vyextrahuje welcome-board tagy z events description (priorita) nebo summary (fallback).

    Konvence v popisu události:
        Welcome: Mgr. Richard Kapustka
        Welcome: PaedDr. Petr Paksi, DBA | Ing. Jana Suchánková
        Company: JAP FUTURE s.r.o.
        Greeting: Vítáme tě!         (none = skrýt, jinak custom; null = default „Vítáme Vás!")
        Photo: https://...
        Sound: birthday-song           (URL nebo named preset)
        Background: true               (= podklad jako narozeniny, nepřebíjí visit)
    """
    description = _strip_html(description or "")

    greeting = None
    photo = None
    sound = None
    background = False

    m = _RE_GREETING.search(description)
    if m:
        greeting = m.group(1).strip()
    m = _RE_PHOTO.search(description)
    if m:
        photo = m.group(1).strip()
    m = _RE_SOUND.search(description)
    if m:
        sound = m.group(1).strip()
    if _RE_BACKGROUND.search(description):
        background = True

    # Priorita 1: explicit Welcome: + Company: v popisu
    names: list[str] = []
    company = ""
    m_w = _RE_WELCOME.search(description)
    if m_w:
        names = _split_names(m_w.group(1))
        m_c = _RE_COMPANY.search(description)
        if m_c:
            company = m_c.group(1).strip()
        return {
            "names": names,
            "company": company,
            "greeting": greeting,
            "photo": photo,
            "sound": sound,
            "background": background,
        }

    # Priorita 2: parse ze summary (např. „Konzultace - Soňa Mikešková")
    m_s = re.search(r"\s+[-–]\s+(.+)$", summary or "", re.UNICODE)
    if m_s:
        welcome_part = m_s.group(1).strip()
        # případně „... ; firma"
        if ";" in welcome_part:
            name_part, company_part = welcome_part.split(";", 1)
            names = _split_names(name_part)
            company = company_part.strip()
        else:
            names = _split_names(welcome_part)

    return {
        "names": names,
        "company": company,
        "greeting": greeting,
        "photo": photo,
        "sound": sound,
        "background": background,
    }


# ---------------------------------------------------------------------------
# Event normalization (port z calendar_normalize)
# ---------------------------------------------------------------------------

def _name_from_email(email: str) -> str:
    """„soňa.mikeskova@gmail.com" → „Soňa Mikešková" (best-effort)."""
    if not email or "@" not in email:
        return email or ""
    local = email.split("@", 1)[0]
    parts = re.split(r"[._\-]+", local)
    return " ".join(p.capitalize() for p in parts if p)


def _parse_iso_to_ts(iso: str) -> int:
    """ISO 8601 → unix timestamp. Vrátí 0 při parsování chyby."""
    if not iso:
        return 0
    try:
        # Python 3.11+ podporuje Z suffix
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except (ValueError, TypeError):
        return 0


def normalize_event(event: dict, calendar_id: str) -> dict[str, Any]:
    """Convert raw Google Calendar event do compact welcome-board friendly dict."""
    start_str = (event.get("start") or {}).get("dateTime") or (event.get("start") or {}).get("date") or ""
    end_str = (event.get("end") or {}).get("dateTime") or (event.get("end") or {}).get("date") or ""

    guests = []
    for a in event.get("attendees") or []:
        email = (a.get("email") or "").lower()
        if email.endswith("@sensio.cz"):
            continue
        guests.append({
            "name": a.get("displayName") or _name_from_email(email),
            "email": email,
        })

    welcome = parse_welcome_tags(event.get("summary", ""), event.get("description", ""))

    return {
        "id": event.get("id", ""),
        "calendar_id": calendar_id,
        "summary": event.get("summary", ""),
        "description": event.get("description", ""),
        "location": event.get("location", ""),
        "start": start_str,
        "end": end_str,
        "start_ts": _parse_iso_to_ts(start_str),
        "end_ts": _parse_iso_to_ts(end_str),
        "color_id": event.get("colorId"),
        "html_link": event.get("htmlLink"),
        "guests": guests,
        "welcome_names": welcome["names"],
        "welcome_company": welcome["company"],
        "welcome_greeting": welcome["greeting"],
        "welcome_photo": welcome["photo"],
        "welcome_sound": welcome["sound"],
        "is_background": welcome["background"],
    }


# ---------------------------------------------------------------------------
# Calendar service
# ---------------------------------------------------------------------------

class CalendarService:
    """Wrapper nad googleapiclient.discovery Calendar v3 + Admin Directory.

    Per-request credentials (jako GmailService) - každý tool call použije
    aktuálního přihlášeného uživatele přes auth.context.
    """

    # Cache resources (rooms) napříč instancemi - 24h TTL
    _rooms_cache: dict[str, tuple[float, list[dict]]] = {}
    _ROOMS_TTL = 86400  # 24h

    @property
    def service(self):
        """Build Calendar v3 service per-request."""
        creds = get_current_google_credentials()
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    @property
    def directory(self):
        """Build Admin Directory v1 service (pro room resource lookup)."""
        creds = get_current_google_credentials()
        return build("admin", "directory_v1", credentials=creds, cache_discovery=False)

    # --- Events: list ---

    def list_events(
        self,
        calendar_id: str = "primary",
        time_min: Optional[str] = None,
        time_max: Optional[str] = None,
        q: Optional[str] = None,
        max_results: int = 50,
        single_events: bool = True,
        order_by: str = "startTime",
    ) -> dict[str, Any]:
        """List events ve specifikovaném časovém okně.

        Args:
            calendar_id: „primary" nebo Calendar ID
            time_min: ISO 8601 (např. „2026-04-29T00:00:00+02:00"); default = now
            time_max: ISO 8601; default = +24h
            q: full-text search query
            max_results: max počet (Google limit 2500, my default 50)
            single_events: True = expand recurring na instances
            order_by: „startTime" nebo „updated"

        Returns:
            dict {ok: bool, count: int, events: [normalized event, ...]}
        """
        if not time_min:
            time_min = datetime.now(timezone.utc).isoformat()
        params: dict[str, Any] = {
            "calendarId": calendar_id,
            "timeMin": time_min,
            "singleEvents": single_events,
            "orderBy": order_by,
            "maxResults": max_results,
        }
        if time_max:
            params["timeMax"] = time_max
        if q:
            params["q"] = q

        try:
            resp = self.service.events().list(**params).execute()
        except HttpError as e:
            return {"ok": False, "error": "calendar_api_failed", "status": e.resp.status, "detail": str(e)}

        items = resp.get("items", [])
        events = [normalize_event(e, calendar_id) for e in items]
        return {"ok": True, "count": len(events), "events": events, "next_page_token": resp.get("nextPageToken")}

    # --- Events: create ---

    def create_event(
        self,
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
        """Vytvoř event v zadaném kalendáři.

        Args:
            calendar_id: cílový kalendář
            summary: název události
            start_iso, end_iso: ISO 8601 začátek/konec
            description: tělo (může obsahovat Welcome:, Company:, Photo:, Sound:, Greeting:, Background: tagy)
            timezone_str: např. „Europe/Prague"
            attendees: list emailů (interní @sensio.cz, externí hosté).
                Pro welcome-board zahrň `welcome@sensio.cz`
            location: textová adresa (např. „Sensio.cz, Na Hrázi 13, Přerov")
            auto_attach_room: True = vyhledej v Workspace Directory místnost matchující
                room_name_match a přidej ji jako resource attendee (pro welcome-board)
            send_updates: „none" (default), „all", „externalOnly"

        Returns:
            dict {ok, event_id, html_link, calendar_id, summary, attendees}
        """
        attendees_list = [{"email": e} for e in (attendees or [])]

        if auto_attach_room:
            room_email = self.find_room_email(room_name_match)
            if room_email:
                attendees_list.append({"email": room_email, "resource": True})

        body: dict[str, Any] = {
            "summary": summary,
            "start": {"dateTime": start_iso, "timeZone": timezone_str},
            "end": {"dateTime": end_iso, "timeZone": timezone_str},
            "attendees": attendees_list,
        }
        if description is not None:
            body["description"] = description
        if location:
            body["location"] = location

        try:
            resp = self.service.events().insert(
                calendarId=calendar_id,
                body=body,
                sendUpdates=send_updates,
            ).execute()
        except HttpError as e:
            return {
                "ok": False,
                "error": "calendar_api_failed",
                "status": e.resp.status,
                "detail": str(e),
            }

        return {
            "ok": True,
            "event_id": resp.get("id"),
            "html_link": resp.get("htmlLink"),
            "calendar_id": calendar_id,
            "summary": resp.get("summary"),
            "attendees": [a.get("email") for a in resp.get("attendees", [])],
        }

    # --- Events: patch ---

    def patch_event(
        self,
        calendar_id: str,
        event_id: str,
        patches: dict[str, Any],
        send_updates: str = "none",
    ) -> dict[str, Any]:
        """Upravit existující event (partial update).

        Args:
            patches: libovolné Calendar event fields (summary, description, start, end, attendees, ...)
        """
        try:
            resp = self.service.events().patch(
                calendarId=calendar_id,
                eventId=event_id,
                body=patches,
                sendUpdates=send_updates,
            ).execute()
        except HttpError as e:
            return {"ok": False, "error": "calendar_api_failed", "status": e.resp.status, "detail": str(e)}

        return {
            "ok": True,
            "event_id": resp.get("id"),
            "html_link": resp.get("htmlLink"),
            "calendar_id": calendar_id,
            "updated": resp.get("updated"),
        }

    # --- Events: delete (s multi-calendar fallback) ---

    def delete_event(
        self,
        calendar_id: str,
        event_id: str,
        send_updates: str = "none",
        fallback_calendars: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Smaž event. Multi-calendar fallback: pokud event není na požadovaném
        kalendáři (404), zkus všechny calendars z fallback_calendars.

        Pattern z welcome-board-sensio/backend/api/event-delete.php (v1.0.2 fix):
        - 204/410 z kteréhokoli kalendáře = úspěch
        - 404 ze všech = úspěch (event nikde není - už dřív smazán)
        - Jiná chyba = error

        Args:
            calendar_id: primární cíl pro delete
            event_id: ID události
            send_updates: „none" / „all" / „externalOnly"
            fallback_calendars: další kalendáře k vyzkoušení pokud primární vrátí 404
        """
        candidates = [calendar_id]
        if fallback_calendars:
            for c in fallback_calendars:
                if c and c not in candidates:
                    candidates.append(c)

        attempts: list[dict[str, Any]] = []
        deleted_from: Optional[str] = None
        last_error: Optional[dict[str, Any]] = None

        for cal in candidates:
            try:
                self.service.events().delete(
                    calendarId=cal,
                    eventId=event_id,
                    sendUpdates=send_updates,
                ).execute()
                attempts.append({"calendar_id": cal, "status": 204})
                deleted_from = cal
                break
            except HttpError as e:
                status = e.resp.status
                attempts.append({"calendar_id": cal, "status": status})
                if status in (404,):
                    # event není na tomto kalendáři, zkus další
                    continue
                if status == 410:
                    # už smazáno - úspěch
                    deleted_from = cal
                    break
                last_error = {"calendar_id": cal, "status": status, "detail": str(e)}
                # Pro non-404/410 chyby přerušit (403/5xx)
                break

        if deleted_from is not None:
            return {
                "ok": True,
                "deleted_id": event_id,
                "calendar_id": deleted_from,
                "attempts": attempts,
            }

        # Žádný kalendář delete neudělal úspěšně.
        # Pokud všechny vrátily 404 → event opravdu nikde není (treat as success).
        all_404 = bool(attempts) and all(a["status"] == 404 for a in attempts)
        if all_404:
            return {
                "ok": True,
                "deleted_id": event_id,
                "attempts": attempts,
                "note": "event_not_found_anywhere",
            }

        return {
            "ok": False,
            "error": "calendar_api_failed",
            "attempts": attempts,
            "last_error": last_error,
        }

    # --- Resources: room lookup (Admin Directory) ---

    def list_room_resources(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        """List Workspace Room Resources s 24h cache.

        Vyžaduje DwD scope `https://www.googleapis.com/auth/admin.directory.resource.calendar.readonly`.
        Pokud scope chybí, vrací prázdný seznam (graceful degradation).
        """
        cache_key = "all"
        now = time.time()
        if not force_refresh and cache_key in self._rooms_cache:
            cached_at, rooms = self._rooms_cache[cache_key]
            if now - cached_at < self._ROOMS_TTL:
                return rooms

        try:
            resp = self.directory.resources().calendars().list(
                customer="my_customer",
                maxResults=100,
            ).execute()
        except HttpError:
            # Bez scope nebo bez admin práv - vrátit prázdné
            return []
        except Exception:
            return []

        rooms = []
        for r in resp.get("items", []):
            rooms.append({
                "email": r.get("resourceEmail", ""),
                "name": r.get("resourceName", ""),
                "generated_name": r.get("generatedResourceName", ""),
                "capacity": r.get("capacity"),
                "building_id": r.get("buildingId", ""),
                "floor_name": r.get("floorName", ""),
                "category": r.get("resourceCategory", ""),
            })

        self._rooms_cache[cache_key] = (now, rooms)
        return rooms

    def find_room_email(self, needle: str) -> Optional[str]:
        """Najdi email místnosti jejíž `name` nebo `generated_name` obsahuje needle (case-insensitive).

        Vrátí první match nebo None.
        """
        if not needle:
            return None
        needle_lc = needle.lower()
        for r in self.list_room_resources():
            name_lc = (r.get("name") or "").lower()
            gen_lc = (r.get("generated_name") or "").lower()
            if needle_lc in name_lc or needle_lc in gen_lc:
                return r.get("email") or None
        return None
