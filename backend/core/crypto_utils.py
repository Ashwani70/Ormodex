import base64
import hmac
import hashlib
import json
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

def _derive_key(ek: str) -> bytes:
    """Derive a 32-byte key from the configured Encryption Key (EK)."""
    ek_bytes = ek.encode('utf-8')
    if len(ek_bytes) == 32:
        return ek_bytes
    # Hash to 32 bytes if not already 32 bytes
    return hashlib.sha256(ek_bytes).digest()

def encrypt_payload(payload: dict, action: str, ek: str) -> dict:
    """
    Encrypt a payload dictionary to GSP payload format.
    Steps:
      1. Base64 encode the JSON of the payload.
      2. Pad the Base64 string to 16-byte boundaries (PKCS5/PKCS7).
      3. Encrypt via AES-256 ECB using derived key from EK.
      4. Base64 encode the ciphertext to form the 'data' field.
      5. Compute HMAC-SHA256 of the 'data' string using derived key from EK.
    """
    key_bytes = _derive_key(ek)
    
    # 1. Base64 encode the JSON of payload
    json_str = json.dumps(payload)
    b64_json = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
    
    # 2. Pad Base64 string (PKCS7/PKCS5)
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(b64_json.encode('utf-8')) + padder.finalize()
    
    # 3. Encrypt via AES-256 ECB
    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    
    # 4. Base64 encode ciphertext to form data field
    data_val = base64.b64encode(ciphertext).decode('utf-8')
    
    # 5. Compute HMAC-SHA256 of data string
    h = hmac.new(key_bytes, data_val.encode('utf-8'), hashlib.sha256)
    hmac_val = h.hexdigest()
    
    return {
        "action": action,
        "data": data_val,
        "hmac": hmac_val
    }

def decrypt_payload(envelope: dict, ek: str) -> dict:
    """
    Decrypt a GSP envelope dictionary.
    Steps:
      1. Verify HMAC-SHA256 of envelope['data'].
      2. Base64 decode envelope['data'] to ciphertext bytes.
      3. Decrypt via AES-256 ECB using derived key from EK.
      4. Unpad to get the Base64 JSON string.
      5. Base64 decode to get JSON string, then parse to dict.
    """
    data_val = envelope.get("data")
    hmac_val = envelope.get("hmac")
    
    if not data_val or not hmac_val:
        raise ValueError("Invalid envelope: missing data or hmac field")
        
    key_bytes = _derive_key(ek)
    
    # 1. Verify HMAC
    h = hmac.new(key_bytes, data_val.encode('utf-8'), hashlib.sha256)
    expected_hmac = h.hexdigest()
    
    if not hmac.compare_digest(hmac_val, expected_hmac):
        raise ValueError("HMAC verification failed")
        
    # 2. Base64 decode data
    ciphertext = base64.b64decode(data_val.encode('utf-8'))
    
    # 3. Decrypt via AES-256 ECB
    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(ciphertext) + decryptor.finalize()
    
    # 4. Unpad
    unpadder = padding.PKCS7(128).unpadder()
    b64_json_bytes = unpadder.update(padded_data) + unpadder.finalize()
    b64_json_str = b64_json_bytes.decode('utf-8')
    
    # 5. Base64 decode JSON string and load
    json_bytes = base64.b64decode(b64_json_str.encode('utf-8'))
    return json.loads(json_bytes.decode('utf-8'))
