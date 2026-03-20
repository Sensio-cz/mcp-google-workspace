import base64
from email.mime.text import MIMEText
from email.utils import parseaddr, formataddr
from email.header import Header
from typing import Any
from googleapiclient.discovery import build
from ..auth.context import get_current_google_credentials


class GmailService:
    def __init__(self):
        self._signature_cache: dict[str, str] = {}

    @property
    def service(self):
        """Build a Gmail service using the current user's credentials (per-request)."""
        creds = get_current_google_credentials()
        return build("gmail", "v1", credentials=creds)

    # --- Podpis ---

    def get_signature(self) -> str:
        """Nacte HTML podpis z Gmail settings."""
        if "primary" not in self._signature_cache:
            sendas = self.service.users().settings().sendAs().list(userId="me").execute()
            for sa in sendas.get("sendAs", []):
                if sa.get("isPrimary"):
                    self._signature_cache["primary"] = sa.get("signature", "")
                    break
        return self._signature_cache.get("primary", "")

    # --- Query ---

    def query_emails(self, query: str, max_results: int = 10) -> list[dict]:
        """Vyhledej emaily dle Gmail query syntaxe."""
        results = self.service.users().messages().list(
            userId="me", q=query, maxResults=max_results
        ).execute()
        messages = results.get("messages", [])
        return [self.get_email_by_id(m["id"]) for m in messages]

    def get_email_by_id(self, email_id: str) -> dict | None:
        """Ziskej detail emailu dle ID."""
        msg = self.service.users().messages().get(
            userId="me", id=email_id, format="full"
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

        body = self._extract_body(msg["payload"])

        return {
            "id": msg["id"],
            "threadId": msg["threadId"],
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "cc": headers.get("Cc", ""),
            "subject": headers.get("Subject", ""),
            "date": headers.get("Date", ""),
            "message_id": headers.get("Message-Id", ""),
            "in_reply_to": headers.get("In-Reply-To", ""),
            "references": headers.get("References", ""),
            "snippet": msg.get("snippet", ""),
            "body": body,
            "labelIds": msg.get("labelIds", []),
        }

    def _extract_body(self, payload: dict) -> str:
        """Extrahuj textovy obsah z MIME payloadu."""
        if payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            if part["mimeType"] == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            body = self._extract_body(part)
            if body:
                return body
        return ""

    # --- Helpers ---

    @staticmethod
    def _safe_to_header(raw_address: str) -> str:
        """Bezpecne zpracuj To header - oprava bugu s diakritikou."""
        name, addr = parseaddr(raw_address)
        if name:
            return formataddr((str(Header(name, "utf-8")), addr))
        return addr

    @staticmethod
    def _text_to_html(text: str) -> str:
        """Konvertuj plain text na HTML (zachovej radky)."""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")

    def _build_message(
        self,
        to: str,
        subject: str,
        body: str,
        signature_html: str | None,
        cc: list[str] | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
    ) -> MIMEText:
        """Sestav MIME zpravu s volitelnym podpisem a reply headers."""
        if signature_html:
            html_body = f"<div dir='ltr'>{self._text_to_html(body)}<br><br>{signature_html}</div>"
            msg = MIMEText(html_body, "html", "utf-8")
        else:
            msg = MIMEText(body, "plain", "utf-8")

        msg["To"] = self._safe_to_header(to)
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = ", ".join(self._safe_to_header(a) for a in cc)
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references
        return msg

    def _get_my_email(self) -> str:
        """Ziskej email aktualniho uzivatele."""
        profile = self.service.users().getProfile(userId="me").execute()
        return profile["emailAddress"]

    # --- Drafty ---

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        include_signature: bool = True,
    ) -> dict:
        """Vytvor draft s automatickym podpisem. Vraci URL na draft v Gmailu."""
        signature = self.get_signature() if include_signature else None
        msg = self._build_message(to, subject, body, signature, cc)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        draft = self.service.users().drafts().create(
            userId="me", body={"message": {"raw": raw}}
        ).execute()

        msg_id = draft["message"]["id"]
        return {
            "draft_id": draft["id"],
            "message_id": msg_id,
            "url": f"https://mail.google.com/mail/u/0/#drafts/{msg_id}",
        }

    def delete_draft(self, draft_id: str) -> dict:
        """Smaz draft."""
        self.service.users().drafts().delete(userId="me", id=draft_id).execute()
        return {"success": True}

    def send_draft(self, draft_id: str) -> dict:
        """Odesli draft."""
        result = self.service.users().drafts().send(
            userId="me", body={"id": draft_id}
        ).execute()
        return {"sent": True, "message_id": result["id"]}

    # --- Reply (OPRAVENY) ---

    def reply_to_email(
        self,
        email_id: str,
        reply_body: str,
        send: bool = False,
        reply_all: bool = False,
        include_signature: bool = True,
    ) -> dict:
        """Odpovez na email - jako draft nebo rovnou odesli. Vzdy ve vlaknu."""
        original = self.get_email_by_id(email_id)
        if not original:
            return {"error": True, "message": "Email nenalezen"}

        to = original["from"]
        cc = None
        if reply_all:
            cc_parts = []
            if original["cc"]:
                cc_parts.extend([a.strip() for a in original["cc"].split(",")])
            if original["to"]:
                cc_parts.extend([a.strip() for a in original["to"].split(",")])
            my_email = self._get_my_email()
            cc = [a for a in cc_parts if my_email not in a] or None

        subject = original["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        signature = self.get_signature() if include_signature else None
        msg = self._build_message(
            to=to,
            subject=subject,
            body=reply_body,
            signature_html=signature,
            cc=cc,
            in_reply_to=original["message_id"],
            references=original.get("references", original["message_id"]),
        )

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        message_body = {"raw": raw, "threadId": original["threadId"]}

        if send:
            result = self.service.users().messages().send(
                userId="me", body=message_body
            ).execute()
            return {"sent": True, "message_id": result["id"]}
        else:
            draft = self.service.users().drafts().create(
                userId="me", body={"message": message_body}
            ).execute()
            msg_id = draft["message"]["id"]
            return {
                "draft_id": draft["id"],
                "message_id": msg_id,
                "url": f"https://mail.google.com/mail/u/0/#drafts/{msg_id}",
            }

    # --- Send ---

    def send_email(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        include_signature: bool = True,
    ) -> dict:
        """Odesli email primo."""
        signature = self.get_signature() if include_signature else None
        msg = self._build_message(
            to=", ".join(to),
            subject=subject,
            body=body,
            signature_html=signature,
            cc=cc,
        )
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = self.service.users().messages().send(
            userId="me", body={"raw": raw}
        ).execute()
        return {"sent": True, "message_id": result["id"]}

    # --- Attachments ---

    def get_attachment(self, email_id: str, attachment_id: str) -> dict:
        """Stahni prilohu."""
        att = self.service.users().messages().attachments().get(
            userId="me", messageId=email_id, id=attachment_id
        ).execute()
        return {"data": att["data"], "size": att["size"]}

    # --- Labels / Modify ---

    def _modify_message(self, email_id: str, add_labels: list[str] | None = None, remove_labels: list[str] | None = None) -> dict:
        """Uprav labely zpravy."""
        body = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels
        self.service.users().messages().modify(
            userId="me", id=email_id, body=body
        ).execute()
        return {"success": True, "email_id": email_id}

    def mark_as_read(self, email_id: str) -> dict:
        """Oznac email jako precteny."""
        return self._modify_message(email_id, remove_labels=["UNREAD"])

    def mark_as_unread(self, email_id: str) -> dict:
        """Oznac email jako neprecteny."""
        return self._modify_message(email_id, add_labels=["UNREAD"])

    def archive(self, email_id: str) -> dict:
        """Archivuj email (odeber z inboxu)."""
        return self._modify_message(email_id, remove_labels=["INBOX"])

    def star(self, email_id: str) -> dict:
        """Pridej hvezdicku."""
        return self._modify_message(email_id, add_labels=["STARRED"])

    def unstar(self, email_id: str) -> dict:
        """Odeber hvezdicku."""
        return self._modify_message(email_id, remove_labels=["STARRED"])

    def add_label(self, email_id: str, label_id: str) -> dict:
        """Pridej label k emailu."""
        return self._modify_message(email_id, add_labels=[label_id])

    def remove_label(self, email_id: str, label_id: str) -> dict:
        """Odeber label z emailu."""
        return self._modify_message(email_id, remove_labels=[label_id])

    # --- Bulk ---

    def trash(self, email_id: str) -> dict:
        """Presun email do kose (obnovitelny 30 dni)."""
        self.service.users().messages().trash(userId="me", id=email_id).execute()
        return {"success": True, "trashed": email_id}

    def bulk_delete(self, message_ids: list[str]) -> dict:
        """Hromadne smazani emailu."""
        self.service.users().messages().batchDelete(
            userId="me", body={"ids": message_ids}
        ).execute()
        return {"deleted": len(message_ids)}
