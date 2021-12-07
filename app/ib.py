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
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.firefox.firefox_binary import FirefoxBinary
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from . import tradelib as tl
from threading import Thread
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GATEWAY_RUN_DIR = os.path.join(ROOT_DIR, 'clientportal.gw/bin/run.sh')
GATEWAY_CONFIG_DIR = os.path.join(ROOT_DIR, 'clientportal.gw/root/conf.yaml')
CHROME_DRIVER_DIR = os.path.join(ROOT_DIR, 'chromedriver_linux64/chromedriver')
FIREFOX_BINARY_DIR = os.path.join(ROOT_DIR, '/usr/bin/firefox/firefox')
FIREFOX_DRIVER_DIR = os.path.join(ROOT_DIR, 'geckodriver-v0.30.0-linux64/geckodriver')


class Subscription(object):

	def __init__(self, broker, msg_id):
		self.broker = broker
		self.msg_id = msg_id


	def onUpdate(self, *args):
		print(f'ON UPDATE: {args}', flush=True)

		self.broker.container.send_queue.append({
			"type": "account",
			"message": {
				"msg_id": self.msg_id,
				"result": {
					"args": args,
					"kwargs": {}
				}
			}
		})


class IB(object):

	def __init__(self, port, user_id, strategy_id, broker_id, username, password):
		print(f'IB INIT: {port}, {user_id}, {username}, {password}', flush=True)

		self.port = port

		self.userId = user_id
		self.strategyId = strategy_id
		self.brokerId = broker_id
		self.username = username
		self.password = password

		self._url = f'https://localhost:{self.port}/v1/api'
		self._session = requests.session()
		self.accounts = []

		self._gui_subscriptions = []

		self._is_gateway_loaded = False
		self._logged_in = False
		self._iserver_auth = False
		self._selected_account = None

		self._start_gateway()
		self._create_webdriver()
		self.standardReconnect()

		# if self.port != '5000':
		t = Thread(target=self._periodic_check)
		t.start()


	def _periodic_check(self):
		c_time = time.time()
		relogin_time = time.time()
		reauth_time = time.time()
		while True:
			if time.time() - c_time >= 10:
				c_time = time.time()
				if time.time() - relogin_time >= 60*60:
					relogin_time = time.time()
					print("[_periodic_check] RELOGGING IN...", flush=True)
					self.standardReconnect()

				res = requests.get(self._url + "/sso/validate", verify=False)
				if res.status_code == 200:
					data = res.json()
					print(f"[_periodic_check] {time.time()} ({res.status_code}) {data}\n", flush=True)

				res = requests.post(self._url + "/tickle", verify=False)
				if res.status_code == 200:
					data = res.json()
					print(f"[_periodic_check] {time.time()} ({res.status_code}) {data}\n", flush=True)
					try:
						if (time.time() - reauth_time >= 60*20 or 
							not data["iserver"]["authStatus"]["authenticated"] or 
							data["iserver"]["authStatus"]["competing"]):

							reauth_time = time.time()
							if data["iserver"]["authStatus"]["competing"]:
								self.restartReconnect()
							else:
								self.standardReconnect()

					except Exception:
						print(f"[_periodic_check] {traceback.format_exc()}\n", flush=True)
						
				elif res.status_code == 401:
					c_time = time.time() - 31
					print(f"[_periodic_check] {time.time()} ({res.status_code}) Unauthorized\n", flush=True)
					self.standardReconnect()
				else:
					c_time = time.time() - 31
					print(f"[_periodic_check] {time.time()} ({res.status_code}) Failed\n", flush=True)


	def standardReconnect(self):
		print(f"[standardReconnect] {time.time()}", flush=True)
		self.login()
		# res = requests.post(self._url + "/iserver/reauthenticate", verify=False)
		res = requests.get(self._url + "/sso/validate", verify=False)
		print(f"[standardReconnect] ({res.status_code}) Validate. {res.json()}\n", flush=True)
		requests.post(self._url + "/iserver/reauthenticate", verify=False)
		if res.status_code == 200:
			checks = 0
			time.sleep(1)
			res = requests.post(self._url + "/iserver/auth/status", verify=False)
			while not res.json()["authenticated"]:
				print(f"[standardReconnect] ({res.status_code}) Reauthenticated. {res.json()}\n", flush=True)

				if checks >= 5:
					print(f"[standardReconnect] Not Authenticated!.\n", flush=True)
					return

				checks += 1
				time.sleep(1)
				res = requests.post(self._url + "/iserver/auth/status", verify=False)
			
			print(f"[standardReconnect] Authenticated!.\n", flush=True)


	def restartReconnect(self):
		print(f"[restartReconnect] {time.time()}", flush=True)
		res = requests.post(self._url + "/logout", verify=False)
		self._stop_gateway()
		self._start_gateway()
		self.standardReconnect()



	# def _periodic_check(self):
	# 	try:
	# 		while True:
	# 			print(f'[_periodic_check] ({self.port}) {time.time()}', flush=True)
	# 			if not self._logged_in:
	# 				try:
	# 					ept = '/sso/validate'
	# 					res = self._session.get(self._url + ept, timeout=2)
	# 					if res.status_code < 500:
	# 						if not self._is_gateway_loaded:
	# 							print(f'[CHECK] ({self.port}) Gateway loaded. To Login: https://ib.algowolf.com:{self.port}/', flush=True)
	# 							self._is_gateway_loaded = True
	# 							# Send gateway loaded message
	# 							for sub in self._gui_subscriptions:
	# 								sub.onUpdate('gateway_loaded')

	# 						if res.status_code == 200:
	# 							if not self._logged_in:
	# 								print(f'[CHECK] ({self.port}) Logged in.', flush=True)
	# 								self._logged_in = True
	# 								# Send logged in message
	# 								for sub in self._gui_subscriptions:
	# 									sub.onUpdate('logged_in')

	# 				except Exception:
	# 					print(traceback.format_exc(), flush=True)

	# 				time.sleep(1)
	# 			else:
	# 				try:
	# 					print(f'[Tickle] {time.time()}', flush=True)
	# 					ept = '/sso/validate'
	# 					res = self._session.get(self._url + ept, timeout=5)
	# 					print(f'[Validate] {res.status_code}', flush=True)
	# 					ept = '/tickle'
	# 					res = self._session.post(self._url + ept, timeout=5)
	# 					print(f'[Tickle] {res.status_code}', flush=True)

	# 					if res.status_code == 200:
	# 						ept = '/iserver/auth/status'
	# 						res = self._session.post(self._url + ept, timeout=5)
	# 						if res.status_code == 200:
	# 							data = res.json()
	# 							print(f'{json.dumps(data, indent=2)}', flush=True)
	# 							if not data.get('authenticated'):
	# 								self._iserver_auth = False
	# 								self.authIServer(timeout=0)
	# 							else:
	# 								self._iserver_auth = True

	# 					if self._iserver_auth:
	# 						ept = '/iserver/account/orders'
	# 						res = self._session.get(self._url + ept, timeout=5)
	# 						print(f'[iserver] {res.status_code}, {res.text}', flush=True)

	# 				except Exception:
	# 					print(traceback.format_exc(), flush=True)

	# 				time.sleep(10)

	# 	except Exception:
	# 		print(f'[_periodic_check] ({self.port}) {traceback.format_exc()}', flush=True)


	def _start_gateway(self):
		print(f'GATEWAY: {[ GATEWAY_RUN_DIR, GATEWAY_CONFIG_DIR, self.port ]}', flush=True)
		self._gateway_process = subprocess.Popen(
			[ GATEWAY_RUN_DIR, GATEWAY_CONFIG_DIR, str(self.port) ]
		)

		time.sleep(2)
		return { 'complete': True }


	def _stop_gateway(self):
		self._gateway_process.terminate()

		try:
			self._gateway_process.wait(timeout=5)
		except subprocess.TimeoutExpired as e:
			self._gateway_process.kill()


	def _create_webdriver(self):
		print("[_create_webdriver] Starting webdriver...", flush=True)
		chrome_options = Options()

		chrome_options.add_argument("--headless")
		chrome_options.add_argument('--ignore-certificate-errors')
		chrome_options.add_argument('--ignore-ssl-errors')
		chrome_options.add_argument("--no-sandbox")
		chrome_options.add_argument("--disable-dev-shm-usage")
		chrome_prefs = {}
		chrome_options.experimental_options["prefs"] = chrome_prefs
		chrome_prefs["profile.default_content_settings"] = {"images": 2}
		# chrome_options.add_argument("--remote-debugging-port=9222")

		self.driver = webdriver.Chrome(options=chrome_options)
		print(f"[_create_webdriver] DRIVER DONE {self.driver}", flush=True)

		# profile = webdriver.FirefoxProfile()
		# profile.accept_untrusted_certs = True

		# options = Options()
		# options.add_argument("--headless")

		# binary = FirefoxBinary(FIREFOX_BINARY_DIR)
		
		# self.driver = webdriver.Firefox(firefox_binary=FIREFOX_BINARY_DIR, executable_path=FIREFOX_DRIVER_DIR, options=options)
		# self.driver = webdriver.Remote(
        #    command_executor='http://selenium_hub:6000/wd/hub',
        #    desired_capabilities=DesiredCapabilities.CHROME, 
		#    options=chrome_options
		# )


	def login(self):

		print("[login] Logging in...", flush=True)
		start_url = f"https://localhost:{self.port}"
		self.driver.get(start_url)

		inputElement = self.driver.find_element_by_id("user_name")
		inputElement.send_keys(self.username)
		inputElement = self.driver.find_element_by_id("password")
		inputElement.send_keys(self.password)
		inputElement = self.driver.find_element_by_id("submitForm")
		inputElement.click()

		checks = 0
		while True:
			checks += 1
			pre_tags = self.driver.find_elements_by_css_selector('pre')
			if len(pre_tags):
				if pre_tags[0].get_attribute('innerHTML') == "Client login succeeds":
					print("[login] LOGGED IN", flush=True)
					break

			error_msg = self.driver.find_elements_by_id("ERRORMSG")
			if len(error_msg):
				if error_msg[0].get_attribute('innerHTML') == "Invalid username password combination":
					print(f"[login] FAILED TO LOGIN", flush=True)
					break

			if checks >= 5:
				return self.login()

			time.sleep(1)


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
