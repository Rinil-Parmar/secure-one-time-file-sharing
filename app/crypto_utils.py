import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


NONCE_SIZE = 12


def derive_key(secret):
    return hashlib.sha256(secret.encode("utf-8")).digest()


def encrypt_bytes(data, secret):
    key = derive_key(secret)
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(key).encrypt(nonce, data, None)
    return ciphertext, base64.b64encode(nonce).decode("ascii")


def decrypt_bytes(ciphertext, nonce_b64, secret):
    key = derive_key(secret)
    nonce = base64.b64decode(nonce_b64)
    return AESGCM(key).decrypt(nonce, ciphertext, None)
