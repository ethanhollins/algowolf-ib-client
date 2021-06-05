import sys
import socketio
import os
import json
import time
import traceback
from app.ib import IB

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

'''
Utilities
'''
class UserContainer(object):

	def __init__(self, sio):
		self.sio = sio
		self.parent = None
		self.users = {}

	def setParent(self, parent):
		self.parent = parent


	def getParent(self):
		return self.parent


	def addUser(self, port, user_id, strategy_id, broker_id, is_parent):
		if port not in self.users:
			self.users[port] = IB(self.sio, port, user_id, strategy_id, broker_id)
			if is_parent:
				self.parent = self.users[port]

		return self.users[port]


	def deleteUser(self, port):
		if port in self.users:
			self.users[port].stop()
			del self.users[port]


	def getUser(self, port):
		return self.users.get(port)


	def replaceUser(self, port, user_id, strategy_id, broker_id):
		user = self.getUser(port)
		if user is not None:
			user.replace(user_id, strategy_id, broker_id)

	def findUser(self, user_id, strategy_id, broker_id):
		for port in self.users:
			user = self.users[port]
			if (
				user.userId == user_id and
				user.strategyId == strategy_id and
				user.brokerId == broker_id and
				user._logged_in
			):
				return port

		return -1


def getConfig():
	path = os.path.join(ROOT_DIR, 'instance/config.json')
	if os.path.exists(path):
		with open(path, 'r') as f:
			return json.load(f)
	else:
		raise Exception('Config file does not exist.')


'''
Initialize
'''

config = getConfig()
sio = socketio.Client(reconnection=False)
user_container = UserContainer(sio)

'''
Socket IO functions
'''

def sendResponse(msg_id, res):
	res = {
		'msg_id': msg_id,
		'result': res
	}

	sio.emit(
		'broker_res', 
		res, 
		namespace='/broker'
	)


def onAddUser(port, user_id, strategy_id, broker_id, is_parent):
	user = user_container.addUser(str(port), user_id, strategy_id, broker_id, is_parent)
	return {
		'_gateway_loaded': user._is_gateway_loaded
	}


def onDeleteUser(port):
	user_container.deleteUser(port)

	return {
		'completed': True
	}


def onReplaceUser(port, user_id, strategy_id, broker_id):
	user_container.replaceUser(port, user_id, strategy_id, broker_id)

	return {
		'completed': True
	}


def onFindUser(user_id, strategy_id, broker_id):
	port = user_container.findUser(user_id, strategy_id, broker_id)

	return {
		'port': port
	}


def getExistingUsers():
	for port in user_container.users:
		pass


def getUser(port):
	return user_container.getUser(port)


def getParent():
	return user_container.getParent()


def findUnusedPort(used_ports):
	print(f'[findUnusedPort] {used_ports}', flush=True)

	max_port = 5000
	for port in user_container.users:
		if port != str(5000):
			if int(port) > max_port:
				max_port = int(port)
			if not port in used_ports:
				if not user_container.users[port].isLoggedIn().get('result'):
					print(f'[findUnusedPort] {port}', flush=True)
					return { 'result': port }

	print(f'[findUnusedPort] {max_port+1}', flush=True)

	return { 'result': max_port+1 }


# Download Historical Data EPT
def _download_historical_data_broker( 
	user, product, period, tz='Europe/London', 
	start=None, end=None, count=None,
	include_current=True,
	**kwargs
):
	return user._download_historical_data_broker(
		product, period, tz='Europe/London', 
		start=start, end=end, count=count,
		**kwargs
	)


def _subscribe_chart_updates(user, msg_id, instrument):
	user._subscribe_chart_updates(msg_id, instrument)
	return {
		'completed': True
	}


# Create Position EPT

# Modify Position EPT

# Delete Position EPT

# Create Order EPT

# Modify Order EPT

# Delete Order EPT

# Get Account Details EPT

# Get All Accounts EPT

def reconnect():
	while True:
		try:
			sio.connect(
				config['STREAM_URL'], 
				headers={
					'Broker': 'ib'
				}, 
				namespaces=['/broker']
			)
			break
		except Exception:
			pass
	print('RECONNECTED!', flush=True)


@sio.on('connect', namespace='/broker')
def onConnect():
	print('CONNECTED!', flush=True)


@sio.on('disconnect', namespace='/broker')
def onDisconnect():
	print('DISCONNECTED', flush=True)
	reconnect()


@sio.on('broker_cmd', namespace='/broker')
def onCommand(data):
	print(f'COMMAND: {data}', flush=True)

	try:
		cmd = data.get('cmd')
		broker = data.get('broker')
		port = None
		if len(data.get('args')):
			port = str(data.get('args')[0])

		user = getUser(port)

		if broker == 'ib':
			res = {}
			if cmd == 'add_user':
				res = onAddUser(*data.get('args'), **data.get('kwargs'))

			elif cmd == 'delete_user':
				res = onDeleteUser(*data.get('args'), **data.get('kwargs'))

			elif cmd == 'replace_user':
				res = onReplaceUser(*data.get('args'), **data.get('kwargs'))

			elif cmd == 'find_user':
				res = onFindUser(*data.get('args'), **data.get('kwargs'))

			elif cmd == 'get_existing_users':
				res = getExistingUsers(*data.get('args'), **data.get('kwargs'))

			elif cmd == 'isLoggedIn':
				res = user.isLoggedIn()

			elif cmd == 'findUnusedPort':
				res = findUnusedPort(*data.get('args'), **data.get('kwargs'))

			elif cmd == '_start_gateway':
				res = user._start_gateway()

			elif cmd == 'getAllAccounts':
				res = user.getAllAccounts()

			elif cmd == 'getAccountInfo':
				res = user.getAccountInfo(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == '_subscribe_gui_updates':
				res = user._subscribe_gui_updates(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == '_get_all_positions':
				res = user._get_all_positions(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == '_get_all_orders':
				res = user._get_all_orders(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == 'createPosition':
				res = user.createPosition(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == 'modifyPosition':
				res = user.modifyPosition(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == 'deletePosition':
				res = user.deletePosition(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == 'getAllAccounts':
				res = user.getAllAccounts(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == 'getAccountInfo':
				res = user.getAccountInfo(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == 'createOrder':
				res = user.createOrder(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == 'modifyOrder':
				res = user.modifyOrder(*data.get('args')[1:], **data.get('kwargs'))

			elif cmd == 'deleteOrder':
				res = user.deleteOrder(*data.get('args')[1:], **data.get('kwargs'))

			sendResponse(data.get('msg_id'), res)

	except Exception as e:
		print(traceback.format_exc(), flush=True)
		sendResponse(data.get('msg_id'), {
			'error': str(e)
		})


def createApp():
	print('CREATING APP')
	while True:
		try:
			sio.connect(
				config['STREAM_URL'], 
				headers={
					'Broker': 'ib'
				}, 
				namespaces=['/broker']
			)
			break
		except Exception:
			pass

	return sio


if __name__ == '__main__':
	sio = createApp()
	print('DONE')
