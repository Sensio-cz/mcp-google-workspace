# Changelog

Všechny podstatné změny v projektu mcp-google-workspace.

Formát: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), verzování: [Semantic Versioning](https://semver.org/).

## [0.2.10] - 21. 3. 2026, 00:30

### Přidáno
- Admin odkazy v `/status/users` (GitHub, Cloud Build, Cloud Run, Logs, OAuth)

## [0.2.9] - 21. 3. 2026, 00:20

### Opraveno
- Odstranění admin odkazů (GitHub, Cloud Run) z veřejné status stránky

## [0.2.8] - 21. 3. 2026, 00:15

### Opraveno
- HTMLResponse import error na `/status/users` (UnboundLocalError)

## [0.2.7] - 21. 3. 2026, 00:10

### Opraveno
- Bezpečná 403 stránka bez nápovědy pro útočníka (žádný hint na `?key=`)

## [0.2.6] - 20. 3. 2026, 23:30

### Přidáno
- `/status/users` - admin stránka se statistikami uživatelů (chráněno API klíčem)
- Denní historie tool callů per uživatel
- Tracking: počet tool callů, chyb, první/poslední přístup per uživatel
- Persistované statistiky v `mcp-stats.json`

## [0.2.2] - 20. 3. 2026, 22:30

### Přidáno
- Logování: [AUTH] přihlášení uživatele (email), [TOOL] volání tools (email)
- Logy viditelné v Cloud Run Logs Explorer

## [0.2.1] - 20. 3. 2026, 22:15

### Přidáno
- CHANGELOG.md, CLAUDE.md, PR šablona
- Release status systém (alpha → beta → rc → stable)
- Aktualizovaný README s kompletním seznamem tools

## [0.2.0] - 20. 3. 2026, 19:30

### Přidáno
- Multi-user OAuth autentizace (Google proxy pro claude.ai)
- Cloud Run deployment s auto-build z GitHubu
- Gmail tools: `gmail_mark_as_read`, `gmail_mark_as_unread`, `gmail_archive`, `gmail_star`, `gmail_unstar`, `gmail_add_label`, `gmail_remove_label`, `gmail_trash`
- Status stránka na root URL (verze, počet tools, odkazy)
- Lokální auto OAuth flow (otevře prohlížeč při prvním použití)
- GDPR pravidlo v SOUL.md (Sensio OS)
- OAuth success stránka v Sensio vizuálu

### Opraveno
- Reply bug: diakritika v To header (lowercase "to" vs "To")
- Automatický Gmail podpis v draftech

### Odstraněno
- `gmail_bulk_delete_messages` - mazal natrvalo, bezpečnostní riziko

## [0.1.0] - 20. 3. 2026, 17:00

### Přidáno
- Gmail tools: query, read, draft, reply, send, attachment
- Google Drive tools: search, read, upload, create folder, delete, shared drives
- Google Sheets tools: create, read, write, append, clear, add/delete sheet
- Auto OAuth flow s PKCE (otevře prohlížeč, uloží token)
- Oprava reply bugu z google-workspace-mcp (diakritika v hlavičkách)
- Automatický Gmail podpis
- Dockerfile pro Cloud Run
