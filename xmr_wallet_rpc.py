import requests
import json

with open('config.json', 'r') as file:
	config = json.load(file)

class XMRWalletRPC:
	def __init__(self):
		self.url = config["WALLET_RPC_ADDRESS"]

	def send(self, method, params = None):
		data = {"jsonrpc":"2.0","id":"0","method":method}
		if params:
			data["params"] = params
		response = requests.post(f"http://{self.url}/json_rpc", json=data).json()
		return response

	def create_address(self):
		address = self.send("create_address",{"account_index":0,"label":"","count":1})
		self.send("store") #saves file with new index
		return address["result"]

	def incoming_transfers(self, subaddr_indices):
		transfers = self.send("incoming_transfers",{"transfer_type":"available","account_index":0,"subaddr_indices":subaddr_indices})
		if transfers == {} or transfers["result"] == {}:
			return []
		return transfers["result"]["transfers"]

	def get_transfers(self, min_height=0):
		transfers = self.send("get_transfers", {"in":True,"account_index":0,"pending":False,"filter_by_height":True,"min_height":min_height})
		if transfers["result"] == {}:
			return []
		return transfers["result"]

	def transfer_no_relay(self, amount, address):
		transfer = self.send("transfer",{"destinations":[{"amount":amount,"address":address}],"account_index":0,"priority":0,"ring_size":16,"get_tx_metadata":True,"do_not_relay":True})
		if not "result" in transfer:
			return None
		return transfer["result"]

	def relay_tx(self, tx_metadata):
		transfer = self.send("relay_tx",{"hex":tx_metadata})
		if not "result" in transfer:
			return None
		return transfer["result"]