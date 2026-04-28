import unittest
from unittest.mock import MagicMock, patch
from sendtransactions.sendtransaction import build_transfer_tx, sign_and_send_transaction, user_lock, user_burn
from utility.prepare_sol_asset import PrepareSOLAsset
from solders.hash import Hash
from solders.keypair import Keypair
from solders.instruction import Instruction
from solders.pubkey import Pubkey
import json
import os
import binascii

class TestSolanaLogic(unittest.TestCase):
    def setUp(self):
        self.kp = Keypair()
        self.wallet_data = {
            "wallet_name": "solana_wallet",
            "main_address": {str(self.kp.pubkey()): binascii.hexlify(bytes(self.kp)).decode()},
            "batch_address": {}
        }
        with open("current_wallets.json", "w") as f:
            json.dump([self.wallet_data], f)

    def tearDown(self):
        if os.path.exists("current_wallets.json"):
            os.remove("current_wallets.json")

    def test_build_transfer_tx_structure(self):
        valid_addr = str(Keypair().pubkey())
        recipients = [(valid_addr, 1000)]
        tx_data = build_transfer_tx(self.kp, recipients, "memo_data")
        self.assertEqual(len(tx_data["instructions"]), 2)

    def test_user_lock_structure(self):
        token_mint = binascii.hexlify(str(Keypair().pubkey()).encode()).decode()
        tx_data, error = user_lock(
            sender_kp=self.kp,
            amount=1000,
            token_pair_id=1038,
            smg_id_hex="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            user_account_hex="abcdef",
            token_mint_hex=token_mint,
            network='devnet'
        )
        self.assertIsNone(error)
        self.assertEqual(len(tx_data["instructions"]), 1)
        self.assertTrue(tx_data["instructions"][0].data.startswith(bytes.fromhex("4211d67eeb855272")))

    def test_user_burn_structure(self):
        token_mint = binascii.hexlify(str(Keypair().pubkey()).encode()).decode()
        tx_data, error = user_burn(
            sender_kp=self.kp,
            amount=1000,
            token_pair_id=1038,
            smg_id_hex="0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            user_account_hex="abcdef",
            token_mint_hex=token_mint,
            network='devnet'
        )
        self.assertIsNone(error)
        self.assertEqual(len(tx_data["instructions"]), 1)
        self.assertTrue(tx_data["instructions"][0].data.startswith(bytes.fromhex("2d4568ad65b42fbc")))

    @patch('solana.rpc.api.Client')
    def test_sign_and_send(self, mock_client):
        mock_service = mock_client.return_value
        mock_service.get_latest_blockhash.return_value.value.blockhash = "11111111111111111111111111111111"
        mock_service.send_transaction.return_value.value = "fake_signature"

        # Use a real instruction ID for mocking
        real_ix = Instruction(Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"), b"test", [])
        tx_data = {"instructions": [real_ix], "sender_kp": Keypair()}

        sig, error = sign_and_send_transaction(tx_data, mock_service)
        self.assertIsNone(error)
        self.assertEqual(sig, "fake_signature")

if __name__ == '__main__':
    unittest.main()
