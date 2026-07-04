# Slack FollowUp Agent

Extracts grounded action items from a pasted meeting transcript and posts them to a Slack channel, resolving owner names to Slack user IDs via Slack's official MCP server.

## Local setup

1. Create a Slack app from `manifest.json` (or update an existing one via **App Manifest**).
2. Before uploading the manifest, replace the `${NGROK_URL}` placeholder in `oauth_config.redirect_urls` with your actual ngrok tunnel host (e.g. `abcd1234.ngrok-free.app`), and replace the `https://example.com/...` placeholders with the same tunnel for the events/interactivity request URLs.
3. Fill in the `.env` file at the repo root (already gitignored — never commit it with real values) with:
   - `SLACK_CLIENT_ID`, `SLACK_CLIENT_SECRET` — from the app's **Basic Information** page, used for the OAuth install flow.
   - `SLACK_SIGNING_SECRET` — from **Basic Information**.
   - `SLACK_APP_TOKEN` — an app-level token (`xapp-...`) with `connections:write`, used for Socket Mode.
   - `GEMINI_API_KEY` — for LLM-based action extraction.
   - Optional: `SLACK_OAUTH_PORT` (default `3000`), `SLACK_INSTALLATION_DIR`, `SLACK_OAUTH_STATE_DIR` — override the local file paths/port used for the install flow.

   `app/main.py` loads `.env` automatically on startup via `python-dotenv`.
4. Run `python -m app.main`. This starts two things in the same process:
   - A Socket Mode connection (handles the `/extract-actions` command, modal submission, and posting).
   - A local Flask server on `SLACK_OAUTH_PORT` serving `/slack/install` and `/slack/oauth_redirect`, so the OAuth install flow has a real HTTP endpoint to hit.
5. Point ngrok at `SLACK_OAUTH_PORT` and visit `https://<ngrok-host>/slack/install` to run through the install flow. Installations (including the per-user `xoxp-...` token) are stored as files under `SLACK_INSTALLATION_DIR` — this is a hackathon-scope store, not meant for production multi-tenant use.

## Enabling MCP access

Slack's MCP server (`mcp.slack.com`) is not turned on by the app manifest — after installing the app, a workspace admin must also flip on **Agents & AI Apps** access for it in the Slack app management settings (the sidebar toggle under the app's configuration), or `mcp.slack.com` will reject requests even with a valid `search:read.users`-scoped user token.
