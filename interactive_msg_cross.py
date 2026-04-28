import sys
import os
import json
import traceback
import time
import concurrent.futures
import binascii
from utility.prepare_sol_asset import PrepareSOLAsset, get_batch_addresses
from sendtransactions.sendtransaction import sign_and_send_transaction, build_transfer_tx, hex_to_pubkey, get_contracts
from sendtransactions.msg_transaction import msg_cross_chain
from sendtransactions.evm_msg_transaction import Erc20TokenRemote
from testcases.get_testcase import GetTestCase
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address, create_associated_token_account, transfer_checked, TransferCheckedParams
from solana.rpc.api import Client

def get_network():
    while True:
        net = input("👉 Please select the Solana network (1: Mainnet-Beta, 2: Devnet): ").strip()
        if net == '1': return 'mainnet-beta'
        elif net == '2': return 'devnet'
        print("❌ Invalid selection.")

def get_case_file():
    folder_path = "testcases"
    if not os.path.exists(folder_path): os.makedirs(folder_path)
    while True:
        files = sorted([f for f in os.listdir(folder_path) if f.endswith('.csv')])
        if not files:
            print(f"📂 No CSV files found in '{folder_path}'.")
            sys.exit(1)
        print("\n--- 📝 Available Test Case Files ---")
        for idx, file_name in enumerate(files, 1): print(f"{idx}. {file_name}")
        choice = input(f"\n👉 Choice (1-{len(files)}) or 'q': ").strip().lower()
        if choice == 'q': sys.exit(0)
        if choice.isdigit() and 1 <= int(choice) <= len(files): return files[int(choice)-1]
        print("❌ Invalid selection.")

def get_wallet_info():
    if not os.path.exists("current_wallets.json"): return None, None, None
    with open("current_wallets.json", 'r') as f: data_list = json.load(f)
    if not data_list: return None, None, None
    data = data_list[0]
    return data['wallet_name'], data['main_address'], data['batch_address'], data

def check_wallet_coverage(case_file):
    cases = GetTestCase(case_file).get_test_cases()
    res = get_wallet_info()
    if not res or not res[0]: return False
    batch_addrs = res[2]
    if not batch_addrs or len(batch_addrs) < len(cases):
        print(f"❌ Error: Need {len(cases)} addresses, have {len(batch_addrs) if batch_addrs else 0}.")
        return False
    return True

