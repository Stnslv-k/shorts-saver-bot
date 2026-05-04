# YouTube Shorts Bot

A Telegram bot that processes YouTube Shorts links, extracts structured knowledge with an LLM, and saves it to Notion or Obsidian.

## Quick start

### 1. Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`ffmpeg` must also be installed on the host for the yt-dlp fallback:

```bash
# macOS
brew install ffmpeg

# Debian/Ubuntu
sudo apt-get install ffmpeg
```

### 2. Configure

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` with your credentials:

| Key | Description |
|-----|-------------|
| `bot.token` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `bot.password` | Shared password users must enter once |
| `llm.backend` | `ollama`, `openai`, or `anthropic` |
| `llm.fallback` | Optional secondary backend if primary fails |
| `storage.backend` | `notion` or `obsidian` |

### 3. Run

```bash
python -m bot.main
```

Or with Docker:

```bash
docker compose up -d
```

## Authentication flow

1. User sends `/start` to the bot
2. Bot prompts for the password
3. User sends the password; on success their Telegram user ID is stored in `data/users.db`
4. Authenticated users never need to enter the password again

## Transcript pipeline

1. **Primary** — `youtube-transcript-api` fetches existing captions (fast, no download)
2. **Fallback** — if no captions exist, `yt-dlp` downloads the audio and `faster-whisper` transcribes it locally

## LLM extraction

The LLM receives the full transcript and returns structured JSON:

- `title` — concise title
- `category` — `github` / `recipe` / `tool` / `article` / `general`
- `summary` — 2–3 sentence summary
- `github_repos` — repos mentioned (explicit URLs or spoken as "github dot com slash ...")
- `recipe` — ingredients + steps if applicable
- `tools` — software tools/apps named
- `tags` — 3–5 descriptive tags

### Backends

| Backend | Config key | Notes |
|---------|-----------|-------|
| Ollama | `llm.ollama` | Local, free. Needs Ollama running |
| OpenAI | `llm.openai` | GPT-4o-mini is cost-effective |
| Anthropic | `llm.anthropic` | Claude Haiku is fast and cheap |

Set `llm.fallback` to a second backend so extraction never silently fails.

## Storage backends

### Notion

Create an integration at <https://www.notion.so/my-integrations> and share your database with it.

Required database properties:

| Property | Type |
|----------|------|
| Name | Title |
| Category | Select |
| Summary | Text |
| Source URL | URL |
| Extracted At | Date |
| Tags | Multi-select |
| Tools | Text |

### Obsidian

Set `storage.obsidian.vault_path` to an absolute path inside your vault. Notes are written as Markdown files with YAML frontmatter.

## Project structure

```
bot/
  main.py        — aiogram bot, handlers, FSM auth
  auth.py        — SQLite authentication
  processor.py   — transcript → LLM → storage pipeline
  models.py      — KnowledgeEntry, ExtractionResult dataclasses
  config.py      — config.yaml loading
  llm/
    base.py      — LLMBackend ABC + extraction prompt
    ollama.py    — Ollama adapter
    openai.py    — OpenAI adapter
    anthropic.py — Anthropic adapter
  storage/
    base.py      — StorageBackend ABC
    notion.py    — Notion adapter
    obsidian.py  — Obsidian adapter
data/            — runtime data (gitignored)
  users.db       — authenticated user IDs
```
