import sys
import os
import time
import concurrent.futures
import binascii
from solana.rpc.api import Client
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from spl.token.constants import TOKEN_PROGRAM_ID
from spl.token.instructions import get_associated_token_address, create_associated_token_account, transfer_checked, TransferCheckedParams

from utility.prepare_sol_asset import PrepareSOLAsset
from utility.interaction_utils import get_network, get_direction, get_case_file, get_wallet_info
from sendtransactions.sendtransaction import sign_and_send_transaction, build_transfer_tx, hex_to_pubkey, get_contracts
from sendtransactions.solana_msg import solana_to_evm_msg
from sendtransactions.evm_msg import Erc20TokenRemote
from testcases.get_testcase import GetTestCase

def check_wallet_coverage(case_file):
    cases = GetTestCase(case_file).get_test_cases()
    res = get_wallet_info()
    if not res: return False
    batch_wallets = res[2]
    if len(batch_wallets) < len(cases):
        print(f"❌ Error: Need {len(cases)} addresses, have {len(batch_wallets)}.")
        return False
    return True

def main_menu(direction, case_file, network):
    print(f"\n🚀 Bridge Runner | Direction: {direction} | Case: {case_file} | Net: {network}")
    asset_preparer = PrepareSOLAsset(network)
    num_cases = len(GetTestCase(case_file).get_test_cases())
    service = Client(asset_preparer.url, timeout=20)

    while True:
        print("\n" + "="*50)
        print("📬 Message Bridge Menu")
        print("="*50)
        print("1. 🛠️  Create Wallets (SOL + EVM)")
        print("2. 🔍 Check Solana Balances")
        print("3. 💸 Distribute Funds (SOL & Tokens)")
        print("4. 🚀 Run Transactions")
        print("5. 🧹 Sweep Assets (Solana)")
        print("6. 🔙 Change Direction/Case")
        print("7. 🚪 Exit")
        print("="*50)
        choice = input("👉 Choice: ").strip()

        if choice == '1':
            asset_preparer.prepare_assets(create=True, batch_address_count=num_cases)

        elif choice == '2':
            if check_wallet_coverage(case_file):
                asset_preparer.check_all_balances(case_file, get_wallet_info()[:3])

        elif choice == '3':
            if not check_wallet_coverage(case_file): continue
            _, main_wallet, batch_wallets, _ = get_wallet_info()
            main_sol = main_wallet['solana']
            main_kp = Keypair.from_bytes(binascii.unhexlify(main_sol['private_key']))

            # Pre-check Main Wallet SOL
            main_bal_res = service.get_balance(main_kp.pubkey())
            if main_bal_res.value < 10000000:
                print(f"❌ Main Wallet {main_kp.pubkey()} has insufficient SOL. Distribution aborted.")
                continue

            cases = GetTestCase(case_file).get_test_cases()
            print(f"💸 Distributing SOL & Tokens for {len(cases)} addresses...")

            def send_distribution_batch(recipients, ata_ixs):
                tx_data = {"instructions": build_transfer_tx(main_kp, recipients)["instructions"]}
                tx_data['instructions'].extend(ata_ixs)
                tx_data['sender_kp'] = main_kp
                sig, err = sign_and_send_transaction(tx_data, service)
                if sig: print(f"    ✅ Batch Success! Signature: {sig}")
                else: print(f"    ❌ Batch Fail: {err}")

            curr_recipients = []
            curr_ata_ixs = []
            for i, wallet in enumerate(batch_wallets):
                if i >= len(cases): break
                case = cases[i]
                addr_str = wallet['solana']['address']
                addr = Pubkey.from_string(addr_str)

                # SOL: 0.015 SOL buffer
                curr_recipients.append((addr_str, int(0.015 * 10**9)))

                # Token
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
            if direction == "sol_to_evm":
                run_sol_to_evm(case_file, network, service)
            else:
                run_evm_to_sol(case_file)

        elif choice == '5':
            res = get_wallet_info()
            payer_kp = None
            if res:
                main_sol = res[1]['solana']
                payer_kp = Keypair.from_bytes(binascii.unhexlify(main_sol['private_key']))
            asset_preparer.sweep_assets(input("👉 Destination Solana Address: ").strip(), payer_kp=payer_kp)

        elif choice == '6':
            return # Back to main loop to re-select

        elif choice == '7':
            sys.exit(0)

def run_sol_to_evm(case_file, network, service):
    if not check_wallet_coverage(case_file): return
    cases = GetTestCase(case_file).get_test_cases()
    _, _, batch_wallets, _ = get_wallet_info()

    try:
        tps = float(input("👉 Enter TPS (e.g. 1.0): ").strip())
    except: tps = 1.0

    print(f"🚀 Running {len(cases)} Solana -> EVM msg transactions...")

    def process_case(idx, wallet, case):
        prefix = f"[{idx+1}/{len(cases)}]"
        kp_hex = wallet['solana']['private_key']
        batch_kp = Keypair.from_bytes(binascii.unhexlify(kp_hex))
        addr_pub = Pubkey.from_string(wallet['solana']['address'])

        try:
            tx, error = solana_to_evm_msg(
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
        for i, (wallet, case) in enumerate(zip(batch_wallets, cases)):
            expected_time = start_time + (i / tps)
            now = time.time()
            if expected_time > now: time.sleep(expected_time - now)
            futures.append(executor.submit(process_case, i, wallet, case))
        for future in concurrent.futures.as_completed(futures): print(future.result())

def run_evm_to_sol(case_file):
    cases = GetTestCase(case_file).get_test_cases()
    _, _, batch_wallets, _ = get_wallet_info()

    use_batch = input("👉 Use batch wallets private keys? (y/n): ").strip().lower() == 'y'

    if not use_batch:
        priv_key = input("👉 Enter EVM Private Key: ").strip()
        if not priv_key.startswith('0x'): priv_key = '0x' + priv_key

    print(f"🚀 Running {len(cases)} EVM -> Solana transactions...")
    for idx, case in enumerate(cases):
        prefix = f"[{idx+1}/{len(cases)}]"
        try:
            if use_batch:
                if idx < len(batch_wallets):
                    priv_key = batch_wallets[idx]['evm']['private_key']
                else:
                    print(f"{prefix} ⚠️ No batch wallet for this case, skipping.")
                    continue

            remote = Erc20TokenRemote(case['node_url'], case['from_token_address'])
            to_bytes = case['to_address'].encode('utf-8')

            print(f"{prefix} Sending {case['cross_amount(eth)']} {case['token_name']} to Solana {case['to_address'][:8]}...")
            tx_hash, _ = remote.send(priv_key, to_bytes, case['amount_raw'])
            print(f"{prefix} ✅ Success! Hash: {tx_hash}")
        except Exception as e:
            print(f"{prefix} ❌ Error: {e}")

def run():
    print("👋 Welcome to Cross-Chain Message Bridge Runner")
    network = get_network()

    while True:
        direction = get_direction()
        case_file = get_case_file(direction)
        if not case_file: continue

        main_menu(direction, case_file, network)

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
