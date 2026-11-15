import copy
import hashlib
import json
import os
import stat
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from wallet import *

@pytest.fixture
def fixture():
    priv, _ = create_keys()
    signer = Ed25519PrivateKey.from_private_bytes(priv)
    sender = address_from_public(pub_bytes(signer))
    _, recipient_pub = create_keys()
    tx = {'version': 1, 'network_id': NETWORK, 'sender': sender,
          'recipient': address_from_public(recipient_pub), 'amount_units': 1250000,
          'nonce': 7, 'memo_hash': hashlib.sha256(b'memo').hexdigest()}
    return signer, tx


def test_address_roundtrip(fixture):
    priv, tx = fixture
    assert parse_address(tx['sender']) == hashlib.sha256(pub_bytes(priv)).digest()[:20]


def test_base58_leading_zero(): assert b58decode(b58encode(b'\x00\x00\x01')) == b'\x00\x00\x01'

@pytest.mark.parametrize('bad', ['0', 'O', 'l', 'abc', ''])
def test_bad_address(bad):
    with pytest.raises(ValueError): parse_address(bad)


def test_checksum(fixture):
    address = fixture[1]['sender']
    last = '1' if address[-1] != '1' else '2'
    with pytest.raises(ValueError): parse_address(address[:-1] + last)


def test_sign_verify(fixture):
    priv, tx = fixture
    assert verify_signed(sign(tx, priv))

@pytest.mark.parametrize('field,value', [('amount_units', 1), ('nonce', 8), ('network_id','other'), ('memo_hash','0'*64), ('recipient', None)])
def test_tamper(fixture, field, value):
    priv, tx = fixture
    env = sign(tx, priv)
    env['transaction'][field] = value
    with pytest.raises(ValueError): verify_signed(env)


def test_wrong_signer(fixture):
    _, tx = fixture
    seed, _ = create_keys()
    with pytest.raises(ValueError): sign(tx, Ed25519PrivateKey.from_private_bytes(seed))


def test_replay(fixture):
    priv, tx = fixture
    env = sign(tx, priv)
    state = set()
    assert verify_signed(env, state)
    with pytest.raises(ValueError, match='replayed'): verify_signed(env, state)


def test_noncanonical_signature(fixture):
    env = sign(fixture[1], fixture[0])
    env['signature'] = env['signature'].upper()
    with pytest.raises(ValueError): verify_signed(env)


def test_order_whitespace(fixture):
    tx = fixture[1]
    assert transaction_bytes(tx) == transaction_bytes(json.loads(json.dumps(dict(reversed(list(tx.items()))), indent=6)))


def test_private_file(tmp_path):
    seed, _ = create_keys()
    path = tmp_path / 'test.key'
    save_private(path, seed)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert pub_bytes(read_private(path))
    with pytest.raises(FileExistsError): save_private(path, seed)

@pytest.mark.parametrize('amount', [0, -1, 2**64, True, '5'])
def test_invalid_amount(fixture, amount):
    tx = fixture[1]; tx['amount_units'] = amount
    with pytest.raises(ValueError): transaction_bytes(tx)
