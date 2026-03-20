# mcp-google-workspace

![Status: Beta](https://img.shields.io/badge/status-beta-yellow)
![Version](https://img.shields.io/badge/version-0.2.1-blue)

MCP server pro Google Workspace (Gmail, Drive, Sheets) s automatickým OAuth flow a multi-user autentizací.

## Funkce

- **Gmail**: query, read, reply, draft, send, archive, star, trash - s automatickým podpisem
- **Google Drive**: search, read, upload, create folders, delete
- **Google Sheets**: read, write, append, clear, add/delete sheets
- **Auto OAuth**: při prvním použití se otevře prohlížeč pro Google přihlášení
- **Multi-user**: každý uživatel se přihlásí svým účtem (Cloud Run remote)
- **Reply fix**: správně zpracovává diakritiku v hlavičkách emailů

## Quick Start (lokální)

Přidejte do `.mcp.json`:

```json
{
  "mcpServers": {
    "google-workspace": {
      "command": "mcp-google-workspace"
    }
  }
}
```

Při prvním použití se otevře prohlížeč pro Google přihlášení. Token se uloží do `~/.config/mcp-google/credentials.json`.

## Cloud Run (remote)

MCP server běží na Cloud Run a je dostupný přes:

```
https://mcp-google-workspace.sensio.cz/mcp
```

### claude.ai Connector

1. Otevřete **claude.ai** - Settings - Connectors
2. Klikněte **Add custom connector**
3. Zadejte:
   - Name: `MCP Google Workspace Sensio`
   - URL: `https://mcp-google-workspace.sensio.cz/mcp`
4. Klikněte **Add** - otevře se Google přihlášení
5. Přihlaste se firemním účtem (@sensio.cz) a klikněte **Povolit**
6. Hotovo - Gmail, Drive a Sheets tools jsou dostupné

## Gmail Tools

| Tool | Popis |
|------|-------|
| `query_gmail_emails` | Vyhledej emaily (Gmail query syntax) |
| `gmail_get_message_details` | Detail emailu včetně těla |
| `gmail_get_attachment_content` | Stáhni přílohu (base64) |
| `create_gmail_draft` | Vytvoř draft s automatickým podpisem |
| `delete_gmail_draft` | Smaž draft |
| `gmail_send_draft` | Odešli existující draft |
| `gmail_reply_to_email` | Odpověz ve vláknu (draft nebo send) |
| `gmail_send_email` | Odešli email přímo |
| `gmail_mark_as_read` | Označ jako přečtené |
| `gmail_mark_as_unread` | Označ jako nepřečtené |
| `gmail_archive` | Archivuj (odeber z inboxu) |
| `gmail_star` | Přidej hvězdičku |
| `gmail_unstar` | Odeber hvězdičku |
| `gmail_add_label` | Přidej label |
| `gmail_remove_label` | Odeber label |
| `gmail_trash` | Přesuň do koše (obnovitelné 30 dní) |

## Drive Tools

| Tool | Popis |
|------|-------|
| `drive_search_files` | Vyhledej soubory |
| `drive_read_file_content` | Přečti obsah (Docs - markdown, Sheets - CSV) |
| `drive_create_folder` | Vytvoř složku |
| `drive_upload_file` | Nahraj soubor (base64) |
| `drive_delete_file` | Smaž soubor |
| `drive_list_shared_drives` | Vypiš sdílené disky |

## Sheets Tools

| Tool | Popis |
|------|-------|
| `sheets_create_spreadsheet` | Vytvoř spreadsheet |
| `sheets_read_range` | Přečti data (A1 notace) |
| `sheets_write_range` | Zapiš data |
| `sheets_append_rows` | Přidej řádky na konec |
| `sheets_clear_range` | Vymaž rozsah |
| `sheets_add_sheet` | Přidej list |
| `sheets_delete_sheet` | Smaž list |

## Konfigurace

Žádná konfigurace není potřeba. Volitelné env proměnné:

| Proměnná | Účel |
|----------|------|
| `GOOGLE_WORKSPACE_REFRESH_TOKEN` | Přeskočit OAuth flow (použít existující token) |
| `GOOGLE_WORKSPACE_CLIENT_ID` | Přepsat výchozí OAuth klienta |
| `GOOGLE_WORKSPACE_CLIENT_SECRET` | Přepsat výchozí OAuth klienta |
| `MCP_TRANSPORT` | `streamable-http` pro Cloud Run |

## Release Status

| Status | Význam |
|--------|--------|
| `alpha` | Interní testování, nestabilní |
| **`beta`** | **Aktuální - funkční, testováno interně** |
| `rc` | Release candidate, čeká na schválení |
| `stable` | Schváleno pro production |

## License

MIT - Sensio.cz s.r.o.
