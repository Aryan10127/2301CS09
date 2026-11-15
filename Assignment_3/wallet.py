"""Toy-chain Ed25519 wallet, strict canonical transaction format and Base58Check."""
import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization

ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
VERSION = 0x6f  # course-only address version, NOT any real cryptocurrency network
NETWORK = 'course-testnet'
FIELDS = {'version', 'network_id', 'sender', 'recipient', 'amount_units', 'nonce', 'memo_hash'}


def sha(data): return hashlib.sha256(data).digest()
def checksum(data): return sha(sha(data))[:4]


def b58encode(data):
    n = int.from_bytes(data, 'big')
    chars = ''
    while n:
        n, r = divmod(n, 58)
        chars = ALPHABET[r] + chars
    return '1' * (len(data) - len(data.lstrip(b'\x00'))) + chars


def b58decode(value):
    if not isinstance(value, str) or not value: raise ValueError('empty address')
    n = 0
    for char in value:
        if char not in ALPHABET: raise ValueError('invalid Base58 character')
        n = n * 58 + ALPHABET.index(char)
    count = len(value) - len(value.lstrip('1'))
    return b'\x00' * count + (n.to_bytes((n.bit_length()+7)//8, 'big') if n else b'')


def address_from_public(public_raw):
    if not isinstance(public_raw, bytes) or len(public_raw) != 32: raise ValueError('public key must be 32 bytes')
    payload = bytes([VERSION]) + sha(public_raw)[:20]
    return b58encode(payload + checksum(payload))


def parse_address(address):
    data = b58decode(address)
    if len(data) != 25 or data[0] != VERSION or checksum(data[:-4]) != data[-4:]:
        raise ValueError('malformed address, version, or checksum')
    if b58encode(data) != address: raise ValueError('noncanonical Base58 address')
    return data[1:21]


def pub_bytes(private):
    return private.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                              format=serialization.PublicFormat.Raw)


def create_keys():
    private = Ed25519PrivateKey.generate()
    seed = private.private_bytes(encoding=serialization.Encoding.Raw,
                                  format=serialization.PrivateFormat.Raw,
                                  encryption_algorithm=serialization.NoEncryption())
    public = pub_bytes(private)
    return seed, public


def save_private(path, seed):
    path = Path(path)
    if path.exists(): raise FileExistsError('private key file already exists; refusing overwrite')
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(path, flags, 0o600)
    try:
        os.fchmod(fd, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, 'w') as f:
            f.write('DANGER: COURSE TEST KEY ONLY - NEVER FUND OR REUSE ON A REAL CHAIN\n')
            f.write(seed.hex() + '\n')
    except BaseException:
        try: os.close(fd)
        except OSError: pass
        raise


def read_private(path):
    lines = Path(path).read_text().splitlines()
    if len(lines) != 2 or not lines[0].startswith('DANGER: COURSE TEST KEY ONLY'):
        raise ValueError('invalid test-only private key format')
    try: seed = bytes.fromhex(lines[1])
    except ValueError as exc: raise ValueError('invalid private key hex') from exc
    if len(seed) != 32: raise ValueError('private seed must contain 32 bytes')
    return Ed25519PrivateKey.from_private_bytes(seed)


def parse_public(text):
    if not isinstance(text, str) or len(text) != 64 or any(c not in '0123456789abcdef' for c in text):
        raise ValueError('public key must be lowercase 64-character hex')
    return bytes.fromhex(text)


def validate_transaction(tx):
    if not isinstance(tx, dict) or set(tx) != FIELDS: raise ValueError('transaction fields mismatch')
    if type(tx['version']) is not int or tx['version'] != 1: raise ValueError('unsupported transaction version')
    if tx['network_id'] != NETWORK: raise ValueError('wrong network ID')
    for key in ('sender', 'recipient'):
        parse_address(tx[key])
    for key in ('amount_units', 'nonce'):
        value = tx[key]
        if type(value) is not int or value < (1 if key == 'amount_units' else 0) or value > 2**64 - 1:
            raise ValueError('invalid ' + key)
    h = tx['memo_hash']
    if not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
        raise ValueError('memo_hash must be lowercase SHA-256 hex')


def transaction_bytes(tx):
    validate_transaction(tx)
    return json.dumps(tx, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def sign(tx, private):
    if address_from_public(pub_bytes(private)) != tx.get('sender'):
        raise ValueError('signer does not own sender address')
    canonical = transaction_bytes(tx)
    public = pub_bytes(private)
    return {'transaction': tx, 'public_key': public.hex(), 'signature': private.sign(b'COURSE-TX-v1\x00' + canonical).hex()}


def verify_signed(signed, spent_nonces=None):
    if not isinstance(signed, dict) or set(signed) != {'transaction', 'public_key', 'signature'}:
        raise ValueError('invalid signed envelope')
    tx = signed['transaction']
    raw = transaction_bytes(tx)
    pub = parse_public(signed['public_key'])
    if address_from_public(pub) != tx['sender']: raise ValueError('wrong signer')
    sig = signed['signature']
    if not isinstance(sig, str) or len(sig) != 128 or any(c not in '0123456789abcdef' for c in sig):
        raise ValueError('noncanonical signature hex')
    try: Ed25519PublicKey.from_public_bytes(pub).verify(bytes.fromhex(sig), b'COURSE-TX-v1\x00' + raw)
    except Exception as exc: raise ValueError('signature verification failed') from exc
    if spent_nonces is not None:
        pair = (tx['network_id'], tx['sender'], tx['nonce'])
        if pair in spent_nonces: raise ValueError('replayed nonce')
        spent_nonces.add(pair)
    return True


def load_json(path): return json.loads(Path(path).read_text('utf-8'))


def main(argv=None):
    p = argparse.ArgumentParser(prog='wallet')
    s = p.add_subparsers(dest='cmd', required=True)
    k = s.add_parser('keygen'); k.add_argument('--private-out', help='optional TEST-ONLY private key file, mode 0600')
    a = s.add_parser('address'); a.add_argument('--public-key', required=True)
    sg = s.add_parser('sign'); sg.add_argument('--transaction', required=True); sg.add_argument('--private-key', required=True); sg.add_argument('--out')
    v = s.add_parser('verify'); v.add_argument('--signed', required=True); v.add_argument('--nonces', help='JSON state file of accepted nonces')
    args = p.parse_args(argv)
    try:
        if args.cmd == 'keygen':
            seed, pub = create_keys()
            if args.private_out: save_private(args.private_out, seed)
            result = {'public_key': pub.hex(), 'address': address_from_public(pub),
                      'private_key_saved': bool(args.private_out), 'warning': 'TEST-ONLY wallet. Never use on mainnet.'}
        elif args.cmd == 'address': result = {'address': address_from_public(parse_public(args.public_key))}
        elif args.cmd == 'sign':
            result = sign(load_json(args.transaction), read_private(args.private_key))
            if args.out: Path(args.out).write_text(json.dumps(result, indent=2) + '\n')
        else:
            state = set()
            if args.nonces and Path(args.nonces).exists():
                state = {(x[0], x[1], x[2]) for x in load_json(args.nonces)}
            verify_signed(load_json(args.signed), state if args.nonces else None)
            if args.nonces:
                Path(args.nonces).write_text(json.dumps([list(x) for x in sorted(state)], indent=2))
            result = {'valid': True, 'replay_state_updated': bool(args.nonces)}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__': sys.exit(main())
