# CLAUDE.md - mcp-google-workspace

MCP server pro Google Workspace (Gmail, Drive, Sheets) s multi-user OAuth autentizací.

## Struktura

```
mcp-google-workspace/
├── mcp_google_workspace/
│   ├── __main__.py          # Entry point (stdio + HTTP transport, --setup CLI)
│   ├── server.py            # FastMCP instance, OAuth provider, status stránka, /google/callback
│   ├── config.py            # OAuth Client ID/Secret, cesty k credentials
│   ├── auth/
│   │   ├── credentials.py   # Načítání credentials (env → soubor → OAuth flow)
│   │   ├── oauth_flow.py    # Lokální PKCE OAuth flow (otevře prohlížeč)
│   │   ├── oauth_provider.py# Remote OAuth provider (proxy na Google pro claude.ai)
│   │   ├── token_store.py   # In-memory úložiště Google tokenů per user (remote)
│   │   └── context.py       # Request context - credentials přihlášeného uživatele
│   ├── services/
│   │   ├── gmail.py         # GmailService - 23 metod (query, reply, draft, labels, trash...)
│   │   ├── drive.py         # DriveService - 7 metod (search, read, upload, folder, delete)
│   │   └── sheets.py        # SheetsService - 7 metod (create, read, write, append, clear, add/delete)
│   └── tools/
│       ├── gmail.py         # 16 Gmail tools (1 zakázán: bulk_delete)
│       ├── drive.py         # 6 Drive tools
│       └── sheets.py        # 7 Sheets tools
├── Dockerfile               # Cloud Run deployment
├── pyproject.toml            # Verze, závislosti, entry point
├── CHANGELOG.md              # Historie změn
└── README.md                 # Dokumentace, tools inventář
```

## Tools inventář (28 aktivních)

### Gmail (16)
| Tool | Popis |
|------|-------|
| `query_gmail_emails` | Vyhledej emaily (Gmail query syntax) |
| `gmail_get_message_details` | Detail emailu včetně těla |
| `gmail_get_attachment_content` | Stáhni přílohu (base64) |
| `create_gmail_draft` | Vytvoř draft s podpisem |
| `delete_gmail_draft` | Smaž draft |
| `gmail_send_draft` | Odešli draft |
| `gmail_reply_to_email` | Odpověz ve vláknu (draft/send) |
| `gmail_send_email` | Odešli email přímo |
| `gmail_mark_as_read` | Označ jako přečtené |
| `gmail_mark_as_unread` | Označ jako nepřečtené |
| `gmail_archive` | Archivuj (odeber z inboxu) |
| `gmail_star` | Přidej hvězdičku |
| `gmail_unstar` | Odeber hvězdičku |
| `gmail_add_label` | Přidej label |
| `gmail_remove_label` | Odeber label |
| `gmail_trash` | Přesuň do koše (obnovitelné 30 dní) |

### Drive (6)
| Tool | Popis |
|------|-------|
| `drive_search_files` | Vyhledej soubory |
| `drive_read_file_content` | Přečti obsah (Docs → markdown, Sheets → CSV) |
| `drive_create_folder` | Vytvoř složku |
| `drive_upload_file` | Nahraj soubor (base64) |
| `drive_delete_file` | Smaž soubor (do koše) |
| `drive_list_shared_drives` | Vypiš sdílené disky |

### Sheets (7)
| Tool | Popis |
|------|-------|
| `sheets_create_spreadsheet` | Vytvoř spreadsheet |
| `sheets_read_range` | Přečti data (A1 notace) |
| `sheets_write_range` | Zapiš data |
| `sheets_append_rows` | Přidej řádky na konec |
| `sheets_clear_range` | Vymaž rozsah |
| `sheets_add_sheet` | Přidej list |
| `sheets_delete_sheet` | Smaž list |

## Pravidla

### Verzování
- Semantic Versioning (semver): MAJOR.MINOR.PATCH
- Verze v `pyproject.toml`
- Každý release má záznam v CHANGELOG.md

### Commit messages
- V češtině, stručné
- Formát: `Oblast: popis změny`

### Release Status

| Status | Význam | Kdo mění | Kritéria |
|--------|--------|----------|----------|
| `alpha` | Nestabilní, interní | AI agent | Základní funkčnost |
| `beta` | Funkční, testováno | AI agent | Všechny tools, 1+ uživatel |
| `rc` | Release candidate | AI agent | 2+ uživatelé, 0 bugů/týden, docs hotové |
| `stable` | Production ready | **Pouze člověk** | Explicitní schválení vlastníkem |

**Aktuální: beta**

### Bezpečnost
- `gmail_bulk_delete_messages` je záměrně zakázán (mazal natrvalo)
- `gmail_trash` přesouvá do koše (obnovitelné 30 dní)
- GDPR: nikdy nezveřejňovat osobní údaje v externích systémech
- OAuth Client ID je veřejný (Desktop app), Client Secret je v kódu (standardní praxe pro desktop apps)

## Infrastruktura

### Cloud Run
- Projekt: Sensio OS Workspace - Stuart (mzdy-487615)
- Region: europe-west1
- URL: https://mcp-google-workspace-581084999054.europe-west1.run.app
- Doména: https://mcp-google-workspace.sensio.cz
- Auto-deploy: push na master → Cloud Build → Cloud Run

### OAuth
- Desktop klient: pro lokální použití (PKCE flow)
- Web klient: pro Cloud Run remote (claude.ai connector)
- Scopes: gmail.readonly, gmail.send, gmail.compose, gmail.modify, drive, spreadsheets
