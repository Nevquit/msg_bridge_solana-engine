import unittest
import struct
import binascii
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from sendtransactions.msg_transaction import msg_cross_chain

class TestMsgCrossChain(unittest.TestCase):
    def setUp(self):
        self.kp = Keypair()

    def test_msg_cross_chain_structure(self):
        # Reference Transaction: 5Q4vLq7WkyKPGDxxxeLifssG5jKMbmnzeKNBJfYTxeAXddfv8EZFGRBqB8ywbWPLPir97kc5RWfLz1NP6GmsLToS
        to_chain_id = 2153201998
        to_contract = "0x174BADB1B8b9248dAe0519C5C8f9fFd9aCb2E779"
        to_user = "0x93a7f07e94EAF48593905735EAC165fEE0306375"
        amount = 10
        token_mint = "4zMMC9srt5Ri5X14GAgXhaHii3GnPAEERYPJgZJDncDU"
        smg_id = "0x000000000000000000000000000000000000000000746573746e65745f303836"
        network = 'devnet'
        gas_limit = 80000

        tx_data, error = msg_cross_chain(
            sender_kp=self.kp,
            to_chain_id=to_chain_id,
            to_contract=to_contract,
            to_user=to_user,
            amount=amount,
            token_mint_hex=token_mint,
            network=network,
            gas_limit=gas_limit
        )

        if error:
            self.fail(f"msg_cross_chain failed: {error}")

        ix = tx_data["instructions"][0]

        # Verify Account structure
        self.assertEqual(str(ix.accounts[0].pubkey), str(self.kp.pubkey()))           # 0: sender (signer)
        self.assertTrue(ix.accounts[0].is_signer)
        self.assertEqual(str(ix.accounts[1].pubkey), "CKyEEvrujycS6Y7CEjhp68XnCeqoPJkauxjNstH4CNQU") # 1: settings
        self.assertEqual(str(ix.accounts[2].pubkey), "9LgjPDcgKqUZBoKgrRtHUYxwV1XRVBbKKPVPsnNHSQsX") # 2: cpiSigner
        self.assertEqual(str(ix.accounts[3].pubkey), "9J17hVJXCcMsD1E7Kv5yNKEgQAhwcu4NvtPQvXkgesiV") # 3: gateway
        self.assertEqual(str(ix.accounts[4].pubkey), "8vfoebTCmYHZi223cmXHx3TBboo57xaqjNCbnvkYLQiS") # 4: nonce
        self.assertEqual(str(ix.accounts[5].pubkey), "9o7zWu1n3q1MCAQp5y8RYmhhVjNpkfhpbSDMeYvjwhZP") # 5: config
        self.assertEqual(str(ix.accounts[8].pubkey), "HGaSHNetDScLfY9tP6fNfarc8pyWjxiXcphJfxgNQ94s") # 8: vault ATA

        # Verify Data structure (88 bytes based on 5Q4v... analysis)
        # Disc(8) + PeerChain(16, u128) + Contract(4+20) + User(4+20) + Amount(8, u64) + Gas(8, u64) = 8+16+24+24+8+8 = 88
        self.assertEqual(len(ix.data), 88)
        self.assertTrue(ix.data.startswith(bytes.fromhex("99968dbe4e73e850")))
        # peer_chain_id (u128 at offset 8)
        self.assertEqual(int.from_bytes(ix.data[8:24], 'little'), to_chain_id)
        # amount (u64 at offset 72)
        self.assertEqual(struct.unpack("<Q", ix.data[72:80])[0], amount)
        # gas_limit (u64 at offset 80)
        self.assertEqual(struct.unpack("<Q", ix.data[80:88])[0], gas_limit)

if __name__ == '__main__':
    unittest.main()
