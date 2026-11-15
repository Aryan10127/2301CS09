import copy
import json
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from ledger import *
from wallet import address_from_public, pub_bytes

@pytest.fixture
def env():
    a = Ed25519PrivateKey.from_private_bytes(b'\x01'*32)
    b = Ed25519PrivateKey.from_private_bytes(b'\x02'*32)
    addr_a = address_from_public(pub_bytes(a)); addr_b = address_from_public(pub_bytes(b))
    state = Ledger({outkey('aa'*32,0):{'value':40,'address':addr_a},
                    outkey('bb'*32,0):{'value':70,'address':addr_a}})
    return state,a,b,addr_a,addr_b


def test_example(): assert example()['accepted']['fee'] == 2

def test_change(env):
    l,a,_,sender,b = env
    tx = build_payment(l,a,b,85,2,7)
    assert tx['outputs'] == [{'value':85,'address':b},{'value':23,'address':sender}]
    assert len(tx['inputs']) == 2
    assert l.apply(tx) == 2


def test_state_unchanged_before_apply(env):
    l,a,_,_,b = env
    old=copy.deepcopy(l.utxos); build_payment(l,a,b,85,2); assert l.utxos==old


def test_repeated_spend(env):
    l,a,_,_,b=env; tx=build_payment(l,a,b,85,2)
    l.apply(tx)
    with pytest.raises(ValueError,match='already spent'): l.apply(tx)


def test_insufficient(env):
    l,a,_,_,b=env
    with pytest.raises(ValueError,match='insufficient'): build_payment(l,a,b,110,1)


def test_exact_change_zero(env):
    l,a,_,_,b=env; tx=build_payment(l,a,b,68,2)
    assert len(tx['outputs'])==1


def test_largest_first(env):
    l,a,_,_,b=env; tx=build_payment(l,a,b,30,1)
    assert tx['inputs'][0]['txid']=='bb'*32


def test_snapshot(env,tmp_path):
    l,*_=env; path=tmp_path/'state.json'; l.save(path)
    assert Ledger.load(path).utxos == l.utxos


def test_invalid_snapshot(env,tmp_path):
    p=tmp_path/'state'; p.write_text('{}')
    with pytest.raises(ValueError): Ledger.load(p)


def bad(env, edit, match=None):
    l,a,other,_,b=env
    tx=build_payment(l,a,b,85,2)
    before=copy.deepcopy(l.utxos)
    edit(tx, other, b)
    with pytest.raises(ValueError, match=match): l.apply(tx)
    assert l.utxos==before


def test_nonexistent(env): bad(env,lambda t,o,b:t['inputs'][0].update(txid='00'*32),'nonexistent')

def test_duplicate(env): bad(env,lambda t,o,b:t['inputs'].append(copy.deepcopy(t['inputs'][0])),'duplicate')

def test_bad_signature(env): bad(env,lambda t,o,b:t['inputs'][0].update(signature='00'*64),'bad signature')

def test_wrong_signer(env): bad(env,lambda t,o,b:t['inputs'][0].update(public_key=pub_bytes(o).hex()),'authorization')

def test_negative_output(env): bad(env,lambda t,o,b:t['outputs'][0].update(value=-1),'invalid')

def test_zero_output(env): bad(env,lambda t,o,b:t['outputs'][0].update(value=0),'invalid')

def test_overflow_output(env): bad(env,lambda t,o,b:t['outputs'][0].update(value=MAX+1),'invalid')

def test_creation(env): bad(env,lambda t,o,b:t['outputs'][0].update(value=200),'bad signature')

def test_signed_creation_rejected(env):
    l,a,_,_,b=env
    tx=build_payment(l,a,b,85,2)
    tx['outputs'][0]['value']=200
    signature=a.sign(DOMAIN+canonical(unsigned(tx))).hex()
    for item in tx['inputs']: item['signature']=signature
    old=copy.deepcopy(l.utxos)
    with pytest.raises(ValueError,match='exceed'):l.apply(tx)
    assert l.utxos==old

def test_bad_change(env): bad(env,lambda t,o,b:t['outputs'][1].update(value=24),'bad signature')

def test_wrong_network(env): bad(env,lambda t,o,b:t.update(network_id='mainnet'),'wrong network')

def test_wrong_version(env): bad(env,lambda t,o,b:t.update(version=2),'version')

def test_bad_txid(env): bad(env,lambda t,o,b:t['inputs'][0].update(txid='xx'),'invalid outpoint')

def test_bad_address(env): bad(env,lambda t,o,b:t['outputs'][0].update(address='invalid'),'Base58')

def test_noncanonical_sig(env): bad(env,lambda t,o,b:t['inputs'][0].update(signature='a'),'noncanonical')

def test_wrong_nonce_type(env): bad(env,lambda t,o,b:t.update(nonce=True),'nonce')

def test_empty_inputs(env): bad(env,lambda t,o,b:t.update(inputs=[]),'empty inputs')

def test_empty_outputs(env): bad(env,lambda t,o,b:t.update(outputs=[]),'empty outputs')

def test_output_sum_overflow(env):
    bad(env,lambda t,o,b:t.update(outputs=[{'value':MAX,'address':b},{'value':10,'address':b}]),'overflow')

def test_input_sum_overflow(env):
    l,a,_,_,b=env
    l.utxos[outkey('aa'*32,0)]['value']=MAX
    tx=build_payment(l,a,b,85,2)
    # force two valid signed inputs using an independent state builder
    tx2=build_payment(Ledger({outkey('aa'*32,0):{'value':40,'address':address_from_public(pub_bytes(a))},
                              outkey('bb'*32,0):{'value':70,'address':address_from_public(pub_bytes(a))}}),a,b,85,2)
    before=copy.deepcopy(l.utxos)
    with pytest.raises(ValueError,match='overflow'): l.apply(tx2)
    assert l.utxos==before

def test_deterministic_id(env):
    l,a,_,_,b=env; x=build_payment(l,a,b,85,2)
    assert txid(x)==txid(copy.deepcopy(x))
