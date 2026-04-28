import struct
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from spl.token.instructions import get_associated_token_address
from .sendtransaction import get_contracts, get_pda, hex_to_pubkey

# Discriminator for LockToken in token-xport-demo
LOCK_TOKEN_DISCRIMINATOR = bytes.fromhex("99968dbe4e73e850")

def encode_lock_token_data(peer_chain_id, peer_app_address_hex, to_user_hex, amount, gas_limit):
    # peer_chain_id is u128 (16 bytes)
    peer_chain_id_bytes = int(peer_chain_id).to_bytes(16, 'little')

    # peer_app_address (Vec<u8>, 20 bytes)
    peer_app_address = bytes.fromhex(peer_app_address_hex.replace('0x', ''))
    if len(peer_app_address) > 20:
        peer_app_address = peer_app_address[-20:]
    elif len(peer_app_address) < 20:
        peer_app_address = peer_app_address.rjust(20, b'\x00')
    peer_app_address_len = struct.pack("<I", 20)

    # target_user (Vec<u8>, 20 bytes)
    target_user = bytes.fromhex(to_user_hex.replace('0x', ''))
    if len(target_user) > 20:
        target_user = target_user[-20:]
    elif len(target_user) < 20:
        target_user = target_user.rjust(20, b'\x00')
    target_user_len = struct.pack("<I", 20)

    data = LOCK_TOKEN_DISCRIMINATOR
    data += peer_chain_id_bytes
    data += peer_app_address_len + peer_app_address
    data += target_user_len + target_user
    # amount is u64 (8 bytes)
    data += struct.pack("<Q", int(amount))
    # gas_limit is u64 (8 bytes)
    data += struct.pack("<Q", int(gas_limit))
    return data

def msg_cross_chain(sender_kp, to_chain_id, to_contract, to_user, amount, token_mint_hex, network, gas_limit=80000, **kwargs):
    try:
        conf = get_contracts(network)
        msg_bridge_prog_id = conf.get('msg_bridge_program_id', "4qyZxqVyE4JsjoW3jgQFqcmuygUUM1hMNUASobcabgC8")
        wmb_prog_id = conf.get('wmb_program_id', "9J17hVJXCcMsD1E7Kv5yNKEgQAhwcu4NvtPQvXkgesiV")
        admin_prog_id = conf.get('admin_board_program_id', "7jYCM8k5Nvwg5vyPpLk2yjivQhexPDMXuK8CSbUKqL6B")

        msg_prog = Pubkey.from_string(msg_bridge_prog_id)
        wmb_prog = Pubkey.from_string(wmb_prog_id)
        admin_prog = Pubkey.from_string(admin_prog_id)

        # PDAs
        settings_pda = get_pda(["settings"], str(msg_prog))
        cpi_signer_pda = get_pda(["CpiSigner"], str(msg_prog))
        fundraiser_pda = get_pda(["fundraiser"], str(msg_prog))

        # WMB Nonce Account
        solana_chain_id = 2147484149 if network == 'devnet' else 115111108
        solana_chain_id_bytes = solana_chain_id.to_bytes(16, 'little')
        peer_chain_id_bytes = int(to_chain_id).to_bytes(16, 'little')
        nonce_account_pda = get_pda([b"nonce", solana_chain_id_bytes, peer_chain_id_bytes, bytes(msg_prog), bytes.fromhex(to_contract.replace('0x', ''))], str(wmb_prog))

        # Admin Config
        config_account_pda = get_pda(["ConfigData"], str(admin_prog))

        # Token Accounts
        token_mint = hex_to_pubkey(token_mint_hex)
        user_ata = get_associated_token_address(sender_kp.pubkey(), token_mint)
        vault_ata = get_associated_token_address(fundraiser_pda, token_mint)

        data = encode_lock_token_data(to_chain_id, to_contract, to_user, amount, gas_limit)

        accounts = [
            AccountMeta(pubkey=sender_kp.pubkey(), is_signer=True, is_writable=True), # 0: sender
            AccountMeta(pubkey=settings_pda, is_signer=False, is_writable=True),      # 1: settings
            AccountMeta(pubkey=cpi_signer_pda, is_signer=False, is_writable=True),   # 2: cpiSigner
            AccountMeta(pubkey=wmb_prog, is_signer=False, is_writable=False),        # 3: gatewayProgram
            AccountMeta(pubkey=nonce_account_pda, is_signer=False, is_writable=True),# 4: nonceAccount
            AccountMeta(pubkey=config_account_pda, is_signer=False, is_writable=False),# 5: configAccount
            AccountMeta(pubkey=token_mint, is_signer=False, is_writable=False),      # 6: mintAccount
            AccountMeta(pubkey=user_ata, is_signer=False, is_writable=True),         # 7: senderTokenAccount
            AccountMeta(pubkey=vault_ata, is_signer=False, is_writable=True),        # 8: vault
            AccountMeta(pubkey=Pubkey.from_string(conf.get('token_program_id', "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")), is_signer=False, is_writable=False), # 9: tokenProgram
            AccountMeta(pubkey=Pubkey.from_string(conf.get('associated_token_program_id', "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")), is_signer=False, is_writable=False), # 10: associatedTokenProgram
            AccountMeta(pubkey=Pubkey.from_string(conf.get('system_program_id', "11111111111111111111111111111111")), is_signer=False, is_writable=False), # 11: systemProgram
        ]

        ix = Instruction(msg_prog, data, accounts)
        return {"instructions": [ix], "sender_kp": sender_kp}, None
    except Exception as e:
        return None, str(e)
