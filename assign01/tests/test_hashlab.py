import base64
import hashlib
import json
import tracemalloc
import pytest
from hashlab import digest, parse_hex, avalanche, canonical_json, file_digest, demonstrations, main


def test_nist_empty():
    assert digest(b'')['sha256'] == 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'


def test_nist_abc():
    assert digest(b'abc')['sha256'] == hashlib.sha256(b'abc').hexdigest()


def test_base64():
    assert digest(b'x')['base64'] == base64.b64encode(hashlib.sha256(b'x').digest()).decode()

@pytest.mark.parametrize('s', ['a', 'zz', '0x12', '12 34', '12\n34'])
def test_bad_hex(s):
    with pytest.raises(ValueError): parse_hex(s)


def test_hex_ok(): assert parse_hex('00FF') == b'\x00\xff'

def test_avalanche():
    r = avalanche(b'abc', 7)
    assert 0 <= r['changed_bits_in_digest'] <= 256
    assert r['original_sha256'] != r['modified_sha256']

@pytest.mark.parametrize('bit', [-1, 0, 8])
def test_invalid_bit(bit):
    with pytest.raises(ValueError): avalanche(b'\x00' if bit == 8 else b'', bit)


def test_canonical_order():
    assert canonical_json({'b': 2, 'a': 1}) == canonical_json({'a': 1, 'b': 2})


def test_canonical_types():
    assert canonical_json({'a': 1}) != canonical_json({'a': '1'})


def test_canonical_reject_non_object():
    with pytest.raises(ValueError): canonical_json([])


def test_newline():
    assert digest(b'abc')['sha256'] != digest(b'abc\n')['sha256']


def test_unicode():
    assert demonstrations()['unicode_NFC_vs_NFD']['same_bytes'] is False


def test_stream_large(tmp_path):
    p = tmp_path / 'large.bin'
    with p.open('wb') as f:
        for _ in range(100): f.write(b'a' * 1024 * 1024)
    tracemalloc.start()
    r = file_digest(p)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert r['bytes'] == 100 * 1024 * 1024
    assert peak < 6 * 1024 * 1024
    assert r['sha256'] == hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()


def test_cli(capsys):
    assert main(['text', 'abc']) == 0
    assert json.loads(capsys.readouterr().out)['bytes'] == 3
    assert main(['hex', 'not-hex']) == 2
