import json
import os
import binascii
import struct
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import TransferParams, transfer
from solders.transaction import Transaction
from solders.message import Message
from solders.instruction import Instruction, AccountMeta
from solana.rpc.types import TxOpts
from solders.hash import Hash
from spl.token.instructions import get_associated_token_address

# Load constants from config
try:
    with open('config/contract_accounts.json', 'r') as f:
        CONTRACTS = json.load(f)
except:
    CONTRACTS = {}

def get_contracts(network):
    return CONTRACTS.get(network, {})

def hex_to_pubkey(hex_str):
    """
    Converts a hex string or base58 string to a Solana Pubkey.
    Handles raw 32-byte hex, ASCII-encoded hex, and standard base58.
    """
    if not hex_str: return None

    # Try base58 directly first
    try:
        return Pubkey.from_string(hex_str)
    except:
        pass

    clean_hex = hex_str.replace('0x', '')
    try:
        raw_bytes = binascii.unhexlify(clean_hex)

        # Check if this is an ASCII-encoded Solana address
        try:
            addr_str = raw_bytes.decode('utf-8')
            return Pubkey.from_string(addr_str)
        except:
            pass

        # Check if it is a direct 32-byte public key
        if len(raw_bytes) == 32:
            return Pubkey.from_bytes(raw_bytes)
    except:
        pass

    raise ValueError(f"Invalid Solana Pubkey format: {hex_str}")

def get_pda(seeds, program_id):
    seed_bytes = []
    for s in seeds:
        if isinstance(s, str): seed_bytes.append(s.encode('utf-8'))
        elif isinstance(s, int): seed_bytes.append(struct.pack("<I", s))
        else: seed_bytes.append(bytes(s))
    res = Pubkey.find_program_address(seed_bytes, Pubkey.from_string(program_id))
    return res[0]

def build_transfer_tx(sender_kp, recipients, custom_data=None):
    instructions = []
    for addr_str, amount in recipients:
        instructions.append(
            transfer(
                TransferParams(
                    from_pubkey=sender_kp.pubkey(),
                    to_pubkey=Pubkey.from_string(addr_str),
                    lamports=int(amount)
                )
            )
        )
    if custom_data:
        memo_prog = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
        instructions.append(Instruction(memo_prog, custom_data.encode('utf-8'), []))
    return {"instructions": instructions, "sender_kp": sender_kp}

def sign_and_send_transaction(tx_data, service):
    try:
        instructions = tx_data["instructions"]

        # Support multiple signers and explicit fee payer
        if "signers" in tx_data:
            signers = tx_data["signers"]
        else:
            signers = [tx_data["sender_kp"]]

        # First signer is the fee payer by default
        fee_payer = tx_data.get("fee_payer_kp", signers[0])

        # Ensure fee payer is the first signer and signers are unique
        final_signers = [fee_payer]
        seen_pubkeys = {str(fee_payer.pubkey())}
        for s in signers:
            if str(s.pubkey()) not in seen_pubkeys:
                final_signers.append(s)
                seen_pubkeys.add(str(s.pubkey()))

        bh_res = service.get_latest_blockhash()
        recent_blockhash = bh_res.value.blockhash
        if isinstance(recent_blockhash, str):
            recent_blockhash = Hash.from_string(recent_blockhash)

        message = Message.new_with_blockhash(instructions, fee_payer.pubkey(), recent_blockhash)
        tx = Transaction(final_signers, message, recent_blockhash)

        # Use TxOpts for better control and confirm transaction status
        opts = TxOpts(skip_preflight=False, preflight_commitment="confirmed")
        res = service.send_transaction(tx, opts=opts)
        return str(res.value), None
    except Exception as e:
        return None, str(e)
