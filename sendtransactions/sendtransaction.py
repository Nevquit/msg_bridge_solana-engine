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

# Discriminators
USER_LOCK_DISCRIMINATOR = bytes.fromhex("4211d67eeb855272")
USER_BURN_DISCRIMINATOR = bytes.fromhex("2d4568ad65b42fbc")

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

def encode_user_lock_data(smg_id_hex, token_pair_id, amount, user_account_hex):
    # smg_id is expected as 32-byte raw data
    smg_id = bytes.fromhex(smg_id_hex.replace('0x', '')).ljust(32, b'\0')[:32]

    # user_account (EVM address) is encoded as ASCII bytes (to match JS engine)
    user_account = user_account_hex.encode('utf-8')
    user_account_len = struct.pack("<I", len(user_account))

    data = USER_LOCK_DISCRIMINATOR
    data += smg_id
    data += struct.pack("<I", int(token_pair_id))
    data += struct.pack("<Q", int(amount))
    data += user_account_len + user_account
    return data

def encode_user_burn_data(smg_id_hex, token_pair_id, amount, fee, token_account_pubkey, user_account_hex):
    smg_id = bytes.fromhex(smg_id_hex.replace('0x', '')).ljust(32, b'\0')[:32]

    # user_account (EVM address) is encoded as ASCII bytes
    user_account = user_account_hex.encode('utf-8')
    user_account_len = struct.pack("<I", len(user_account))

    data = USER_BURN_DISCRIMINATOR
    data += smg_id
    data += struct.pack("<I", int(token_pair_id))
    data += struct.pack("<Q", int(amount))
    data += struct.pack("<Q", int(fee))
    data += bytes(Pubkey.from_string(token_account_pubkey))
    data += user_account_len + user_account
    return data

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

def user_lock(sender_kp, amount, token_pair_id, smg_id_hex, user_account_hex, token_mint_hex, network, dest_chain_id=2153201998):
    try:
        conf = get_contracts(network)
        bridge_prog = Pubkey.from_string(conf['bridge_program_id'])
        admin_prog = Pubkey.from_string(conf['admin_board_program_id'])
        fee_config_prog = Pubkey.from_string(conf['fee_config_program_id'])

        is_coin = token_mint_hex.replace('0x', '').startswith('000000000000')

        sol_vault = get_pda(["vault"], str(bridge_prog))

        if is_coin:
            # Placeholders for optional accounts when it's native SOL
            user_ata = bridge_prog
            token_vault = bridge_prog
            token_mint = bridge_prog
        else:
            token_mint = hex_to_pubkey(token_mint_hex)
            user_ata = get_associated_token_address(sender_kp.pubkey(), token_mint)
            token_vault = get_associated_token_address(sol_vault, token_mint)

        token_pair_pda = get_pda(["TokenPairInfo", int(token_pair_id)], str(admin_prog))
        config_pda = get_pda(["ConfigData"], str(admin_prog))
        fee_pda = get_pda(["FeeData", int(dest_chain_id)], str(fee_config_prog))

        data = encode_user_lock_data(smg_id_hex, token_pair_id, amount, user_account_hex)

        accounts = [
            AccountMeta(pubkey=sender_kp.pubkey(), is_signer=True, is_writable=True), # user
            AccountMeta(pubkey=sol_vault, is_signer=False, is_writable=True), # solVault
            AccountMeta(pubkey=user_ata, is_signer=False, is_writable=True), # userAta (Optional)
            AccountMeta(pubkey=token_vault, is_signer=False, is_writable=True), # tokenVault (Optional)
            AccountMeta(pubkey=token_mint, is_signer=False, is_writable=True), # mappingTokenMint (Optional)
            AccountMeta(pubkey=Pubkey.from_string(conf['feeReceiver']), is_signer=False, is_writable=True), # feeReceiver
            AccountMeta(pubkey=admin_prog, is_signer=False, is_writable=False), # adminBoardProgram
            AccountMeta(pubkey=config_pda, is_signer=False, is_writable=False), # configAccount
            AccountMeta(pubkey=token_pair_pda, is_signer=False, is_writable=True), # tokenPairAccount
            AccountMeta(pubkey=fee_pda, is_signer=False, is_writable=False), # cctpAdminBoardFeeAccount
            AccountMeta(pubkey=Pubkey.from_string(conf['token_program_id']), is_signer=False, is_writable=False),
            AccountMeta(pubkey=Pubkey.from_string(conf['associated_token_program_id']), is_signer=False, is_writable=False),
            AccountMeta(pubkey=Pubkey.from_string(conf['system_program_id']), is_signer=False, is_writable=False),
        ]

        ix = Instruction(bridge_prog, data, accounts)
        return {"instructions": [ix], "sender_kp": sender_kp}, None
    except Exception as e:
        return None, str(e)

def user_burn(sender_kp, amount, token_pair_id, smg_id_hex, user_account_hex, token_mint_hex, network, fee=10200000, dest_chain_id=2153201998):
    try:
        conf = get_contracts(network)
        admin_prog = Pubkey.from_string(conf['admin_board_program_id'])
        bridge_prog = Pubkey.from_string(conf['bridge_program_id'])
        fee_config_prog = Pubkey.from_string(conf['fee_config_program_id'])

        # Hardcoded expected tokenManagerProgram based on error trace
        token_manager_prog = Pubkey.from_string("6PcqfvWkBv3m9F5XBU2kMAedycs6BPzDGfi8zcWam3kH")

        token_mint = hex_to_pubkey(token_mint_hex)
        user_ata = get_associated_token_address(sender_kp.pubkey(), token_mint)

        token_pair_pda = get_pda(["TokenPairInfo", int(token_pair_id)], str(admin_prog))
        config_pda = get_pda(["ConfigData"], str(admin_prog))
        fee_pda = get_pda(["FeeData", int(dest_chain_id)], str(fee_config_prog))

        data = encode_user_burn_data(smg_id_hex, token_pair_id, amount, fee, str(token_mint), user_account_hex)

        accounts = [
            AccountMeta(pubkey=sender_kp.pubkey(), is_signer=True, is_writable=True), # user
            AccountMeta(pubkey=user_ata, is_signer=False, is_writable=True), # userAta
            AccountMeta(pubkey=token_mint, is_signer=False, is_writable=True), # mappingTokenMint
            AccountMeta(pubkey=config_pda, is_signer=False, is_writable=False), # configAccount
            AccountMeta(pubkey=token_manager_prog, is_signer=False, is_writable=False), # tokenManagerProgram
            AccountMeta(pubkey=Pubkey.from_string(conf['feeReceiver']), is_signer=False, is_writable=True), # feeReceiver
            AccountMeta(pubkey=admin_prog, is_signer=False, is_writable=False), # adminBoardProgram
            AccountMeta(pubkey=token_pair_pda, is_signer=False, is_writable=True), # tokenPairAccount
            AccountMeta(pubkey=fee_pda, is_signer=False, is_writable=False), # cctpAdminBoardFeeAccount
            AccountMeta(pubkey=Pubkey.from_string(conf['token_program_id']), is_signer=False, is_writable=False),
            AccountMeta(pubkey=Pubkey.from_string(conf['associated_token_program_id']), is_signer=False, is_writable=False),
            AccountMeta(pubkey=Pubkey.from_string(conf['system_program_id']), is_signer=False, is_writable=False),
        ]

        ix = Instruction(bridge_prog, data, accounts)
        return {"instructions": [ix], "sender_kp": sender_kp}, None
    except Exception as e:
        return None, str(e)

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
