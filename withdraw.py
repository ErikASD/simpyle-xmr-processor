from xmr_wallet_rpc import XMRWalletRPC
import models
import requests

xmr_wallet_rpc = XMRWalletRPC()

NORMALIZER = 1000 * 1000 * 1000 * 1000

class Withdraw:
	def __init__(self, config):
		self.ESTIMATE_LOOP = config["ESTIMATE_LOOP"]
		self.ESTIMATE_RETRY_MAX = config["ESTIMATE_RETRY_MAX"]
		self.ESTIMATE_PERCENT_DOWN = config["ESTIMATE_PERCENT_DOWN"]

	def request_withdraw(self, db, db_withdraw_request, address):
		amount = db_withdraw_request.amount

		try:
			if self.ESTIMATE_LOOP:

				retry_count = 0
				transfer = xmr_wallet_rpc.transfer_no_relay(amount, address)
				while not transfer and retry_count < self.ESTIMATE_RETRY_MAX:
					amount = int(amount * (1-(self.ESTIMATE_PERCENT_DOWN/100)))
					transfer = xmr_wallet_rpc.transfer_no_relay(amount, address)
					retry_count += 1
				
				if not transfer:
					db_withdraw_request.refund(db)
					return "unable to estimate transfer"

			else:

				transfer = xmr_wallet_rpc.transfer_no_relay(amount, address)
				if not transfer:
					db_withdraw_request.refund(db)
					return "estimate transfer failed"


			transfer2 = xmr_wallet_rpc.transfer_no_relay(amount - transfer["fee"], address) #sends adjusted amount with fee, perfect above 0.0002 XMR
			if not transfer2:
				db_withdraw_request.refund(db)
				return "transfer failed"

			transfer_final = xmr_wallet_rpc.relay_tx(transfer2["tx_metadata"])
			if not transfer_final:
				db_withdraw_request.refund(db)
				return "relay failed"
		except requests.exceptions.RequestException:
			#When RPC relay throws a request exception and quits before refund.
			db_withdraw_request.refund(db)
			return "relay failed"

		db_withdraw_request.succeed(db, transfer2["fee"], transfer_final["tx_hash"])
		return "transfered"