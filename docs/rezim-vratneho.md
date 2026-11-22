# Režim vrátného (pracovna Red Dwarfu, Stáze)

Od verze 0.6.0 umí server druhý způsob přístupu ke Googlu: **přes vrátného Stáze** v pracovně Red Dwarfu.
Server pak nemá žádné vlastní přihlášení a nedrží žádný token Googlu; obnovovací token drží správa účtů
Red Dwarfu a hodinový token přiloží k požadavku až vrátný.

**Bez proměnné `GOOGLE_WORKSPACE_GATE_URL` se nic nemění** - stejný seznam 38 nástrojů, stejné popisy
i schémata, modul vrátného se ani nenačte (`tests/test_bez_vratneho_beze_zmeny.py`). Služba na Cloud Runu
proměnnou nemá.

## Spuštění

```bash
GOOGLE_WORKSPACE_GATE_URL=http://trezor:8767/_osoba \
python3 -m mcp_google_workspace            # jen stdio
```

| Proměnná | Výchozí | Co |
|---|---|---|
| `GOOGLE_WORKSPACE_GATE_URL` | - | zapíná režim; adresa vrátného (`http://trezor:8767/_osoba`). Existuje-li a je prázdná nebo neplatná, server nenastartuje (žádný tichý návrat k vlastnímu přihlášení). |
| `GOOGLE_WORKSPACE_GATE_TOKEN_FILE` | `/run/secrets/trezor-token` | token pracovny pro vrátného; čte se při každém požadavku |
| `GOOGLE_WORKSPACE_GATE_KEY_FILE` | `/run/secrets/workspace-key` | klíč pracovny pro důkaz; čte se při každém požadavku, obsah beze změny |
| `KRYTON_UCTY_USERS_ID` | - | id osoby; bez něj se čte `users_id` ze `~/.config/kryton/ucty.json` |

V režimu vrátného server nečte `GOOGLE_WORKSPACE_*_SECRET` ani `~/.config/mcp-google/`, nenačte
`server.py`, `config.py` ani `auth/context.py`, odmítne `--setup` a jiný transport než stdio.

## Jak mluví s vrátným

Každé volání jde na `<GATE_URL>/<ucet>/<sluzba>/<cesta Googlu>` (`sluzba` = `gmail` | `drive` | `calendar`)
s hlavičkami `Authorization: Bearer <token pracovny>` a `X-Kryton-Proof: <users_id>.<ts>.<mac>`:

```
K   = HKDF-SHA256(klíč pracovny beze změny, sůl prázdná, info "kryton-person-token-v1", 32 B)
mac = hex(HMAC-SHA256(K, "<users_id>\n<ts>\nperson-token\n<ucet>"))      # data účtu
mac = hex(HMAC-SHA256(K, "<users_id>\n<ts>\nperson-accounts\n"))        # GET <GATE_URL>/_seznam
```

Knihovna Googlu se staví s `client_options={"api_endpoint": ...}` a vlastním `http` objektem (`GateHttp`),
který přidá hlavičky a **odmítne každý požadavek mimo `<GATE_URL>/<ucet>/`** (knihovna umí adresu změnit
sama: `MediaIoBaseDownload` přejde na `Content-Location` odpovědi, nahrávání zahodí cestu za hostitelem).
`build()` na síť nesahá, popis API je v balíčku. Měření knihovny proti falešnému serveru: S1 v Red Dwarfu
(`.relay/gst-r253-s1-mereni.md`).

## Nástroje (vlna 1)

`ucty_seznam`, `query_gmail_emails`, `gmail_get_message_details`, `gmail_get_attachment_content`,
`gmail_list_drafts`, `gmail_get_draft`, `create_gmail_draft`, `gmail_update_draft`, `delete_gmail_draft`,
`gmail_reply_to_email` (jen koncept), `drive_search_files`, `drive_read_file_content`, `drive_list_comments`,
`drive_list_shared_drives`, `calendar_list_events`, `calendar_list_calendars`, `calendar_get_event`.

