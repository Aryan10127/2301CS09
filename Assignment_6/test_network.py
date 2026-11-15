"""
Assignment 6 – test suite
Run with: pytest test_network.py -v
"""
import asyncio
import pytest
import pytest_asyncio
import time
from network import (Node, Mempool, tx_id, block_id,
                     send_msg, recv_msg, MAX_MSG)
import json, struct

pytestmark = pytest.mark.asyncio

BASE_PORT = 19200

def make_tx(sender="alice", recipient="bob", amount=10, fee=1, nonce=1):
    return {"sender": sender, "recipient": recipient,
            "amount": amount, "fee": fee, "nonce": nonce}

def make_block(txs=None, prev="0"*64, nonce=0):
    txs = txs or []
    root = tx_id(txs[0]) if txs else "0"*64
    return {"version": 1, "prev_hash": prev,
            "merkle_root": root, "timestamp": int(time.time()),
            "nonce": nonce, "transactions": txs}

# ---- helpers ---------------------------------------------------------------

async def boot(n: int, base=BASE_PORT) -> list[Node]:
    """Start n nodes in a chain topology and wait for them to connect."""
    nodes = [Node(f"node{i}", "127.0.0.1", base + i,
                  seeds=[("127.0.0.1", base + i - 1)] if i > 0 else [])
             for i in range(n)]
    for node in nodes:
        await node.start()
    await asyncio.sleep(0.3)
    return nodes

async def teardown(nodes):
    for n in nodes:
        await n.stop()

# ---- Mempool unit tests ----------------------------------------------------

def test_mempool_add_dedup():
    m = Mempool()
    tx = make_tx()
    assert m.add(tx) is True
    assert m.add(tx) is False
    assert len(m) == 1

def test_mempool_fee_order():
    m = Mempool()
    m.add(make_tx(fee=1, nonce=1))
    m.add(make_tx(fee=100, nonce=2))
    ordered = m.ordered()
    fees = [t["fee"] for t in ordered]
    assert fees == sorted(fees, reverse=True)

def test_mempool_remove():
    m = Mempool()
    tx = make_tx()
    m.add(tx)
    m.remove(tx_id(tx))
    assert len(m) == 0

def test_mempool_expiry(monkeypatch):
    import network
    m = Mempool()
    tx = make_tx()
    m.add(tx)
    # fake old receipt time
    tid = tx_id(tx)
    m._entries[tid].received = time.time() - 400
    assert len(m.ordered()) == 0

# ---- tx_id / block_id stability --------------------------------------------

def test_txid_stable():
    tx = make_tx()
    assert tx_id(tx) == tx_id(tx)

def test_blockid_stable():
    b = make_block()
    assert block_id(b) == block_id(b)

def test_txid_changes_with_content():
    assert tx_id(make_tx(amount=1)) != tx_id(make_tx(amount=2))

# ---- wire protocol ---------------------------------------------------------
@pytest.mark.asyncio
async def test_send_recv_roundtrip():
    async def handler(reader, writer):
        msg = await recv_msg(reader)
        await send_msg(writer, msg)
        writer.close()

    srv = await asyncio.start_server(handler, "127.0.0.1", BASE_PORT + 50)
    r, w = await asyncio.open_connection("127.0.0.1", BASE_PORT + 50)
    payload = {"type": "ping", "data": "hello"}
    await send_msg(w, payload)
    result = await recv_msg(r)
    assert result == payload
    w.close()
    srv.close()
    await srv.wait_closed()

@pytest.mark.asyncio
async def test_oversized_message_rejected():
    async def handler(reader, writer):
        try:
            await recv_msg(reader)
        except ValueError:
            pass
        writer.close()
    srv = await asyncio.start_server(handler, "127.0.0.1", BASE_PORT + 51)
    r, w = await asyncio.open_connection("127.0.0.1", BASE_PORT + 51)
    big = b"x" * (MAX_MSG + 1)
    w.write(struct.pack(">I", len(big)) + big)
    await w.drain()
    await asyncio.sleep(0.1)
    w.close(); srv.close()

# ---- network integration tests ---------------------------------------------

@pytest.mark.asyncio
async def test_five_nodes_connect():
    nodes = await boot(5)
    await asyncio.sleep(0.5)
    # each node should have at least one peer
    for n in nodes:
        assert len(n.peers) >= 1
    await teardown(nodes)

