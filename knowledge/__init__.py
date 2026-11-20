"""Knowledge base for the bot: the website extraction agent and RAG search.

- sources.py     which websites to crawl
- crawler.py     the extraction agent (HTML + PDF, runs once, resumable)
- chunker.py     splits pages into small chunks
- embeddings.py  local multilingual embeddings
- builder.py     crawl -> chunk -> embed -> save (skips if already built)
- retriever.py   hybrid search used by the bot at runtime
"""
