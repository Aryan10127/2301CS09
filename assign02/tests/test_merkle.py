import copy
import hashlib
import json
import pytest
from merkle import root, prove, verify, validate_proof, leaf_hash, EMPTY_ROOT, benchmarks, main

ITEMS = [x.encode() for x in 'abcde']


def test_empty(): assert root([]) == EMPTY_ROOT

def test_single():
    assert root([b'a']) == leaf_hash(b'a')
    assert prove([b'a'], 0)['siblings'] == []
    assert verify(b'a', prove([b'a'], 0), root([b'a']).hex())

@pytest.mark.parametrize('n', [2, 3, 4, 5, 8, 9, 17])
def test_every_leaf(n):
    leaves = ITEMS[:n] if n <= 5 else [bytes([i]) for i in range(n)]
    for i, leaf in enumerate(leaves):
        p = prove(leaves, i)
        assert verify(leaf, p, root(leaves).hex())
        assert not verify(leaf + b'!', p, root(leaves).hex())


def test_root_order(): assert root([b'a', b'b']) != root([b'b', b'a'])

def test_leaf_domain(): assert leaf_hash(b'a') != hashlib.sha256(b'a').digest()

@pytest.mark.parametrize('mutate', [
    lambda p: p.update(leaf_index=-1), lambda p: p.update(tree_size=0),
    lambda p: p['siblings'].append(p['siblings'][0]),
    lambda p: p['siblings'][0].update(side='up'),
    lambda p: p['siblings'][0].update(side='left'),
    lambda p: p['siblings'][0].update(hash='bad'),
    lambda p: p['siblings'][0].update(hash='F'*64),
    lambda p: p.update(leaf_index=True),
])
def test_bad_proofs(mutate):
    p = prove(ITEMS, 0)
    mutate(p)
    with pytest.raises(ValueError): validate_proof(p)


def test_odd_tail_tamper():
    p = prove(ITEMS, 4)
    p['siblings'][0]['hash'] = '00' * 32
    assert not verify(ITEMS[4], p, root(ITEMS).hex())


def test_proof_json_roundtrip():
    p = prove(ITEMS, 2)
    assert verify(ITEMS[2], json.loads(json.dumps(p)), root(ITEMS).hex())


def test_wrong_index_in_range():
    p = prove(ITEMS, 1)
    p['leaf_index'] = 0
    with pytest.raises(ValueError): validate_proof(p)


def test_benchmark_small():
    assert [x['leaves'] for x in benchmarks((8, 16))] == [8, 16]


def test_cli(tmp_path, capsys):
    path = tmp_path / 'items.json'
    path.write_text('["a", "b", "c", "d", "e"]')
    assert main(['prove', str(path), '--index', '2']) == 0
    proof = json.loads(capsys.readouterr().out)
    fp = tmp_path / 'proof.json'
    fp.write_text(json.dumps(proof))
    assert main(['verify', '--leaf', 'c', '--proof', str(fp), '--root', root(ITEMS).hex()]) == 0