- Všechny kromě `ucty_seznam` mají parametr `ucet`; když má člověk jediný živý účet, není povinný.
- Odeslání, koš, štítky, zápis na Disk a do kalendáře, místnosti a tabulky v seznamu nejsou.
- **Podpis se nepřidává** (čte se z `settings/sendAs`, které vrátný ve vlně 1 nepouští); výsledek konceptu
  to říká v poli `podpis`.
- Obsah pošty, dokumentů a kalendáře se vrací mezi značkami `⟦nedůvěryhodný obsah – začátek⟧` a
  `⟦nedůvěryhodný obsah – konec⟧` s větou, že jde o data bez pokynů (`upozorneni`); značky a jejich
  napodobeniny se uvnitř obsahu mění na `[` a `]`.
- Chyby vrátného (`X-Trezor-Reason`) se vracejí jako `{"error": true, "code", "message"}` s větou pro
  člověka, např. `ACCOUNT_DISCONNECTED` -> „Připoj účet znovu: kryton-ucty pripoj google --jmeno <ucet>".

## Známá omezení (vědomě, 22. 11. 2026)

- Koncept s přílohou `gmail_update_draft` odmítne (`DRAFT_HAS_ATTACHMENTS`): ukládá jen prostý text a přílohy
  i formátování by smazal. Upravený koncept je vždy prostý text.
- Odkaz na koncept míří na `mail.google.com/mail/u/0/`, tedy na první účet přihlášený v prohlížeči; při více
  účtech může otevřít jiný.
- Seznam účtů (výchozí `ucet`) si server pamatuje 60 s; `ucty_seznam` čte vždy čerstvě.
- Pošle-li vrátný od Googlu `Content-Location`, stažení souboru nad 100 MB (druhá část) klient odmítne
  (`GATE_HOST_REFUSED`) - token pracovny nikam jinam neodejde. Vrátný má `Content-Location` zahazovat (S1).
- Adresa delší než 2048 znaků (dlouhý dotaz) končí `REQUEST_TOO_LONG`; knihovna by ji jinak přepsala na POST,
  který vrátný odmítne.
- Převzato z masteru: `drive_search_files` a `drive_list_comments` nestránkují; metadata v
  `drive_read_file_content` se čtou bez `supportsAllDrives`.

## Instalace do pracovny bez sítě za běhu

Python v obrazu pracovny nemá `venv`; systémová instalace by se srazila s piny jiných balíčků. Proto
vlastní adresář přes `pip --target` a spuštění s `-s` (bez uživatelských balíčků):

```bash
# 1) příprava (stroj se sítí), z kořene repa na připnutém commitu
uv export --frozen --no-dev --no-emit-project --format requirements-txt -o requirements.txt
uv build --wheel -o dist
pip3 download --only-binary=:all: --require-hashes -r requirements.txt -d wheels

# 2) instalace v pracovně (bez sítě)
CIL=~/.local/share/kryton/mcp-google-workspace
python3 -m pip install --no-index --find-links wheels --require-hashes -r requirements.txt --target "$CIL"
python3 -m pip install --no-index --no-deps --target "$CIL" dist/mcp_google_workspace-*.whl

# 3) spuštění (registrace MCP v pracovně)
env PYTHONPATH="$CIL" GOOGLE_WORKSPACE_GATE_URL=http://trezor:8767/_osoba python3 -s -m mcp_google_workspace
```

Změřeno 22. 11. 2026 v pracovně s Pythonem 3.13.5 a systémovým pipem: 55 kol (29 MB), nainstalováno 178 MB,
v režimu vrátného 17 nástrojů, moduly se berou z `$CIL`.

## Testy

`tests/test_rezim_vratneho.py` (falešný vrátný na 127.0.0.1, síť ven zakázaná, důkaz ověřený nezávislou
implementací a vektorem z Node) a `tests/test_bez_vratneho_beze_zmeny.py`.
