# Assignment 6 – P2P Mempool and Block Relay Network

Five nodes over localhost TCP with inventory relay, mempool, partition simulation.

## Setup
```bash
pip install pytest pytest-asyncio
```

## Run all tests
```bash
pytest test_network.py -v
```

## Run the partition simulation manually
```bash
python simulate.py
```

## Message types
handshake, peers, inv, getdata, tx, block, ping, pong, error

## Folder layout
- `network.py` — node, mempool, wire protocol
- `test_network.py` — full test suite
- `simulate.py` — 5-node partition/heal demo with logs
- `requirements.txt` — dependencies