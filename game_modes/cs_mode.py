"""
Requires python >3.10
"""

from pyspades.constants import CTF_MODE
from pyspades.contained import PositionData
from twisted.internet.reactor import callLater
from time import time
from random import randint, choice
from math import floor
import asyncio

PRACTICE_TIME = 5 # SECONDS
FREEZE_TIME = 5 # SECONDS
MINIMUM_PLAYERS = 2

ROUND_TIME = 120 # SECONDS
ROUND_END_TIME = 10

WIN_ROUNDS = 13

SPAWN_RANGE = 5 # x+5 and x-5 = 10

WAITING_PLAYER_MESSAGE_INTERVAL = 5
MAX_FIND_SPAWN_ATTEMPS = 10

async def game_loop(protocol):
	practice_countdown = PRACTICE_TIME
	freeze_time_countdown = FREEZE_TIME
	round_time_countdown = ROUND_TIME
	last_ts = 0

	while True:
		try:
			match protocol.game_state:
				case 0:
					if not protocol.required_players() and time()-last_ts>=WAITING_PLAYER_MESSAGE_INTERVAL:
						protocol.broadcast_chat_status("{}/{}".format(protocol.blue_team.count()+protocol.green_team.count(), MINIMUM_PLAYERS))
						protocol.broadcast_chat_status("Waiting for players...\n")
						last_ts = time()

						if practice_countdown != PRACTICE_TIME:
							protocol.broadcast_chat("Not enough players to start, waiting more players...")
						practice_countdown = PRACTICE_TIME+1

					elif protocol.required_players() and time()-last_ts >= 1:
						last_ts = time()
						practice_countdown -= 1

						if practice_countdown > 10 and not practice_countdown%10:
							protocol.broadcast_chat_status("WARM UP")
							protocol.broadcast_chat_status("Game starting in: {} seconds".format((practice_countdown+PRACTICE_TIME)-PRACTICE_TIME))
						elif practice_countdown > 0 and practice_countdown <= 10:
							protocol.broadcast_chat_status("WARM UP")
							protocol.broadcast_chat_status("Game starting in: {} seconds".format((practice_countdown+PRACTICE_TIME)-PRACTICE_TIME))
						elif practice_countdown <= 0:
							freeze_time_countdown = FREEZE_TIME
							protocol.broadcast_chat("GAME STARTING!")
							protocol.game_state = 1
							last_ts = 0
				case 1:
					if protocol.green_team.flag.player is None:
						choice(list(protocol.green_team.get_players())).take_flag()

					if time()-last_ts >= 1:
						freeze_time_countdown -= 1
						last_ts = time()

						protocol.broadcast_chat_status("FREEZE TIME")
						protocol.broadcast_chat_status("{} seconds".format((freeze_time_countdown+FREEZE_TIME)-FREEZE_TIME))

						if freeze_time_countdown <= 0:
							protocol.game_state = 2
							round_time_countdown = ROUND_TIME+1
							last_ts = 0

							blue_team_p = protocol.blue_team.score
							green_team_p = protocol.green_team.score

							protocol.broadcast_chat_status("ROUND STARTED")
							protocol.broadcast_chat_status("Blue {} - {} Green".format(blue_team_p, green_team_p))
				case 2:
					if time()-last_ts >= 1:
						last_ts = time()
						round_time_countdown -= 1

						secs = str(round_time_countdown%60)
						if len(secs) < 2:
							secs = "0"+secs

						mins = str(floor(round_time_countdown/60))
						if len(mins) < 2:
							mins = "0"+mins

						if round_time_countdown > 30 and not round_time_countdown%30:
							protocol.broadcast_chat_status("ROUND TIME")
							protocol.broadcast_chat_status(mins+":"+secs)
						elif round_time_countdown > 0 and round_time_countdown < 30:
							protocol.broadcast_chat_status("ROUND TIME")
							protocol.broadcast_chat_status(mins+":"+secs)
						elif round_time_countdown <= 0:
							protocol.game_state = 3
							protocol.handle_round_timeout()
				case 3:
					freeze_time_countdown = FREEZE_TIME
					last_ts = 0


			player_list = list(protocol.players.values())
			for player in player_list:
				if player is None:
					continue

				if player.world_object is None:
					continue

				if player.team.id != 0 and player.team.id != 1:
					continue

				match protocol.game_state:
					case 1:
						player.set_location(player.start_position)
					case 2:
						if player.team.other.flag.player is player:
							x,y,z = player.world_object.position.get()

							for bomb in protocol.bomb_sites:
								bx_min, bx_max = bomb[0]
								if not (x >= bx_min and x <= bx_max):
									continue

								by_min, by_max = bomb[1]
								if not (y >= by_min and y <= by_max):
									continue

								bz_min, bz_max = bomb[2]
								if not (z >= bz_min and z <= bz_max):
									continue

								if not protocol.planting and time()-protocol.bomb_message_ts>=2:
									protocol.bomb_message_ts = time()
									player.send_chat("Plant hitting the ground with spade")

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
		3 = round end
		4 = planted
		"""
		game_state = -1

		game_loop = None

		ct_spawn = None
		t_spawn = None
		bomb_sites = []

		bomb_message_ts = 0
		planting = False

		def __init__(self, *args, **kwargs):
			if self.game_loop is None:
				self.game_loop = ev_loop.create_task(game_loop(self))

			return protocol.__init__(self, *args, **kwargs)

		def on_flag_spawn(self, x,y,z,flag,entity_id):
			return (0,0,0)
		def on_base_spawn(self,x,y,z,base,entity_id):
			return (0,0,0)

		def on_map_change(self, _map):
			self.game_state = -1

			ext = self.map_info.extensions
			self.ct_spawn = self.map_info.extensions["ct_spawn"]
			self.t_spawn = self.map_info.extensions["t_spawn"]

			self.bomb_sites = self.map_info.extensions["bomb_sites"]

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

		def broadcast_chat_warning(self, message):
			player_l = list(self.players.values())
			for player in player_l:
				if player is None:
					continue

				if player.world_object is None:
					continue

				player.send_chat_warning(message)

		def handle_round_win(self, team):
			self.game_state = 1

			for player in list(self.players.values()):
				if player.world_object is None:
					continue
				if player.team.spectator:
					continue

				if player.world_object.dead:
					player.spawn((0,0,0))

				player.refill()

			if team is None:
				self.blue_team.score += 1
				team = self.blue_team
			else:
				MVP = choice(list(team.get_players()))
				MVP.take_flag()
				MVP.capture_flag()

		def handle_round_timeout(self):
			self.broadcast_chat_status("ROUND TIMEOUT")

			if self.blue_team.count() > 0:
				self.broadcast_chat_warning("CT Won!")
				callLater(ROUND_END_TIME, self.handle_round_win, self.blue_team)

			elif self.green_team.count() > 0:
				self.broadcast_chat_warning("TR Won!")
				callLater(ROUND_END_TIME, self.handle_round_win, self.green_team)

			else:
				callLater(ROUND_END_TIME, self.handle_round_win, None)

		def handle_death(self):
			if self.game_state != 2:
				return

			ct_players = list(self.blue_team.get_players())
			tr_players = list(self.green_team.get_players())

			ct_dead_team = 0
			for ct in ct_players:
				if ct.world_object is None or ct.world_object.dead:
					ct_dead_team += 1

			if ct_dead_team == len(ct_players):
				self.game_state = 3
				self.broadcast_chat_warning("TR Won!")
				callLater(ROUND_END_TIME, self.handle_round_win, self.green_team)

			tr_dead_team = 0
			for tr in tr_players:
				if tr.world_object is None or tr.world_object.dead:
					tr_dead_team += 1

			if tr_dead_team == len(tr_players):
				self.game_state = 3
				self.broadcast_chat_warning("CT Won!")
				callLater(ROUND_END_TIME, self.handle_round_win, self.blue_team)

	class csConnection(connection):
		start_position = (0,0,0)

		def on_spawn(self, pos):
			if self.protocol.game_state > 1:
				self.kill()

			return connection.on_spawn(self, pos)

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

				if r_z-(z-3) > 8:
					continue

				for pos in self.protocol.pos_table:
					if self.is_location_free(r_x + pos[0], r_y + pos[1], r_z + pos[2]):
						if not (r_x + pos[0] > x-SPAWN_RANGE and r_x + pos[0] < x+SPAWN_RANGE):
							continue

						if not (r_y + pos[1] > y-SPAWN_RANGE and r_y + pos[1] < y+SPAWN_RANGE):
							continue

						r_x = r_x + pos[0]
						r_y = r_y + pos[1]
						r_z = self.protocol.map.get_z(r_x, r_y, r_z)

				if (r_x > x-SPAWN_RANGE and r_x < x+SPAWN_RANGE) and (r_y > y-SPAWN_RANGE and r_y < y+SPAWN_RANGE):
					break

			# magic number for not glitching
			self.start_position = (r_x, r_y, r_z-2)

		def on_spawn_location(self, pos):
			self.find_spawn()

			return self.start_position

		def get_respawn_time(self):
			if self.protocol.game_state < 2:
				return 0
			else:
				return -1

		def respawn(self):
			if self.protocol.game_state > 1:
				return False

			return connection.respawn(self)

		def on_kill(self, killer, _type, nade):
			if self.protocol.game_state == 2 and self.world_object is not None:
				self.world_object.dead = True
				self.protocol.handle_death()

			return connection.on_kill(self, killer, _type, nade)

		def on_disconnect(self):
			if self.protocol.game_state == 2:
				self.world_object.dead = True
				self.protocol.handle_death()

			return connection.on_disconnect(self)

	return csProtocol, csConnection