# P2P Mempool implementation
"""
Assignment 6 – P2P Mempool and Block Relay Network
Five nodes over localhost TCP with inventory relay, mempool, and partition simulation.
"""

import asyncio
import hashlib
import json
import logging
import os
import random
import struct
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FORMAT = json.dumps({
    "ts": "%(asctime)s", "node": "%(node_id)s",
    "peer": "%(peer_id)s", "event": "%(event)s",
    "obj": "%(obj_id)s", "msg": "%(message)s"
})

class NodeAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        self.extra.setdefault("peer_id", "-")
        self.extra.setdefault("event", "-")
        self.extra.setdefault("obj_id", "-")
        return msg, kwargs

def make_logger(node_id: str):
    logger = logging.getLogger(node_id)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            f"%(asctime)s node={node_id} peer=%(peer_id)s "
            f"event=%(event)s obj=%(obj_id)s %(message)s"
        ))
        logger.addHandler(h)
    logger.setLevel(logging.DEBUG)
    return NodeAdapter(logger, {"node_id": node_id, "peer_id": "-",
                                 "event": "-", "obj_id": "-"})

# ---------------------------------------------------------------------------
# Wire protocol  –  4-byte length prefix + JSON body, max 1 MB
# ---------------------------------------------------------------------------
MAX_MSG = 1_048_576

async def send_msg(writer: asyncio.StreamWriter, msg: dict):
    body = json.dumps(msg).encode()
    if len(body) > MAX_MSG:
        raise ValueError("message too large")
    writer.write(struct.pack(">I", len(body)) + body)
    await writer.drain()

async def recv_msg(reader: asyncio.StreamReader) -> Optional[dict]:
    hdr = await reader.readexactly(4)
    size = struct.unpack(">I", hdr)[0]
    if size > MAX_MSG:
        raise ValueError(f"oversized message: {size}")
    body = await reader.readexactly(size)
    return json.loads(body)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def tx_id(tx: dict) -> str:
    canonical = json.dumps(tx, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode())

def block_id(block: dict) -> str:
    header = {k: block[k] for k in
              ("version", "prev_hash", "merkle_root", "timestamp", "nonce")}
    canonical = json.dumps(header, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode())

@dataclass
class MempoolEntry:
    tx: dict
    fee_rate: float
    received: float = field(default_factory=time.time)
    expiry: float = 300.0  # seconds

    def expired(self) -> bool:
        return time.time() - self.received > self.expiry

# ---------------------------------------------------------------------------
# Mempool
# ---------------------------------------------------------------------------
class Mempool:
    def __init__(self):
        self._entries: dict[str, MempoolEntry] = {}

    def add(self, tx: dict) -> bool:
        """Returns True if newly added, False if duplicate or conflict."""
        tid = tx_id(tx)
        if tid in self._entries:
            return False
        fee = tx.get("fee", 0)
        size = len(json.dumps(tx))
        fee_rate = fee / max(size, 1)
        self._entries[tid] = MempoolEntry(tx=tx, fee_rate=fee_rate)
        return True

    def remove(self, tid: str):
        self._entries.pop(tid, None)

    def has(self, tid: str) -> bool:
        return tid in self._entries

    def get(self, tid: str) -> Optional[dict]:
        e = self._entries.get(tid)
        return e.tx if e else None

    def ordered(self) -> list[dict]:
        """Return txs sorted by fee rate descending, pruning expired."""
        self._prune()
        return [e.tx for e in sorted(
            self._entries.values(), key=lambda e: -e.fee_rate)]

    def ids(self) -> list[str]:
        self._prune()
        return list(self._entries)

    def _prune(self):
        expired = [tid for tid, e in self._entries.items() if e.expired()]
        for tid in expired:
            del self._entries[tid]

    def __len__(self):
        return len(self._entries)

# ---------------------------------------------------------------------------
# Peer connection
# ---------------------------------------------------------------------------
RATE_LIMIT = 100  # max messages per second per peer