@pytest.mark.asyncio
async def test_tx_propagates_to_all():
    nodes = await boot(5)
    await asyncio.sleep(0.5)
    tx = make_tx(sender="alice", nonce=42)
    await nodes[0].broadcast_tx(tx)
    await asyncio.sleep(0.5)
    tid = tx_id(tx)
    for n in nodes:
        assert n.mempool.has(tid), f"{n.node_id} missing tx"
    await teardown(nodes)

@pytest.mark.asyncio
async def test_block_propagates_to_all():
    nodes = await boot(5)
    await asyncio.sleep(0.5)
    block = make_block()
    await nodes[0].broadcast_block(block)
    await asyncio.sleep(0.5)
    bid = block_id(block)
    for n in nodes:
        assert bid in n.blocks, f"{n.node_id} missing block"
    await teardown(nodes)

@pytest.mark.asyncio
async def test_duplicate_tx_not_relayed_twice():
    nodes = await boot(3)
    await asyncio.sleep(0.3)
    tx = make_tx(nonce=99)
    await nodes[0].broadcast_tx(tx)
    await nodes[0].broadcast_tx(tx)   # second broadcast same tx
    await asyncio.sleep(0.3)
    tid = tx_id(tx)
    for n in nodes:
        assert n.mempool.has(tid)
    await teardown(nodes)

@pytest.mark.asyncio
async def test_block_removes_tx_from_mempool():
    nodes = await boot(3)
    await asyncio.sleep(0.3)
    tx = make_tx(nonce=77)
    await nodes[0].broadcast_tx(tx)
    await asyncio.sleep(0.2)
    block = make_block(txs=[tx])
    await nodes[0].broadcast_block(block)
    await asyncio.sleep(0.3)
    tid = tx_id(tx)
    for n in nodes:
        assert not n.mempool.has(tid), f"{n.node_id} still has tx in mempool"
    await teardown(nodes)

@pytest.mark.asyncio
async def test_partition_and_heal():
    nodes = await boot(5, base=BASE_PORT + 100)
    await asyncio.sleep(0.5)

    # partition: split into [0,1] and [2,3,4]
    nodes[2].partition()
    nodes[3].partition()
    nodes[4].partition()
    await asyncio.sleep(0.2)

    # mine on each side
    tx_a = make_tx(sender="alice", nonce=1)
    tx_b = make_tx(sender="bob",   nonce=2)
    block_a = make_block(txs=[tx_a], nonce=1)
    block_b = make_block(txs=[tx_b], nonce=2)

    await nodes[0].broadcast_block(block_a)
    await nodes[2].broadcast_block(block_b)
    await asyncio.sleep(0.2)

    # heal partition
    nodes[2].heal([("127.0.0.1", BASE_PORT + 100)])
    nodes[3].heal([("127.0.0.1", BASE_PORT + 100)])
    nodes[4].heal([("127.0.0.1", BASE_PORT + 101)])
    await asyncio.sleep(0.8)

    # all nodes should have both blocks after convergence
    bid_a = block_id(block_a)
    bid_b = block_id(block_b)
    for n in nodes:
        assert bid_a in n.blocks or bid_b in n.blocks, \
            f"{n.node_id} has neither block"

    await teardown(nodes)

@pytest.mark.asyncio
async def test_malformed_message_handled():
    nodes = await boot(2, base=BASE_PORT + 200)
    await asyncio.sleep(0.3)
    # send garbage bytes directly
    r, w = await asyncio.open_connection("127.0.0.1", BASE_PORT + 200)
    w.write(b"\xff\xff\xff\xff" + b"not json at all")
    await w.drain()
    await asyncio.sleep(0.2)
    # node should still be alive
    assert nodes[0]._server is not None
    w.close()
    await teardown(nodes)

@pytest.mark.asyncio
async def test_unknown_message_type_gets_error():
    nodes = await boot(1, base=BASE_PORT + 300)
    await asyncio.sleep(0.1)

    r, w = await asyncio.open_connection("127.0.0.1", BASE_PORT + 300)
    await send_msg(w, {"type": "handshake", "version": 1,
                       "node_id": "spy", "port": 0})
    await recv_msg(r)  # handshake reply
    await recv_msg(r)  # "peers" message the node sends right after handshake
    await asyncio.sleep(0.1)

    await send_msg(w, {"type": "foobar_unknown"})
    try:
        resp = await asyncio.wait_for(recv_msg(r), timeout=1)
        assert resp.get("type") == "error"
    except asyncio.TimeoutError:
        pass
    w.close()
    await teardown(nodes)