"""Domain-separated SHA-256 Merkle tree; odd nodes duplicated at each level."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def sha(b): return hashlib.sha256(b).digest()
def leaf_hash(data): return sha(b'\x00' + data)
def node_hash(left, right): return sha(b'\x01' + left + right)
EMPTY_ROOT = sha(b'\x02')


def levels(leaves):
    level = [leaf_hash(x) for x in leaves]
    if not level: return []
    result = [level]
    while len(level) > 1:
        level = [node_hash(level[i], level[i+1] if i + 1 < len(level) else level[i])
                 for i in range(0, len(level), 2)]
        result.append(level)
    return result


def root(leaves):
    lv = levels(leaves)
    return lv[-1][0] if lv else EMPTY_ROOT


def prove(leaves, index):
    if type(index) is not int or index < 0 or index >= len(leaves): raise ValueError('index out of range')
    lv = levels(leaves)
    proof = {'leaf_index': index, 'tree_size': len(leaves), 'siblings': []}
    for level in lv[:-1]:
        sibling_index = index ^ 1
        proof['siblings'].append({'side': 'left' if index & 1 else 'right',
                                  'hash': level[sibling_index if sibling_index < len(level) else index].hex()})
        index //= 2
    return proof


def validate_proof(proof):
    if not isinstance(proof, dict) or set(proof) != {'leaf_index', 'tree_size', 'siblings'}:
        raise ValueError('invalid proof fields')
    i, size, siblings = proof['leaf_index'], proof['tree_size'], proof['siblings']
    if type(i) is not int or type(size) is not int or not (0 <= i < size) or not isinstance(siblings, list):
        raise ValueError('invalid leaf index/tree size/siblings')
    expected_levels, n = 0, size
    while n > 1:
        expected_levels += 1
        n = (n + 1) // 2
    if len(siblings) != expected_levels: raise ValueError('proof has incorrect length')
    idx, width = i, size
    for s in siblings:
        if not isinstance(s, dict) or set(s) != {'side', 'hash'} or s['side'] not in ('left', 'right'):
            raise ValueError('invalid sibling direction/fields')
        if s['side'] != ('left' if idx % 2 else 'right'): raise ValueError('direction disagrees with leaf index')
        h = s['hash']
        if not isinstance(h, str) or len(h) != 64 or any(c not in '0123456789abcdef' for c in h):
            raise ValueError('invalid hash (lowercase 64-character hex required)')
        idx //= 2
        width = (width + 1) // 2


def verify(leaf, proof, expected_root):
    validate_proof(proof)
    if not isinstance(expected_root, str) or len(expected_root) != 64 or any(c not in '0123456789abcdef' for c in expected_root):
        raise ValueError('invalid expected root')
    h = leaf_hash(leaf)
    idx, width = proof['leaf_index'], proof['tree_size']
    for s in proof['siblings']:
        other = bytes.fromhex(s['hash'])
        if idx % 2 == 0 and idx + 1 >= width and other != h:
            return False  # a duplicated odd tail must match itself
        h = node_hash(other, h) if s['side'] == 'left' else node_hash(h, other)
        idx //= 2
        width = (width + 1) // 2
    return h.hex() == expected_root


def benchmarks(sizes=(8, 1024, 100000)):
    output = []
    for n in sizes:
        items = [i.to_bytes(8, 'big') for i in range(n)]
        start = time.perf_counter()
        top = root(items).hex()
        elapsed = time.perf_counter() - start
        p = prove(items, n // 2)
        output.append({'leaves': n, 'build_seconds': round(elapsed, 6),
                       'root': top, 'proof_steps': len(p['siblings']),
                       'proof_json_bytes': len(json.dumps(p, separators=(',', ':')).encode())})
    return output


def main(argv=None):
    p = argparse.ArgumentParser(prog='merkle')
    sub = p.add_subparsers(dest='cmd', required=True)
    for name in ('root', 'prove'):
        parser = sub.add_parser(name)
        parser.add_argument('items', help='JSON file containing an array of UTF-8 strings')
        if name == 'prove': parser.add_argument('--index', required=True, type=int)
    v = sub.add_parser('verify')
    v.add_argument('--leaf', required=True)
    v.add_argument('--proof', required=True)
    v.add_argument('--root', required=True)
    sub.add_parser('benchmark')
    args = p.parse_args(argv)
    try:
        if args.cmd in ('root', 'prove'):
            parsed = json.loads(Path(args.items).read_text('utf-8'))
            if not isinstance(parsed, list) or not all(isinstance(x, str) for x in parsed):
                raise ValueError('items must be a JSON list of strings')
            items = [x.encode('utf-8') for x in parsed]
            result = {'tree_size': len(items), 'root': root(items).hex()} if args.cmd == 'root' else prove(items, args.index)
        elif args.cmd == 'verify':
            result = {'valid': verify(args.leaf.encode(), json.loads(Path(args.proof).read_text('utf-8')), args.root)}
        else: result = benchmarks()
        print(json.dumps(result, indent=2))
        return 0 if args.cmd != 'verify' or result['valid'] else 1
    except (OSError, ValueError, TypeError, KeyError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 2


if __name__ == '__main__': sys.exit(main())
