# Cross-Chain Message Bridge Runner

This repository contains an interactive tool for running cross-chain message transactions between Solana and EVM networks.

## Features

- **Directional Testing**: Choose between Solana -> EVM and EVM -> Solana directions.
- **Modular Design**: Separate modules for Solana and EVM transaction logic.
- **Wallet Management**: Unified wallet generation (Solana + EVM) derived from a single mnemonic.
- **Case Management**: Test cases are organized by direction in subfolders.
- **Interactive Menu**: Easy-to-use menu for creating wallets, checking balances, distributing funds, and running transactions.

## Project Structure

- `interactive_runner.py`: The main entry point for the interactive tool.
- `sendtransactions/`:
  - `solana_msg.py`: Logic for Solana -> EVM message transactions.
  - `evm_msg.py`: Logic for EVM -> Solana message transactions.
  - `sendtransaction.py`: Core Solana transaction utilities.
- `utility/`:
  - `prepare_sol_asset.py`: Wallet generation and asset management (SOL/Tokens).
  - `interaction_utils.py`: Common CLI interaction helpers.
- `testcases/`:
  - `sol_to_evm/`: CSV files containing test cases for Solana to EVM.
  - `evm_to_sol/`: CSV files containing test cases for EVM to Solana.
- `config/`: Configuration files for RPCs, contract addresses, and ABIs.

## Getting Started

### Prerequisites

- Python 3.7+
- Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

### Configuration

- Ensure `config/rpc.json` contains valid RPC URLs for your target networks.
- Ensure `config/contract_accounts.json` has the correct program and contract addresses.

### Usage

1. Run the interactive runner:
   ```bash
   python interactive_runner.py
   ```
2. Select the Solana network (Mainnet-Beta or Devnet).
3. Select the bridge direction (Solana -> EVM or EVM -> Solana).
4. Select a test case file from the listed options.
5. Use the menu to:
   - **Create Wallets**: Generates a main wallet and batch wallets for testing. Credentials are saved in `current_wallets.json`.
   - **Check Balances**: Verifies SOL and token balances for all generated wallets.
   - **Distribute Funds**: Sends SOL and tokens from the main wallet to batch wallets.
   - **Run Transactions**: Executes the cross-chain message transactions.
   - **Sweep Assets**: Reclaims remaining SOL and tokens to a specified address.

## Test Case Format

Test cases are CSV files with specific columns depending on the direction. Refer to the existing files in `testcases/sol_to_evm/` and `testcases/evm_to_sol/` for examples.
