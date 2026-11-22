"""Bez GOOGLE_WORKSPACE_GATE_URL se server chova presne jako pred rezimem vratneho (kontrakt C5).

Rezim vratneho (Stáze v pracovne Red Dwarfu) se zapina jen promennou. Sluzba Sensia na
Cloud Runu ji nema, takze se pro ni nesmi zmenit nic: stejny seznam 38 nastroju, stejne
popisy i schemata (otisk nize) a modul vratneho se ani nenaimportuje.

OTISK SEZNAMU NASTROJU je sha256 z `list_tools()` (jmena, popisy, vstupni a vystupni
schemata) zmereny 22. 11. 2026 na master e3a1e90 s mcp 1.30.0 z uv.lock. Kdyz se zmeni
nastroj zamerne nebo se povysi `mcp` (jine generovani schemat), otisk se prepocita na
masteru bez rezimu vratneho a zapise sem s datem.
"""

import json
import os
import subprocess
import sys

OTISK_MASTER = "6efb0d7c4bb49900f2affe2763c6665f5821c1bedb91aa97dfc96af168c627f4"

NASTROJE_MASTER = [
    "calendar_create_event", "calendar_delete_event", "calendar_find_room_email", "calendar_list_events",
    "calendar_list_rooms", "calendar_patch_event", "create_gmail_draft", "delete_gmail_draft",
    "drive_create_comment", "drive_create_folder", "drive_delete_file", "drive_list_comments",
    "drive_list_shared_drives", "drive_read_file_content", "drive_search_files", "drive_update_file_content",
    "drive_upload_file", "gmail_add_label", "gmail_archive", "gmail_get_attachment_content",
    "gmail_get_message_details", "gmail_mark_as_read", "gmail_mark_as_unread", "gmail_remove_label",
    "gmail_reply_to_email", "gmail_send_draft", "gmail_send_email", "gmail_star", "gmail_trash",
    "gmail_unstar", "query_gmail_emails", "sheets_add_sheet", "sheets_append_rows", "sheets_clear_range",
    "sheets_create_spreadsheet", "sheets_delete_sheet", "sheets_read_range", "sheets_write_range",
]

SKRIPT = r"""
import asyncio, hashlib, json, sys
import mcp_google_workspace.__main__ as m
ts = asyncio.run(m.mcp.list_tools())
d = [t.model_dump(mode='json') for t in sorted(ts, key=lambda t: t.name)]
print(json.dumps({
    "jmena": [t.name for t in sorted(ts, key=lambda t: t.name)],
    "otisk": hashlib.sha256(json.dumps(d, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
    "moduly": sorted(k for k in sys.modules if k.startswith("mcp_google_workspace")),
}))
"""


def _bez_vratneho():
    env = {k: v for k, v in os.environ.items() if not k.startswith("GOOGLE_WORKSPACE_GATE")}
    env.pop("KRYTON_UCTY_USERS_ID", None)
    vystup = subprocess.run([sys.executable, "-c", SKRIPT], env=env, capture_output=True, text=True, timeout=120)
    assert vystup.returncode == 0, vystup.stderr
    return json.loads(vystup.stdout.strip().splitlines()[-1])


def test_bez_promenne_je_seznam_nastroju_stejny_jako_na_masteru():
    v = _bez_vratneho()
    assert v["jmena"] == NASTROJE_MASTER
    assert v["otisk"] == OTISK_MASTER, "zmenil se popis nebo schema nektereho nastroje bez rezimu vratneho"


def test_bez_promenne_se_modul_vratneho_ani_nenaimportuje():
    moduly = _bez_vratneho()["moduly"]
    assert "mcp_google_workspace.auth.gate" not in moduly
    assert "mcp_google_workspace.gate_app" not in moduly
