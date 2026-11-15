"""Bytes-first SHA-256 diagnostic CLI. Bit indices are MSB-first."""
import argparse
import base64
import hashlib
import json
import sys
import unicodedata
from pathlib import Path


def canonical_json(value):
    """UTF-8 JSON, lexicographic Unicode key order, compact separators, no NaN."""
    if not isinstance(value, dict):
        raise ValueError('canonical-json expects a JSON object')
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(data):
    h = hashlib.sha256(data).digest()
    return {'bytes': len(data), 'sha256': h.hex(), 'base64': base64.b64encode(h).decode('ascii')}


def file_digest(path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    count = 0
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(chunk_size), b''):
            count += len(chunk)
            h.update(chunk)
    raw = h.digest()
    return {'bytes': count, 'sha256': raw.hex(), 'base64': base64.b64encode(raw).decode('ascii')}


def parse_hex(value):
    if len(value) % 2:
        raise ValueError('hex string must have even length')
    try:
        return bytes.fromhex(value) if not any(ch.isspace() for ch in value) else _bad_hex()
    except ValueError as e:
        raise ValueError('invalid hex input (no spaces or prefix allowed)') from e


def _bad_hex():
    raise ValueError('hex must not contain whitespace')


def avalanche(data, bit):
    if bit < 0 or bit >= len(data) * 8:
        raise ValueError('bit index out of bounds (0 is the most-significant bit of byte 0)')
    changed = bytearray(data)
    changed[bit // 8] ^= 1 << (7 - bit % 8)
    a, b = hashlib.sha256(data).digest(), hashlib.sha256(changed).digest()
    return {'bit': bit, 'original_sha256': a.hex(), 'modified_sha256': b.hex(),
            'changed_bits_in_digest': sum((x ^ y).bit_count() for x, y in zip(a, b))}


def demonstrations():
    pairs = {
        'trailing_newline': (b'hello', b'hello\n'),
        'CRLF_vs_LF': (b'hello\r\n', b'hello\n'),
        'unicode_NFC_vs_NFD': ('é'.encode(), unicodedata.normalize('NFD', 'é').encode()),
        'integer_vs_string': (canonical_json({'n': 5}), canonical_json({'n': '5'})),
        'key_order_canonical': (canonical_json({'z': 1, 'a': 2}), canonical_json({'a': 2, 'z': 1})),
        'key_order_raw': (b'{"z":1,"a":2}', b'{"a":2,"z":1}'),
    }
    return {k: {'left_hex': x.hex(), 'right_hex': y.hex(), 'same_bytes': x == y,
                'left_sha256': hashlib.sha256(x).hexdigest(), 'right_sha256': hashlib.sha256(y).hexdigest()}
            for k, (x, y) in pairs.items()}


def main(argv=None):
    p = argparse.ArgumentParser(prog='hashlab')
    sub = p.add_subparsers(dest='cmd', required=True)
    for cmd, arg in [('text', 'value'), ('hex', 'value'), ('file', 'path'), ('canonical-json', 'path')]:
        s = sub.add_parser(cmd)
        s.add_argument(arg, help='for canonical-json use a JSON file or - for stdin' if cmd == 'canonical-json' else None)
    av = sub.add_parser('avalanche')
    group = av.add_mutually_exclusive_group(required=True)
    group.add_argument('--text')
    group.add_argument('--hex')
    group.add_argument('--file')
    av.add_argument('--bit', type=int, required=True)
    sub.add_parser('demo')
    args = p.parse_args(argv)
    try:
        if args.cmd == 'text': result = digest(args.value.encode('utf-8'))
        elif args.cmd == 'hex': result = digest(parse_hex(args.value))
        elif args.cmd == 'file': result = file_digest(args.path)
        elif args.cmd == 'canonical-json':
            content = sys.stdin.buffer.read() if args.path == '-' else Path(args.path).read_bytes()
            result = digest(canonical_json(json.loads(content)))
        elif args.cmd == 'avalanche':
            data = (args.text.encode('utf-8') if args.text is not None else
                    parse_hex(args.hex) if args.hex is not None else Path(args.file).read_bytes())
            result = avalanche(data, args.bit)
        else: result = demonstrations()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
