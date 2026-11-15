"""In-memory P2PKH UTXO validator with canonical Ed25519 signatures."""
import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path
from wallet import (NETWORK, address_from_public, parse_address, parse_public, pub_bytes,
                    create_keys, verify_signed, Ed25519PrivateKey)

MAX = 2**64 - 1
DOMAIN = b'COURSE-UTXO-v1\x00'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


def hex32(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def outkey(txid, index): return f'{txid}:{index}'


def unsigned(tx):
    return {'version': tx['version'], 'network_id': tx['network_id'], 'nonce': tx['nonce'],
            'inputs': [{'txid': i['txid'], 'index': i['index']} for i in tx['inputs']],
            'outputs': tx['outputs']}


def txid(tx): return hashlib.sha256(canonical(tx)).hexdigest()


def check_uint(value, name, positive=False):
    if type(value) is not int or not (1 if positive else 0) <= value <= MAX:
        raise ValueError(f'invalid {name}: uint64 required')


def validate_shape(tx):
    if not isinstance(tx, dict) or set(tx) != {'version','network_id','nonce','inputs','outputs'}:
        raise ValueError('transaction fields mismatch')
    if tx['version'] != 1 or type(tx['version']) is not int: raise ValueError('unsupported transaction version')
    if tx['network_id'] != NETWORK: raise ValueError('wrong network')
    check_uint(tx['nonce'], 'nonce')
    if not isinstance(tx['inputs'], list) or not tx['inputs']: raise ValueError('empty inputs')
    if not isinstance(tx['outputs'], list) or not tx['outputs']: raise ValueError('empty outputs')
    for i in tx['inputs']:
        if not isinstance(i, dict) or set(i) != {'txid', 'index', 'public_key', 'signature'}:
            raise ValueError('invalid input fields')
        if not hex32(i['txid']): raise ValueError('invalid outpoint transaction ID')
        check_uint(i['index'], 'output index')
        parse_public(i['public_key'])
        sig = i['signature']
        if type(sig) is not str or len(sig) != 128 or any(c not in '0123456789abcdef' for c in sig):
            raise ValueError('noncanonical signature')
    for o in tx['outputs']:
        if not isinstance(o, dict) or set(o) != {'value','address'}: raise ValueError('invalid output fields')
        check_uint(o['value'], 'output value', positive=True)
        parse_address(o['address'])


class Ledger:
    def __init__(self, utxos=None):
        self.utxos = copy.deepcopy(utxos if utxos is not None else {})
        self._validate_snapshot()

    def _validate_snapshot(self):
        for key, item in self.utxos.items():
            if not isinstance(key, str) or ':' not in key or not isinstance(item, dict) or set(item) != {'value','address'}:
                raise ValueError('malformed snapshot')
            tx, idx = key.rsplit(':', 1)
            if not hex32(tx) or not idx.isdigit() or str(int(idx)) != idx: raise ValueError('invalid snapshot outpoint')
            check_uint(item['value'], 'snapshot value', True)
            parse_address(item['address'])

    def apply(self, tx):
        """Return fee; no mutation until *all* checks have passed."""
        validate_shape(tx)
        keys = [outkey(i['txid'], i['index']) for i in tx['inputs']]
        if len(keys) != len(set(keys)): raise ValueError('duplicate input outpoint')
        missing = [k for k in keys if k not in self.utxos]
        if missing: raise ValueError('nonexistent or already spent input: ' + missing[0])
        total_out = 0
        for output in tx['outputs']:
            if total_out > MAX - output['value']: raise ValueError('output sum overflow')
            total_out += output['value']
        signable = DOMAIN + canonical(unsigned(tx))
        total_in = 0
        for inp, key in zip(tx['inputs'], keys):
            previous = self.utxos[key]
            if address_from_public(bytes.fromhex(inp['public_key'])) != previous['address']:
                raise ValueError('authorization failed: public key does not own input')
            try:
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
                Ed25519PublicKey.from_public_bytes(bytes.fromhex(inp['public_key'])).verify(
                    bytes.fromhex(inp['signature']), signable)
            except Exception as exc:
                raise ValueError('bad signature') from exc
            if total_in > MAX - previous['value']: raise ValueError('input sum overflow')
            total_in += previous['value']
        if total_out > total_in: raise ValueError('outputs exceed inputs')
        identifier = txid(tx)
        new_keys = [outkey(identifier, i) for i in range(len(tx['outputs']))]
        if any(k in self.utxos and k not in keys for k in new_keys): raise ValueError('txid collision')
        new_state = self.utxos.copy()
        for key in keys: del new_state[key]
        for key, output in zip(new_keys, tx['outputs']): new_state[key] = copy.deepcopy(output)
        self.utxos = new_state
        return total_in - total_out

    def save(self, path):
        Path(path).write_text(json.dumps({'format':'course-utxo-v1', 'utxos':self.utxos}, indent=2, sort_keys=True)+'\n')

    @classmethod
    def load(cls, path):
        data = json.loads(Path(path).read_text('utf-8'))
        if not isinstance(data, dict) or set(data) != {'format', 'utxos'} or data['format'] != 'course-utxo-v1':
            raise ValueError('invalid ledger snapshot format')
        return cls(data['utxos'])


def build_payment(ledger, private, recipient, amount, fee, nonce=0):
    """Deterministic largest-first selection, lexical outpoint tie-breaker."""
    check_uint(amount, 'amount', positive=True)
    check_uint(fee, 'fee')
    check_uint(nonce, 'nonce')
    if amount > MAX - fee: raise ValueError('amount plus fee overflow')
    parse_address(recipient)
    sender = address_from_public(pub_bytes(private))
    choices = sorted(((k, v) for k, v in ledger.utxos.items() if v['address'] == sender),
                     key=lambda item: (-item[1]['value'], item[0]))
    chosen = []
    total = 0
    for key, v in choices:
        chosen.append(key)
        if total > MAX - v['value']: raise ValueError('coin selection overflow')
        total += v['value']
        if total >= amount + fee: break
    if total < amount + fee: raise ValueError('insufficient funds')
    outputs = [{'value': amount, 'address': recipient}]
    change = total - amount - fee
    if change: outputs.append({'value': change, 'address': sender})
    inputs = []
    for key in chosen:
        prevtx, idx = key.rsplit(':', 1)
        inputs.append({'txid': prevtx, 'index': int(idx), 'public_key': pub_bytes(private).hex(), 'signature': ''})
    tx = {'version': 1, 'network_id': NETWORK, 'nonce': nonce, 'inputs': inputs, 'outputs': outputs}
    signed_bytes = DOMAIN + canonical(unsigned(tx))
    for i in tx['inputs']: i['signature'] = private.sign(signed_bytes).hex()
    return tx


def example():
    # Deterministic *public* fixed inputs, for reproducible trace only; NEVER use on mainnet.
    alice = Ed25519PrivateKey.from_private_bytes(b'\x01'*32)
    bob = Ed25519PrivateKey.from_private_bytes(b'\x02'*32)
    a = address_from_public(pub_bytes(alice)); b = address_from_public(pub_bytes(bob))
    ledger = Ledger({outkey('aa'*32, 0): {'value':40,'address':a},
                     outkey('bb'*32, 0): {'value':70,'address':a}})
    tx = build_payment(ledger, alice, b, 85, 2, nonce=7)
    accepted_fee = ledger.apply(tx)
    after = copy.deepcopy(ledger.utxos)
    try: ledger.apply(tx)
    except ValueError as e: rejected = str(e)
    return {'initial': {'format':'course-utxo-v1', 'utxos': {
                outkey('aa'*32, 0):{'value':40,'address':a},outkey('bb'*32, 0):{'value':70,'address':a}}},
            'transaction': tx, 'accepted': {'txid':txid(tx), 'fee':accepted_fee},
            'final': {'format':'course-utxo-v1','utxos':after},
            'rejected_second_spend': rejected}


def main(argv=None):
    p = argparse.ArgumentParser(prog='ledger')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('demo')
    val = sub.add_parser('apply'); val.add_argument('--state', required=True); val.add_argument('--transaction', required=True); val.add_argument('--out', required=True)
    b = sub.add_parser('build'); b.add_argument('--state', required=True); b.add_argument('--private-key', required=True)
    b.add_argument('--recipient', required=True); b.add_argument('--amount', type=int, required=True)
    b.add_argument('--fee', type=int, required=True); b.add_argument('--nonce', type=int, default=0)
    args = p.parse_args(argv)
    try:
        if args.cmd == 'demo': result = example()
        elif args.cmd == 'build':
            from wallet import read_private
            result = build_payment(Ledger.load(args.state), read_private(args.private_key), args.recipient, args.amount, args.fee, args.nonce)
        else:
            state = Ledger.load(args.state)
            tx = json.loads(Path(args.transaction).read_text())
            fee = state.apply(tx)
            state.save(args.out)
            result = {'accepted': True, 'fee':fee, 'txid':txid(tx), 'state_path':args.out}
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f'rejected: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__': sys.exit(main())
