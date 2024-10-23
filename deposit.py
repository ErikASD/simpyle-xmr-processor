import qrcode
import qrcode.image.svg
from xmr_wallet_rpc import XMRWalletRPC
import models
import time


xmr_wallet_rpc = XMRWalletRPC()

class Deposit:
	def __init__(self):
		pass

	def get_qr_svg(self, address):
		qr = qrcode.QRCode(image_factory=qrcode.image.svg.SvgPathImage, box_size=10,border=0)
		qr.add_data(f"monero:{address}")
		qr.make(fit=True)
		img = qr.make_image(attrib={'class': 'qr-image-d'})
		svg = img.to_string(encoding='unicode')
		return svg

	def check_deposits(self, db):
		#NO SWEEP ARCHITECHTURE, high read/write when many transactions are unspent, best used for hotwallet frequently spending incoming outputs.
		transfers = xmr_wallet_rpc.incoming_transfers([])
		tx_hashes = []
		tx_hashes_unlocked = set()

		for transfer in transfers:
			transfer["address_index"] = transfer["subaddr_index"]["minor"]
			if transfer["subaddr_index"]["minor"] == 0:
				continue
			tx_hashes.append(transfer["tx_hash"])
			if transfer["unlocked"]:
				tx_hashes_unlocked.add(transfer["tx_hash"])

		#tries to insert all given transfers, next line will deal with all edge cases
		models.Transaction.bulk_insert(db, transfers)

		#credits all pending transactions in db that are unlocked
		txes_no_credit = models.Transaction.get_by_no_credit(db)
		for transaction in txes_no_credit:
			if transaction.tx_hash in tx_hashes_unlocked: #o(1) lookup for sets
				transaction.credit(db)

	def create_deposit_if_none(self, db, user):
		if user.xmr_address is None:
			address = xmr_wallet_rpc.create_address()
			user.create_address(db, address)
