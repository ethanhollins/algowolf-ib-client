import sys
import os
import json
import time
import zmq
import traceback
import shortuuid
from threading import Thread
from app.ib import IB

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

'''
Utilities
'''
class UserContainer(object):

	def __init__(self):
		self.parent = None
		self.users = {}
		self.add_user_queue = []
		self.send_queue = []
		self.zmq_context = zmq.Context()
		self.next_port = 5000

	def setParent(self, parent):
		self.parent = parent


	def getParent(self):
		return self.parent


	def addUser(self, port, user_id, strategy_id, broker_id, username, password, is_parent):
		if broker_id not in self.users:
			self.users[broker_id] = IB(port, user_id, strategy_id, broker_id, username, password)
			if is_parent:
				self.parent = self.users[broker_id]

		return self.users[broker_id]


	def deleteUser(self, broker_id):
		if broker_id in self.users:
			self.users[broker_id].stop()
			del self.users[broker_id]


	def getUser(self, broker_id):
		return self.users.get(broker_id)


	def replaceUser(self, port, user_id, strategy_id, broker_id):
		user = self.getUser(broker_id)
		if user is not None:
			user.replace(user_id, strategy_id, broker_id)

	def findUser(self, user_id, strategy_id, broker_id):
		for broker_id in self.users:
			user = self.users[broker_id]
			if (
				user.userId == user_id and
				user.strategyId == strategy_id and
				user.brokerId == broker_id and
				user._logged_in
			):
				return broker_id

		return -1

	def addToUserQueue(self):
		_id = shortuuid.uuid()
		self.add_user_queue.append(_id)
		while self.add_user_queue[0] != _id:
			time.sleep(0.1)


	def popUserQueue(self):
		del self.add_user_queue[0]


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
user_container = UserContainer()

'''
Socket IO functions
'''

def sendResponse(msg_id, res):
	res = {
		"type": "broker_reply",
		"message": {
			'msg_id': msg_id,
			'result': res
		}
	}

	user_container.send_queue.append(res)


def onAddUser(user_id, strategy_id, broker_id, username, password, is_parent):
	user_container.addToUserQueue()
	try:
		if broker_id not in user_container.users:
			user = user_container.addUser(str(user_container.next_port), user_id, strategy_id, broker_id, username, password, is_parent)
			user_container.next_port += 1
		else:
			user = user_container.getUser(broker_id)
	
	except Exception:
		print(traceback.format_exc())
	finally:
		user_container.popUserQueue()

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


def onCommand(data):
	print(f'COMMAND: {data}', flush=True)

	try:
		cmd = data.get('cmd')
		broker = data.get('broker')
		broker_id = data.get('broker_id')

		if broker_id is None:
			user = getParent()
		else:
			user = getUser(broker_id)

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


def send_loop():
	user_container.zmq_req_socket = user_container.zmq_context.socket(zmq.DEALER)
	user_container.zmq_req_socket.connect("tcp://zmq_broker:5557")

	while True:
		try:
			if len(user_container.send_queue):
				item = user_container.send_queue[0]
				del user_container.send_queue[0]

				user_container.zmq_req_socket.send_json(item, zmq.NOBLOCK)

		except Exception:
			print(traceback.format_exc())

		time.sleep(0.001)


def run():
	user_container.zmq_pull_socket = user_container.zmq_context.socket(zmq.PULL)
	user_container.zmq_pull_socket.connect("tcp://zmq_broker:5564")

	user_container.zmq_poller = zmq.Poller()
	user_container.zmq_poller.register(user_container.zmq_pull_socket, zmq.POLLIN)

	while True:
		socks = dict(user_container.zmq_poller.poll())

		if user_container.zmq_pull_socket in socks:
			message = user_container.zmq_pull_socket.recv_json()
			print(f"[ZMQ_PULL] {message}")
			onCommand(message)


if __name__ == '__main__':
	print("START IB", flush=True)
	Thread(target=send_loop).start()
	run()
