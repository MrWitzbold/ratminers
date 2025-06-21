import pygame
import sys

pygame.init()

pygame.mixer.init()
pygame.mixer.music.load('resources/sounds/music.mp3')
pygame.mixer.music.set_volume(1)
pygame.mixer.music.play(-1)

sounds = {
	'break': pygame.mixer.Sound('resources/sounds/break.mp3'),
	'crouch': pygame.mixer.Sound('resources/sounds/crouch.mp3'),
	'jump': pygame.mixer.Sound('resources/sounds/jump.mp3')
}

for sound in sounds.values():
	sound.set_volume(1.5)

tile_size = 16

screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
screen_width, screen_height = screen.get_size()

map_width = screen_width // tile_size
map_height = screen_height // tile_size

clock = pygame.time.Clock()

tile_textures = {
	0: pygame.image.load('resources/img/block_air2.png'),
	1: pygame.image.load('resources/img/block_dirt.png'),
	2: pygame.image.load('resources/img/block_stone.png')
}

item_defs = {
	1: {
		'name': "Wooden pickaxe",
		'image': pygame.image.load('resources/img/pick.png'),
		'can_break': True
	}
}

world = []

def is_solid(x, y):
	grid_x = int(x // tile_size)
	grid_y = int(y // tile_size)
	return world[grid_y][grid_x] != 0

for y in range(map_height):
	layer = []
	for x in range(map_width):
		if y < 20:
			layer.append(0)
		elif y <= 30:
			layer.append(1)
		else:
			layer.append(2)
	world.append(layer)
	
class player:
	def __init__(self, x, y):
		self.x = x
		self.y = y
		self.vel_y = 0
		self.speed = 7
		self.on_ground = False
		self.gravity = 0.3
		self.jump_force = -6
		self.facing_right = True
		self.crouching = False
		self.rat_stand = pygame.image.load('resources/img/rat.png')
		self.rat_crouch = pygame.image.load('resources/img/crouched_rat.png')
		self.inventory = [
			{'id': 1, 'amount': 1}, None, None, None, None, None, None, None, None, None, None
		]
		self.invslot = pygame.image.load('resources/img/empty_inv.png')
		self.selectedslot = pygame.image.load('resources/img/selected_inv.png')
		self.selectedslot_id = 0
	
	def update(self, keys, mouse_buttons):
		if keys[pygame.K_LEFT]:
			newx = self.x - self.speed
			checkheight = 8
			if self.crouching:
				checkheight = 16
			if not is_solid(newx - 16, self.y + checkheight):
				self.x = newx
			self.facing_right = False
			
		if keys[pygame.K_RIGHT]:
			newx = self.x + self.speed
			checkheight = 8
			if self.crouching:
				checkheight = 16
			if not is_solid(newx + 16, self.y + checkheight):
				self.x = newx
			self.facing_right = True

		if event.type == pygame.KEYDOWN:
			if keys[pygame.K_UP]:
				if self.crouching == True:
					if is_solid(self.x + 8, self.y) == False:
						self.crouching = False
				else:
					if self.on_ground:
						self.vel_y = self.jump_force
						self.on_ground = False
						sounds['jump'].play()
						
		if event.type == pygame.KEYDOWN:
			if keys[pygame.K_DOWN] and self.crouching == False:
				self.crouching = True
				sounds['crouch'].play()
		
		if keys[pygame.K_1]:
			self.selectedslot_id = 0
		if keys[pygame.K_2]:
			self.selectedslot_id = 1
		if keys[pygame.K_3]:
			self.selectedslot_id = 2
		if keys[pygame.K_4]:
			self.selectedslot_id = 3
		if keys[pygame.K_5]:
			self.selectedslot_id = 4
		if keys[pygame.K_6]:
			self.selectedslot_id = 5
		if keys[pygame.K_7]:
			self.selectedslot_id = 6
		if keys[pygame.K_8]:
			self.selectedslot_id = 7
		if keys[pygame.K_9]:
			self.selectedslot_id = 8
		if keys[pygame.K_0]:
			self.selectedslot_id = 9
		
		# breaking blocks *-*
		if mouse_buttons[0]:
			held_item = self.inventory[self.selectedslot_id]
			if held_item and item_defs[held_item['id']]['can_break'] == True:
				mouse_x, mouse_y = pygame.mouse.get_pos()
				target_x = mouse_x // tile_size
				target_y = mouse_y // tile_size
				player_tilex = (self.x+8) // tile_size
				player_tiley = (self.y+16) // tile_size
				
				distx = abs(player_tilex - target_x)
				disty = abs(player_tiley - target_y)
				
				if 0 <= target_x < map_width and 0 <= target_y < map_width:
					block_id = world[target_y][target_x]
					if block_id != 0 and (distx <= 6 and disty <= 5):
						world[target_y][target_x] = 0
						sounds['break'].play()
		
		self.vel_y += self.gravity
		new_y = self.y + self.vel_y

		if self.vel_y > 0:  # Falling
			if is_solid(self.x + 8, new_y + 31):
				self.y = ((new_y + 31) // tile_size) * tile_size - 32
				self.vel_y = 0
				self.on_ground = True
			else:
				self.y = new_y
				self.on_ground = False
		elif self.vel_y < 0:  # Jumping
			if is_solid(self.x + 8, new_y):
				self.vel_y = 0  # bumping into ceiling
			else:
				self.y = new_y
	
	def draw_plr(self, screen):
		img = self.rat_stand
		draw_y = self.y
		if self.crouching:
			img = self.rat_crouch
			draw_y = self.y + 16
		if self.facing_right:
			screen.blit(img, (self.x, draw_y))
		else:
			flipped = pygame.transform.flip(img, True, False)
			screen.blit(flipped, (self.x, draw_y))
		# drawing the items logic
		held_item = self.inventory[self.selectedslot_id]
		if held_item:
			# draw in cursor
			pygame.mouse.set_visible(False)
			mouse_x, mouse_y = pygame.mouse.get_pos()
			held_item = rat.inventory[rat.selectedslot_id]
			if held_item:
				item_id = held_item['id']
				item_img = pygame.transform.scale(item_defs[item_id]['image'], (16, 16))
				screen.blit(item_img, (mouse_x, mouse_y))
			# draw in hand
			item_id = held_item['id']
			item_img = pygame.transform.scale(item_defs[item_id]['image'], (16, 16))
			offset_x = 0
			if self.facing_right:
				offset_x = 12
			else:
				offset_x = -4
			offset_x = 12 if self.facing_right else -4
			offset_y = 8
			item_x = self.x + offset_x
			item_y = draw_y + offset_y
			
			if self.facing_right:
				screen.blit(item_img, (item_x, item_y))
			else:
				flipped_item = pygame.transform.flip(item_img, True, False)
				screen.blit(flipped_item, (item_x, item_y))
		else:
			pygame.mouse.set_visible(True)
	
	def draw_inv(self, screen):
		for i, slot in enumerate(self.inventory):
			img = pygame.transform.scale(self.invslot, (64, 64))
			if i == self.selectedslot_id:
				img = pygame.transform.scale(self.selectedslot, (64, 64))
			screen.blit(img, (i*64, 0))
			
			if slot:
				item_id = slot['id']
				item_img = pygame.transform.scale(item_defs[item_id]['image'], (64, 64))
				screen.blit(item_img, (i*64, 0))
				
				font = pygame.font.SysFont(None, 24)
				count_text = font.render(str(slot['amount']), True, (255, 255, 255))
				screen.blit(count_text, (i*64 + 48, 48))
	
rat = player(5 * tile_size, 5 * tile_size)

while True:
	for event in pygame.event.get():
		if event.type == pygame.QUIT:
			pygame.quit()
			sys.exit()
		
	keys = pygame.key.get_pressed()
	mouse_buttons = pygame.mouse.get_pressed()
	
	for y in range(map_height):
		for x in range(map_width):
			tile_id = world[y][x]
			tile = tile_textures[tile_id]
			screen.blit(tile, (x *tile_size, y * tile_size))

	rat.update(keys, mouse_buttons)
	rat.draw_plr(screen)
	rat.draw_inv(screen)
	pygame.display.flip()
	clock.tick(60)