"""Toy PoW chain with cumulative-work fork choice and state-snapshot reorganisations."""
import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path
from ledger import Ledger, canonical, txid, build_payment, outkey, check_uint, MAX
from merkle import root as merkle_root
from wallet import address_from_public, pub_bytes, parse_address, Ed25519PrivateKey

ZERO = '00' * 32
SUBSIDY = 50
MAX_TARGET = 2**256 - 1
EASY = 2**252 - 1
HARD = 2**250 - 1


def hash_header(header): return hashlib.sha256(header_bytes(header)).hexdigest()


def header_bytes(header):
    if not isinstance(header, dict) or set(header) != {'version','prev_hash','merkle_root','timestamp','target','nonce'}:
        raise ValueError('invalid block header fields')
    if type(header['version']) is not int or header['version'] != 1: raise ValueError('unsupported header version')
    for key in ('prev_hash','merkle_root'):
        s = header[key]
        if type(s) is not str or len(s) != 64 or any(c not in '0123456789abcdef' for c in s):
            raise ValueError('invalid ' + key)
    for key in ('timestamp','nonce'):
        check_uint(header[key], key)
    target = header['target']
    if type(target) is not int or not 1 <= target <= MAX_TARGET: raise ValueError('invalid target')
    return (header['version'].to_bytes(4,'little') + bytes.fromhex(header['prev_hash']) +
            bytes.fromhex(header['merkle_root']) + header['timestamp'].to_bytes(8,'little') +
            target.to_bytes(32,'big') + header['nonce'].to_bytes(8,'little'))


def block_root(transactions):
    return merkle_root([canonical(tx) for tx in transactions]).hex()


def coinbase(height, miner, reward=SUBSIDY):
    parse_address(miner)
    check_uint(height,'height')
    check_uint(reward,'reward',positive=True)
    return {'coinbase': True, 'height': height, 'outputs': [{'value':reward,'address':miner}]}


def mine(prev_hash, transactions, target=EASY, timestamp=None, start_nonce=0):
    header = {'version':1, 'prev_hash':prev_hash, 'merkle_root':block_root(transactions),
              'timestamp':int(time.time()) if timestamp is None else timestamp,
              'target':target, 'nonce':start_nonce}
    start=time.perf_counter()
    while header['nonce'] <= MAX:
        value=int(hash_header(header),16)
        if value <= target:
            seconds=time.perf_counter()-start
            return {'header':header.copy(),'transactions':copy.deepcopy(transactions)}, {
                'attempts':header['nonce']-start_nonce+1,'seconds':round(seconds,6),
                'hashes_per_second':round((header['nonce']-start_nonce+1)/max(seconds,1e-9),2)}
        header['nonce'] += 1
    raise ValueError('nonce range exhausted')


def work(target): return (1 << 256) // (target+1)


class Chain:
    def __init__(self):
        self.nodes = {}  # hash -> {block,parent,height,work,state}
        self.tip = None
        self.utxos = {}  # active-chain state; snapshots allow rollback without inverse tx replay
        self.reorg_log = []

    def branch(self, parent):
        if parent == ZERO: return Ledger(), -1, 0
        if parent not in self.nodes: raise ValueError('unknown parent block')
        node = self.nodes[parent]
        return Ledger(node['state']), node['height'], node['work']

    def add(self, block):
        if not isinstance(block, dict) or set(block) != {'header','transactions'}:
            raise ValueError('invalid block format')
        header, transactions = block['header'], block['transactions']
        hb = header_bytes(header)
        block_id = hashlib.sha256(hb).hexdigest()
        if block_id in self.nodes: raise ValueError('duplicate block')
        if int(block_id,16) > header['target']: raise ValueError('invalid proof of work')
        parent = header['prev_hash']
        if parent == ZERO and self.nodes: raise ValueError('second genesis not allowed')
        ledger, parent_height, parent_work = self.branch(parent)
        if parent != ZERO and header['timestamp'] < self.nodes[parent]['block']['header']['timestamp']:
            raise ValueError('timestamp earlier than parent')
        if not isinstance(transactions,list) or not transactions: raise ValueError('empty block transactions')
        if block_root(transactions) != header['merkle_root']: raise ValueError('incorrect Merkle root')
        height = parent_height + 1
        first = transactions[0]
        if not isinstance(first,dict) or set(first) != {'coinbase','height','outputs'} or first.get('coinbase') is not True or first.get('height') != height or type(first['height']) is not int:
            raise ValueError('invalid coinbase placement/height')
        outputs = first['outputs']
        if not isinstance(outputs,list) or len(outputs) != 1 or not isinstance(outputs[0],dict) or set(outputs[0]) != {'value','address'}:
            raise ValueError('invalid coinbase outputs')
        check_uint(outputs[0]['value'], 'coinbase value', True)
        parse_address(outputs[0]['address'])
        fees = 0
        seen = set()
        for transaction in transactions[1:]:
            if isinstance(transaction, dict) and 'coinbase' in transaction: raise ValueError('extra coinbase')
            tid = txid(transaction)
            if tid in seen: raise ValueError('duplicate transaction in block')
            seen.add(tid)
            fee = ledger.apply(transaction)
            if fees > MAX-fee: raise ValueError('fee overflow')
            fees += fee
        if fees > MAX-SUBSIDY or outputs[0]['value'] > SUBSIDY+fees:
            raise ValueError('excess coinbase value')
        coinbase_id = hashlib.sha256(canonical(first)).hexdigest()
        cb_outpoint = outkey(coinbase_id, 0)
        if cb_outpoint in ledger.utxos: raise ValueError('coinbase outpoint collision')
        ledger.utxos[cb_outpoint] = copy.deepcopy(outputs[0])
        accumulated = parent_work + work(header['target'])
        # Only commit a fully checked block. Active state only changes if it wins.
        self.nodes[block_id] = {'block':copy.deepcopy(block), 'parent':parent,
                                'height':height,'work':accumulated,'state':copy.deepcopy(ledger.utxos)}
        current = self.nodes[self.tip]['work'] if self.tip else -1
        if accumulated > current:  # deterministic tie: keep incumbent
            old = self.tip
            self.tip = block_id
            self.utxos = copy.deepcopy(ledger.utxos)
            if old is not None and parent != old:
                self.reorg_log.append({'old_tip':old,'new_tip':block_id,
                                       'disconnected':self._disconnected(old,block_id)})
        return block_id

    def _disconnected(self, old_tip, new_tip):
        ancestors = set()
        cur = new_tip
        while cur != ZERO:
            ancestors.add(cur);cur=self.nodes[cur]['parent']
        stale=[];cur=old_tip
        while cur not in ancestors and cur != ZERO:
            stale.append(cur);cur=self.nodes[cur]['parent']
        return stale

    def active_path(self):
        path=[];cur=self.tip
        while cur is not None and cur != ZERO:
            path.append(cur);cur=self.nodes[cur]['parent']
        return list(reversed(path))


