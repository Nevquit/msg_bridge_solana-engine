import sys
import os
import json
import traceback
import time
import concurrent.futures
from utility.prepare_sol_asset import PrepareSOLAsset, get_batch_addresses
from sendtransactions.sendtransaction import sign_and_send_transaction, user_lock, user_burn, build_transfer_tx, hex_to_pubkey, get_contracts
from testcases.get_testcase import GetTestCase
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address, create_associated_token_account, transfer_checked, TransferCheckedParams
import binascii
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
    # Also return the full data to access private keys
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
    print("👋 Interactive Solana Bridge Runner")
    network = get_network()
    case_file = get_case_file()
    asset_preparer = PrepareSOLAsset(network)
    num_cases = len(GetTestCase(case_file).get_test_cases())

    # Use the same RPC as asset_preparer
    service = Client(asset_preparer.url, timeout=20)

    while True:
        print("\n" + "="*50 + "\n🚀 Solana Engine Menu\n" + "="*50)
        print("1. 🛠️ Create Wallets\n2. 🔍 Check Balance & Fees\n3. 💸 Distribute Funds\n4. 🚀 Run Transactions\n5. 🧹 Clear Assets\n6. 🚪 Exit\n" + "="*50)
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

            cases = GetTestCase(case_file).get_test_cases()
            print(f"💸 Distributing SOL & Tokens for {len(batch_addrs)} addresses...")
            print("⏳ Note: This may take a few seconds to confirm on-chain.")

            # Prepare batch recipients (each needs network_fee + gas buffer)
            recipients = []
            ata_instructions = []
            conf = get_contracts(network)

            for i, (addr_str, kp_hex) in enumerate(batch_addrs.items()):
                if i >= len(cases): break
                case = cases[i]
                addr = Pubkey.from_string(addr_str)

                # SOL Distribution
                amount = case['network_fee_raw'] + int(0.01 * 10**9) # fee + buffer
                recipients.append((addr_str, amount))

                # Token Distribution
                if '0x000000000000' not in case['from_token_address']:
                    try:
                        token_mint = hex_to_pubkey(case['from_token_address'])
                        ata_addr = get_associated_token_address(addr, token_mint)
                        main_ata = get_associated_token_address(main_kp.pubkey(), token_mint)

                        # Check if transfer is actually needed
                        t_bal_res = service.get_token_account_balance(ata_addr)
                        current_t_bal = int(t_bal_res.value.amount) if t_bal_res.value else 0

                        if current_t_bal < case['amount_raw']:
                            # 1. Ensure ATA exists
                            res = service.get_account_info(ata_addr)
                            if res.value is None:
                                print(f"  - Adding ATA creation for {case['token_name']} on {addr_str[:8]}...")
                                ata_instructions.append(
                                    create_associated_token_account(
                                        payer=main_kp.pubkey(),
                                        owner=addr,
                                        mint=token_mint
                                    )
                                )

                            # 2. Add Token Transfer instruction
                            print(f"  - Adding {case['token_name']} transfer ({case['amount_raw']}) to {addr_str[:8]}...")
                            ata_instructions.append(
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
                    except Exception as e:
                        if "could not find account" in str(e).lower():
                             # Still need to create ATA and transfer if not found
                             print(f"  - Adding ATA creation for {case['token_name']} on {addr_str[:8]}...")
                             ata_instructions.append(
                                 create_associated_token_account(
                                     payer=main_kp.pubkey(),
                                     owner=addr,
                                     mint=token_mint
                                 )
                             )
                             ata_instructions.append(
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
                        else:
                             print(f"  - Skip Token for {addr_str[:8]}: {e}")

            tx_data = build_transfer_tx(main_kp, recipients)
            tx_data['instructions'].extend(ata_instructions)

            if not tx_data['instructions']:
                print("✅ Nothing to distribute.")
                continue

            sig, err = sign_and_send_transaction(tx_data, service)
            if sig: print(f"✅ Distribution success! Signature: {sig}")
            else: print(f"❌ Distribution fail: {err}")

        elif choice == '4':
            if not check_wallet_coverage(case_file): continue
            cases = GetTestCase(case_file).get_test_cases()
            _, _, batch_addrs, wallet_data = get_wallet_info()

            try:
                tps = float(input("👉 Enter Transactions Per Second (TPS, e.g. 1.0): ").strip())
                if tps <= 0: tps = 1.0
            except:
                tps = 1.0

            print(f"🚀 Running {len(cases)} transactions at {tps} TPS...")

            def process_case(idx, addr_str, case):
                prefix = f"[{idx+1}/{len(cases)}]"
                kp_hex = batch_addrs[addr_str]
                batch_kp = Keypair.from_bytes(binascii.unhexlify(kp_hex))
                addr_pub = Pubkey.from_string(addr_str)

                try:
                    # 1. Prepare bridge instruction
                    tx, error = None, None
                    if case['bridge_type'] == 'USER_TOKEN_LOCK':
                        tx, error = user_lock(
                            sender_kp=batch_kp,
                            amount=case['amount_raw'],
                            token_pair_id=case['token_pair_id'],
                            smg_id_hex=case['smg'],
                            user_account_hex=case['to_address'],
                            token_mint_hex=case['from_token_address'],
                            network=network,
                            dest_chain_id=case.get('to_chain_id', 2153201998)
                        )
                    elif case['bridge_type'] == 'USER_TOKEN_BURN':
                        tx, error = user_burn(
                            sender_kp=batch_kp,
                            amount=case['amount_raw'],
                            token_pair_id=case['token_pair_id'],
                            smg_id_hex=case['smg'],
                            user_account_hex=case['to_address'],
                            token_mint_hex=case['from_token_address'],
                            network=network,
                            fee=case['network_fee_raw'],
                            dest_chain_id=case.get('to_chain_id', 2153201998)
                        )
                    else:
                        return f"{prefix} ⚠️ Unknown type: {case['bridge_type']}"

                    if error:
                        return f"{prefix} ❌ Error preparing tx: {error}"

                    # 2. Bundle ATA creation if needed
                    if '0x000000000000' not in case['from_token_address']:
                        token_mint = hex_to_pubkey(case['from_token_address'])
                        ata_addr = get_associated_token_address(addr_pub, token_mint)

                        try:
                            # Use a local service instance for thread safety if needed,
                            # but Client is generally thread-safe for simple requests
                            res = service.get_account_info(ata_addr)
                            ata_missing = (res.value is None)
                        except:
                            ata_missing = True

                        if ata_missing:
                            ata_ix = create_associated_token_account(
                                payer=batch_kp.pubkey(),
                                owner=addr_pub,
                                mint=token_mint
                            )
                            tx['instructions'].insert(0, ata_ix)

                    # 3. Send transaction
                    sig, err = sign_and_send_transaction(tx, service)
                    if sig:
                        return f"{prefix} ✅ Success! {sig[:12]}..."
                    else:
                        return f"{prefix} ❌ Failed: {err}"
                except Exception as e:
                    return f"{prefix} ❌ Exception: {e}"

            # Execution with Rate Limiting
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = []
                start_time = time.time()
                for i, (addr_str, case) in enumerate(zip(batch_addrs.keys(), cases)):
                    # Rate limiting: wait until it's time for the next tx
                    expected_time = start_time + (i / tps)
                    now = time.time()
                    if expected_time > now:
                        time.sleep(expected_time - now)

                    futures.append(executor.submit(process_case, i, addr_str, case))

                for future in concurrent.futures.as_completed(futures):
                    print(future.result())

        elif choice == '5': asset_preparer.sweep_assets(input("👉 Destination: ").strip())
        elif choice == '6': sys.exit(0)

if __name__ == "__main__": main()
