# Assignment 5 — Blocks, Toy Proof of Work, Forks & Reorganisation

**Aryan Phad · 2301CS09** | Python 3.11+ | Local simulated chain

```bash
python -m pip install -r requirements.txt
python chain.py fork-demo > examples/fork-trace.json
python chain.py benchmark --trials 20 > examples/pow-benchmark.json
python -m pytest -q
# Optional single-block mining (replace address with one from wallet.py keygen):
python wallet.py keygen
python chain.py mine --miner ADDRESS --height 0
```

## Block format and validity

Header is **116 bytes**: `version` uint32 LE (4), `prev_hash` raw 32 bytes, `merkle_root` raw 32 bytes, `timestamp` uint64 LE (8), `target` uint256 BE (32), `nonce` uint64 LE (8). Hash = `SHA256(header_bytes)`, interpreted as **big-endian unsigned 256-bit integer**, valid if `hash <= target`. Work contribution = `floor(2^256 / (target+1))`. Transactions are JSON objects hashed as canonical bytes by the Assignment 2 domain-separated Merkle tree (`merkle.py`, copied here). Header hex appears under `genesis_header_hex` in the demo trace.

A valid block must have a known parent (or initial zero parent), an immutable valid header, valid PoW, Merkle root matching all ordered transactions, timestamp no earlier than parent, exactly one first-position coinbase, and valid signed UTXO transitions (`ledger.py`). Coinbase: `{"coinbase":true,"height":H,"outputs":[{"value":N,"address":"..."}]}`; height must match parent height + 1, value positive and no greater than **subsidy 50 + transaction fees**. Ordinary transactions use the complete Assignment 4 authenticated format. Each coinbase output has a `SHA256(canonical_coinbase):0` outpoint; coinbase is credited after regular block transactions, so it cannot be spent in its own block. Genesis coinbase establishes initial spendable UTXOs. Timestamp and target are educational externally chosen values, *not* consensus-retargeted or wall-clock constrained; no real-world security guarantee.

## Competing branches and reorganisation diagram

```text
                Genesis (G)
                /         \
 Miner A EASY  A1          B1  Miner B HARD
               |            \
              A2             selected tip (higher work)
               |
              A3  (longer but LOWER work)

A: 3 × 16 = 48 post-genesis work
B: 1 × 64 = 64 post-genesis work
```

A1 spends a genesis coinbase UTXO from Alice to Bob. After A3 is initially selected, a late-arriving high-work B1 wins. `Chain` stores verified per-block UTXO snapshots; on reorg the active state is replaced with the winning branch's validated snapshot, thereby restoring outputs spent only on A and discarding outputs created there. `reorg_log` records disconnected hashes. All validation happens before `nodes`, `tip`, or active `utxos` are committed. Ties retain the incumbent. The simulation is deterministic in logical outcome even though mined nonces differ by target/timestamp.

## Mining experiment

`benchmark --trials 20` runs three toy targets (approximate expected attempts 8, 16, 64), recording observed average attempts and measured aggregate hashes/second. Trials are randomly distributed by SHA-256 nonce search; observed means may differ from theoretical expectation, especially with 20 trials. Generated measured traces are included under `examples/`, so you can discuss actual results from this execution. Header hex: see `examples/fork-trace.json`.

## Demo recording (3–4 minutes)

Show `fork-demo` branch heights/work, selected tip, reorg log, and before/after UTXO state. Show header hex and benchmark report; run pytest. Explain why the longer fork loses, whole-block atomic rejection, and why in-memory toy difficulty should not be confused with production consensus.
