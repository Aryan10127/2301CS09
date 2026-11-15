# Assignment 7 — Solidity Escrow

**Student:** Aryan Phad  
**Roll number:** 2301CS09  
**Course:** Blockchain, IIT Patna (July–December 2026)

## Overview

This project implements an educational three-party ETH escrow contract using **Solidity 0.8.24** and **Foundry**. The three distinct roles are:

- **Buyer:** funds the escrow and can release funds to the seller.
- **Seller:** receives the payment after release, or can raise a dispute.
- **Arbiter:** resolves a dispute by awarding funds to either the buyer or seller.

Payments are **pull-based**: `release()` or `resolve()` credits the beneficiary's `pending` balance, and that beneficiary calls `withdraw()` to receive ETH. The contract uses custom errors, events, checks-effects-interactions, and a reentrancy guard.

> **Local demonstration only.** `script/Interact.s.sol` uses Anvil's public, deterministic test mnemonic. Never use these accounts or this mnemonic with real funds or a public network.

## Contract state machine

```text
                    +----------+
                    | Created  |
                    +----------+
                     |        |
           fund()    |        | approveCancel() by both
                     v        v
                 +--------+  +-----------+
                 | Funded |  | Cancelled |
                 +--------+  +-----------+
                  |      |
         release()|      |raiseDispute()
                  v      v
             +--------+  +----------+
             |Released|  | Disputed |
             +--------+  +----------+
                           |        |
                   resolve(true)  resolve(false)
                           v        v
                    +----------------+  +-----------------+
                    |ResolvedToBuyer |  |ResolvedToSeller |
                    +----------------+  +-----------------+
```

`Released`, `ResolvedToBuyer`, `ResolvedToSeller`, and `Cancelled` are terminal **state-machine** states. A credited beneficiary can still call `withdraw()` after the state becomes terminal.

## Files

| Path | Purpose |
|---|---|
| `src/Escrow.sol` | Escrow implementation and access/state checks |
| `test/Escrow.t.sol` | Foundry unit, rejection, reentrancy, and fuzz tests |
| `script/Interact.s.sol` | Local deployment, funding, release, and withdrawal demonstration |
| `foundry.toml` | Solidity 0.8.24, project paths, and 1,000 fuzz runs |
| `gas-report.txt` | Saved Foundry test/gas output |
| `receipts/run-latest.json` | Example local Anvil transaction/broadcast record |
| `SPEC.md` | Intended specification document (check/update its contents before submitting) |
| `THREAT_MODEL.md` | Intended threat-model document (check/update its contents before submitting) |
| `lib/forge-std` | Foundry standard library, installed as a Git dependency/submodule |

## Requirements

- [Foundry](https://book.getfoundry.sh/getting-started/installation) (`forge` and `anvil`) on your `PATH`.
- Git for retrieving `forge-std` if the dependency is not already present.
- A terminal (PowerShell, Bash, or similar).

This is a **Foundry/Solidity** project. Python and `pip install -r requirements.txt` are not needed to compile or test the Solidity contract.

## Setup and tests

Run these commands from **inside `assign07/`**:

```powershell
forge --version
forge build
forge test
```

The single full-suite command is:

```powershell
forge test
```

For detailed test names and logs:

```powershell
forge test -vv
```

For a fresh gas report:

```powershell
forge test --gas-report
```

The supplied `gas-report.txt` records **34 passing tests** (including fuzz tests with 1,000 runs as configured). Run `forge test` on your machine to verify your checkout rather than relying only on that saved output.

If `forge-std` is missing after cloning the repository, try from the repository root:

```powershell
git submodule update --init --recursive
```

If your Git submodule configuration has broken paths after renaming the directory from `Assignment_7` to `assign07`, repair the submodule configuration before attempting to build.

## Local deployment and interaction

Open **two terminals**.

**Terminal 1 — start the local chain:**

```powershell
anvil
```

Leave this terminal running. By default Anvil listens at `http://127.0.0.1:8545` and exposes its well-known, funded development accounts.

**Terminal 2 — from `assign07/` deploy and run the scripted flow:**

```powershell
forge script script/Interact.s.sol:Interact --rpc-url http://127.0.0.1:8545 --broadcast -vv
```

`Interact.s.sol` performs the following real local-chain transactions:

1. Deploys `Escrow` with three separate buyer, seller, and arbiter addresses derived from Anvil's test mnemonic.
2. Funds the escrow with **1 ether** from the buyer.
3. Releases the payment from the buyer to the seller's pending balance.
4. Withdraws the payment from the seller account.
5. Prints the deployed address, final state, escrow balance, and liabilities.

Expected terminal state after this scenario is `Released` (enum value `2`). After successful withdrawal, escrow balance and recorded liabilities are both zero. Contract addresses and transaction hashes depend on the local chain state; don't assume a saved receipt refers to the current Anvil session.

**Do not run this script against a public RPC endpoint.** It embeds the standard, publicly known Anvil demonstration mnemonic.

## Safety properties and tests

The tests exercise:

- Rejection of zero addresses and overlapping buyer/seller/arbiter roles.
- Buyer-only funding, nonzero deposit, and prevention of repeated funding.
- Buyer-only release, buyer/seller dispute rights, and arbiter-only resolution.
- Two-party cancellation before funding and rejected transitions after terminal states.
- Independent beneficiary withdrawals, prevention of double withdrawal, and reentrancy protection.
- Fuzzing of deposited amounts, beneficiary selection, and unauthorized caller addresses.
- The accounting invariant `address(escrow).balance == escrow.liabilities()` across tested ordinary flows.

The contract does **not** implement a post-funding, mutually approved cancellation; after funding, the intended routes are release or dispute and arbiter resolution.

## Suggested short demo recording

1. Show `src/Escrow.sol` and the state machine above.
2. Run `forge test` and show the test summary.
3. Start `anvil` in one terminal and run the `forge script ... --broadcast -vv` command in another.
4. Point out `Final state`, `Escrow balance`, and `Liabilities` in the actual output.
5. Briefly show the saved receipts and gas report.

All commands should be run against the real code on your own machine. Anvil provides **local test ETH only**.