def simulate():
    alice=Ed25519PrivateKey.from_private_bytes(b'\x01'*32)
    bob=Ed25519PrivateKey.from_private_bytes(b'\x02'*32)
    a=address_from_public(pub_bytes(alice));b=address_from_public(pub_bytes(bob))
    chain=Chain(); stats=[]
    genesis, metric = mine(ZERO,[coinbase(0,a)], EASY, timestamp=100)
    g=chain.add(genesis);stats.append(metric)
    # Miner A makes a 3-block EASY branch containing a spend to Bob.
    spend=build_payment(Ledger(chain.utxos),alice,b,25,1,nonce=1)
    aa1,m=mine(g,[coinbase(1,a,51),spend], EASY, timestamp=101); a1=chain.add(aa1);stats.append(m)
    aa2,m=mine(a1,[coinbase(2,a)], EASY, timestamp=102); a2=chain.add(aa2);stats.append(m)
    aa3,m=mine(a2,[coinbase(3,a)], EASY, timestamp=103); a3=chain.add(aa3);stats.append(m)
    before=copy.deepcopy(chain.utxos)
    # Miner B has 1 much-harder block off genesis: 64 work vs A's 3*16=48.
    bb1,m=mine(g,[coinbase(1,b)], HARD, timestamp=104); b1=chain.add(bb1);stats.append(m)
    assert chain.tip==b1
    assert chain.utxos==chain.nodes[b1]['state']
    assert chain.utxos != before
    return {'genesis':g, 'branch_A':{'blocks':[a1,a2,a3], 'work':chain.nodes[a3]['work'],
                                   'height':chain.nodes[a3]['height']},
            'branch_B':{'blocks':[b1], 'work':chain.nodes[b1]['work'], 'height':chain.nodes[b1]['height']},
            'selected_tip':chain.tip, 'active_path':chain.active_path(),
            'reorganisations':chain.reorg_log, 'before_utxos':before, 'after_utxos':chain.utxos,
            'genesis_header_hex':header_bytes(genesis['header']).hex(), 'mining_stats':stats}


def benchmark(targets=(2**253-1, EASY, HARD), count=20):
    output=[]
    alice=address_from_public(pub_bytes(Ed25519PrivateKey.from_private_bytes(b'\x03'*32)))
    for target in targets:
        attempts=[];start=time.perf_counter()
        for j in range(count):
            _,m=mine(ZERO,[coinbase(0,alice)],target,timestamp=100+j)
            attempts.append(m['attempts'])
        elapsed=time.perf_counter()-start
        output.append({'target_hex':f'{target:064x}','expected_attempts':round(2**256/(target+1),3),
                       'observed_avg_attempts':round(sum(attempts)/count,3),
                       'total_hashes':sum(attempts), 'total_seconds':round(elapsed,6),
                       'hashes_per_second':round(sum(attempts)/max(elapsed,1e-9),2)})
    return output


def main(argv=None):
    p=argparse.ArgumentParser(prog='chain')
    sub=p.add_subparsers(dest='cmd',required=True)
    sub.add_parser('fork-demo')
    bm=sub.add_parser('benchmark');bm.add_argument('--trials',type=int,default=20)
    mn=sub.add_parser('mine');mn.add_argument('--parent',default=ZERO);mn.add_argument('--height',type=int,default=0)
    mn.add_argument('--miner',required=True);mn.add_argument('--target',default=f'{EASY:064x}',help='64-character hex target')
    mn.add_argument('--timestamp',type=int);mn.add_argument('--reward',type=int,default=SUBSIDY)
    args=p.parse_args(argv)
    try:
        if args.cmd=='fork-demo': result=simulate()
        elif args.cmd=='benchmark':
            if args.trials<1: raise ValueError('trials must be positive')
            result=benchmark(count=args.trials)
        else:
            target=int(args.target,16)
            block,metrics=mine(args.parent,[coinbase(args.height,args.miner,args.reward)],target,args.timestamp)
            result={'block':block,'header_hex':header_bytes(block['header']).hex(),
                    'block_hash':hash_header(block['header']),'metrics':metrics}
        print(json.dumps(result,indent=2))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as e:
        print(f'rejected: {e}',file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
