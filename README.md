# YouTube Shorts Bot

A Telegram bot that processes YouTube Shorts links, extracts structured knowledge with an LLM, and saves it to Notion or Obsidian.

## What it does

1. Send a YouTube Shorts URL to your private Telegram bot.
2. The bot fetches captions or downloads audio and transcribes it locally with Whisper.
3. Optional Vision support analyzes keyframes when the important content is on screen.
4. An LLM extracts a structured knowledge entry.
5. The entry is saved to Notion or an Obsidian-compatible Markdown folder.

## Requirements

- Python 3.11+
- `ffmpeg` and `ffprobe`
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- At least one LLM backend: Ollama, OpenAI, Anthropic, or OpenRouter
- One storage backend: Notion database or an Obsidian vault path

## Quick start

### 1. Install system dependencies

`ffmpeg` must be installed for fallback audio download/transcription and Vision keyframe extraction:

```bash
# macOS
brew install ffmpeg

# Debian/Ubuntu
sudo apt-get update && sudo apt-get install -y ffmpeg
```

### 2. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

### 3. Configure

```bash
cp config.yaml.example config.yaml
```

Edit `config.yaml` with your credentials:

| Key | Description |
|-----|-------------|
| `bot.token` | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `bot.password` | Shared password users must enter once |
| `llm.backend` | `ollama`, `openai`, `anthropic`, or `openrouter` |
| `llm.fallback` | Optional secondary backend if primary fails |
| `storage.backend` | `notion` or `obsidian` |

You can also start with only `bot.token` and `bot.password`, then configure the rest from Telegram with `/setup`.

### 4. Run locally

```bash
python3 -m bot.main
```

### 5. Run one Short locally without Telegram

```bash
./run-live "https://www.youtube.com/shorts/VIDEO_ID"
```

Useful flags:

```bash
./run-live --json "https://www.youtube.com/shorts/VIDEO_ID"
./run-live --no-history "https://www.youtube.com/shorts/VIDEO_ID"
./run-live --config /path/to/config.yaml "https://www.youtube.com/shorts/VIDEO_ID"
./run-live --cookies-from-browser brave "https://www.youtube.com/shorts/VIDEO_ID"
./run-live --cookies /path/to/cookies.txt "https://www.youtube.com/shorts/VIDEO_ID"
```

This command uses the same LLM, Vision, search, and storage backends as the bot, but prints the result in the terminal and saves it directly without Telegram auth or chat interaction.

### 6. Run with Docker

```bash
export OBSIDIAN_HOST_VAULT_PATH="/path/to/your/obsidian/vault"
docker compose up -d
```

The compose file mounts `./config.yaml`, `./data`, and an Obsidian directory to `/vault`. Inside Docker, `OBSIDIAN_VAULT_PATH=/vault` overrides `config.yaml`, so the bot writes to the mounted host folder instead of an internal container path.

## Configuration examples

### Fully local LLM with Ollama

```yaml
llm:
  backend: ollama
  fallback: null
  ollama:
    url: "http://host.docker.internal:11434"
    model: "llama3.1:8b"
```

### OpenRouter free models with paid fallback

```yaml
llm:
  backend: openrouter
  fallback: openai

  openrouter:
    api_key: "sk-or-YOUR_KEY"
    max_free_models: 3

  openai:
    api_key: "YOUR_OPENAI_API_KEY"
    model: "gpt-4o-mini"
```

If the paid fallback key is missing, OpenRouter still tries the ranked free models and `openrouter/free`; only the final fallback step fails.

## Authentication flow

1. User sends `/start` to the bot
2. Bot prompts for the password
3. User sends the password; on success their Telegram user ID is stored in `data/users.db`
4. Authenticated users never need to enter the password again

## Transcript pipeline

1. **Primary** — `youtube-transcript-api` fetches existing captions (fast, no download)
2. **Fallback** — if no captions exist, `yt-dlp` downloads the audio and `faster-whisper` transcribes it locally
3. **Failure handling** — if captions, download, transcription, and optional Vision all produce no usable input, the bot returns a clear Telegram error instead of saving an empty note

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
| OpenRouter | `llm.openrouter` | Free models first — see below |

