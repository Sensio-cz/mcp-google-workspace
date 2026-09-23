# Nasazení: klíč na tokeny, adresa serveru, secret

## Co se změnilo a proč

Server držel registrované klienty, auth kódy a vydané tokeny v paměti instance
a mapování na Google tokeny v `/tmp/mcp-tokens.json`. Cloud Run ale instanci po
nečinnosti uspí a při zátěži spustí další, takže token, který si claude.ai
uložil, po chvíli neznala žádná instance. Projevem bylo `invalid_token` při
každém volání nástroje, **zatímco v Connectors zůstala fajfka** — ta je o tokenu
u klienta, ne o paměti serveru.

Nově si server nepamatuje nic: každá vydaná hodnota nese svůj obsah
zašifrovaný klíčem serveru (`mcp_google_workspace/auth/sealed.py`). Je proto
jedno, která instance požadavek obslouží a kolikrát se služba restartuje.

## Tři proměnné prostředí

| Proměnná | Povinná | K čemu |
|---|---|---|
| `MCP_TOKEN_KEY` | **ano pro HTTP režim** | Klíč, kterým se pečetí tokeny. Bez něj server v HTTP režimu **nenastartuje** a řekne proč. Do 23. 9. 2026 to tu stálo, ale neplatilo to: proces naběhl a rozbilo se to až uživateli na `/register` chybou 500. Stdio běh klíč nepotřebuje. |
| `MCP_ADMIN_KEY` | doporučeno | Jediná ochrana stránky `/status/users`. Bez ní je ten výpis otevřený. |
| `MCP_SERVER_URL` | doporučeno | Adresa, kterou server o sobě hlásí v OAuth metadatech a posílá Googlu jako redirect. Výchozí je `https://mcp-google-workspace.sensio.cz`. |
| `GOOGLE_WORKSPACE_CLIENT_SECRET` | **ano vždy** | Secret OAuth klienta. **V kódu už není žádná výchozí hodnota.** Povinný i pro lokální (stdio) přihlášení - Google ho vyžaduje i při PKCE (změřeno 23. 9. 2026). Do té doby tu stálo „ano pro web klienta", což platilo jen zdánlivě. |

### Vygenerování klíče

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Ulož ho do Secret Manageru a připoj ke službě:

```bash
printf '%s' '<klic>' | gcloud secrets create mcp-token-key --data-file=-
gcloud run services update mcp-google-workspace --region europe-west1 \
  --update-secrets MCP_TOKEN_KEY=mcp-token-key:latest \
  --update-env-vars MCP_SERVER_URL=https://mcp-google-workspace.sensio.cz
```

**Výměna klíče odhlásí všechny uživatele** — všechny vydané tokeny naráz
přestanou platit a konektor se musí připojit znovu. Je to zároveň jediný způsob,
jak hromadně odvolat přístup.

## Co tahle změna vědomě neřeší

- **Jednotlivý token nejde odvolat.** Zapečetěný token platí, dokud nevyprší
  (přístupový hodinu, obnovovací 30 dní). Odvolání po jednom by potřebovalo
  sdílený seznam, tedy přesně tu paměť, kvůli které vznikl problém. Hromadné
  odvolání = výměna `MCP_TOKEN_KEY`.
- **Auth kód jde použít vícekrát** po dobu své platnosti (60 s), pokud ho někdo
  zachytí i s `code_verifier`. Na jedné instanci je to **zhoršení** proti
  původnímu stavu, kdy se kód po výměně z paměti smazal; na více instancích
  původní řešení naopak selhávalo úplně. Skutečná jednorázovost by potřebovala
  sdílené úložiště. Totéž platí pro `state` (platnost 10 minut, aby se člověk
  stihl přihlásit ke Googlu).
- **Řetěz obnovy má tvrdý strop 30 dní od prvního přihlášení.** Konektor se tedy
  po měsíci odpojí a chce nové přihlášení, i když se používá denně. Bez toho by
  každá obnova posunula platnost dál a uniklý token by platil navždy.
- **Registrace klienta (`client_id`) nemá konec platnosti** — zneplatní ji až
  výměna klíče.
- **`/revoke` zmizel z metadat.** Endpoint, který vrátí 200 a nic neudělá, je
  horší než žádný: člověk si myslí, že přístup ukončil.
- **Statistiky zůstávají v `/tmp`** a po uspání instance se část ztratí. Jsou to
  čísla do status stránky, ne přístup.

## Po nasazení ověř

```bash
curl -s https://mcp-google-workspace.sensio.cz/.well-known/oauth-authorization-server | head -c 200
```

V odpovědi musí být `mcp-google-workspace.sensio.cz`, ne `...run.app`. Pak
v claude.ai konektor odpoj a znovu připoj (staré tokeny jsou z jiné éry) a nech
zavolat některý nástroj.
