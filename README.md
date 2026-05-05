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
