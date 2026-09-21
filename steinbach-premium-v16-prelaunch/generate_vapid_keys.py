"""Generate VAPID keys for Web Push.
Requires the packages from requirements.txt (pywebpush installs py-vapid/cryptography).
"""
from __future__ import annotations
import base64
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

root=Path(__file__).resolve().parent
private=ec.generate_private_key(ec.SECP256R1())
pem=private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
path=root/'vapid_private.pem'; path.write_bytes(pem)
public=private.public_key().public_numbers()
raw=b'\x04'+public.x.to_bytes(32,'big')+public.y.to_bytes(32,'big')
public_b64=base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
print(f'STEINBACH_VAPID_PRIVATE_KEY={path}')
print(f'STEINBACH_VAPID_PUBLIC_KEY={public_b64}')
print('STEINBACH_VAPID_SUBJECT=mailto:info@immobilienservice-steinbach.de')
