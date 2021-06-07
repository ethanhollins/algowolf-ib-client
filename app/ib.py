import numpy as np
import pandas as pd
import time
import os
import ntplib
import shortuuid
import subprocess
import requests
import json
import traceback
from . import tradelib as tl
from threading import Thread
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATEWAY_RUN_DIR = os.path.join(ROOT_DIR, 'clientportal.gw/bin/run.sh')
GATEWAY_CONFIG_DIR = os.path.join(ROOT_DIR, 'clientportal.gw/root/conf.yaml')


class Subscription(object):

	def __init__(self, broker, msg_id):
		self.broker = broker
		self.msg_id = msg_id


	def onUpdate(self, *args):
		print(f'ON UPDATE: {args}', flush=True)

		self.broker._send_response(
			self.msg_id,
			{
				'args': list(args),
				'kwargs': {}
			}
		)


class IB(object):

	def __init__(self, sio, port, user_id, strategy_id, broker_id):
		print('IB INIT', flush=True)

		self.sio = sio
		self.port = port

		self.userId = user_id
		self.strategyId = strategy_id
		self.brokerId = broker_id

		self._url = f'http://ib_client:{self.port}/v1/api'
		self._session = requests.session()
		self.accounts = []

		self._gui_subscriptions = []

		self._is_gateway_loaded = False
		self._logged_in = False
		self._iserver_auth = False
		self._selected_account = None

		if self.port != '5000':
			t = Thread(target=self._periodic_check)
			print(f'Is Daemon: {t.isDaemon()}', flush=True)
			t.start()


	def _periodic_check(self):
		try:
			while True:
				print(f'[_periodic_check] ({self.port}) {time.time()}', flush=True)
				if not self._logged_in:
					try:
						ept = '/sso/validate'
						res = self._session.get(self._url + ept, timeout=2)
						if res.status_code < 500:
							if not self._is_gateway_loaded:
								print(f'[CHECK] ({self.port}) Gateway loaded. To Login: http://127.0.0.1:{self.port}/', flush=True)
								self._is_gateway_loaded = True
								# Send gateway loaded message
								for sub in self._gui_subscriptions:
									sub.onUpdate('gateway_loaded')

							if res.status_code == 200:
								if not self._logged_in:
									print(f'[CHECK] ({self.port}) Logged in.', flush=True)
									self._logged_in = True
									# Send logged in message
									for sub in self._gui_subscriptions:
										sub.onUpdate('logged_in')

					except Exception:
						print(traceback.format_exc(), flush=True)

					time.sleep(1)
				else:
					try:
						print(f'[Tickle] {time.time()}', flush=True)
						ept = '/tickle'
						res = self._session.post(self._url + ept, timeout=5)

						print(f'[Tickle] {res.status_code}', flush=True)

						if res.status_code == 200:
							data = res.json()
							print(f'{json.dumps(data, indent=2)}', flush=True)
							if not data["iserver"]["authStatus"]["authenticated"]:
								self._iserver_auth = False
								self.authIServer(timeout=0)
							else:
								self._iserver_auth = True

						if self._iserver_auth:
							ept = '/iserver/account/orders'
							res = self._session.get(self._url + ept, timeout=5)
							print(f'[iserver] {res.status_code}, {res.text}', flush=True)

					except Exception:
						print(traceback.format_exc(), flush=True)

					time.sleep(10)

		except Exception:
			print(f'[_periodic_check] ({self.port}) {traceback.format_exc()}', flush=True)



	def _start_gateway(self):
		print(f'GATEWAY: {[ GATEWAY_RUN_DIR, GATEWAY_CONFIG_DIR, self.port ]}', flush=True)
		self._gateway_process = subprocess.Popen(
			[ GATEWAY_RUN_DIR, GATEWAY_CONFIG_DIR, str(self.port) ]
		)

		return { 'complete': True }


	def isLoggedIn(self):
		ept = '/sso/validate'
		print(f'[isLoggedIn] {self._url + ept}', flush=True)
		res = self._session.get(self._url + ept)

		print(f'[isLoggedIn] (1) {res.status_code} {res.text}', flush=True)
		if res.status_code == 200:
			data = res.json()
			print(f'[isLoggedIn] (2) {data}', flush=True)
			self._logged_in = True
			return { 'result': True }
		else:
			print(f'[isLoggedIn] (3)', flush=True)
			self._logged_in = False
			return { 'result': False }


	def _send_response(self, msg_id, res):
		res = {
			'msg_id': msg_id,
			'result': res
		}

		try:
			self.sio.emit(
				'broker_res', 
				res, 
				namespace='/broker'
			)
		except Exception:
			print(traceback.format_exc(), flush=True)


	def replace(self, user_id, strategy_id, broker_id):
		self.userId = user_id
		self.strategyId = strategy_id
		self.brokerId = broker_id


	def _download_historical_data_broker(self, 
		product, period, tz='Europe/London', 
		start=None, end=None, count=None,
		force_download=False
	):
		return


	def _get_all_positions(self, account_id):
		ept = f'/portfolio/{account_id}/positions/0'
		print(f'[_get_all_positions] {ept}', flush=True)
		res = self._session.get(self._url + ept)
		
		if res.status_code == 200:
			data = res.json()
			print(f'[_get_all_positions] {json.dumps(data, indent=2)}', flush=True)
			

			return {}
		else:
			res = { 'error': 'Error retrieving accounts.' }
			return res


	def createPosition(self,
		product, lotsize, direction,
		account_id, entry_range, entry_price,
		sl_range, tp_range, sl_price, tp_price
	):
		# EURUSD: 36163422

		payload = {
			'accountId': account_id,
			'ticker': 'EURUSD',
			'orderType': 'MKT',
			'side': 'BUY',
			'quantity': 1,
			'tif': 'GTC',
			'outsideRTH': True,
			# 'conid': 36163422,
			# 'secType': 'CASH',
		}

		ept = f'/iserver/account/{account_id}/order'
		print(f'[createPosition] {ept}', flush=True)
		res = self._session.post(self._url + ept)
		print(f'[createPosition] ({res.status_code}) {res.text}', flush=True)
		
		if res.status_code == 200:
			data = res.json()
			print(f'[createPosition] {json.dumps(data, indent=2)}', flush=True)

			return {}
		else:
			res = { 'error': 'Error retrieving accounts.' }
			return res


	def modifyPosition(self, pos, sl_price, tp_price):
		payload = {
			'accountId': account_id,
			'orderId': account_id,
			# 'conid': 36163422,
			'price': None,
			'quantity': None,
			'outsideRTH': True,
		}

		ept = f'/iserver/account/{account_id}/order/{order_id}'
		print(f'[modifyPosition] {ept}', flush=True)
		res = self._session.post(self._url + ept)
		
		if res.status_code == 200:
			data = res.json()
			print(f'[modifyPosition] {json.dumps(data, indent=2)}', flush=True)

			return {}
		else:
			res = { 'error': 'Error retrieving accounts.' }
			return res


	def deletePosition(self, pos, lotsize):
		payload = {
			'accountId': account_id,
			'orderId': account_id
		}

		ept = f'/iserver/account/{account_id}/order/{order_id}'
		print(f'[deletePosition] {ept}', flush=True)
		res = self._session.delete(self._url + ept)
		
		if res.status_code == 200:
			data = res.json()
			print(f'[deletePosition] {json.dumps(data, indent=2)}', flush=True)

			return {}
		else:
			res = { 'error': 'Error retrieving accounts.' }
			return res


	def _get_all_orders(self, account_id):
		return


	def authIServer(self, timeout=30):
		print('Authenticating IServer', flush=True)

		ept = '/iserver/reauthenticate?force=True'
		res = self._session.get(self._url + ept, timeout=5)

		ept = '/iserver/auth/status'
		start_time = time.time()
		while time.time() - start_time < timeout:
			res = self._session.get(self._url + ept)
			if res.status_code == 200:
				data = res.json()
				if data.get('authenticated'):
					self._iserver_auth = True
					print('Authenticating IServer Complete', flush=True)
					break
			time.sleep(1)


	def getAllAccounts(self):
		self.authIServer()

		ept = '/portfolio/accounts'
		print(f'[getAllAccounts] {self._url + ept}', flush=True)
		res = self._session.get(self._url + ept)
		print(f'[getAllAccounts] {res.status_code}, {res.text}', flush=True)
		
		if res.status_code == 200:
			data = res.json()
			print(f'[getAllAccounts] {json.dumps(data, indent=2)}', flush=True)
			# self.accounts = data['accounts']
			# self._selected_account = data['selectedAccount']
			res = { 'accounts': [] }
			for i in data:
				res['accounts'].append(i['id'])

			return res
		else:
			res = { 'error': 'Error retrieving accounts.' }
			return res


	def getAccountInfo(self, account_id):
		ept = f'/portfolio/{account_id}/summary'
		print(f'[getAccountInfo] {ept}', flush=True)
		res = self._session.get(self._url + ept)
		print(f'[getAccountInfo] {res.status_code} {res.text}', flush=True)
		
		if res.status_code == 200:
			data = res.json()
			# print(f'[getAccountInfo] {json.dumps(data, indent=2)}', flush=True)
			# res = { 'accounts': data['accounts'] }
			result = {
				account_id: {
					'currency': data['availablefunds']['currency'],
					'balance': data['fullavailablefunds']['amount'],
					'pl': 0,
					'margin': data['initmarginreq']['amount'],
					'available': data['availablefunds']['amount']
				}
			}

			return result
		else:
			res = { 'error': 'Error retrieving accounts.' }
			return res


	def createOrder(self, 
		product, lotsize, direction,
		account_id, order_type, entry_range, entry_price,
		sl_range, tp_range, sl_price, tp_price
	):
		payload = {
			'accountId': account_id,
			'ticker': 'EURUSD',
			'orderType': 'MKT',
			'side': 'BUY',
			'quantity': 1,
			'tif': 'GTC',
			'outsideRTH': True,
			# 'conid': 36163422,
			# 'secType': 'CASH',
		}

		ept = f'/iserver/account/{account_id}/order'
		print(f'[createOrder] {ept}', flush=True)
		res = self._session.post(self._url + ept)
		
		if res.status_code == 200:
			data = res.json()
			print(f'[createOrder] {json.dumps(data, indent=2)}', flush=True)
			

			return {}
		else:
			res = { 'error': 'Error retrieving accounts.' }
			return res


	def modifyOrder(self, order, lotsize, entry_price, sl_price, tp_price):
		payload = {
			'accountId': account_id,
			'orderId': account_id,
			# 'conid': 36163422,
			'price': None,
			'quantity': None,
			'outsideRTH': True,
		}

		ept = f'/iserver/account/{account_id}/order/{order_id}'
		print(f'[modifyOrder] {ept}', flush=True)
		res = self._session.post(self._url + ept)
		
		if res.status_code == 200:
			data = res.json()
			print(f'[modifyOrder] {json.dumps(data, indent=2)}', flush=True)
			

			return {}
		else:
			res = { 'error': 'Error retrieving accounts.' }
			return res


	def deleteOrder(self, order):
		payload = {
			'accountId': account_id,
			'orderId': account_id
		}

		ept = f'/iserver/account/{account_id}/order/{order_id}'
		print(f'[deleteOrder] {ept}', flush=True)
		res = self._session.delete(self._url + ept)
		
		if res.status_code == 200:
			data = res.json()
			print(f'[deleteOrder] {json.dumps(data, indent=2)}', flush=True)
			

			return {}
		else:
			res = { 'error': 'Error retrieving accounts.' }
			return res


	def _subscribe_gui_updates(self, msg_id):
		self._gui_subscriptions.append(Subscription(self, msg_id))
