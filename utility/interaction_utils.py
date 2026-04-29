import sys
import os
import json

def get_network():
    while True:
        net = input("👉 Please select the Solana network (1: Mainnet-Beta, 2: Devnet): ").strip()
        if net == '1': return 'mainnet-beta'
        elif net == '2': return 'devnet'
        print("❌ Invalid selection.")

def get_direction():
    while True:
        print("\n--- 🧭 Select Bridge Direction ---")
        print("1. From Solana to EVM")
        print("2. From EVM to Solana")
        choice = input("👉 Choice (1-2) or 'q': ").strip().lower()
        if choice == 'q': sys.exit(0)
        if choice == '1': return "sol_to_evm"
        if choice == '2': return "evm_to_sol"
        print("❌ Invalid selection.")

def get_case_file(direction):
    folder_path = os.path.join("testcases", direction)
    if not os.path.exists(folder_path):
        print(f"📂 Folder '{folder_path}' not found.")
        return None

    while True:
        files = sorted([f for f in os.listdir(folder_path) if f.endswith('.csv')])
        if not files:
            print(f"📂 No CSV files found in '{folder_path}'.")
            return None

        print(f"\n--- 📝 Available Cases in {direction} ---")
        for idx, file_name in enumerate(files, 1): print(f"{idx}. {file_name}")
        choice = input(f"\n👉 Choice (1-{len(files)}) or 'b' to go back: ").strip().lower()
        if choice == 'b': return None
        if choice.isdigit() and 1 <= int(choice) <= len(files):
            return os.path.join(direction, files[int(choice)-1])
        print("❌ Invalid selection.")

def get_solana_wallet_info():
    if not os.path.exists("current_solana_wallets.json"): return None
    try:
        with open("current_solana_wallets.json", 'r') as f: data_list = json.load(f)
        if not data_list: return None
        data = data_list[0]
        return data['wallet_name'], data['main_wallet'], data.get('batch_wallets', []), data
    except Exception as e:
        print(f"❌ Error reading current_solana_wallets.json: {e}")
        return None

def get_evm_wallet_info():
    if not os.path.exists("current_evm_wallets.json"): return None
    try:
        with open("current_evm_wallets.json", 'r') as f: data_list = json.load(f)
        if not data_list: return None
        data = data_list[0]
        return data['wallet_name'], data['main_wallet'], data.get('batch_wallets', []), data
    except Exception as e:
        print(f"❌ Error reading current_evm_wallets.json: {e}")
        return None
