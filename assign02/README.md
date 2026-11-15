# Assignment 2 — Merkle Trees and Inclusion Proofs

**Aryan Phad · 2301CS09** | Python 3.11+ | SHA-256, no Merkle dependency

## Quick start

```bash
python merkle.py root examples/transactions.json
python merkle.py prove examples/transactions.json --index 2 > examples/proof.json
python merkle.py verify --leaf "Carol->Dave:1" --proof examples/proof.json --root ROOT_FROM_FIRST_COMMAND
python merkle.py benchmark
python -m pytest -q
```

Input file: JSON array of UTF-8 strings; leaf data is exactly each string's UTF-8 encoding. Root and hashes use **lowercase hex**. Empty root = `SHA256(0x02)`; leaves = `SHA256(0x00 || raw_data)`; internal nodes = `SHA256(0x01 || left_digest || right_digest)`. A lone final node is duplicated at **every level**. Proof `side` indicates sibling placement (not the target's placement). Proof size must equal the tree height, and directions must match `leaf_index`; duplicated-tail sibling must equal the running hash. Verification accepts only leaf bytes, proof JSON and expected root. No network access.

## Exact five-leaf inclusion path (index 2)

```text
                         ROOT = H(N0123, N4444)
                           /                 \
                N0123 = H(N01,N23)        N4444 = H(N44,N44)
                   /           \                   /       \
              N01 = H(L0,L1)  N23 = H(L2,L3)      N44       N44
                 /   \          /   \              / \
                L0   L1        [L2]  L3            L4  L4

Proof for leaf index 2:
  level 0: L3     RIGHT
  level 1: N01    LEFT
  level 2: N4444  RIGHT
```

Here `H(a,b)` abbreviates the domain-separated `H(0x01 || a || b)`; `Li=H(0x00 || transaction_i)`.

## Performance report

Run `python merkle.py benchmark > benchmark-results.json` to obtain **measured on your machine** construction time, root, proof steps, and compact JSON proof size for 8, 1,024, and 100,000 leaves. Results are not hard-coded; timing depends on machine load. Complexity: construction O(n) time and O(n) memory; inclusion proof O(log n) hashes and bytes, verification O(log n). Note `prove` rebuilds a full tree, so standalone proof generation is O(n).

## Demo recording (2–3 minutes)

Display five-leaf diagram, root, proof JSON, successful verification, then change `--leaf` and show a failed verification. Run benchmark and pytest. Mention duplicate-last odd-leaf rule and why domain separation matters.

Checked-in concrete examples are `examples/root.json`, `examples/proof.json`, and `examples/benchmark-results.json`. The root hash from `examples/root.json` can be pasted directly into the verify command.
