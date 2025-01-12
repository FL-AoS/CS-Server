"""
Requires python >3.10
"""

from pyspades.constants import CTF_MODE, SPADE_TOOL
from pyspades.contained import PositionData
from pyspades.collision import distance_3d
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

BOMB_CODE = "7355608"
BOMB_PLANT_TIME = 3.5
BOMB_EXPLOSION_TIME = 40
BOMB_BEEP_DISTANCE = 40

BOMB_DEFUSE_WO_KIT = 10
BOMB_DEFUSE_W_KIT = 5

WAITING_PLAYER_MESSAGE_INTERVAL = 5
MAX_FIND_SPAWN_ATTEMPS = 10

async def game_loop(protocol):
	practice_countdown = PRACTICE_TIME
	freeze_time_countdown = FREEZE_TIME
	round_time_countdown = ROUND_TIME
	last_ts = 0

	bomb_message_ts = 0
	bomb_plant_code_index = 0
	defuse_message_ts = 0

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

				case 4:
					boom_time_left = floor(BOMB_EXPLOSION_TIME-(time()-protocol.planted_ts))

					if time()-bomb_message_ts >= 1: #TODO MAKE IT MORE CS2 LIKE, USING A GRAPH
						bomb_message_ts = time()

						if not boom_time_left%5 and boom_time_left>20:
							protocol.beep_near()
						elif not boom_time_left%2 and boom_time_left>8 and boom_time_left<20:
							protocol.beep_near()
						elif boom_time_left<=8:
							protocol.beep_near(True)

					if time()-protocol.planted_ts >= BOMB_EXPLOSION_TIME:
						protocol.game_state = 3
						protocol.broadcast_chat_warning("TR Won!")
						callLater(ROUND_END_TIME, protocol.handle_round_win, protocol.green_team)

						protocol.broadcast_chat_error("KABOOM")


			player_list = list(protocol.players.values())
			for player in player_list:
				if player is None:
					continue

				if player.world_object is None:
					continue

				if player.team.id != 0 and player.team.id != 1:
					continue

				x,y,z = player.world_object.position.get()

				match protocol.game_state:
					case 1:
						player.set_location(player.start_position)
					case 2:
						if player.team.other.flag.player is player:
							if protocol.planting is None:
								for bomb in protocol.bomb_sites:
									bx_min, bx_max = bomb[0]
									by_min, by_max = bomb[1]
									bz_min, bz_max = bomb[2]

									if (x >= bx_min and x <= bx_max) and (y >= by_min and y <= by_max) and (z >= bz_min and z <= bz_max):
										if time()-bomb_message_ts>=2:
											bomb_message_ts = time()
											bomb_plant_code_index = 0
											player.send_chat("Plant hitting the ground with spade")

							elif protocol.planting is player:
								if time()-protocol.planting_start_ts > BOMB_PLANT_TIME:
									protocol.game_state = 4
									protocol.planted_ts = time()

									protocol.planting = None
									bomb_plant_code_index = 0

									player.drop_flag()
									player.team.other.flag.set(*protocol.planting_pos)
									player.team.other.flag.update()

									protocol.broadcast_chat_error("BOMB HAS BEEN PLANTED!")

								if time()-bomb_message_ts >= BOMB_PLANT_TIME/len(BOMB_CODE) and bomb_plant_code_index < len(BOMB_CODE):
									bomb_message_ts = time()

									player.send_chat_warning(BOMB_CODE[:bomb_plant_code_index])
									bomb_plant_code_index += 1
					case 4:
						if protocol.defusing is None and player.team.id == protocol.blue_team.id:
							if time()-defuse_message_ts>=2 and distance_3d((x,y,z), protocol.planting_pos) <= 1:
								defuse_message_ts = time()
								bomb_plant_code_index = 0
								player.send_chat("Defuse hitting the ground with spade")

						elif protocol.defusing is player:
							# by default lets use with kit, when we implement the shop, we change it
							defuse_t = BOMB_DEFUSE_W_KIT

							if time()-protocol.defusing_start_ts > defuse_t:
								protocol.game_state = 3

								protocol.defusing = None
								protocol.broadcast_chat_error("BOMB HAS BEEN DEFUSED!")

								callLater(ROUND_END_TIME, protocol.handle_round_win, protocol.blue_team)

							if time()-defuse_message_ts >= defuse_t/len(BOMB_CODE) and bomb_plant_code_index < len(BOMB_CODE):
								defuse_message_ts = time()

								player.send_chat_warning(BOMB_CODE[:bomb_plant_code_index].ljust(len(BOMB_CODE), "*"))
								bomb_plant_code_index += 1

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

		planting = None
		planting_pos = None
		planting_start_ts = 0

		defusing = None
		defusing_start_ts = 0

		planted_ts = 0

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

		def broadcast_chat_error(self, message):
			player_l = list(self.players.values())
			for player in player_l:
				if player is None:
					continue

				if player.world_object is None:
					continue

				player.send_chat_error(message)

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
			if self.game_state != 2 and self.game_state != 4:
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

			if self.game_state == 4:
				return

			tr_dead_team = 0
			for tr in tr_players:
				if tr.world_object is None or tr.world_object.dead:
					tr_dead_team += 1

			if tr_dead_team == len(tr_players):
				self.game_state = 3
				self.broadcast_chat_warning("CT Won!")
				callLater(ROUND_END_TIME, self.handle_round_win, self.blue_team)

		def beep_near(self, beep_hard=False):
			for player in list(self.players.values()):
				if player.world_object is None:
					return

				b_x, b_y, b_z = self.planting_pos
				x, y, z = player.world_object.position.get()

				dx = abs(b_x-x)
				dy = abs(b_y-y)

				if dx < BOMB_BEEP_DISTANCE and dy < BOMB_BEEP_DISTANCE:
					if beep_hard:
						player.send_chat_error("BEEP")
					else:
						player.send_chat_warning("BEEP")

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

		def stop_bomb_planting(self):
			self.protocol.planting = None
			self.protocol.planting_pos = None

			self.send_chat("Stopped planting the bomb")

		def stop_bomb_defusing(self):
			self.protocol.defusing = None

			self.send_chat("Stopped defusing the bomb")

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

		def on_flag_take(self):
			if self.protocol.game_state != 2 and self.protocol.game_state != 1:
				return False

			return connection.on_flag_take(self)

		def on_kill(self, killer, _type, nade):
			if self.protocol.game_state == 2 or self.protocol.game_state == 4 and self.world_object is not None:
				self.world_object.dead = True
				self.protocol.handle_death()

			return connection.on_kill(self, killer, _type, nade)

		def on_disconnect(self):
			if self.protocol.game_state == 2 or self.protocol.game_state == 4:
				self.world_object.dead = True
				self.protocol.handle_death()

			return connection.on_disconnect(self)

		def on_position_update(self):
			if self.world_object is not None:
				if self.protocol.planting is self and self.protocol.game_state == 2:
					if distance_3d(self.world_object.position.get(), self.protocol.planting_pos) > 1:
						self.stop_bomb_planting()

				if self.protocol.defusing is self and self.protocol.game_state == 4:
					if distance_3d(self.world_object.position.get(), self.protocol.planting_pos) > 1:
						self.stop_bomb_defusing()

			return connection.on_position_update(self)

		def on_tool_changed(self, tool):
			if self.protocol.planting is self and self.protocol.game_state == 2:
				self.stop_bomb_planting()

			if self.protocol.defusing is self and self.protocol.game_state == 4:
				self.stop_bomb_defusing()

			return connection.on_tool_changed(self, tool)

		def on_shoot_set(self, shoot):
			if self.world_object is None or (self.protocol.game_state != 2 and self.protocol.game_state != 4):
				return connection.on_shoot_set(self, shoot)

			if not shoot:
				if self.protocol.planting is self:
					self.stop_bomb_planting()

				if self.protocol.defusing is self:
					self.stop_bomb_defusing()

			if shoot and self.tool == SPADE_TOOL:
				x,y,z = self.world_object.position.get()

				if self.protocol.game_state == 2 and self.team.id == self.protocol.green_team.id and self.team.other.flag.player is self:
					for bomb in self.protocol.bomb_sites:
						bx_min, bx_max = bomb[0]
						by_min, by_max = bomb[1]
						bz_min, bz_max = bomb[2]

						if (x >= bx_min and x <= bx_max) and (y >= by_min and y <= by_max) and (z >= bz_min and z <= bz_max):
							self.protocol.planting = self
							self.protocol.planting_pos = (x,y,z)
							self.protocol.planting_start_ts = time()

							self.send_chat("Planting the bomb...")

				if self.protocol.game_state == 4 and self.team.id == self.protocol.blue_team.id and self.protocol.defusing is None:
					if distance_3d(self.world_object.position.get(), self.protocol.planting_pos) <= 1:
						self.protocol.defusing = self
						self.protocol.defusing_start_ts = time()

						self.send_chat("Defusing the bomb...")

			return connection.on_shoot_set(self, shoot)


	return csProtocol, csConnection