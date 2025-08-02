"""Encryption utilities for Direktive.ai integration."""
import base64
import os
import logging
from typing import Optional, Dict, Any
import json
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

from .const import (
    ENCRYPTION_ALGORITHM,
    ENCRYPTION_KEY_LENGTH,
    ENCRYPTION_IV_LENGTH,
    SUBSCRIPTION_TYPE_PRO,
)

_LOGGER = logging.getLogger(__name__)

def generate_encryption_key() -> str:
    """Generate a new encryption key."""
    # Generate a random key
    key = os.urandom(ENCRYPTION_KEY_LENGTH)
    return base64.b64encode(key).decode('utf-8')

def encrypt_data(data: Dict[str, Any], encryption_key: str) -> str:
    """Encrypt data using AES-256-CBC."""
    try:
        iv = os.urandom(16)  # Generate a random 16-byte IV
        cipher = Cipher(algorithms.AES(base64.b64decode(encryption_key)), modes.CBC(iv))
        encryptor = cipher.encryptor()
        
        # Convert JSON to string
        plaintext = json.dumps(data)

        # Pad data to be a multiple of 16 bytes (AES block size)
        padder = padding.PKCS7(128).padder()        
        padded_data = padder.update(plaintext.encode()) + padder.finalize()

        ciphertext = encryptor.update(padded_data) + encryptor.finalize()
        
        # Encode result as base64 for easy transport
        return base64.b64encode(iv + ciphertext).decode('utf-8')
    
    except Exception as err:
        _LOGGER.error("Error encrypting data: %s", str(err))
        raise

def decrypt_data(encrypted_data: str, encryption_key: str) -> Dict[str, Any]:
    """Decrypt data using AES-256-CBC."""
    try:
        # Decode base64 encrypted data
        encrypted_bytes = base64.b64decode(encrypted_data)
        
        # Extract IV (first 16 bytes) and ciphertext
        iv = encrypted_bytes[:16]
        ciphertext = encrypted_bytes[16:]
        
        # Create decipher with AES-256-CBC
        key = base64.b64decode(encryption_key)
        cipher = Cipher(
            algorithms.AES(key),
            modes.CBC(iv)
        )
        decryptor = cipher.decryptor()
        
        # Decrypt the data
        decrypted_padded_data = decryptor.update(ciphertext) + decryptor.finalize()
        
        # Unpad data
        unpadder = padding.PKCS7(128).unpadder()
        decrypted_data = unpadder.update(decrypted_padded_data) + unpadder.finalize()
        
        # Convert back to dictionary
        return json.loads(decrypted_data.decode('utf-8'))
    except Exception as err:
        _LOGGER.error("Error decrypting data: %s", str(err))
        raise

def should_encrypt(subscription_type: Optional[str]) -> bool:
    """Check if data should be encrypted based on subscription type."""
    # return subscription_type == SUBSCRIPTION_TYPE_PRO
    return True