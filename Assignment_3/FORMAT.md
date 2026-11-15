# Byte-level wallet specification — version 1

**Key type:** Ed25519, 32-byte raw public key and 32-byte seed; OS CSPRNG through `cryptography`. Public keys are encoded as lowercase 64-character hexadecimal strings.

**Address:** `Base58Check(0x6f || SHA256(raw_public_key)[0:20] || SHA256(SHA256(payload))[0:4])`. `0x6f` is a deliberately educational version-byte choice (also used elsewhere); **this wallet is not compatible with or safe for cryptocurrency mainnet**. Addresses must decode to exactly 25 bytes and roundtrip to canonical Base58.

**Canonical transaction:** exactly seven JSON fields `version`, `network_id`, `sender`, `recipient`, `amount_units`, `nonce`, `memo_hash`. `version` must equal integer 1, network ID must equal `course-testnet`, addresses must be well formed, `amount_units` is unsigned 64-bit and >0, `nonce` unsigned 64-bit, `memo_hash` lowercase 32-byte SHA-256 hex. Serialize with Python `json.dumps(tx, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')`. Since all fields are constrained to ASCII or integer values, the bytes are cross-platform. Never sign original JSON file whitespace or order. A signature covers exactly `ASCII("COURSE-TX-v1") || 0x00 || canonical_json_bytes` with Ed25519. The envelope contains JSON `transaction`, 32-byte raw `public_key` (lowercase hex), and 64-byte raw `signature` (lowercase hex). Ed25519 verification enforces a valid signature encoding.

**Replay:** `(network_id, sender, nonce)` can occur once in the application-level accepted-nonce set. CLI `verify --nonces file.json` persists the set; without `--nonces`, verification is *stateless* and cannot detect replay between invocations. Always synchronize this set atomically with ledger state in production; this is a learning project.

## Threat model

- Key theft / malware: private-key files are **optional**, test-only, mode 0600 on POSIX; do not commit them. File is unencrypted. Never use for real money.
- Weak randomness: use OS randomness via maintained Ed25519 API; never derive keys from user passwords or predictable seeds.
- Replay: domain prefix + network ID + monotonically unique sender nonce; persisted replay tracking is optional in demo.
- Clipboard replacement: verify the full destination address out of band before signing.
- Phishing: sign only transaction bytes that have been displayed and reviewed; never paste seeds into websites.
- Accidental mainnet use: educational version/network identifiers, no RPC, prominent warnings; no interoperability claim.
