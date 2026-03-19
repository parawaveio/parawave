# parawave

One decorator. Any function. Durable parallel execution.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-3.9%20|%203.10%20|%203.11%20|%203.12%20|%203.13-green.svg)]()

Parawave turns any Python function — sync or async — into a parallel,
resumable job with retry, rate limiting, and persistence.
Built for managing thousands of LLM API calls. Zero dependencies.

## Install

```bash
pip install parawave
```

The base install has **zero dependencies** — just parawave and the Python standard library.

| Extra | Packages | What it enables | Install |
|-------|----------|-----------------|---------|
| `sqlite` | `aiosqlite`, `aiofiles` | Persistent storage, cross-session resume | `pip install parawave[sqlite]` |
| `notebook` | `nest_asyncio` | Jupyter / Colab support | `pip install parawave[notebook]` |
| `all` | All of the above | Everything | `pip install parawave[all]` |

## Quick Start

```python
import parawave

@parawave(
    max_concurrency=20,
    rate_limit=50,
    retry=parawave.RetryPolicy(max_retries=3, backoff="exponential"),
)
async def enrich(city: str) -> dict:
    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"One fun fact about {city}"}],
    )
    return {"fact": response.choices[0].message.content}

result = enrich.run(data=[{"city": c} for c in cities])
```

```
[parawave] Starting run-e914e6b685e6 | 20 items | concurrency=20
[parawave] 20/20 (15 completed, 5 failed, 10 retried) | 2.1s | 9.6 items/s
[parawave] Completed run-e914e6b685e6 | 15/20 completed | 30 attempts, 10 retried, 5 failed | 2.1s
[parawave] To resume: .resume() | Cross-session: .resume("run-e914e6b685e6")
```

Some items failed. Resume to retry only what's left:

```python
result = enrich.resume()
```

```
[parawave] Resuming run-e914e6b685e6 | 15/20 previously completed | concurrency=20
[parawave] 20/20 (20 completed, 1 retried) | 0.2s | 86.8 items/s
[parawave] Completed run-e914e6b685e6 | 20/20 completed | 2.3s
```

Works with sync functions too:

```python
@parawave(max_concurrency=10)
def fetch(url: str) -> str:
    return requests.get(url).text
```

With `storage="sqlite"`, resume works across sessions — kill the process,
restart later, pick up where you left off.

## How it works

Decorate any function with `@parawave()`. Call `.run(data=[...])` to fan out
items with bounded concurrency. Failed items retry automatically. Call
`.resume()` to retry only what's left.

No daemon. No worker process. No message broker. Everything runs in your Python process.

## More

Parawave also supports lifecycle hooks, shared state, warmup mode, result
export (JSON, CSV), run tagging, and run history via RunManager. See the
[quickstart notebook](examples/quickstart.ipynb) for the full tour.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/parawaveio/parawave/blob/main/examples/quickstart.ipynb)

## License

MIT
