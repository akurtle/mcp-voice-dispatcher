# MCP Voice Dispatcher

Voice-first automation prototype that records microphone input, transcribes it with OpenAI, maps the transcript into typed MCP tool calls, and executes those calls against a local Node-based MCP server that proxies Notion and Gmail REST APIs.

## What it does

- Captures a short microphone clip or accepts a WAV file.
- Transcribes speech with OpenAI speech-to-text.
- Routes intent with schema-enforced structured outputs.
- Discovers available MCP tools dynamically over stdio.
- Calls Gmail and Notion backends through a Node.js MCP server.

## Architecture

1. `mcp_voice_dispatcher.audio` records a mono WAV clip from the system microphone.
2. `mcp_voice_dispatcher.transcriber` sends that file to OpenAI's transcription API.
3. `mcp_voice_dispatcher.router` selects a context-aware prompt template and parses a typed `RoutedIntent` with `responses.parse`.
4. `mcp_voice_dispatcher.mcp_client` launches `src/mcp_server/index.js`, performs MCP initialization, lists tools, and calls the selected tool.
5. `src/mcp_server/index.js` exposes `gmail_send_email` and `notion_create_page` as MCP tools backed by Gmail and Notion REST APIs.

## Quickstart

### 1. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
npm install
```

### 2. Configure secrets

Copy `.env.example` to `.env` and fill in:

- `OPENAI_API_KEY`
- `NOTION_API_TOKEN`
- `NOTION_DATABASE_ID`
- `GMAIL_ACCESS_TOKEN`
- `GMAIL_FROM_EMAIL`
- optional tuning such as `MCP_POOL_SIZE` for the number of long-lived MCP stdio sessions

### 3. Run the dashboard

```bash
python -m mcp_voice_dispatcher serve --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000` to:

- record audio directly from the browser
- upload an audio file for transcription and routing
- test typed commands before you speak them
- review confidence against an execution threshold
- edit the generated Gmail or Notion payload before approval
- explicitly approve the MCP tool call before any side effect occurs

### 4. Run the CLI

Record from the microphone:

```bash
python -m mcp_voice_dispatcher listen
```

Dispatch an existing WAV file:

```bash
python -m mcp_voice_dispatcher dispatch --audio .\samples\demo.wav
```

Preview routing without sending anything:

```bash
python -m mcp_voice_dispatcher listen --dry-run
```

List tools exposed by the MCP server:

```bash
python -m mcp_voice_dispatcher tools
```

## Example commands

- "Email Sarah and Jamal that the deployment moved to Friday at 2 PM."
- "Create a Notion note called Sprint Retro with bullets for wins, blockers, and action items."

## Technical debt called out explicitly

- No retry layer for OpenAI, Notion, or Gmail requests yet.
- Edge-case disambiguation still depends on a clarification branch rather than multi-turn recovery.
- Auth is env-token based and should move to hardened OAuth flows or secret storage.
- MCP rate limiting and queueing are not implemented yet.
- Approval state is currently an in-memory store, so pending reviews do not survive process restarts.

## Notes

- The Python router uses OpenAI structured outputs with a Pydantic schema for typed intent objects.
- The Node server keeps REST integrations isolated behind MCP tools so the Python app never needs backend-specific HTTP logic.
- The current microphone workflow records a fixed-duration clip for simplicity.
- The dashboard uses FastAPI plus a lightweight browser client so users can interact with the prototype without touching the terminal.