def main():
    print("🚀 Solana Interactive Message Cross-Chain Runner")
    network = get_network()
    case_file = get_case_file()
    asset_preparer = PrepareSOLAsset(network)
    num_cases = len(GetTestCase(case_file).get_test_cases())
    service = Client(asset_preparer.url, timeout=20)

    while True:
        print("\n" + "="*50 + "\n📬 Message Bridge Menu\n" + "="*50)
        print("1. 🛠️ Create Wallets\n2. 🔍 Check Balance\n3. 💸 Distribute Funds\n4. 🚀 Run Solana Msg Transactions\n5. 🚀 Run EVM to Solana Msg Transactions\n6. 🧹 Clear Assets\n7. 🚪 Exit\n" + "="*50)
        choice = input("👉 Choice: ").strip()

        if choice == '1':
            asset_preparer.prepare_assets(create=True, batch_address_count=num_cases)
        elif choice == '2':
            if check_wallet_coverage(case_file):
                asset_preparer.check_all_balances(case_file, get_wallet_info()[:3])
        elif choice == '3':
            if not check_wallet_coverage(case_file): continue
            _, main_addrs, batch_addrs, wallet_data = get_wallet_info()
            main_kp_hex = list(main_addrs.values())[0]
            main_kp = Keypair.from_bytes(binascii.unhexlify(main_kp_hex))

            # Pre-check Main Wallet SOL
            main_bal_res = service.get_balance(main_kp.pubkey())
            if main_bal_res.value < 10000000: # < 0.01 SOL
                print(f"❌ Main Wallet {main_kp.pubkey()} has insufficient SOL ({main_bal_res.value/10**9}). Distribution aborted.")
                continue

            cases = GetTestCase(case_file).get_test_cases()
            print(f"💸 Distributing SOL & Tokens for {len(batch_addrs)} addresses...")

            def send_distribution_batch(recipients, ata_ixs):
                tx_data = {"instructions": build_transfer_tx(main_kp, recipients)["instructions"]}
                tx_data['instructions'].extend(ata_ixs)
                tx_data['sender_kp'] = main_kp
                sig, err = sign_and_send_transaction(tx_data, service)
                if sig: print(f"    ✅ Batch Success! Signature: {sig}")
                else: print(f"    ❌ Batch Fail: {err}")

            curr_recipients = []
            curr_ata_ixs = []
            for i, (addr_str, kp_hex) in enumerate(batch_addrs.items()):
                if i >= len(cases): break
                case = cases[i]
                addr = Pubkey.from_string(addr_str)

                # SOL: 0.015 SOL buffer
                curr_recipients.append((addr_str, int(0.015 * 10**9)))

                # Token: USDC or other
                if '0x000000000000' not in case['from_token_address']:
                    try:
                        token_mint = hex_to_pubkey(case['from_token_address'])
                        ata_addr = get_associated_token_address(addr, token_mint)
                        main_ata = get_associated_token_address(main_kp.pubkey(), token_mint)

                        res = service.get_account_info(ata_addr)
                        if res.value is None:
                            curr_ata_ixs.append(create_associated_token_account(main_kp.pubkey(), addr, token_mint))

                        curr_ata_ixs.append(
                            transfer_checked(
                                TransferCheckedParams(
                                    program_id=TOKEN_PROGRAM_ID,
                                    source=main_ata,
                                    mint=token_mint,
                                    dest=ata_addr,
                                    owner=main_kp.pubkey(),
                                    amount=case['amount_raw'],
                                    decimals=case['from_token_decimals']
                                )
                            )
                        )
                    except Exception as e: print(f"  - Skip Token for {addr_str[:8]}: {e}")

                if len(curr_recipients) >= 4:
                    send_distribution_batch(curr_recipients, curr_ata_ixs)
                    curr_recipients, curr_ata_ixs = [], []

            if curr_recipients: send_distribution_batch(curr_recipients, curr_ata_ixs)

        elif choice == '4':
            if not check_wallet_coverage(case_file): continue
            cases = GetTestCase(case_file).get_test_cases()
            _, _, batch_addrs, wallet_data = get_wallet_info()

            try:
                tps = float(input("👉 Enter TPS (e.g. 1.0): ").strip())
            except: tps = 1.0

            print(f"🚀 Running {len(cases)} message cross-chain transactions...")

            def process_case(idx, addr_str, case):
                prefix = f"[{idx+1}/{len(cases)}]"
                kp_hex = batch_addrs[addr_str]
                batch_kp = Keypair.from_bytes(binascii.unhexlify(kp_hex))
                addr_pub = Pubkey.from_string(addr_str)

                try:
                    tx, error = msg_cross_chain(
                        sender_kp=batch_kp,
                        to_chain_id=case.get('to_chain_id', 2153201998),
                        to_contract=case.get('to_token_address', '0x174BADB1B8b9248dAe0519C5C8f9fFd9aCb2E779'),
                        to_user=case['to_address'],
                        amount=case['amount_raw'],
                        token_mint_hex=case['from_token_address'],
                        network=network,
                        gas_limit=case.get('gas_limit', 80000)
                    )

                    if error: return f"{prefix} ❌ Error: {error}"

                    if '0x000000000000' not in case['from_token_address']:
                        token_mint = hex_to_pubkey(case['from_token_address'])
                        ata_addr = get_associated_token_address(addr_pub, token_mint)
                        if service.get_account_info(ata_addr).value is None:
                            tx['instructions'].insert(0, create_associated_token_account(batch_kp.pubkey(), addr_pub, token_mint))

                    sig, err = sign_and_send_transaction(tx, service)
                    return f"{prefix} {'✅ Success' if sig else '❌ Fail'}: {sig or err}"
                except Exception as e: return f"{prefix} ❌ Exception: {e}"

            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                start_time = time.time()
                futures = []
                for i, (addr_str, case) in enumerate(zip(batch_addrs.keys(), cases)):
                    expected_time = start_time + (i / tps)
                    now = time.time()
                    if expected_time > now: time.sleep(expected_time - now)
                    futures.append(executor.submit(process_case, i, addr_str, case))
                for future in concurrent.futures.as_completed(futures): print(future.result())

        elif choice == '5':
            cases = GetTestCase(case_file).get_test_cases()
            priv_key = input("👉 Enter EVM Private Key: ").strip()
            if not priv_key.startswith('0x'): priv_key = '0x' + priv_key

            print(f"🚀 Running {len(cases)} EVM to Solana transactions...")
            for idx, case in enumerate(cases):
                prefix = f"[{idx+1}/{len(cases)}]"
                try:
                    remote = Erc20TokenRemote(case['node_url'], case['from_token_address'])
                    # to_address in CSV is Solana ATA address string
                    to_bytes = case['to_address'].encode('utf-8')

                    print(f"{prefix} Sending {case['cross_amount(eth)']} {case['token_name']} to Solana {case['to_address'][:8]}...")
                    tx_hash, _ = remote.send(priv_key, to_bytes, case['amount_raw'])
                    print(f"{prefix} ✅ Success! Hash: {tx_hash}")
                except Exception as e:
                    print(f"{prefix} ❌ Error: {e}")

        elif choice == '6':
            res = get_wallet_info()
            payer_kp = None
            if res and res[1]:
                main_kp_hex = list(res[1].values())[0]
                payer_kp = Keypair.from_bytes(binascii.unhexlify(main_kp_hex))
            asset_preparer.sweep_assets(input("👉 Destination Address: ").strip(), payer_kp=payer_kp)
        elif choice == '7': sys.exit(0)

if __name__ == "__main__": main()
