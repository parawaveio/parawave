# ParaWave: One decorator turns any function into a durable parallel runner. Zero dependencies.

[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-3.9%20|%203.10%20|%203.11%20|%203.12%20|%203.13-green.svg)]()

Parawave (short for **parallel wave**) turns any Python function — sync or async —
into a parallel, resumable runner with retry, rate limiting, and persistence.

Built for managing thousands of LLM API calls — OpenAI, Anthropic, or any provider.
Bring your own function, parawave handles the rest. Zero dependencies.

## Install

```bash
pip install parawave
```

The base install has **zero dependencies** — just parawave and the Python standard library.

| Extra      | Packages                | What it enables                          | Install                          |
| ---------- | ----------------------- | ---------------------------------------- | -------------------------------- |
| `sqlite`   | `aiosqlite`, `aiofiles` | Persistent storage, cross-session resume | `pip install parawave[sqlite]`   |
| `notebook` | `nest_asyncio`          | Jupyter / Colab support                  | `pip install parawave[notebook]` |
| `all`      | All of the above        | Everything                               | `pip install parawave[all]`      |

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
        model="gpt-5.4-nano",
        messages=[{"role": "user", "content": f"One fun fact about {city}"}],
    )
    return {"fact": response.choices[0].message.content}

result = enrich.run(data=[{"city": c} for c in cities])
```

```
[parawave] Starting run-e914e6b685e6 | 20 items | concurrency=20
[parawave] 5/20 (5 completed) | 0.8s | 6.3 items/s
[parawave] 12/20 (10 completed, 2 failed, 3 retried) | 1.4s | 8.6 items/s
[parawave] 18/20 (14 completed, 4 failed, 6 retried) | 1.9s | 9.5 items/s
[parawave] 20/20 (15 completed, 5 failed, 10 retried) | 2.1s | 9.6 items/s
[parawave] Completed run-e914e6b685e6 | 15/20 completed | 30 attempts, 10 retried, 5 failed | 2.1s
[parawave] To resume: .resume() | Cross-session: .resume("run-e914e6b685e6")
```

Some items failed — check what went wrong:

```python
for item in result.failed:
    print(f"{item.input['city']}: {item.error}")
```

```
Tokyo: RateLimitError: rate limit exceeded
Berlin: RateLimitError: rate limit exceeded
Seoul: APITimeoutError: request timed out
Mumbai: RateLimitError: rate limit exceeded
Cairo: APIConnectionError: connection reset
```

Resume to retry only the 5 failed items:

```python
result = enrich.resume()
```

```
[parawave] Resuming run-e914e6b685e6 | 15/20 previously completed | concurrency=20
[parawave] 3/5 (3 completed) | 0.1s | 30.0 items/s
[parawave] 5/5 (5 completed, 1 retried) | 0.2s | 25.0 items/s
[parawave] Completed run-e914e6b685e6 | 20/20 completed | 2.3s
```

Works with sync functions too — any function, any provider:

```python
@parawave(max_concurrency=10)
def fetch(url: str) -> str:
    return requests.get(url).text
```

With `storage="sqlite"`, resume works across sessions — kill the process,
restart later, pick up where you left off.

## Examples

| Notebook | Description |
| -------- | ----------- |
| [01 — Quickstart](examples/01_quickstart.ipynb) | Core patterns — run, retry, resume, hooks, RunManager |
| [02 — Synthetic Data Pipeline](examples/02_synthetic_data_pipeline.ipynb) | Rate and classify HuggingFace data with an LLM |
| [03 — Advanced Synthetic Pipeline](examples/03_advanced_synthetic_pipeline.ipynb) | SharedState + Jinja templates for diverse synthetic data |

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/parawaveio/parawave/blob/main/examples/01_quickstart.ipynb)

## How it works

It's dead simple — three steps:

1. **Decorate** any function with `@parawave()`
2. **Run** with `.run(data=[...])` — items fan out in parallel with bounded concurrency
3. **Resume** with `.resume()` — retries only what failed

That's it. No daemon. No worker process. No message broker. Everything runs in your Python process.

## More

Parawave also supports lifecycle hooks, shared state, warmup mode, result
export (JSON, CSV), run tagging, and run history via RunManager. See the
[quickstart notebook](examples/01_quickstart.ipynb) for the full tour.

## Community

If you find parawave useful, please [star this repo](https://github.com/parawaveio/parawave) — it helps others discover the project.

- [Issues](https://github.com/parawaveio/parawave/issues) — bug reports and feature requests
- [Discussions](https://github.com/parawaveio/parawave/discussions) — questions and ideas

This project is actively maintained. Contributions welcome.

## License

MIT
