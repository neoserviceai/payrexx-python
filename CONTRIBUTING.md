# Contributing

Bug reports, corrections and coverage for the endpoints that are still missing are
all welcome.

## Setup

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Before opening a pull request

```bash
ruff format .
ruff check .
mypy
pytest
```

CI runs the same four on Python 3.10 through 3.13, with `ruff format --check`, so
unformatted code fails rather than being fixed for you.

## What the checks enforce

The toolchain is strict because this library moves money, and a suite that
silently covers less than you think is worse than none:

- coverage floor of 90 %, `--strict-markers`, `--strict-config`, `xfail_strict`,
  warnings as errors, doctests run as tests
- `mypy --strict` over `src/` **and** `tests/`, with `warn_unreachable`; a bare
  `# type: ignore` is rejected — give it a code
- around 20 ruff rule families, including `S` (security) and `DTZ` (naive
  datetimes)

Every rule disabled in `pyproject.toml` carries the reason it is disabled. If a
rule blocks something legitimate, add the ignore *with its reason* rather than
loosening the whole family.

## Conventions that matter here

**Never retry a non-idempotent verb.** Payrexx exposes no idempotency key. `POST`,
`PUT` and `PATCH` stay out of `_RETRYABLE_METHODS`; a transport failure raises
`PayrexxTransportError` so the caller can reconcile rather than resend.

**Encode every payload through `encode_form`.** The API only understands PHP's
indexed bracket notation (`pm[0]=twint`); other spellings return `200 OK` and are
silently dropped.

**Parse tolerantly.** Models keep the untouched response in `raw`, and unknown
enum values pass through rather than raising. A field Payrexx adds tomorrow must
not break a payment flow.

**Say where a fact comes from.** Much of this library encodes behaviour that is
undocumented or that the REST reference gets wrong. When you add such a fact, note
its source in the docstring — the PHP SDK, or a live observation with its date.
That is what makes the next reader able to check it.

## Adding an endpoint

1. A resource class under `src/payrexx/resources/`, or a method on an existing one.
2. A model in `models.py` if the response has a shape worth typing — with
   `from_api` tolerating an empty payload.
3. Tests: the HTTP verb and path, the encoding of any list or nested field, and
   one parse of a realistic payload.
4. A row in the README's coverage table.

Check the [official PHP SDK](https://github.com/payrexx/payrexx-php) for the verb
and the field names before the REST reference — it is more complete, and where the
two disagree the SDK has so far been right.
