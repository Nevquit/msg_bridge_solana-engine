import json
import os
import binascii
import requests
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from mnemonic import Mnemonic
from testcases.get_testcase import GetTestCase
from sendtransactions.sendtransaction import hex_to_pubkey

class PrepareSOLAsset:
    def __init__(self, network='devnet'):
        self.network = network
        try:
            with open('config/rpc.json', 'r') as f:
                rpc_config = json.load(f)
            self.url = rpc_config.get(network, "https://api.devnet.solana.com")
        except:
            self.url = "https://api.devnet.solana.com"

    def prepare_assets(self, create=True, batch_address_count=0):
        if not create: return
        mnemo = Mnemonic("english")
        words = mnemo.generate(strength=128)
        main_keypair = Keypair()
        batch_keypairs = [Keypair() for _ in range(batch_address_count)]
        wallet_data = {
            "wallet_name": f"key_set_{os.urandom(4).hex()}",
            "mnemonic": words,
            "address_type": "Enterprise",
            "main_address": {str(main_keypair.pubkey()): binascii.hexlify(bytes(main_keypair)).decode()},
            "batch_address": {str(kp.pubkey()): binascii.hexlify(bytes(kp)).decode() for kp in batch_keypairs}
        }
        with open("current_wallets.json", "w") as f:
            json.dump([wallet_data], f, indent=4)
        if not os.path.exists("wallets"): os.makedirs("wallets")
        wallet_file = os.path.join("wallets", f"{wallet_data['wallet_name']}.json")
        with open(wallet_file, "w") as f:
            json.dump(wallet_data, f, indent=4)
        print(f"✅ Created main: {main_keypair.pubkey()}, batch count: {batch_address_count}")

    def _get_balance_http(self, addr_str):
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [addr_str]
        }
        try:
            response = requests.post(self.url, json=payload, timeout=20)
            if response.status_code == 200:
                data = response.json()
                if "result" in data:
                    return data["result"]["value"], None
                elif "error" in data:
                    return None, f"RPC Error: {data['error'].get('message')}"
            return None, f"HTTP {response.status_code}"
        except Exception as e:
            return None, f"Connection Failed: {str(e)}"

    def _get_token_balance_http(self, addr_str, mint_str):
        from spl.token.instructions import get_associated_token_address
        try:
            owner = Pubkey.from_string(addr_str)

            # Support both hex and base58 token mint addresses
            mint = hex_to_pubkey(mint_str)

            ata = get_associated_token_address(owner, mint)

            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getTokenAccountBalance",
                "params": [str(ata)]
            }
            response = requests.post(self.url, json=payload, timeout=20)
            if response.status_code == 200:
                data = response.json()
                if "result" in data:
                    return int(data["result"]["value"]["amount"]), None
                elif "error" in data:
                    # If ATA doesn't exist, balance is effectively 0
                    if "could not find account" in data['error'].get('message', '').lower():
                        return 0, None
                    return None, f"RPC Error: {data['error'].get('message')}"
            return None, f"HTTP {response.status_code}"
        except Exception as e:
            return None, f"Token Balance Failed: {str(e)}"

    def format_float(self, val):
        """Formats float to avoid scientific notation, max 9 decimals."""
        return f"{val:.9f}".rstrip('0').rstrip('.')

    def check_all_balances(self, case_file, wallet_info):
        _, main_address_dict, batch_address_dict = wallet_info
        cases = GetTestCase(case_file).get_test_cases()

        # SOL Needs
        total_network_fees = sum(c['network_fee_raw'] for c in cases)
        total_gas_reserve = 0.01 * 10**9 * len(cases)
        total_sol_needed = total_network_fees + total_gas_reserve

        # Token Needs (Aggregated for Main)
        token_needs = {}
        for c in cases:
            if '0x000000000000' not in c['from_token_address']:
                mint = c['from_token_address']
                token_needs[mint] = token_needs.get(mint, 0) + c['amount_raw']

        print("\n" + "="*80)
        print(f"🔍 Solana Balance Diagnostics (via RPC: {self.url})")
        print("="*80)

        # 1. Main Address Check
        for addr_str in main_address_dict.keys():
            balance, err = self._get_balance_http(addr_str)
            sol_status = f"❌ Error: {err}" if err else (f"✅ {self.format_float(balance/10**9)} SOL" if balance >= total_sol_needed else f"⚠️ LOW ({self.format_float(balance/10**9)} SOL, Need {self.format_float(total_sol_needed/10**9)})")

            token_summaries = []
            for mint, needed_raw in token_needs.items():
                case = next(c for c in cases if c['from_token_address'] == mint)
                t_bal, t_err = self._get_token_balance_http(addr_str, mint)
                if t_err:
                    token_summaries.append(f"{case['token_name']}: {t_err}")
                else:
                    t_needed_f = needed_raw / (10**case['from_token_decimals'])
                    t_bal_f = t_bal / (10**case['from_token_decimals'])
                    t_status = "✅" if t_bal >= needed_raw else "❌"
                    token_summaries.append(f"{t_status} {case['token_name']}: {self.format_float(t_bal_f)} (Need: {self.format_float(t_needed_f)})")

            print(f"MAIN WALLET: {addr_str}")
            print(f"  SOL Status: {sol_status}")
            for ts in token_summaries: print(f"  {ts}")

        # 2. Batch Addresses Check
        print("-" * 80)
        print(f"{'BATCH':<10} | {'ADDRESS':<15} | {'SOL':<10} | {'TOKEN STATUS'}")
        print("-" * 80)
        for i, addr_str in enumerate(batch_address_dict.keys()):
            if i >= len(cases): break
            case = cases[i]
            balance, err = self._get_balance_http(addr_str)
            needed_sol = case['network_fee_raw'] + (0.005 * 10**9)
            sol_status = "❌ ERR" if err else ("✅ OK" if balance >= needed_sol else "⚠️ LOW")

            token_status = "N/A"
            if '0x000000000000' not in case['from_token_address']:
                t_bal, t_err = self._get_token_balance_http(addr_str, case['from_token_address'])
                if t_err: token_status = f"{case['token_name']}: Error"
                else:
                    t_bal_f = t_bal / (10**case['from_token_decimals'])
                    t_needed_f = case['amount_raw'] / (10**case['from_token_decimals'])
                    t_check = "✅" if t_bal >= case['amount_raw'] else "❌"
                    token_status = f"{t_check} {case['token_name']}: {self.format_float(t_bal_f)}/{self.format_float(t_needed_f)}"

            print(f"{i+1:<10} | {addr_str[:12]}... | {sol_status:<10} | {token_status}")
        print("="*80 + "\n")

    def sweep_assets(self, destination_address, payer_kp=None):
        from sendtransactions.sendtransaction import sign_and_send_transaction, build_transfer_tx
        from spl.token.instructions import get_associated_token_address, transfer_checked, TransferCheckedParams, create_associated_token_account
        from spl.token.constants import TOKEN_PROGRAM_ID
        from solana.rpc.api import Client
        from solana.rpc.types import TokenAccountOpts

        print(f"🧹 Sweeping all assets to {destination_address}...")
        try:
            dest_pubkey = hex_to_pubkey(destination_address)
        except:
            print(f"❌ Invalid destination address: {destination_address}")
            return

        if not os.path.exists("current_wallets.json"):
            print("❌ No wallets found to sweep.")
            return

        with open("current_wallets.json", "r") as f:
            wallets = json.load(f)

        service = Client(self.url)

        # Pre-check Payer Balance if provided
        if payer_kp:
            payer_bal = service.get_balance(payer_kp.pubkey()).value
            if payer_bal < 5000000: # 0.005 SOL
                print(f"❌ Payer {payer_kp.pubkey()} has insufficient SOL ({payer_bal/10**9}). Sweep aborted.")
                return

        for wallet in wallets:
            # Combine main and batch addresses
            all_addrs = {**wallet.get("main_address", {}), **wallet.get("batch_address", {})}

            for addr_str, kp_hex in all_addrs.items():
                kp = Keypair.from_bytes(binascii.unhexlify(kp_hex))
                print(f"  - Checking wallet {addr_str[:8]}...")

                # 1. Sweep SPL Tokens
                try:
                    # Get all token accounts for this owner
                    opts = TokenAccountOpts(program_id=TOKEN_PROGRAM_ID)
                    token_accounts_res = service.get_token_accounts_by_owner(kp.pubkey(), opts)
                    if token_accounts_res.value:
                        for acc in token_accounts_res.value:
                            acc_pubkey = acc.pubkey
                            # Fetch balance
                            bal_res = service.get_token_account_balance(acc_pubkey)
                            amount = int(bal_res.value.amount)

                            if amount > 0:
                                # Need to find the mint to derive destination ATA
                                acc_info = service.get_account_info(acc_pubkey).value
                                # Anchor/SPL token accounts have mint at the beginning (bytes 0..32)
                                mint = Pubkey.from_bytes(acc_info.data[:32])
                                dest_ata = get_associated_token_address(dest_pubkey, mint)

                                # Prepare transfer instruction
                                print(f"    * Sweeping {amount} of token {str(mint)[:8]}...")
                                instructions = []

                                # Ensure destination ATA exists
                                dest_ata_info = service.get_account_info(dest_ata).value
                                if dest_ata_info is None:
                                    payer_pubkey = payer_kp.pubkey() if payer_kp else kp.pubkey()
                                    instructions.append(create_associated_token_account(payer_pubkey, dest_pubkey, mint))

                                instructions.append(
                                    transfer_checked(
                                        TransferCheckedParams(
                                            program_id=TOKEN_PROGRAM_ID,
                                            source=acc_pubkey,
                                            mint=mint,
                                            dest=dest_ata,
                                            owner=kp.pubkey(),
                                            amount=amount,
                                            decimals=bal_res.value.decimals
                                        )
                                    )
                                )
                                tx_payload = {"instructions": instructions}
                                if payer_kp:
                                    tx_payload["signers"] = [payer_kp, kp]
                                    tx_payload["fee_payer_kp"] = payer_kp
                                else:
                                    tx_payload["sender_kp"] = kp

                                sig, err = sign_and_send_transaction(tx_payload, service)
                                if sig: print(f"    ✅ Token sweep success! Signature: {sig}")
                                else: print(f"    ❌ Token sweep fail: {err}")
                except Exception as e:
                    print(f"    ⚠️ Token sweep failed for {addr_str[:8]}: {e}")

                # 2. Sweep SOL
                try:
                    # Fetch fresh balance after token transfers
                    bal_res = service.get_balance(kp.pubkey())
                    balance = bal_res.value

                    # Buffer to prevent "insufficient lamports" error
                    buffer = 5000
                    # If payer_kp is provided, it pays the transaction fee
                    # Otherwise, kp pays its own fee (usually 5000 lamports)
                    fee_estimate = 0 if payer_kp else 5000

                    if balance > (fee_estimate + buffer):
                        sweep_amount = balance - fee_estimate - buffer
                        print(f"    * Sweeping {sweep_amount/10**9} SOL...")
                        tx_data = build_transfer_tx(kp, [(str(dest_pubkey), sweep_amount)])
                        if payer_kp:
                            tx_data["signers"] = [payer_kp, kp]
                            tx_data["fee_payer_kp"] = payer_kp

                        sig, err = sign_and_send_transaction(tx_data, service)
                        if sig: print(f"    ✅ SOL sweep success! Signature: {sig}")
                        else: print(f"    ❌ SOL sweep fail: {err}")
                except Exception as e:
                    print(f"    ⚠️ SOL sweep failed for {addr_str[:8]}: {e}")

def get_batch_addresses():
    if not os.path.exists("current_wallets.json"): return {}
    with open("current_wallets.json", "r") as f: data = json.load(f)
    return data[0].get("batch_address", {})
