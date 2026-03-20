from typing import Any
from ..server import mcp
from ..services.gmail import GmailService

_gmail = None


def _get_gmail() -> GmailService:
    global _gmail
    if _gmail is None:
        _gmail = GmailService()
    return _gmail


@mcp.tool()
async def query_gmail_emails(query: str, max_results: int = 10) -> dict[str, Any]:
    """Vyhledej emaily v Gmailu. Pouzij Gmail query syntax (is:unread, from:, subject:, newer_than:7d)."""
    return {"emails": _get_gmail().query_emails(query, max_results)}


@mcp.tool()
async def gmail_get_message_details(email_id: str) -> dict[str, Any]:
    """Ziskej detail emailu vcetne tela zpravy."""
    result = _get_gmail().get_email_by_id(email_id)
    return result or {"error": True, "message": "Email nenalezen"}


@mcp.tool()
async def gmail_get_attachment_content(email_id: str, attachment_id: str) -> dict[str, Any]:
    """Stahni obsah prilohy emailu (base64)."""
    return _get_gmail().get_attachment(email_id, attachment_id)


@mcp.tool()
async def create_gmail_draft(
    to: str,
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> dict[str, Any]:
    """Vytvor draft emailu s automatickym podpisem. Vraci URL na draft v Gmailu."""
    return _get_gmail().create_draft(to, subject, body, cc, bcc)


@mcp.tool()
async def delete_gmail_draft(draft_id: str) -> dict[str, Any]:
    """Smaz draft emailu."""
    return _get_gmail().delete_draft(draft_id)


@mcp.tool()
async def gmail_send_draft(draft_id: str) -> dict[str, Any]:
    """Odesli existujici draft."""
    return _get_gmail().send_draft(draft_id)


@mcp.tool()
async def gmail_reply_to_email(
    email_id: str,
    reply_body: str,
    send: bool = False,
    reply_all: bool = False,
) -> dict[str, Any]:
    """Odpovez na email ve vlaknu. Default: vytvori draft (send=False). Automaticky prida podpis a zachova vlakno."""
    return _get_gmail().reply_to_email(email_id, reply_body, send=send, reply_all=reply_all)


@mcp.tool()
async def gmail_send_email(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
) -> dict[str, Any]:
    """Odesli email primo (bez draftu). Automaticky prida podpis."""
    return _get_gmail().send_email(to, subject, body, cc)


@mcp.tool()
async def gmail_mark_as_read(email_id: str) -> dict[str, Any]:
    """Oznac email jako precteny."""
    return _get_gmail().mark_as_read(email_id)


@mcp.tool()
async def gmail_mark_as_unread(email_id: str) -> dict[str, Any]:
    """Oznac email jako neprecteny."""
    return _get_gmail().mark_as_unread(email_id)


@mcp.tool()
async def gmail_archive(email_id: str) -> dict[str, Any]:
    """Archivuj email (odeber z inboxu)."""
    return _get_gmail().archive(email_id)


@mcp.tool()
async def gmail_star(email_id: str) -> dict[str, Any]:
    """Pridej hvezdicku k emailu."""
    return _get_gmail().star(email_id)


@mcp.tool()
async def gmail_unstar(email_id: str) -> dict[str, Any]:
    """Odeber hvezdicku z emailu."""
    return _get_gmail().unstar(email_id)


@mcp.tool()
async def gmail_add_label(email_id: str, label_id: str) -> dict[str, Any]:
    """Pridej label k emailu."""
    return _get_gmail().add_label(email_id, label_id)


@mcp.tool()
async def gmail_remove_label(email_id: str, label_id: str) -> dict[str, Any]:
    """Odeber label z emailu."""
    return _get_gmail().remove_label(email_id, label_id)


@mcp.tool()
async def gmail_bulk_delete_messages(message_ids: list[str]) -> dict[str, Any]:
    """Hromadne smaz emaily dle seznamu ID."""
    return _get_gmail().bulk_delete(message_ids)
