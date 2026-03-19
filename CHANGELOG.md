# Changelog

## 0.1.0 — Initial Release

### Features
- Decorator-based parallel execution (`@parawave`)
- Configurable concurrency and rate limiting
- Retry with backoff strategies (fixed, exponential, exponential_jitter)
- SQLite persistent storage (optional, via `parawave[sqlite]`)
- Resume from failures (same-session or cross-session with SQLite)
- RunManager for querying past runs
- Lifecycle hooks (on_start, on_item_complete, on_item_error, on_retry, on_complete)
- SharedState for thread-safe shared data
- Warmup mode for early error detection
- Jupyter/Colab support (via `parawave[notebook]`)
- Result export (to_dict, to_json, to_csv)
- Zero base dependencies
