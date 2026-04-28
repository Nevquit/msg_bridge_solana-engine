import json
from web3 import Web3
from eth_account import Account

class Erc20TokenRemote:
    def __init__(self, node_url, sc_addr, abi_path="config/ERC20TokenRemote.json"):
        self.w3 = Web3(Web3.HTTPProvider(node_url))
        with open(abi_path, 'r') as f:
            abi = json.load(f)
        self.contract = self.w3.eth.contract(address=Web3.to_checksum_address(sc_addr), abi=abi)

    def send(self, private_key, to_bytes, amount):
        """
        Sends tokens cross-chain.
        :param private_key: Private key of the sender
        :param to_bytes: Destination address as bytes (e.g., Solana ATA)
        :param amount: Amount to send
        """
        account = Account.from_key(private_key)

        # Build transaction
        nonce = self.w3.eth.get_transaction_count(account.address)

        # The JS reference uses signedSc.send(to, amount, { gasLimit: 10000000 })
        txn = self.contract.functions.send(to_bytes, int(amount)).build_transaction({
            'from': account.address,
            'nonce': nonce,
            'gas': 1000000, # Using a more reasonable default than 10M, but can be adjusted
            'gasPrice': self.w3.eth.gas_price
        })

        # Sign and send
        signed_txn = self.w3.eth.account.sign_transaction(txn, private_key=private_key)
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)

        # Wait for receipt
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt.transactionHash.hex(), receipt

    def get_token_balance(self, address):
        return self.contract.functions.balanceOf(Web3.to_checksum_address(address)).call()

    def get_wmb_gateway(self):
        return self.contract.functions.wmbGateway().call()

# Usage example (mirroring send() in the provided JS):
# if __name__ == "__main__":
#     # from config.js
#     tokenTransferScAddr = '0x174BADB1B8b9248dAe0519C5C8f9fFd9aCb2E779'
#     nodeUrl = "https://gwan-ssl.wandevs.org:46891"
#     solUserATA = "rcMakHp2MwBYqYxXDpLa3A7QNt4Q7JdR7MneuPuzf2u"
#
#     # In Python, we need the private key or mnemonic
#     # wallet = Account.from_mnemonic(words)
#
#     remote = Erc20TokenRemote(nodeUrl, tokenTransferScAddr)
#     # receiptTo must be bytes in Python to match bytes in Solidity
#     import base58
#     to_bytes = base58.b58decode(solUserATA)
#     # tx_hash, receipt = remote.send(private_key, to_bytes, 9)
