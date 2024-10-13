import gnupg
from hashlib import sha256, sha512
import time
from uuid import uuid4
import models

class PGPLogin:
	def __init__(self, PEPPER):
		self.gpg = gnupg.GPG()
		self.PEPPER = PEPPER

	def generate_encrypted_confirmation_code(self, pubkey):
		importres = self.gpg.import_keys(pubkey)
		if len(importres.fingerprints) != 1:
			return None, None, None
		fingerprint = importres.fingerprints[0]
		if not fingerprint:
			return None, None, None
		confirmation_code = self.generate_confirmation_code()
		self.gpg.trust_keys([fingerprint], 'TRUST_ULTIMATE')
		encrypted_data = self.gpg.encrypt(confirmation_code, fingerprint)
		self.gpg.delete_keys([fingerprint])
		return fingerprint, confirmation_code, encrypted_data

	def generate_confirmation_code(self):
		code = sha512(f"{time.time()}{uuid4()}{self.PEPPER}".encode()).hexdigest()
		return code

	def create_login_code_in_db(self, db, fingerprint, confirmation_code):
		login_code = models.LoginCode.create(db, fingerprint, confirmation_code)
		return login_code

	def verify_login_code(self, db,  pubkey, confirmation_code):
		importres = self.gpg.import_keys(pubkey)
		display_name = importres.stderr.split('"')[1]
		fingerprint = importres.results[0]["fingerprint"]
		login_code = models.LoginCode.get(db, fingerprint, confirmation_code)
		self.gpg.delete_keys([fingerprint])
		return login_code, display_name, fingerprint