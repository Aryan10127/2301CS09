# Assignment 3 — Keys, Addresses, Signed Transactions

**Aryan Phad · 2301CS09** | Python 3.11+ | `cryptography` Ed25519

```bash
python -m pip install -r requirements.txt
python wallet.py keygen --private-out demo.key
python wallet.py keygen                        # recipient: note public address, private key NOT exported
python wallet.py address --public-key PUBLIC_KEY_HEX
# Replace sender/recipient in examples/transaction.template.json, save as tx.json
python wallet.py sign --transaction tx.json --private-key demo.key --out signed.json
python wallet.py verify --signed signed.json --nonces demo-nonces.json
python -m pytest -q
```

Keep `demo.key` and `demo-nonces.json` **out of Git** (`.gitignore`). `keygen` exports public data only unless `--private-out` is explicitly set; its private file uses POSIX 0600. Signing checks sender ownership and canonicalizes JSON before signing. Re-verifying with the same nonce state rejects replay. See `FORMAT.md` for exact address, byte format, signature domain, test-only warning, and threat model. Never put real cryptocurrency keys or assets in this system.

## Demo recording

Show keygen without private material, then opt-in test private file and permissions, address, sign, verify, verify again with `--nonces` to show replay rejection, edit signed amount to show signature failure, and run tests. Avoid showing the contents of any private key on camera.

For a one-command **ephemeral demo without handling private keys**, run `python demo.py`. The `examples/signed.public.json` fixture contains a fixed-key signed transaction with no private key; its public signing-byte vector is recorded in `examples/test-vector.json`.
