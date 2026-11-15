# Blockchain Assignments 1–5 — Submission Pack

**Student:** Aryan Phad | **Roll number:** 2301CS09 | **Implementation:** Python 3.11+

The five `Assignment_x` directories in this archive correspond directly to the five existing folders in the `2301CS09` private Git repository. **Merge/copy only these directories into your repository root; leave your existing `Assignment_6` and `Assignment_7` untouched.**

## Setup and verification

From the repository root:

```bash
cd Assignment_1 && python -m pip install -r requirements.txt && python -m pytest -q && cd ..
cd Assignment_2 && python -m pip install -r requirements.txt && python -m pytest -q && cd ..
cd Assignment_3 && python -m pip install -r requirements.txt && python -m pytest -q && cd ..
cd Assignment_4 && python -m pip install -r requirements.txt && python -m pytest -q && cd ..
cd Assignment_5 && python -m pip install -r requirements.txt && python -m pytest -q && cd ..
```

See each folder's `README.md` for execution commands, design decisions, test cases, required diagrams/reports, and a short recording walkthrough. All five folders are **independently runnable**: some shared educational modules are intentionally copied into later assignments so each checkout works without relative imports from other assignments. No server or real cryptocurrency network is needed.

## Suggested recording order

1. Assignment 1: demonstrate byte-versus-text distinction, avalanche, streamed file hashing (README commands).
2. Assignment 2: root, JSON inclusion proof, verification, five-leaf diagram, benchmark.
3. Assignment 3: Ed25519 test wallet, address derivation, sign, verify, replay rejection; show no private keys on camera.
4. Assignment 4: ready-made deterministic Alice/Bob trace, change output, rejected second spend, tests.
5. Assignment 5: competing miner branches, winning shorter higher-work fork, reorg UTXOs, mining benchmark, tests.

## Git submission checklist

- Keep the repo named exactly `2301CS09` and private.
- Invite collaborator `blockchain.iitp.20261@atomicmail.io` as instructed in the PDF.
- Confirm the seven folder names are exactly `Assignment_1`, ... `Assignment_7`.
- Do not commit keys, local replay data, `.pytest_cache`, `__pycache__`, or venvs.
- Record an **unlisted** YouTube video **with audio** for each assignment, then submit each video URL separately in the professor's form: https://forms.cloud.microsoft/r/huBck9hkD7
- Ensure each assignment runs from its folder, and make your own final confirmation that all requirements are met.

This is educational software with local toy-chain assumptions. It does not implement mainnet security, P2P consensus, chain persistence, or production wallet protections.
