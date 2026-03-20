# mcp-google-workspace

MCP server for Google Workspace (Gmail, Drive, Sheets) with automatic OAuth flow and Gmail signature support.

## Features

- **Gmail**: query, read, reply, draft, send, bulk delete - with automatic signature
- **Google Drive**: search, read, upload, create folders, delete
- **Google Sheets**: read, write, append, clear, add/delete sheets
- **Auto OAuth**: opens browser on first run, no manual token setup
- **Reply fix**: correctly handles non-ASCII characters in email headers

## Quick Start

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "google-workspace": {
      "command": "uvx",
      "args": ["mcp-google-workspace"]
    }
  }
}
```

On first run, a browser window opens for Google sign-in. After authorization, the token is saved locally to `~/.config/mcp-google/credentials.json`.

## Configuration

No configuration needed for most users. Optional environment variables:

| Variable | Purpose |
|----------|---------|
| `GOOGLE_WORKSPACE_REFRESH_TOKEN` | Skip OAuth flow (use existing token) |
| `GOOGLE_WORKSPACE_CLIENT_ID` | Override default OAuth client |
| `GOOGLE_WORKSPACE_CLIENT_SECRET` | Override default OAuth client |

## Gmail Tools

| Tool | Description |
|------|-------------|
| `query_gmail_emails` | Search emails (Gmail query syntax) |
| `gmail_get_message_details` | Get full email details |
| `gmail_get_attachment_content` | Download attachment |
| `create_gmail_draft` | Create draft with signature |
| `delete_gmail_draft` | Delete a draft |
| `gmail_send_draft` | Send existing draft |
| `gmail_reply_to_email` | Reply in thread (draft or send) |
| `gmail_send_email` | Send email directly |
| `gmail_bulk_delete_messages` | Bulk delete emails |

## Drive Tools

| Tool | Description |
|------|-------------|
| `drive_search_files` | Search files |
| `drive_read_file_content` | Read file content |
| `drive_create_folder` | Create folder |
| `drive_upload_file` | Upload file |
| `drive_delete_file` | Delete file |
| `drive_list_shared_drives` | List shared drives |

## Sheets Tools

| Tool | Description |
|------|-------------|
| `sheets_create_spreadsheet` | Create new spreadsheet |
| `sheets_read_range` | Read data range |
| `sheets_write_range` | Write data range |
| `sheets_append_rows` | Append rows |
| `sheets_clear_range` | Clear range |
| `sheets_add_sheet` | Add sheet tab |
| `sheets_delete_sheet` | Delete sheet tab |

## License

MIT - Sensio.cz s.r.o.
