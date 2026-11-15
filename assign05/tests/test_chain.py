import copy
import pytest
from chain import *

@pytest.fixture
def env():
    alice=Ed25519PrivateKey.from_private_bytes(b'\x01'*32)
    bob=Ed25519PrivateKey.from_private_bytes(b'\x02'*32)
    a=address_from_public(pub_bytes(alice));b=address_from_public(pub_bytes(bob))
    c=Chain();block,_=mine(ZERO,[coinbase(0,a)],EASY,timestamp=10)
    genesis=c.add(block)
    return c,genesis,alice,a,b


def test_genesis(env):
    c,g,*_=env
    assert c.tip==g and len(c.utxos)==1 and c.nodes[g]['height']==0


def test_work(): assert work(HARD)>3*work(EASY)


def test_mine_pow(env):
    _,g,_,a,_=env
    b,m=mine(g,[coinbase(1,a)],EASY,timestamp=11)
    assert int(hash_header(b['header']),16)<=EASY
    assert m['attempts']>=1


def test_hex_size(env):
    c,g,*_=env
    assert len(header_bytes(c.nodes[g]['block']['header']))==116


def test_reorg():
    result=simulate()
    assert result['selected_tip']==result['branch_B']['blocks'][0]
    assert result['branch_B']['height']<result['branch_A']['height']
    assert result['branch_B']['work']>result['branch_A']['work']
    assert result['before_utxos']!=result['after_utxos']
    assert result['reorganisations'][-1]['disconnected'] == list(reversed(result['branch_A']['blocks']))


def invalid(env, modify, reason=None, remine=False):
    c,g,_,a,b=env
    block,_=mine(g,[coinbase(1,a)],EASY,timestamp=11)
    modify(block,a,b)
    if remine:
        h=block['header'];block,_=mine(h['prev_hash'],block['transactions'],h['target'],h['timestamp'])
    else:
        h=block['header']
        try:
            while int(hash_header(h),16)>h['target']:
                h['nonce'] += 1
        except (ValueError,OverflowError,TypeError):
            pass
    old=copy.deepcopy(c.utxos);tip=c.tip;count=len(c.nodes)
    with pytest.raises(ValueError,match=reason): c.add(block)
    assert c.utxos==old and c.tip==tip and len(c.nodes)==count


def test_wrong_root(env): invalid(env,lambda bl,a,b:bl['header'].update(merkle_root='00'*32),'Merkle')


def test_invalid_pow(env):
    c,g,_,a,_=env
    block,_=mine(g,[coinbase(1,a)],EASY,timestamp=11)
    # deterministically set nonce so hash fails PoW
    nonce=block['header']['nonce']+1
    while True:
        block['header']['nonce']=nonce
        if int(hash_header(block['header']),16)>EASY:break
        nonce+=1
    before=copy.deepcopy(c.utxos)
    with pytest.raises(ValueError,match='proof of work'):c.add(block)
    assert c.utxos==before


def test_excess_reward(env): invalid(env,lambda bl,a,b:bl['transactions'][0]['outputs'][0].update(value=51),'excess',True)

def test_bad_coinbase_height(env): invalid(env,lambda bl,a,b:bl['transactions'][0].update(height=99),'coinbase',True)

def test_bad_coinbase_placement(env): invalid(env,lambda bl,a,b:bl['transactions'].insert(0,{}),'coinbase',True)

def test_bad_timestamp(env): invalid(env,lambda bl,a,b:bl['header'].update(timestamp=9),'timestamp',True)

def test_unknown_parent(env): invalid(env,lambda bl,a,b:bl['header'].update(prev_hash='dd'*32),'unknown parent')

def test_invalid_header_version(env): invalid(env,lambda bl,a,b:bl['header'].update(version=3),'version')

def test_bad_target(env): invalid(env,lambda bl,a,b:bl['header'].update(target=0),'target')

def test_duplicate_block(env):
    c,g,_,a,_=env
    with pytest.raises(ValueError,match='duplicate'):c.add(c.nodes[g]['block'])


def test_invalid_tx(env):
    c,g,private,a,b=env
    spend=build_payment(Ledger(c.utxos),private,b,25,1)
    spend['outputs'][0]['value']=26
    block,_=mine(g,[coinbase(1,a),spend],EASY,timestamp=11)
    before=copy.deepcopy(c.utxos)
    with pytest.raises(ValueError,match='bad signature'):c.add(block)
    assert c.utxos==before


def test_valid_tx(env):
    c,g,private,a,b=env
    spend=build_payment(Ledger(c.utxos),private,b,25,1)
    block,_=mine(g,[coinbase(1,a,51),spend],EASY,timestamp=11)
    c.add(block)
    assert any(x['value']==25 and x['address']==b for x in c.utxos.values())


def test_duplicate_tx(env):
    c,g,private,a,b=env
    spend=build_payment(Ledger(c.utxos),private,b,25,1)
    block,_=mine(g,[coinbase(1,a,51),spend,spend],EASY,timestamp=11)
    with pytest.raises(ValueError):c.add(block)


def test_extra_coinbase(env):
    c,g,private,a,b=env
    block,_=mine(g,[coinbase(1,a),coinbase(1,b)],EASY,timestamp=11)
    with pytest.raises(ValueError,match='extra coinbase'):c.add(block)


def test_benchmark(): assert len(benchmark((2**255-1,),count=2))==1
