
from cryptography.fernet import Fernet

secret_key = 'TI31VYJ-ldAq-FXo5QNPKV_lqGTFfp-MIdbK2Hm5F1E='  # 与加密时一致

def decrypt_password(encrypted_password: str) -> str:
    fernet = Fernet(secret_key)
    decrypted_bytes = fernet.decrypt(encrypted_password.encode())
    return decrypted_bytes.decode()

original_db_password = decrypt_password("gAAAAABnXWu4elfGvkGUs8ByAFcp4zgxRTNqY-XWqnzSEwgKB934AQinhyFmKfzJu2FqUDoJ3aVHgllx13F6NSLDLoljvO9ypg==")
print(original_db_password)