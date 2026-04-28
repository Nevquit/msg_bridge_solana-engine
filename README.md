# Solana Engine

A tool for generating Solana accounts and sending transactions with custom data (Memo), inspired by the `bridge_bitcoin-engine` project structure.

## Features

- **Account Generation**: Create multiple Solana accounts.
- **Transactions**: Send SOL with custom data attachments using the Memo program.
- **Interactive CLI**: Easy-to-use menu for all operations.

## Installation

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

Run the interactive runner:
```bash
python3 interactive_runner_v1.0.py
```

### 1. Create Accounts
Generates a main account and multiple batch accounts based on the test case file. Keys are saved to `current_wallets.json` (which is ignored by git).

### 2. Check Balance
Fetches current SOL balances for all managed accounts.

### 3. Run Transactions
Executes transfers from batch accounts to target addresses with custom memo data.

### 4. Message Cross-Chain
Executes cross-chain message transfers using the WMB protocol.
Run the message bridge runner:
```bash
python3 interactive_msg_cross.py
```

## Project Structure

- `utility/prepare_sol_asset.py`: Logic for account creation and balance checking.
- `sendtransactions/sendtransaction.py`: Logic for Solana transaction building and broadcasting.
- `interactive_runner_v1.0.py`: Main entry point.
- `test/`: Unit tests.
- `testcases/`: CSV files containing test cases.
