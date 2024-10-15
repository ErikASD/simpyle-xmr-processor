from xmr_wallet_rpc import XMRWalletRPC
import models

xmr_wallet_rpc = XMRWalletRPC()

NORMALIZER = 1000 * 1000 * 1000 * 1000

class Withdraw:
	def __init__(self, config):
		self.ESTIMATE_RETRY_MAX = config["ESTIMATE_RETRY_MAX"]
		self.ESTIMATE_PERCENT_DOWN = config["ESTIMATE_PERCENT_DOWN"]

	def request_withdraw(self, db, user, amount, address):
		original_amount = int(float(amount) * NORMALIZER)
		amount = original_amount
		deducted = user.balance_deduct(db, original_amount)
		if not deducted:
			return "not enough balance"
		
		################
		retry_count = 0
		transfer = xmr_wallet_rpc.transfer_no_relay(amount, address)
		while not transfer and retry_count < self.ESTIMATE_RETRY_MAX:
			amount = int(amount * (1-(self.ESTIMATE_PERCENT_DOWN/100))) #compounds, with default config goes down to 95% untill gives up, only happens in small cases
			transfer = xmr_wallet_rpc.transfer_no_relay(amount, address)
			retry_count += 1
		
		if not transfer:
			user.balance_add(db, original_amount)
			return "unable to estimate transfer"
		#################


		"""
		can replace code within the "#"s with code in "*"s for a more error prone estimate, usually reached when max withdraw occurs, but does not reduce amount with while loop:

		*****************
		transfer = xmr_wallet_rpc.transfer_no_relay(amount, address)
		if not transfer:
			user.balance_add(db, original_amount)
			return "estimate transfer failed"
		*****************


		"""

		transfer2 = xmr_wallet_rpc.transfer_no_relay(amount - transfer["fee"], address) #sends adjusted amount with fee, perfect above 0.0002 XMR
		if not transfer2:
			user.balance_add(db, original_amount)
			return "transfer failed"

		transfer_final = xmr_wallet_rpc.relay_tx(transfer2["tx_metadata"])
		if not transfer_final:
			user.balance_add(db, original_amount)
			return "relay failed"
		return "transfered"
