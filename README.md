# Ilm Assit

**Ilm Assit:** is a WhatsApp chatbot that answers students' and parents' questions about higher
education in Pakistan, in English, Urdu or Roman Urdu. It covers HEC-recognised universities and
their policies, fee structures, need-based and merit scholarships, provincial endowment funds, and
fully funded scholarships abroad. A built-in scraping agent collects this information from official
websites, including HEC, the provincial endowment funds, university financial-aid offices and
international scholarship programmes. It reads both web pages and PDFs and stores them in a
searchable knowledge base. Ilm Assit uses retrieval-augmented generation (RAG) over these official
sources, so every answer is grounded in current eligibility rules, deadlines and application steps,
and it links to the official page.

- **Text message in → text reply** (with the official source link)
- **Voice note in → voice note reply** (falls back to text if the voice step fails)

## How it works

```
                 one time                                   every message
 official sites ─────────► data/raw/pages.jsonl ──► data/index/ ◄──── hybrid search ◄── question
 (knowledge/sources.py)    (scraping agent)         chunks + embeddings      │
                                                                         Groq LLM ──► WhatsApp
```

1. **Scraping agent** (`knowledge/crawler.py`) crawls the sites in `knowledge/sources.py`:
   seed pages + links up to 2 levels deep on the same site, HTML and PDFs, ~300 pages per
   site (600 for HEC). It respects robots.txt and waits 1 second between requests per site.
   Progress is saved, so an interrupted crawl resumes instead of restarting.
2. **Indexing** (`knowledge/builder.py`) splits pages into small chunks and embeds them with a
   local multilingual model (English / Urdu / Roman Urdu, no API key). The index is saved to `data/index/`.
3. **Answering** (`app/services/llm_service.py`) finds the 6 most relevant chunks for each
   question (meaning-based + keyword search) and asks the Groq LLM to answer only from them.

The scraping agent **runs only once**. If `data/index/` exists, it is skipped.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in your WhatsApp and Groq keys
```

`ffmpeg` must be installed for voice replies (`brew install ffmpeg` on Mac).

## Run

```bash
python build_knowledge_base.py   # scraping agent: one-time crawl + index (roughly 30–60 min, resumable)
python run.py                    # start the bot on port 8000
```

If you skip the first command, `python run.py` builds the knowledge base on its first start.
Set `AUTO_BUILD_KB=false` in `.env` to turn that off.

### Updating the data later

| Command | What it does |
|---|---|
| `python build_knowledge_base.py --force` | Delete everything and crawl all sites again |
| `python build_knowledge_base.py --only "Chevening Pakistan"` | Re-crawl one site, keep the rest |
| `python build_knowledge_base.py --reindex` | Keep crawled pages, only re-chunk and re-embed |
| `python build_knowledge_base.py --list-sources` | Show the site names |

Restart the bot after rebuilding. To add a website, add a `Source(...)` in `knowledge/sources.py`
and run with `--only "<its name>"`.

## Project structure

```
run.py                     start the bot (builds the knowledge base on first start)
build_knowledge_base.py    run the scraping agent + indexing (CLI)
app/
  __init__.py              Flask app factory, loads the knowledge base at startup
  config.py                settings from .env
  views.py                 /webhook endpoints (verification + incoming messages)
  decorators/security.py   checks Meta's request signature
  services/
    groq_client.py         shared Groq client
    llm_service.py         RAG answer + per-user chat history
    audio_service.py       speech-to-text and text-to-speech (voice notes)
  utils/
    whatsapp_utils.py      text → text, voice → voice message handling
    whatsapp_api.py        WhatsApp Cloud API calls (send, upload, download)
knowledge/
  sources.py               websites to crawl
  crawler.py               scraping agent
  extract.py               HTML / PDF → clean text
  chunker.py               split pages into chunks
  embeddings.py            local embedding model
  builder.py               crawl → chunk → embed → save (run once)
  retriever.py             hybrid search used at runtime
data/                      created at runtime (crawled pages, index, model, chat history)
```

For production, run with gunicorn: `gunicorn -w 1 --threads 8 -b 0.0.0.0:8000 run:app`.
