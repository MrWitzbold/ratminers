import pygame
import sys

pygame.init()

tile_size = 16

screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
screen_width, screen_height = screen.get_size()

map_width = screen_width // tile_size
map_height = screen_height // tile_size

clock = pygame.time.Clock()

tile_textures = {
	0: pygame.image.load('resources/img/block_air.png'),
	1: pygame.image.load('resources/img/block_dirt.png'),
	2: pygame.image.load('resources/img/block_stone.png')
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
		self.speed = 2
		self.on_ground = False
		self.gravity = 0.3
		self.jump_force = -6
		self.facing_right = True
		self.crouching = False
		self.rat_stand = pygame.image.load('resources/img/rat.png')
		self.rat_crouch = pygame.image.load('resources/img/crouched_rat.png')
	
	def update(self, keys):
		if keys[pygame.K_LEFT]:
			self.x -= self.speed
			self.facing_right = False
			
		if keys[pygame.K_RIGHT]:
			self.x += self.speed
			self.facing_right = True

		if keys[pygame.K_UP]:
			if self.crouching == True:
				self.crouching = False
			else:
				if self.on_ground:
					self.vel_y = self.jump_force
					self.on_ground = False
		
		if keys[pygame.K_DOWN]:
			self.crouching = True
		
		self.vel_y += self.gravity # gravity stops my up speed and starts fall speed
		self.y += self.vel_y # update my y with my speed
		
		if is_solid(self.x + 8, self.y + 31): # gets center bottom of rat
			self.y = ((self.y + 31) // tile_size) * tile_size - 32
			self.vel_y = 0
			self.on_ground = True
		else:
			self.on_ground = False
	
	def draw(self, screen):
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
			
		
rat = player(5 * tile_size, 5 * tile_size)

while True:
	for event in pygame.event.get():
		if event.type == pygame.QUIT:
			pygame.quit()
			sys.exit()
		
	keys = pygame.key.get_pressed()
	for y in range(map_height):
		for x in range(map_width):
			tile_id = world[y][x]
			tile = tile_textures[tile_id]
			screen.blit(tile, (x *tile_size, y * tile_size))

	rat.update(keys)
	rat.draw(screen)
	pygame.display.flip()
	clock.tick(60)