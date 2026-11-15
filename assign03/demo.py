"""Safe all-in-one Assignment 3 public-data demo (ephemeral key, no private file)."""
import hashlib
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from wallet import NETWORK, address_from_public, pub_bytes, sign, verify_signed


def main():
    alice = Ed25519PrivateKey.generate()
    bob = Ed25519PrivateKey.generate()
    tx = {'version':1,'network_id':NETWORK,'sender':address_from_public(pub_bytes(alice)),
          'recipient':address_from_public(pub_bytes(bob)), 'amount_units':1250000,
          'nonce':7,'memo_hash':hashlib.sha256(b'course demo').hexdigest()}
    envelope = sign(tx,alice)
    print(json.dumps(envelope,indent=2))
    nonces=set()
    print('Verified:',verify_signed(envelope,nonces))
    try: verify_signed(envelope,nonces)
    except ValueError as e: print('Expected second verification rejection:',e)
    envelope['transaction']['amount_units']+=1
    try: verify_signed(envelope)
    except ValueError as e: print('Expected tampering rejection:',e)


if __name__ == '__main__': main()