class PeerConn:
    def __init__(self, peer_id: str, reader, writer, node):
        self.peer_id = peer_id
        self.reader = reader
        self.writer = writer
        self.node = node
        self._msg_times: list[float] = []

    def _rate_ok(self) -> bool:
        now = time.time()
        self._msg_times = [t for t in self._msg_times if now - t < 1.0]
        if len(self._msg_times) >= RATE_LIMIT:
            return False
        self._msg_times.append(now)
        return True

    async def send(self, msg: dict):
        try:
            await send_msg(self.writer, msg)
        except Exception:
            await self.node._drop_peer(self.peer_id)

    async def run(self):
        log = self.node.log
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(recv_msg(self.reader), timeout=30)
                except asyncio.TimeoutError:
                    await self.send({"type": "ping"})
                    continue
                if msg is None:
                    break
                if not self._rate_ok():
                    await self.send({"type": "error", "reason": "rate_limit"})
                    continue
                await self.node._handle(self.peer_id, msg)
        except (asyncio.IncompleteReadError, ConnectionResetError,
                json.JSONDecodeError, ValueError) as e:
            log.info(str(e), extra={"peer_id": self.peer_id,
                                     "event": "peer_error", "obj_id": "-"})
        finally:
            await self.node._drop_peer(self.peer_id)

# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------
class Node:
    VERSION = 1

    def __init__(self, node_id: str, host: str, port: int,
                 seeds: list[tuple[str, int]] | None = None):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.seeds = seeds or []
        self.mempool = Mempool()
        self.blocks: dict[str, dict] = {}          # block_id -> block
        self.chain: list[str] = []                 # ordered block ids
        self.peers: dict[str, PeerConn] = {}       # peer_id -> PeerConn
        self.known_inv: dict[str, set] = {}        # peer_id -> set of inv ids
        self.log = make_logger(node_id)
        self._server: asyncio.AbstractServer | None = None
        self._partitioned = False

    # ---- lifecycle --------------------------------------------------------

    async def start(self):
        self._server = await asyncio.start_server(
            self._on_connect, self.host, self.port)
        self.log.info(f"listening on {self.port}",
                      extra={"event": "start", "peer_id": "-", "obj_id": "-"})
        for host, port in self.seeds:
            asyncio.create_task(self._connect_to(host, port))

    async def stop(self):
        for peer_id in list(self.peers):
            await self._drop_peer(peer_id)
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=2)
            except asyncio.TimeoutError:
                pass
    # ---- connection handling ----------------------------------------------

    async def _on_connect(self, reader, writer):
        """Inbound connection."""
        await self._do_handshake(reader, writer, outbound=False)

    async def _connect_to(self, host: str, port: int):
        """Outbound connection."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=5)
            await self._do_handshake(reader, writer, outbound=True)
        except Exception as e:
            self.log.info(str(e), extra={"event": "connect_fail",
                                          "peer_id": f"{host}:{port}", "obj_id": "-"})

    async def _do_handshake(self, reader, writer, outbound: bool):
        try:
            if outbound:
                await send_msg(writer, {
                    "type": "handshake", "version": self.VERSION,
                    "node_id": self.node_id, "port": self.port})
                resp = await asyncio.wait_for(recv_msg(reader), timeout=5)
            else:
                resp = await asyncio.wait_for(recv_msg(reader), timeout=5)
                await send_msg(writer, {
                    "type": "handshake", "version": self.VERSION,
                    "node_id": self.node_id, "port": self.port})

            if resp.get("type") != "handshake":
                writer.close(); return
            if resp.get("version", 0) != self.VERSION:
                await send_msg(writer, {"type": "error",
                                         "reason": "version_mismatch"})
                writer.close(); return

            peer_id = resp["node_id"]
            if peer_id == self.node_id or peer_id in self.peers:
                writer.close(); return
            if self._partitioned:
                writer.close(); return

            conn = PeerConn(peer_id, reader, writer, self)
            self.peers[peer_id] = conn
            self.known_inv[peer_id] = set()
            self.log.info("connected", extra={"event": "peer_connected",
                                               "peer_id": peer_id, "obj_id": "-"})
            # advertise what we know
            await self._send_inv(conn)
            # share peer list
            await conn.send({"type": "peers",
                             "peers": [[self.host, self.port]]})
            asyncio.create_task(conn.run())
        except Exception as e:
            self.log.info(str(e), extra={"event": "handshake_fail",
                                          "peer_id": "?", "obj_id": "-"})
            writer.close()

    async def _drop_peer(self, peer_id: str):
        conn = self.peers.pop(peer_id, None)
        self.known_inv.pop(peer_id, None)
        if conn:
            try: conn.writer.close()
            except Exception: pass
            self.log.info("dropped", extra={"event": "peer_dropped",
                                             "peer_id": peer_id, "obj_id": "-"})

    # ---- message dispatch -------------------------------------------------

    async def _handle(self, peer_id: str, msg: dict):
        t = msg.get("type")
        log_extra = {"peer_id": peer_id, "event": t or "unknown", "obj_id": "-"}

        if t == "ping":
            await self.peers[peer_id].send({"type": "pong"})

        elif t == "pong":
            pass

        elif t == "peers":
            for host, port in msg.get("peers", []):
                if (host, port) != (self.host, self.port):
                    asyncio.create_task(self._connect_to(host, port))

        elif t == "inv":
            missing = []
            for item in msg.get("items", []):
                inv_id = item["id"]
                kind = item["kind"]
                self.known_inv.setdefault(peer_id, set()).add(inv_id)
                if kind == "tx" and not self.mempool.has(inv_id):
                    missing.append(item)
                elif kind == "block" and inv_id not in self.blocks:
                    missing.append(item)
            if missing:
                await self.peers[peer_id].send(
                    {"type": "getdata", "items": missing})

        elif t == "getdata":
            for item in msg.get("items", []):
                inv_id = item["id"]
                kind = item["kind"]
                if kind == "tx":
                    tx = self.mempool.get(inv_id)
                    if tx:
                        await self.peers[peer_id].send(
                            {"type": "tx", "tx": tx})
                elif kind == "block":
                    block = self.blocks.get(inv_id)
                    if block:
                        await self.peers[peer_id].send(
                            {"type": "block", "block": block})

        elif t == "tx":
            tx = msg.get("tx", {})
            tid = tx_id(tx)
            log_extra["obj_id"] = tid
            if self.mempool.add(tx):
                self.log.info("accepted", extra={**log_extra, "event": "tx_accepted"})
                await self._announce_inv("tx", tid, exclude=peer_id)
            else:
                self.log.info("dup", extra={**log_extra, "event": "tx_dup"})

        elif t == "block":
            block = msg.get("block", {})
            bid = block_id(block)
            log_extra["obj_id"] = bid
            if bid not in self.blocks:
                self.blocks[bid] = block
                self.chain.append(bid)
                # remove mined txs from mempool
                for tx in block.get("transactions", []):
                    self.mempool.remove(tx_id(tx))
                self.log.info("accepted", extra={**log_extra, "event": "block_accepted"})
                await self._announce_inv("block", bid, exclude=peer_id)
            else:
                self.log.info("dup", extra={**log_extra, "event": "block_dup"})

        elif t == "error":
            self.log.info(msg.get("reason"), extra={**log_extra, "event": "peer_error"})

        else:
            await self.peers[peer_id].send(
                {"type": "error", "reason": "unknown_message_type"})

    # ---- inventory helpers ------------------------------------------------

    async def _send_inv(self, conn: PeerConn):
        items = ([{"kind": "tx", "id": tid} for tid in self.mempool.ids()] +
                 [{"kind": "block", "id": bid} for bid in self.blocks])
        if items:
            await conn.send({"type": "inv", "items": items})

    async def _announce_inv(self, kind: str, obj_id: str, exclude: str = ""):
        for peer_id, conn in list(self.peers.items()):
            if peer_id == exclude:
                continue
            if obj_id not in self.known_inv.get(peer_id, set()):
                await conn.send({"type": "inv",
                                 "items": [{"kind": kind, "id": obj_id}]})

    # ---- public API -------------------------------------------------------

    async def broadcast_tx(self, tx: dict):
        tid = tx_id(tx)
        self.mempool.add(tx)
        await self._announce_inv("tx", tid)
        self.log.info("broadcast", extra={"event": "tx_broadcast",
                                           "peer_id": "-", "obj_id": tid})

    async def broadcast_block(self, block: dict):
        bid = block_id(block)
        self.blocks[bid] = block
        self.chain.append(bid)
        for tx in block.get("transactions", []):
            self.mempool.remove(tx_id(tx))
        await self._announce_inv("block", bid)
        self.log.info("broadcast", extra={"event": "block_broadcast",
                                           "peer_id": "-", "obj_id": bid})

    def partition(self):
        """Drop all peers and refuse new connections (simulates network split)."""
        self._partitioned = True
        for peer_id in list(self.peers):
            asyncio.create_task(self._drop_peer(peer_id))
        self.log.info("partitioned", extra={"event": "partition",
                                             "peer_id": "-", "obj_id": "-"})

    def heal(self, seeds: list[tuple[str, int]]):
        """Reconnect after partition."""
        self._partitioned = False
        for host, port in seeds:
            asyncio.create_task(self._connect_to(host, port))
        self.log.info("healed", extra={"event": "heal",
                                        "peer_id": "-", "obj_id": "-"})