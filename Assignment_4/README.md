# Assignment 4 — UTXO Ledger and Validator

**Aryan Phad · 2301CS09** | Python 3.11+ | Ed25519 P2PKH

```bash
python -m pip install -r requirements.txt
python ledger.py demo > examples/trace.json
python -m pytest -q
# For standalone files, use examples/trace.json's initial and transaction fields:
# python ledger.py build --state initial.json --private-key demo.key --recipient ADDRESS --amount 85 --fee 2 --nonce 7
# python ledger.py apply --state initial.json --transaction payment.json --out final.json
```

`demo` deterministically creates Alice outputs (40, 70), sends 85 to Bob for fee 2, returns change 23, then rejects replay of the same spent outpoints; it prints **full initial and final snapshots** and exact trace/rejection reason. Key bytes in the demo are public fixed **test vectors**, not secure wallet keys. Don't fund or deploy them. Snapshot files use `{ "format": "course-utxo-v1", "utxos": { "txid:index": {"value": N, "address": "..."} } }`.

## Transaction and authorization specification

`txid=SHA256(canonical JSON of full signed transaction)`; a transaction contains exactly `version=1`, `network_id="course-testnet"`, `nonce` uint64, nonempty `inputs`, nonempty `outputs`. Input: 32-byte lowercase hex txid, zero-based uint64 index, 32-byte Ed25519 raw pubkey lowercase hex, 64-byte signature lowercase hex. Output: uint64 positive value, version-0x6f Base58Check P2PKH address; see copied `wallet.py` for address rules. Signature covers `b"COURSE-UTXO-v1\\x00" + canonical_json({version,network_id,nonce,inputs:[{txid,index}],outputs})`, excluding signature and pubkey bytes, with the *full ordered* list of inputs/outputs. Canonical JSON uses sorted keys, compact separators, UTF-8. Pubkey hash must match each referenced output. Signed inputs can't be added/removed or reordered without invalidation.

**Coin selection:** deterministic largest-first, ties broken by ascending `txid:index`; spend enough to cover amount+fee, create change if nonzero. Fee = sum(inputs) - sum(outputs). All values and intermediate totals checked against unsigned 64-bit bounds. Duplicate/missing inputs, incorrect keys/signatures, malformed outputs, inflation or sum overflow reject. The proposed update is calculated in a separate dictionary and committed only if every check succeeds. A failed transaction leaves the original state unchanged. No generic minting API: initial snapshot is a trusted course-genesis fixture. Persistence saves/reloads logical state; real systems would also need journaled disk commits, concurrency control, and durable replay protection.

## Demo recording

Run `demo`, show `initial`, the accepted transaction and `final` plus second-spend rejection, then `python -m pytest -q` (over 20 validation cases). Point out atomic state transitions, auth, largest-first selection, and change.

**Checked-in reproducible sample data:** `examples/initial.json`, `examples/payment.json`, `examples/final.json`, and `examples/trace.json`. The payment can be independently replayed without access to the signing seed:

```bash
python ledger.py apply --state examples/initial.json --transaction examples/payment.json --out replayed.json
```

`replayed.json` should have the same logical UTXOs as `examples/final.json`; you can delete the generated file after the demo.
