from cryptography.fernet import Fernet

# Generate a key and save it securely (do this only once)
key = Fernet.generate_key()
with open("env.key", "wb") as key_file:
    key_file.write(key)

# Encrypt the .env file
with open("env.key", "rb") as key_file:
    key = key_file.read()
fernet = Fernet(key)

with open(".env", "rb") as file:
    original = file.read()

encrypted = fernet.encrypt(original)

with open(".env.enc", "wb") as encrypted_file:
    encrypted_file.write(encrypted)

print("Encrypted .env to .env.enc. Store env.key securely!")
