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
│   │   ├── sealed.py        # Pečetění hodnot (Fernet) - client_id, kódy, tokeny
│   │   ├── credentials.py   # Načítání credentials (env → soubor → OAuth flow)
│   │   ├── oauth_flow.py    # Lokální PKCE OAuth flow (otevře prohlížeč)
│   │   ├── oauth_provider.py# Remote OAuth provider (proxy na Google pro claude.ai)
│   │   ├── token_store.py   # In-memory úložiště Google tokenů per user (remote)
│   │   └── context.py       # Request context - credentials přihlášeného uživatele
│   ├── services/
│   │   ├── gmail.py         # GmailService - 23 metod (query, reply, draft, labels, trash...)
│   │   ├── drive.py         # DriveService - 7 metod (search, read, upload, folder, delete)
│   │   ├── sheets.py        # SheetsService - 7 metod (create, read, write, append, clear, add/delete)
│   │   └── calendar.py      # CalendarService - události a místnosti
│   └── tools/
│       ├── gmail.py         # 16 Gmail tools (1 zakázán: bulk_delete)
│       ├── drive.py         # 6 Drive tools
│       ├── sheets.py        # 7 Sheets tools
│       └── calendar.py      # 6 Calendar tools
├── docs/nasazeni-a-klice.md  # Klíč na tokeny, adresa serveru, secret
├── tests/                    # pytest; `uv run --with pytest --with cryptography pytest tests/ -q`
├── Dockerfile               # Cloud Run deployment
├── pyproject.toml            # Verze, závislosti, entry point
├── CHANGELOG.md              # Historie změn
└── README.md                 # Dokumentace, tools inventář
```

## Tools inventář (35 aktivních: 16 Gmail + 6 Drive + 7 Sheets + 6 Calendar)

### Gmail (16)
| Tool | Popis |
|------|-------|
| `query_gmail_emails` | Vyhledej emaily (Gmail query syntax) |
| `gmail_get_message_details` | Detail emailu včetně těla |
| `gmail_get_attachment_content` | Stáhni přílohu (base64) |
| `create_gmail_draft` | Vytvoř draft s podpisem |
| `delete_gmail_draft` | Smaž draft |
| `gmail_send_draft` | Odešli draft |
| `gmail_reply_to_email` | Odpověz ve vláknu (draft/send), volitelně na jinou adresu (`to`) |
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
- OAuth Client ID je veřejný (Desktop app). **Client Secret v kódu NENÍ** a nesmí se
  tam vrátit: do 22. 9. 2026 tam stál jako výchozí hodnota a tenhle repozitář je
  veřejný. Bere se z `GOOGLE_WORKSPACE_CLIENT_SECRET` a pro lokální přihlášení je
  povinný - Google ho vyžaduje i při PKCE (změřeno 23. 9. 2026).

## Infrastruktura

### Cloud Run
- Projekt: Sensio OS Workspace - Stuart (mzdy-487615)
- Region: europe-west1
- URL: https://mcp-google-workspace-581084999054.europe-west1.run.app
- Doména: https://mcp-google-workspace.sensio.cz
- **Merge do `master` = nasazení na produkci.** Cloud Build trigger
  `cloudrun-mcp-google-workspace-europe-west1-Sensio-cz-mcp-gookmz` (region
  **europe-west1**, od 20. 3. 2026) po každém pushi do `master` sestaví image
  a nasadí novou revizi. Změřeno 26. 9. 2026: merge PR #8 v 11:12:21 UTC,
  build 11:12:25, revize `00037` v 11:13:55. Stejně se sestavil i merge PR #4
  (23. 9. 00:04 UTC).
  Od 23. do 26. 9. 2026 tu stálo, že auto-deploy neexistuje - `gcloud builds
  triggers list` **bez `--region`** hledá jen globální triggery a regionální
  nevidí. Při kontrole proto vždy s regionem:

  ```bash
  gcloud builds triggers list --region europe-west1 --project mzdy-487615
  gcloud builds list --region europe-west1 --project mzdy-487615 --limit 5
  ```

  Ověř pak, že běží nová revize: `gcloud run revisions list --service
  mcp-google-workspace --region europe-west1 --project mzdy-487615 --limit 3`.
  Ruční `gcloud run deploy mcp-google-workspace --source . --region
  europe-west1 --project mzdy-487615` je jen nouzová cesta (trigger nefunguje).

### OAuth
- Desktop klient: pro lokální použití. PKCE **i** client secret - Google secret
  vyžaduje i při PKCE, samotné PKCE mu nestačí (změřeno 23. 9. 2026).
- Web klient: pro Cloud Run remote (claude.ai connector). Jeho `client_id`
  i secret jsou v prostředí služby, ne v kódu.
- `MCP_TOKEN_KEY` (povinný pro HTTP režim) leží v Secret Manageru jako tajemství
  `mcp-token-key`. **Pozor: účet, který službu nasazuje, a účet, pod kterým běží,
  jsou dva různé** (změřeno 23. 9. 2026) a `secretAccessor` binding je jen na tom
  prvním. Než budeš upravovat práva ke klíči, **změř si, kdo ho čte**:
  `gcloud run services describe mcp-google-workspace --region europe-west1
  --format="value(spec.template.spec.serviceAccountName)"` a
  `gcloud secrets get-iam-policy mcp-token-key`. Jinak službu rozbiješ.
  Tohle nastavení je vedené k nápravě mimo repozitář (veřejný repo není místo
  na popis toho, jak jsou nastavená práva).
  Výměna klíče odhlásí všechny uživatele - podrobnosti v `docs/nasazeni-a-klice.md`.
- Scopes: gmail.readonly, gmail.send, gmail.compose, gmail.modify, drive, spreadsheets
