## Summary
<!-- Stručně popiš, co tento PR řeší -->

## Changes
<!-- Seznam změn -->
- [ ] Změna 1
- [ ] Změna 2

## Testing
- [ ] Lokální MCP server se spustí (`mcp-google-workspace`)
- [ ] Gmail tools fungují (query, reply, draft)
- [ ] Drive tools fungují (search, read)
- [ ] Sheets tools fungují (read, write)
- [ ] Merge = nasazení (Cloud Build trigger v europe-west1). Po merge ověřit novou revizi: `gcloud run revisions list --service mcp-google-workspace --region europe-west1 --project mzdy-487615 --limit 3`
- [ ] Status stránka ukazuje správnou verzi

## Checklist
- [ ] CHANGELOG.md aktualizován
- [ ] Verze v pyproject.toml bumpnuta
- [ ] Žádné hardcoded credentials (kromě Desktop OAuth Client ID)
- [ ] Žádné osobní údaje v kódu (GDPR)
