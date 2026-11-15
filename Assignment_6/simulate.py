"""
Run: python simulate.py
Starts 5 nodes, broadcasts txs and blocks, simulates a partition, heals it,
and shows convergence in the logs.
"""
import asyncio
import time
from network import Node, tx_id, block_id

def make_tx(sender="alice", recipient="bob", amount=10, fee=1, nonce=1):
    return {"sender": sender, "recipient": recipient,
            "amount": amount, "fee": fee, "nonce": nonce}

def make_block(txs=None, prev="0"*64, nonce=0):
    import time as _t
    txs = txs or []
    root = tx_id(txs[0]) if txs else "0"*64
    return {"version": 1, "prev_hash": prev,
            "merkle_root": root, "timestamp": int(_t.time()),
            "nonce": nonce, "transactions": txs}

async def main():
    BASE = 18100
    nodes = [Node(f"N{i}", "127.0.0.1", BASE + i,
                  seeds=[("127.0.0.1", BASE + i - 1)] if i > 0 else [])
             for i in range(5)]

    print("=== Starting 5 nodes ===")
    for n in nodes: await n.start()
    await asyncio.sleep(0.5)
    print(f"Peers per node: {[len(n.peers) for n in nodes]}")

    print("\n=== Broadcasting tx1 from N0 ===")
    tx1 = make_tx(sender="alice", nonce=1)
    await nodes[0].broadcast_tx(tx1)
    await asyncio.sleep(0.5)
    print(f"Mempool sizes: {[len(n.mempool) for n in nodes]}")

    print("\n=== Partitioning: N0,N1 | N2,N3,N4 ===")
    nodes[2].partition(); nodes[3].partition(); nodes[4].partition()
    await asyncio.sleep(0.3)

    print("Mining block_A on N0's side, block_B on N2's side")
    block_a = make_block(nonce=1)
    block_b = make_block(nonce=2)
    await nodes[0].broadcast_block(block_a)
    await nodes[2].broadcast_block(block_b)
    await asyncio.sleep(0.3)

    print(f"Blocks in N0: {len(nodes[0].blocks)}, N2: {len(nodes[2].blocks)}")

    print("\n=== Healing partition ===")
    nodes[2].heal([("127.0.0.1", BASE)])
    nodes[3].heal([("127.0.0.1", BASE)])
    nodes[4].heal([("127.0.0.1", BASE + 1)])
    await asyncio.sleep(1.0)

    print("\n=== Final state ===")
    for n in nodes:
        print(f"  {n.node_id}: peers={list(n.peers)}, "
              f"blocks={len(n.blocks)}, mempool={len(n.mempool)}")

    for n in nodes: await n.stop()

asyncio.run(main())