"""
Requires python 3.10>
"""

from pyspades.constants import CTF_MODE
from pyspades.contained import PositionData
from time import time
from random import randint
import asyncio

PRACTICE_TIME = 30 # SECONDS
MINIMUM_PLAYERS = 2

SPAWN_RANGE = 5 # x+5 and x-5 = 10

WAITING_PLAYER_MESSAGE_INTERVAL = 5
MAX_FIND_SPAWN_ATTEMPS = 10

async def game_loop(protocol):
	practice_countdown = PRACTICE_TIME
	last_message = 0

	while True:
		try:
			match protocol.game_state:
				case 0:
					if not protocol.required_players() and time()-last_message>=WAITING_PLAYER_MESSAGE_INTERVAL:
						protocol.broadcast_chat_status("{}/{}".format(protocol.blue_team.count()+protocol.green_team.count(), MINIMUM_PLAYERS))
						protocol.broadcast_chat_status("Waiting for players...\n")
						last_message = time()

						if practice_countdown != PRACTICE_TIME:
							protocol.broadcast_chat("Not enough players to start, waiting more players...")
						practice_countdown = PRACTICE_TIME

					elif protocol.required_players() and time()-last_message >= 1:
						last_message = time()
						practice_countdown -= 1

						if practice_countdown > 5 and not practice_countdown%10:
							protocol.broadcast_chat_status("WARM UP")
							protocol.broadcast_chat_status("Game starting in: {} seconds".format((practice_countdown+PRACTICE_TIME)-PRACTICE_TIME))
						elif practice_countdown > 0 practice_countdown <= 5:
							protocol.broadcast_chat_status("WARM UP")
							protocol.broadcast_chat_status("Game starting in: {} seconds".format((practice_countdown+PRACTICE_TIME)-PRACTICE_TIME))
						elif practice_countdown <= 0:
							protocol.broadcast_chat("GAME STARTING!")
							protocol.game_state = 1

			player_list = list(protocol.players.values())
			for player in player_list:
				if player is None:
					continue

				if player.world_object is None:
					continue

				if player.team.id != 0 and player.team.id != 1:
					continue

		except Exception as e:
			print(e)

		await asyncio.sleep(0.001)

ev_loop = asyncio.get_event_loop()
def apply_script(protocol, connection, config):
	class csProtocol(protocol):
		game_mode = CTF_MODE

		"""
		-1 = map_change
		0 = warm up
		1 = freeze time
		2 = game running
		"""
		game_state = -1

		game_loop = None

		ct_spawn = None
		t_spawn = None

		def __init__(self, *args, **kwargs):
			if self.game_loop is None:
				self.game_loop = ev_loop.create_task(game_loop(self))

			return protocol.__init__(self, *args, **kwargs)

		def on_map_change(self, _map):
			self.game_state = -1

			ext = self.map_info.extensions
			self.ct_spawn = self.map_info.extensions["ct_spawn"]
			self.t_spawn = self.map_info.extensions["t_spawn"]

			return protocol.on_map_change(self, _map)

		def required_players(self):
			t1_c = self.blue_team.count()
			t2_c = self.green_team.count()

			if t1_c <= 0 or t2_c <= 0:
				return False

			if t1_c+t2_c >= MINIMUM_PLAYERS:
				return True

			return False

		def broadcast_chat_status(self, message):
			player_l = list(self.players.values())
			for player in player_l:
				if player is None:
					continue

				if player.world_object is None:
					continue

				player.send_chat_status(message)

	class csConnection(connection):
		start_position = (0,0,0)

		def on_team_join(self, team):
			if team.id != 0 and team.id != 1:
				return connection.on_team_join(self, team)

			if self.protocol.game_state > 0:
				return connection.on_team_join(self, team)
			
			self.protocol.game_state = 0	

			return connection.on_team_join(self, team)

		def find_spawn(self):
			x,y,z = self.protocol.ct_spawn

			if self.team.id == 1:
				x,y,z = self.protocol.t_spawn

			r_x = r_y = r_z = 0
			attemps = 0
			while True:
				if attemps >= MAX_FIND_SPAWN_ATTEMPS:
					break

				attemps += 1

				r_x = randint(x-SPAWN_RANGE, x+SPAWN_RANGE)
				r_y = randint(y-SPAWN_RANGE, y+SPAWN_RANGE)
				r_z = self.protocol.map.get_z(x,y,z-3)

				print(r_x, r_y, r_z, r_z-(z-3))

				if r_z-(z-3) > 8:
					continue

				if self.protocol.map.get_solid(r_x, r_y, r_z-3) or self.protocol.map.get_solid(r_x, r_y, r_z-2) or self.protocol.map.get_solid(r_x, r_y, r_z-1):
					continue

				break

			# magic number for not glitching
			self.start_position = (r_x, r_y, r_z-2.27)

		def on_spawn_location(self, pos):
			self.find_spawn()

			return self.start_position

		def set_position(self, x,y,z):
			pos_p = PositionData()
			pos_p.x = x
			pos_p.y = y
			pos_p.z = z

			self.send_contained(pos_p)
			self.world_object.set_position(x,y,z)

	return csProtocol, csConnection