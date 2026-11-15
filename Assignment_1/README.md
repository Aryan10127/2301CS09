# Assignment 1 — Bytes, Hashes, and Reproducible Data

**Aryan Phad · 2301CS09** | Python 3.11+ | Standard-library implementation

## Run from this folder

```bash
python hashlab.py text "Alice pays Bob 10"
python hashlab.py hex 48656c6c6f
python hashlab.py file examples/input.json
python hashlab.py avalanche --text "Alice pays Bob 10" --bit 7
python hashlab.py canonical-json examples/input.json
python hashlab.py demo
python -m pytest -q
```

`python hashlab.py ...` is the portable equivalent of `hashlab ...`; an executable `hashlab` wrapper is included for POSIX systems. The CLI prints machine-readable JSON with byte count, SHA-256 hex and Base64. Bit 0 is the MSB of byte 0.

## Canonical JSON rules

Parse JSON into a top-level object; recursively sort object keys by Python's Unicode code-point order, output compact JSON with no insignificant whitespace, preserve UTF-8 without ASCII escaping, keep JSON string and numeric types distinct, reject NaN/Infinity. No Unicode normalization is applied; semantically equivalent numeric representations such as 1 and 1.0 are **not** folded together. This is a documented educational format, not RFC 8785 JCS. Duplicate JSON input keys should be avoided (Python JSON parsing keeps the last value).

## Reproducibility

`demo` prints both exact bytes and hashes for LF/CRLF, trailing newline, NFC/NFD Unicode, integers vs strings, and raw vs canonical key order. `file` hashes in 1 MiB chunks. The test suite hashes a 100 MiB fixture while checking traced Python allocation peak stays below 6 MiB; note OS buffers aren't measured by tracemalloc.

## Demo recording (2–3 minutes)

Show text and hex modes, compare `text "hello"` with `file` containing `hello\n`, run `avalanche`, `canonical-json`, `demo`, then `python -m pytest -q`. Explain byte identity vs visual identity and streamed hashing.