Set `llm.fallback` to a second backend so extraction never silently fails.

## Cost Optimization with OpenRouter

[OpenRouter](https://openrouter.ai) aggregates hundreds of LLM providers and exposes a number of genuinely free models — no credit card required.

### How the smart backend works

1. On first use, the bot fetches the current free-model rankings from [`shir-man.com/api/free-llm/top-models`](https://shir-man.com/api/free-llm/top-models) and caches the list for 1 hour.
2. It filters to models where `healthStatus == "passed"` **and** `supportsResponseFormat == true` (JSON mode — required for reliable extraction).
3. It tries the top `max_free_models` (default 3) in rank order.
4. On rate limit (HTTP 429) or any error, it silently moves to the next model.
5. If all ranked models fail, it tries `openrouter/free` — OpenRouter's own managed free router.
6. If that also fails, it falls back to whichever backend is set in `llm.fallback` (e.g. `gpt-4o-mini`).

### Setup

1. Register at <https://openrouter.ai> and create an API key — it's free.
2. In `config.yaml`:

```yaml
llm:
  backend: openrouter
  fallback: openai      # paid safety net when all free models are busy

  openrouter:
    api_key: "sk-or-YOUR_KEY"
    max_free_models: 3

  openai:
    api_key: "YOUR_OPENAI_API_KEY"
    model: "gpt-4o-mini"
```

### Cost comparison

| Path | Cost per Short |
|------|---------------|
| Free OpenRouter model (success) | $0 |
| OpenRouter managed free (`openrouter/free`) | $0 |
| GPT-4o-mini fallback | ~$0.005–0.01 |

In practice the free path succeeds the vast majority of the time during off-peak hours. The paid fallback is a safety net for burst rate limiting.

## Telegram commands

| Command | Description |
|---------|-------------|
| `/start` | Authenticate with the shared password |
| `/setup` | Configure LLM, storage, Vision, and language from Telegram |
| `/status` | Show masked active configuration |
| `/history` | Show recent saved entries with source/delete actions |

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `yt-dlp` says `Sign in to confirm you're not a bot` | Run `./run-live --cookies-from-browser brave ...` or set `YTDLP_COOKIES_FROM_BROWSER=brave` |
| `./run-live` says backends are not ready | Set `llm.*` and `storage.*` in `config.yaml`, or keep using settings already stored by `/setup` |
| Telegram bot says `Saved!` but nothing appears in Obsidian | For Docker runs, set `OBSIDIAN_HOST_VAULT_PATH` and recreate the container so `/vault` is mounted |
| `python` shows syntax errors on type hints | Use `python3`; Python 2 is still the default on some machines |
| Bot says setup is incomplete | Run `/status` and configure missing LLM/storage values with `/setup` |
| Shorts with no captions fail | Confirm `ffmpeg` is installed and Docker has network access for `yt-dlp` |
| Obsidian notes are not created in Docker | Mount the vault path into the container and use the container path in config |
| Ollama fails in Docker | Use `host.docker.internal` or uncomment the compose `extra_hosts` block on Linux |

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
    openrouter.py — OpenRouter free-model adapter
  storage/
    base.py      — StorageBackend ABC
    notion.py    — Notion adapter
    obsidian.py  — Obsidian adapter
data/            — runtime data (gitignored)
  users.db       — authenticated user IDs
```

## Verification

```bash
python3 -m compileall -q bot
python3 -m unittest discover -s tests
./run-live --help
```

## One-click setup

Prefer not to deal with config files and Docker manually? There is a setup package on Gumroad that includes an interactive installer script, a step-by-step PDF guide, and a ready-to-use Notion database template. The bot is running in about 3 minutes.

→ [gumroad.com/l/shorts-saver-bot](https://stasphere26.gumroad.com/l/waktiw)
