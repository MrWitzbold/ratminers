"""
Rat Game -- single file sandbox platformer.

Controls
--------
A / D  or  Left / Right : move
W / Up / Space          : jump
S / Down                : crouch (hold)
1..0  or  mouse wheel   : select hotbar slot
Left mouse button       : mine (hold)
Right mouse button      : place selected block
Q                       : drop selected item
E / Tab                 : toggle inventory + crafting
Ctrl + S                : save the game
ESC                     : close inventory, or quit

In the inventory:
  left click   -- pick up a stack / place it / swap / craft
  right click  -- split a stack in half (larger half follows the cursor),
                  or place one item at a time, or craft

Drops within 6 tiles of the player are vacuumed up after 6 continuous
seconds inside that radius; touching one directly still picks it up almost
instantly.
"""

import json
import math
import os
import random
import sys

import pygame

# =============================================================================
# CONFIG
# =============================================================================
TILE_SIZE = 16
FPS = 60

PLAYER_WIDTH = 16
PLAYER_HEIGHT = 32
PLAYER_CROUCH_HEIGHT = 16
PLAYER_SPEED = 2.5
PLAYER_GRAVITY = 0.3
PLAYER_JUMP_FORCE = -6.0
PLAYER_MAX_FALL_SPEED = 20.0
PLAYER_STEP_HEIGHT = TILE_SIZE

COLLISION_SUBSTEP = 4.0

REACH_X = 6.0
REACH_Y = 5.0

STACK_SIZE = 64
HOTBAR_SIZE = 10
BACKPACK_SIZE = 30

SLOT_SIZE = 24

ASSET_DIR = "resources"
IMAGE_DIR = f"{ASSET_DIR}/img"
SOUND_DIR = f"{ASSET_DIR}/sounds"

SKY_COLOR = (24, 26, 34)
LETTERBOX_COLOR = (0, 0, 0)

TARGET_LOGICAL_HEIGHT = 320

WORLD_TILES_W = 200
WORLD_TILES_H = 100

CAMERA_LERP_X = 0.20
CAMERA_LERP_Y = 0.12
CAMERA_Y_ANCHOR = 0.6

TREE_MIN_SPACING = 8
TREE_MAX_SPACING = 14
TREE_FIRST_MIN = 10
TREE_FIRST_MAX = 14
TREE_MIN_HEIGHT = 4
TREE_MAX_HEIGHT = 7
TREE_MIN_CANOPY = 2
TREE_MAX_CANOPY = 3

IRON_VEIN_CHANCE = 0.015
IRON_VEIN_MIN = 2
IRON_VEIN_MAX = 6
IRON_ORE_MIN_Y = 22

EMERALD_VEIN_CHANCE = 0.0008
EMERALD_VEIN_MIN = 1
EMERALD_VEIN_MAX = 3
EMERALD_ORE_MIN_Y = 35
EMERALD_MIN = 15

BREAK_SOUND_COOLDOWN_MS = 40

# Pickup behaviour
PICKUP_CONTACT_RADIUS = 24          # instant pickup within this radius
PICKUP_CONTACT_DELAY = 0.35         # seconds after drop before instant pickup
PICKUP_VACUUM_RADIUS = TILE_SIZE * 6
PICKUP_VACUUM_TIME = 6.0            # seconds in radius before auto-pickup

# Save / load
SAVE_PATH = "savegame.json"
SAVE_MESSAGE_DURATION = 3.0


# =============================================================================
# ASSETS
# =============================================================================
TILE_TEXTURES = {}
TILE_DEFS = {}
ITEM_DEFS = {}
IMAGES = {}
SOUNDS = {}


class _NullSound:
    def play(self, *args, **kwargs):
        pass

    def set_volume(self, volume):
        pass


def _load_image(filename, size=None):
    path = f"{IMAGE_DIR}/{filename}"
    try:
        image = pygame.image.load(path)
    except pygame.error as exc:
        raise SystemExit(f"Could not load image '{path}': {exc}") from exc
    image = image.convert_alpha()
    if size is not None:
        image = pygame.transform.scale(image, size)
    return image


def _load_sound(filename):
    path = f"{SOUND_DIR}/{filename}"
    try:
        return pygame.mixer.Sound(path)
    except pygame.error as exc:
        print(f"warning: could not load sound '{path}': {exc}")
        return _NullSound()


def _play(name):
    sound = SOUNDS.get(name)
    if sound is not None:
        sound.play()


def load_assets():
    try:
        pygame.mixer.init()
    except pygame.error as exc:
        print(f"warning: no audio device ({exc})")

    if pygame.mixer.get_init() is None:
        for name in ("break", "crouch", "jump"):
            SOUNDS[name] = _NullSound()
    else:
        for name in ("break", "crouch", "jump"):
            SOUNDS[name] = _load_sound(f"{name}.mp3")
            SOUNDS[name].set_volume(1.0)
            SOUNDS["break"].set_volume(30.0)
        try:
            pygame.mixer.music.load(f"{SOUND_DIR}/music.mp3")
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.play(-1)
        except pygame.error as exc:
            print(f"warning: could not play music: {exc}")

    TILE_TEXTURES.clear()
    TILE_TEXTURES.update({
        1: _load_image("block_dirt.png", (TILE_SIZE, TILE_SIZE)),
        2: _load_image("block_stone.png", (TILE_SIZE, TILE_SIZE)),
        3: _load_image("block_oak.png", (TILE_SIZE, TILE_SIZE)),
        4: _load_image("leaves.png", (TILE_SIZE, TILE_SIZE)),
        5: _load_image("block_planks.png", (TILE_SIZE, TILE_SIZE)),
        6: _load_image("iron_ore.png", (TILE_SIZE, TILE_SIZE)),
        7: _load_image("emerald_ore.png", (TILE_SIZE, TILE_SIZE)),
    })

    TILE_DEFS.clear()
    TILE_DEFS.update({
        1: {"name": "Dirt", "hardness": 0.6, "drop_item": 2,
            "particle_color": (110, 80, 50)},
        2: {"name": "Stone", "hardness": 1.8, "drop_item": 3,
            "particle_color": (140, 140, 140)},
        3: {"name": "Oak", "hardness": 1.2, "drop_item": 6,
            "particle_color": (110, 80, 50)},
        4: {"name": "Leaves", "hardness": 0.3, "drop_item": 5,
            "particle_color": (60, 140, 60)},
        5: {"name": "Planks", "hardness": 1.2, "drop_item": 6,
            "particle_color": (150, 120, 80)},
        6: {"name": "Iron ore", "hardness": 2.5, "drop_item": 7,
            "particle_color": (200, 160, 100)},
        7: {"name": "Emerald ore", "hardness": 4.0, "drop_item": 8,
            "particle_color": (50, 200, 100)},
    })

    ITEM_DEFS.clear()
    ITEM_DEFS.update({
        1: {"name": "Wooden pickaxe",
            "image": _load_image("pick.png", (TILE_SIZE, TILE_SIZE)),
            "type": "tool", "can_break": True, "strength": 1.0,
            "stackable": False},
        2: {"name": "Dirt", "image": TILE_TEXTURES[1],
            "type": "block", "tile_id": 1, "stackable": True},
        3: {"name": "Stone", "image": TILE_TEXTURES[2],
            "type": "block", "tile_id": 2, "stackable": True},
        4: {"name": "Oak", "image": TILE_TEXTURES[3],
            "type": "block", "tile_id": 3, "stackable": True},
        5: {"name": "Leaves", "image": TILE_TEXTURES[4],
            "type": "block", "tile_id": 4, "stackable": True},
        6: {"name": "Planks", "image": TILE_TEXTURES[5],
            "type": "block", "tile_id": 5, "stackable": True},
        7: {"name": "Iron",
            "image": _load_image("iron.png", (TILE_SIZE, TILE_SIZE)),
            "type": "material", "stackable": True},
        8: {"name": "Emerald",
            "image": _load_image("emerald.png", (TILE_SIZE, TILE_SIZE)),
            "type": "material", "stackable": True},
        9: {"name": "Iron pickaxe",
            "image": _load_image("iron_pick.png", (TILE_SIZE, TILE_SIZE)),
            "type": "tool", "can_break": True, "strength": 4.0,
            "stackable": False},
        10: {"name": "Emerald pickaxe",
            "image": _load_image("emerald_pick.png", (TILE_SIZE, TILE_SIZE)),
            "type": "tool", "can_break": True, "strength": 10.0,
            "stackable": False},
    })

    IMAGES["rat"] = _load_image("rat.png", (PLAYER_WIDTH, PLAYER_HEIGHT))
    IMAGES["rat_crouch"] = _load_image(
        "crouched_rat.png", (PLAYER_WIDTH, PLAYER_CROUCH_HEIGHT))
    IMAGES["rat_left"] = pygame.transform.flip(IMAGES["rat"], True, False)
    IMAGES["rat_crouch_left"] = pygame.transform.flip(
        IMAGES["rat_crouch"], True, False)
    IMAGES["slot"] = _load_image("empty_inv.png", (SLOT_SIZE, SLOT_SIZE))
    IMAGES["slot_selected"] = _load_image(
        "selected_inv.png", (SLOT_SIZE, SLOT_SIZE))


# =============================================================================
# WORLD
# =============================================================================
class World:
    AIR = 0
    DIRT = 1
    STONE = 2
    OAK = 3
    LEAVES = 4
    PLANKS = 5
    IRON_ORE = 6
    EMERALD_ORE = 7

    NON_SOLID = {AIR, OAK, LEAVES}

    def __init__(self, width, height):
        self.width = max(1, width)
        self.height = max(1, height)
        self.tiles = [[self.AIR] * self.width for _ in range(self.height)]
        self.generate()

    def generate(self):
        base = min(20, max(0, self.height - 8))
        for y in range(self.height):
            row = self.tiles[y]
            for x in range(self.width):
                hill = int(math.sin(x * 0.08) * 2 + math.sin(x * 0.21) * 1.5)
                surface_y = base + hill
                if y < surface_y:
                    row[x] = self.AIR
                elif y <= surface_y + 10:
                    row[x] = self.DIRT
                else:
                    row[x] = self.STONE
        self._generate_ores()
        self._generate_trees()

    def _generate_ores(self):
        for y in range(IRON_ORE_MIN_Y, self.height):
            for x in range(self.width):
                if self.tiles[y][x] != self.STONE:
                    continue
                if random.random() < IRON_VEIN_CHANCE:
                    self._grow_vein(x, y, self.IRON_ORE,
                                    IRON_VEIN_MIN, IRON_VEIN_MAX)

        for y in range(EMERALD_ORE_MIN_Y, self.height):
            for x in range(self.width):
                if self.tiles[y][x] != self.STONE:
                    continue
                if random.random() < EMERALD_VEIN_CHANCE:
                    self._grow_vein(x, y, self.EMERALD_ORE,
                                    EMERALD_VEIN_MIN, EMERALD_VEIN_MAX)

        current = self._count_tile(self.EMERALD_ORE)
        if current < EMERALD_MIN:
            candidates = []
            for y in range(EMERALD_ORE_MIN_Y, self.height):
                for x in range(self.width):
                    if self.tiles[y][x] == self.STONE:
                        candidates.append((x, y))
            random.shuffle(candidates)
            for x, y in candidates:
                if current >= EMERALD_MIN:
                    break
                if self.tiles[y][x] != self.STONE:
                    continue
                size = random.randint(EMERALD_VEIN_MIN, EMERALD_VEIN_MAX)
                current += self._grow_vein(x, y, self.EMERALD_ORE,
                                           size, size)

    def _grow_vein(self, x0, y0, tile_id, min_size, max_size):
        target = random.randint(min_size, max_size)
        placed = 0
        frontier = [(x0, y0)]
        visited = set()
        while frontier and placed < target:
            idx = random.randrange(len(frontier))
            x, y = frontier.pop(idx)
            if (x, y) in visited:
                continue
            visited.add((x, y))
            if not (0 <= x < self.width and 0 <= y < self.height):
                continue
            if self.tiles[y][x] != self.STONE:
                continue
            self.tiles[y][x] = tile_id
            placed += 1
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                frontier.append((x + dx, y + dy))
        return placed

    def _count_tile(self, tile_id):
        return sum(row.count(tile_id) for row in self.tiles)

    def _generate_trees(self):
        x = random.randint(TREE_FIRST_MIN, TREE_FIRST_MAX)
        while x < self.width - TREE_MIN_SPACING:
            surface_y = None
            for y in range(self.height):
                if self.tiles[y][x] != self.AIR:
                    surface_y = y
                    break
            if surface_y is None or surface_y < 8:
                x += random.randint(TREE_MIN_SPACING, TREE_MAX_SPACING)
                continue
            if self.tiles[surface_y][x] != self.DIRT:
                x += random.randint(TREE_MIN_SPACING, TREE_MAX_SPACING)
                continue

            trunk_h = random.randint(TREE_MIN_HEIGHT, TREE_MAX_HEIGHT)
            canopy_r = random.randint(TREE_MIN_CANOPY, TREE_MAX_CANOPY)
            base_y = surface_y - 1

            if base_y - trunk_h - canopy_r < 0:
                x += random.randint(TREE_MIN_SPACING, TREE_MAX_SPACING)
                continue

            for i in range(trunk_h):
                self.tiles[base_y - i][x] = self.OAK

            top_y = base_y - trunk_h + 1
            for dy in range(-canopy_r, canopy_r + 1):
                for dx in range(-canopy_r, canopy_r + 1):
                    if dx * dx + dy * dy > canopy_r * canopy_r + 1:
                        continue
                    ty = top_y + dy
                    tx = x + dx
                    if 0 <= ty < self.height and 0 <= tx < self.width:
                        if self.tiles[ty][tx] == self.AIR:
                            self.tiles[ty][tx] = self.LEAVES

            x += random.randint(TREE_MIN_SPACING, TREE_MAX_SPACING)

    def in_bounds(self, tx, ty):
        return 0 <= tx < self.width and 0 <= ty < self.height

    def get_tile(self, tx, ty):
        if self.in_bounds(tx, ty):
            return self.tiles[ty][tx]
        return self.AIR

    def set_tile(self, tx, ty, tile_id):
        if self.in_bounds(tx, ty):
            self.tiles[ty][tx] = tile_id

    def is_solid(self, tx, ty):
        if ty < 0:
            return False
        if tx < 0 or tx >= self.width or ty >= self.height:
            return True
        return self.tiles[ty][tx] not in self.NON_SOLID

    def solid_tiles_overlapping(self, rect):
        found = []
        left = rect.left // TILE_SIZE
        right = (rect.right - 1) // TILE_SIZE
        top = rect.top // TILE_SIZE
        bottom = (rect.bottom - 1) // TILE_SIZE
        for ty in range(top, bottom + 1):
            for tx in range(left, right + 1):
                if self.is_solid(tx, ty):
                    found.append(pygame.Rect(
                        tx * TILE_SIZE, ty * TILE_SIZE,
                        TILE_SIZE, TILE_SIZE))
        return found


# =============================================================================
# CONTAINER
# =============================================================================
class Container:
    def __init__(self, size):
        self.slots = [None] * size

    def __len__(self):
        return len(self.slots)

    def max_stack(self, item_id):
        item_def = ITEM_DEFS.get(item_id)
        if item_def and not item_def.get("stackable", True):
            return 1
        return STACK_SIZE

    def add(self, item_id, amount=1):
        if amount <= 0:
            return 0
        stack = self.max_stack(item_id)
        for slot in self.slots:
            if slot and slot["id"] == item_id and slot["amount"] < stack:
                moved = min(stack - slot["amount"], amount)
                slot["amount"] += moved
                amount -= moved
                if amount <= 0:
                    return 0
        for i, slot in enumerate(self.slots):
            if slot is None:
                moved = min(stack, amount)
                self.slots[i] = {"id": item_id, "amount": moved}
                amount -= moved
                if amount <= 0:
                    return 0
        return amount


class Inventory(Container):
    def __init__(self, hotbar_size=HOTBAR_SIZE, backpack_size=BACKPACK_SIZE):
        super().__init__(hotbar_size + backpack_size)
        self.hotbar_size = hotbar_size
        self.selected = 0

    @property
    def selected_item(self):
        return self.slots[self.selected]

    def select(self, index):
        if 0 <= index < self.hotbar_size:
            self.selected = index

    def scroll(self, direction):
        self.selected = (self.selected + direction) % self.hotbar_size


# =============================================================================
# ITEM DROP
# =============================================================================
class ItemDrop:
    GRAVITY = 700.0

    def __init__(self, cx, cy, item_id, amount=1):
        self.x = float(cx)
        self.y = float(cy)
        self.vx = random.uniform(-90, 90)
        self.vy = random.uniform(-280, -140)
        self.item_id = item_id
        self.amount = amount
        self.age = 0.0
        self.grounded = False
        self.bob_phase = random.uniform(0, math.tau)
        self.in_range_time = 0.0

    def update(self, world, dt):
        self.age += dt
        if self.grounded:
            self.bob_phase += 4.0 * dt
            return

        self.vy = min(self.vy + self.GRAVITY * dt, 600.0)
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vx *= 0.95

        if self.vy > 0:
            bottom = self.y + 4
            feet_ty = int(bottom // TILE_SIZE)
            mid_tx = int(self.x // TILE_SIZE)
            if world.is_solid(mid_tx, feet_ty):
                self.y = feet_ty * TILE_SIZE - 4
                self.vy = 0.0
                self.vx = 0.0
                self.grounded = True

    @property
    def can_pickup(self):
        return self.age > PICKUP_CONTACT_DELAY

    def draw(self, surface, camera):
        item_def = ITEM_DEFS.get(self.item_id)
        if item_def is None or item_def.get("image") is None:
            return
        size = 10
        image = pygame.transform.scale(item_def["image"], (size, size))
        bob = math.sin(self.bob_phase) * 2 if self.grounded else 0
        sx = int(self.x - size / 2) - int(camera.x)
        sy = int(self.y - size / 2 + bob) - int(camera.y)
        surface.blit(image, (sx, sy))


# =============================================================================
# PARTICLE
# =============================================================================
class Particle:
    def __init__(self, x, y, vx, vy, color, life=0.5, size=2):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.life = life
        self.max_life = life
        self.size = size

    def update(self, dt):
        self.vy += 900.0 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt

    @property
    def alive(self):
        return self.life > 0

    def draw(self, surface, camera):
        if not self.alive:
            return
        sx = int(self.x) - int(camera.x)
        sy = int(self.y) - int(camera.y)
        pygame.draw.rect(surface, self.color, (sx, sy, self.size, self.size))


# =============================================================================
# PLAYER
# =============================================================================
class Player:
    def __init__(self, game, world, x, y):
        self.game = game
        self.world = world
        self.x = float(x)
        self.y = float(y)
        self.vel_y = 0.0
        self.on_ground = False
        self.facing_right = True
        self.crouching = False
        self.inventory = Inventory()
        self.mining_tx = None
        self.mining_ty = None
        self.mining_progress = 0.0

    @property
    def height(self):
        return PLAYER_CROUCH_HEIGHT if self.crouching else PLAYER_HEIGHT

    @property
    def rect(self):
        return pygame.Rect(int(self.x), int(self.y),
                           PLAYER_WIDTH, self.height)

    def _probe_ground(self):
        probe = self.rect.move(0, 1)
        return bool(self.world.solid_tiles_overlapping(probe))

    def handle_event(self, event, world_mouse_pos):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w, pygame.K_SPACE):
                self.jump()
            elif event.key == pygame.K_q:
                self.drop_selected()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self.try_place(world_mouse_pos)

    def update(self, keys, mining, world_mouse_pos, dt, pause_input=False):
        self.on_ground = self._probe_ground()

        if pause_input:
            if not self.on_ground:
                self.vel_y = min(self.vel_y + PLAYER_GRAVITY,
                                 PLAYER_MAX_FALL_SPEED)
            self.move(0.0, self.vel_y)
            self.on_ground = self._probe_ground()
            if self.on_ground and self.vel_y > 0:
                self.vel_y = 0.0
            self._reset_mining()
            return

        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.set_crouching(True)
        else:
            self.set_crouching(False)

        move_x = 0.0
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            move_x -= PLAYER_SPEED
            self.facing_right = False
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            move_x += PLAYER_SPEED
            self.facing_right = True

        if not self.on_ground:
            self.vel_y = min(self.vel_y + PLAYER_GRAVITY,
                             PLAYER_MAX_FALL_SPEED)
        elif self.vel_y > 0:
            self.vel_y = 0.0

        self.move(move_x, self.vel_y)

        self.on_ground = self._probe_ground()
        if self.on_ground and self.vel_y > 0:
            self.vel_y = 0.0

        self._update_mining(mining, world_mouse_pos, dt)

    def set_crouching(self, want):
        if want == self.crouching:
            return
        delta = PLAYER_HEIGHT - PLAYER_CROUCH_HEIGHT
        if want:
            self.crouching = True
            self.y += delta
            _play("crouch")
        else:
            stand_rect = pygame.Rect(int(self.x), int(self.y) - delta,
                                     PLAYER_WIDTH, PLAYER_HEIGHT)
            if not self.world.solid_tiles_overlapping(stand_rect):
                self.crouching = False
                self.y -= delta

    def jump(self):
        if not self.on_ground:
            return
        if self.crouching:
            self.set_crouching(False)
            if self.crouching:
                return
        self.vel_y = PLAYER_JUMP_FORCE
        self.on_ground = False
        _play("jump")

    def move(self, dx, dy):
        if dy != 0:
            steps = max(1, int(math.ceil(abs(dy) / COLLISION_SUBSTEP)))
            step_y = dy / steps
            for _ in range(steps):
                self._move_axis(0.0, step_y)

        if dx != 0:
            steps = max(1, int(math.ceil(abs(dx) / COLLISION_SUBSTEP)))
            step_x = dx / steps
            for _ in range(steps):
                old_x = self.x
                self._move_axis(step_x, 0.0)
                if self.x == old_x and self.on_ground:
                    if self._try_step_up(step_x):
                        self._move_axis(step_x, 0.0)

    def _move_axis(self, dx, dy):
        if dx == 0.0 and dy == 0.0:
            return

        self.x += dx
        self.y += dy

        rect = self.rect
        tiles = self.world.solid_tiles_overlapping(rect)
        if not tiles:
            return

        if dx > 0:
            rect.right = min(t.left for t in tiles)
        elif dx < 0:
            rect.left = max(t.right for t in tiles)
        elif dy > 0:
            rect.bottom = min(t.top for t in tiles)
            self.vel_y = 0.0
        else:
            rect.top = max(t.bottom for t in tiles)
            self.vel_y = 0.0

        self.x = float(rect.left)
        self.y = float(rect.top)

    def _try_step_up(self, step_x):
        if not self.on_ground:
            return False
        ahead_x = self.x + (PLAYER_WIDTH if step_x > 0 else -1)
        probe_rect = pygame.Rect(int(ahead_x), int(self.y),
                                 PLAYER_WIDTH, self.height)
        blocking = self.world.solid_tiles_overlapping(probe_rect)
        if not blocking:
            return False
        block_top = min(t.top for t in blocking)
        step_height = (self.y + self.height) - block_top
        if step_height <= 0 or step_height > PLAYER_STEP_HEIGHT:
            return False
        new_y = self.y - step_height
        test_rect = pygame.Rect(int(self.x + step_x), int(new_y),
                                PLAYER_WIDTH, self.height)
        if self.world.solid_tiles_overlapping(test_rect):
            return False
        self.y = float(new_y)
        return True

    def _update_mining(self, mining, world_mouse_pos, dt):
        if not mining:
            self._reset_mining()
            return
        item = self.inventory.selected_item
        if item is None:
            self._reset_mining()
            return
        item_def = ITEM_DEFS.get(item["id"])
        if not item_def or not item_def.get("can_break"):
            self._reset_mining()
            return

        target_x = int(world_mouse_pos[0] // TILE_SIZE)
        target_y = int(world_mouse_pos[1] // TILE_SIZE)
        if not self.world.in_bounds(target_x, target_y):
            self._reset_mining()
            return
        tile_id = self.world.get_tile(target_x, target_y)
        if tile_id == World.AIR:
            self._reset_mining()
            return

        cx = (self.x + PLAYER_WIDTH / 2) / TILE_SIZE
        cy = (self.y + self.height / 2) / TILE_SIZE
        if abs(cx - target_x) > REACH_X or abs(cy - target_y) > REACH_Y:
            self._reset_mining()
            return

        if (self.mining_tx, self.mining_ty) != (target_x, target_y):
            self.mining_tx = target_x
            self.mining_ty = target_y
            self.mining_progress = 0.0

        tile_def = TILE_DEFS.get(tile_id)
        if tile_def is None:
            return
        strength = max(item_def.get("strength", 1.0), 0.1)
        break_time = tile_def["hardness"] / strength
        self.mining_progress += dt / break_time

        if random.random() < 0.2:
            self.game.spawn_particle(
                target_x * TILE_SIZE + random.uniform(2, TILE_SIZE - 2),
                target_y * TILE_SIZE + random.uniform(2, TILE_SIZE - 2),
                tile_def["particle_color"])

        if self.mining_progress >= 1.0:
            self.game.break_block(target_x, target_y)
            self._reset_mining()

    def _reset_mining(self):
        self.mining_tx = None
        self.mining_ty = None
        self.mining_progress = 0.0

    def try_place(self, world_mouse_pos):
        item = self.inventory.selected_item
        if item is None:
            return False
        item_def = ITEM_DEFS.get(item["id"])
        if not item_def or item_def.get("type") != "block":
            return False

        target_x = int(world_mouse_pos[0] // TILE_SIZE)
        target_y = int(world_mouse_pos[1] // TILE_SIZE)
        if not self.world.in_bounds(target_x, target_y):
            return False
        if self.world.get_tile(target_x, target_y) != World.AIR:
            return False

        cx = (self.x + PLAYER_WIDTH / 2) / TILE_SIZE
        cy = (self.y + self.height / 2) / TILE_SIZE
        if abs(cx - target_x) > REACH_X or abs(cy - target_y) > REACH_Y:
            return False

        tile_rect = pygame.Rect(target_x * TILE_SIZE, target_y * TILE_SIZE,
                                TILE_SIZE, TILE_SIZE)
        if self.rect.colliderect(tile_rect):
            return False

        self.world.set_tile(target_x, target_y, item_def["tile_id"])
        item["amount"] -= 1
        if item["amount"] <= 0:
            self.inventory.slots[self.inventory.selected] = None
        return True

    def drop_selected(self):
        item = self.inventory.selected_item
        if item is None:
            return
        drop = ItemDrop(self.x + PLAYER_WIDTH / 2,
                        self.y + self.height / 2,
                        item["id"], item["amount"])
        drop.vx = 120 if self.facing_right else -120
        drop.vy = -200
        self.game.drops.append(drop)
        self.inventory.slots[self.inventory.selected] = None

    def draw(self, surface, camera):
        if self.crouching:
            image = IMAGES["rat_crouch" if self.facing_right else "rat_crouch_left"]
        else:
            image = IMAGES["rat" if self.facing_right else "rat_left"]
        sx = int(self.x) - int(camera.x)
        sy = int(self.y) - int(camera.y)
        surface.blit(image, (sx, sy))
        self._draw_held_item(surface, sx, sy)

    def _draw_held_item(self, surface, sx, sy):
        item = self.inventory.selected_item
        if item is None:
            return
        item_def = ITEM_DEFS.get(item["id"])
        if item_def is None or item_def.get("image") is None:
            return
        image = item_def["image"]
        if not self.facing_right:
            image = pygame.transform.flip(image, True, False)
        offset_x = 12 if self.facing_right else -4
        surface.blit(image, (sx + offset_x, sy + 8))


# =============================================================================
# CAMERA
# =============================================================================
class Camera:
    def __init__(self, viewport_w, viewport_h):
        self.x = 0.0
        self.y = 0.0
        self.viewport_w = viewport_w
        self.viewport_h = viewport_h

    def snap(self, target_rect, world_w_px, world_h_px):
        self._set_target(target_rect, world_w_px, world_h_px, 1.0, 1.0)

    def follow(self, target_rect, world_w_px, world_h_px):
        self._set_target(target_rect, world_w_px, world_h_px,
                         CAMERA_LERP_X, CAMERA_LERP_Y)

    def _set_target(self, target_rect, world_w_px, world_h_px, lx, ly):
        target_x = target_rect.centerx - self.viewport_w / 2
        target_y = target_rect.centery - self.viewport_h * CAMERA_Y_ANCHOR
        self.x += (target_x - self.x) * lx
        self.y += (target_y - self.y) * ly
        max_x = max(0, world_w_px - self.viewport_w)
        max_y = max(0, world_h_px - self.viewport_h)
        self.x = max(0.0, min(self.x, max_x))
        self.y = max(0.0, min(self.y, max_y))


# =============================================================================
# RENDERER
# =============================================================================
class Renderer:
    def __init__(self, screen):
        self.screen = screen
        sw, sh = screen.get_size()
        self.zoom = max(1, int(math.ceil(sh / TARGET_LOGICAL_HEIGHT)))
        self.logical_w = sw // self.zoom
        self.logical_h = sh // self.zoom
        self.scaled_w = self.logical_w * self.zoom
        self.scaled_h = self.logical_h * self.zoom
        self.offset_x = (sw - self.scaled_w) // 2
        self.offset_y = (sh - self.scaled_h) // 2
        self.surface = pygame.Surface((self.logical_w, self.logical_h))

    def present(self):
        if self.zoom == 1:
            self.screen.blit(self.surface, (self.offset_x, self.offset_y))
        else:
            scaled = pygame.transform.scale(
                self.surface, (self.scaled_w, self.scaled_h))
            self.screen.fill(LETTERBOX_COLOR)
            self.screen.blit(scaled, (self.offset_x, self.offset_y))

    def screen_to_logical(self, pos):
        return ((pos[0] - self.offset_x) / self.zoom,
                (pos[1] - self.offset_y) / self.zoom)


# =============================================================================
# GUI
# =============================================================================
class Widget:
    def __init__(self, rect):
        self.rect = pygame.Rect(rect)
        self.visible = True
        self.enabled = True
        self.mouse_pos = (0, 0)

    def handle_event(self, event):
        return False

    def update(self, dt):
        pass

    def draw(self, surface):
        pass


class GUIManager:
    def __init__(self):
        self.widgets = []
        self.mouse_pos = (0, 0)

    def add(self, widget):
        self.widgets.append(widget)
        return widget

    def handle_event(self, event):
        for widget in reversed(self.widgets):
            if widget.visible and widget.enabled and widget.handle_event(event):
                return True
        return False

    def update(self, dt):
        for widget in self.widgets:
            if widget.visible:
                widget.update(dt)

    def draw(self, surface):
        for widget in self.widgets:
            if widget.visible:
                widget.mouse_pos = self.mouse_pos
                widget.draw(surface)


def draw_tooltip(surface, pos, text, font_size=14):
    font = pygame.font.SysFont(None, font_size)
    text_surf = font.render(text, True, (240, 240, 240))
    padding = 4
    w = text_surf.get_width() + padding * 2
    h = text_surf.get_height() + padding * 2
    x, y = pos
    sw, sh = surface.get_size()
    if x + w > sw - 2:
        x = sw - w - 2
    if y + h > sh - 2:
        y = y - h - 18
    if x < 2:
        x = 2
    if y < 2:
        y = 2
    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    bg.fill((20, 20, 30, 220))
    pygame.draw.rect(bg, (100, 100, 120), bg.get_rect(), 1)
    surface.blit(bg, (x, y))
    surface.blit(text_surf, (x + padding, y + padding))


class Label(Widget):
    def __init__(self, pos, text="", size=20, color=(255, 255, 255)):
        super().__init__((pos[0], pos[1], 0, 0))
        self.text = text
        self.color = color
        self.font = pygame.font.SysFont(None, size)

    def draw(self, surface):
        if self.text:
            surface.blit(self.font.render(self.text, True, self.color),
                         self.rect.topleft)


class Panel(Widget):
    def __init__(self, rect, color=(18, 18, 24, 210),
                 border_color=(80, 80, 100)):
        super().__init__(rect)
        self.color = color
        self.border_color = border_color

    def draw(self, surface):
        bg = pygame.Surface(self.rect.size, pygame.SRCALPHA)
        bg.fill(self.color)
        surface.blit(bg, self.rect.topleft)
        pygame.draw.rect(surface, self.border_color, self.rect,
                         width=2, border_radius=8)


class Button(Widget):
    def __init__(self, rect, text, on_click=None, size=20):
        super().__init__(rect)
        self.text = text
        self.on_click = on_click
        self.font = pygame.font.SysFont(None, size)
        self.hovered = False
        self.bg_color = (40, 40, 52)
        self.hover_color = (70, 70, 92)
        self.border_color = (200, 200, 210)
        self.text_color = (240, 240, 240)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                if self.on_click:
                    self.on_click()
                return True
        return False

    def draw(self, surface):
        color = self.hover_color if self.hovered else self.bg_color
        pygame.draw.rect(surface, color, self.rect, border_radius=6)
        pygame.draw.rect(surface, self.border_color, self.rect,
                         width=2, border_radius=6)
        label = self.font.render(self.text, True, self.text_color)
        surface.blit(label, label.get_rect(center=self.rect.center))


class Hotbar(Widget):
    def __init__(self, inventory, logical_size, margin_top=8):
        width = inventory.hotbar_size * SLOT_SIZE
        x = (logical_size[0] - width) // 2
        super().__init__((x, margin_top, width, SLOT_SIZE))
        self.inventory = inventory
        self.font = pygame.font.SysFont(None, 18)

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if pygame.K_1 <= event.key <= pygame.K_9:
                self.inventory.select(event.key - pygame.K_1)
                return True
            if event.key == pygame.K_0:
                self.inventory.select(9)
                return True
        elif event.type == pygame.MOUSEWHEEL:
            self.inventory.scroll(-event.y)
            return True
        return False

    def _slot_rect(self, i):
        return pygame.Rect(self.rect.left + i * SLOT_SIZE,
                           self.rect.top, SLOT_SIZE, SLOT_SIZE)

    def draw(self, surface):
        for i in range(self.inventory.hotbar_size):
            slot = self.inventory.slots[i]
            rect = self._slot_rect(i)
            key = "slot_selected" if i == self.inventory.selected else "slot"
            surface.blit(IMAGES[key], rect.topleft)
            if slot is None:
                continue
            item_def = ITEM_DEFS.get(slot["id"])
            if item_def is None or item_def.get("image") is None:
                continue
            img = pygame.transform.scale(item_def["image"],
                                         (SLOT_SIZE, SLOT_SIZE))
            surface.blit(img, rect.topleft)
            if slot["amount"] > 1:
                text = self.font.render(str(slot["amount"]), True, (255, 255, 255))
                surface.blit(text,
                             (rect.right - text.get_width() - 2,
                              rect.bottom - text.get_height() - 1))

        mx, my = self.mouse_pos
        for i in range(self.inventory.hotbar_size):
            slot = self.inventory.slots[i]
            if slot is None:
                continue
            rect = self._slot_rect(i)
            if rect.collidepoint(mx, my):
                item_def = ITEM_DEFS.get(slot["id"])
                if item_def:
                    draw_tooltip(surface, (mx + 10, my + 10),
                                 item_def["name"])
                break


class InventoryScreen(Widget):
    """Backpack + hotbar + 3x3 crafting grid with result slot.

    Controls inside this panel:
        Left click     -- pick up / place / swap / craft
        Right click    -- split a stack in half (larger half follows the
                          cursor), or drop one item at a time when already
                          holding a stack, or craft one from the result.
    """
    PADDING = 8
    SECTION_GAP = 16
    RESULT_GAP = 12

    PICKAXE_RECIPES = {
        3: 1,   # Stone -> Wooden pickaxe
        7: 9,   # Iron -> Iron pickaxe
        8: 10,  # Emerald -> Emerald pickaxe
    }
    PLANKS_ITEM = 6

    def __init__(self, inventory, logical_size, slot_size=SLOT_SIZE,
                 hotbar_rows=1):
        self.container = inventory
        self.inventory = inventory
        self.crafting = Container(9)
        self.crafting_result = None
        self.slot_size = slot_size
        self.hotbar_rows = hotbar_rows
        self.cols = HOTBAR_SIZE
        self.row_gap = slot_size // 2
        self.font = pygame.font.SysFont(None, 18)

        self.hotbar_size = inventory.hotbar_size
        self.backpack_row_count = ((len(inventory) - self.hotbar_size)
                                   // self.cols)

        inv_w = self.cols * slot_size
        inv_h = ((self.backpack_row_count + self.hotbar_rows) * slot_size
                 + self.row_gap)
        craft_w = 3 * slot_size
        craft_h = 3 * slot_size
        result_w = slot_size

        inner_w = (inv_w + self.SECTION_GAP
                   + craft_w + self.RESULT_GAP + result_w)
        inner_h = max(inv_h, craft_h)

        panel_w = inner_w + self.PADDING * 2
        panel_h = inner_h + self.PADDING * 2
        x = (logical_size[0] - panel_w) // 2
        y = (logical_size[1] - panel_h) // 2
        super().__init__((x, y, panel_w, panel_h))

        self.inner_x = x + self.PADDING
        self.inner_y = y + self.PADDING
        self.crafting_x = self.inner_x + inv_w + self.SECTION_GAP
        self.crafting_y = self.inner_y
        self.result_x = self.crafting_x + craft_w + self.RESULT_GAP
        self.result_y = self.inner_y + slot_size

        self.dragging = None
        self.drag_origin = None
        self._game_ref = None

        self._refresh_result()

    # -- recipe --------------------------------------------------------------
    def _check_recipe(self):
        grid = self.crafting.slots
        top = [grid[0], grid[1], grid[2]]
        if any(s is None for s in top):
            return None
        material = top[0]["id"]
        if any(s["id"] != material for s in top):
            return None
        if grid[3] is not None or grid[5] is not None:
            return None
        if grid[6] is not None or grid[8] is not None:
            return None
        if grid[4] is None or grid[4]["id"] != self.PLANKS_ITEM:
            return None
        if grid[7] is None or grid[7]["id"] != self.PLANKS_ITEM:
            return None
        return self.PICKAXE_RECIPES.get(material)

    def _refresh_result(self):
        result_id = self._check_recipe()
        self.crafting_result = ({"id": result_id, "amount": 1}
                                if result_id is not None else None)

    def _consume_ingredients(self):
        for i in (0, 1, 2, 4, 7):
            slot = self.crafting.slots[i]
            if slot is None:
                continue
            slot["amount"] -= 1
            if slot["amount"] <= 0:
                self.crafting.slots[i] = None

    def _try_craft(self):
        if self.crafting_result is None:
            return False
        result_id = self.crafting_result["id"]

        if self.dragging is not None:
            if self.dragging["id"] != result_id:
                return False
            cap = self.inventory.max_stack(result_id)
            if self.dragging["amount"] >= cap:
                return False
            self.dragging["amount"] += 1
        else:
            leftover = self.inventory.add(result_id, 1)
            if leftover > 0:
                return False

        self._consume_ingredients()
        self._refresh_result()
        return True

    # -- geometry ------------------------------------------------------------
    def _inventory_slot_rects(self):
        for i in range(len(self.container)):
            if i < self.hotbar_size:
                row = self.backpack_row_count
                col = i
                add_gap = True
            else:
                bi = i - self.hotbar_size
                row = bi // self.cols
                col = bi % self.cols
                add_gap = False
            sx = self.inner_x + col * self.slot_size
            sy = self.inner_y + row * self.slot_size
            if add_gap:
                sy += self.row_gap
            yield i, pygame.Rect(sx, sy, self.slot_size, self.slot_size)

    def _crafting_slot_rects(self):
        for i in range(9):
            row = i // 3
            col = i % 3
            sx = self.crafting_x + col * self.slot_size
            sy = self.crafting_y + row * self.slot_size
            yield i, pygame.Rect(sx, sy, self.slot_size, self.slot_size)

    def _result_rect(self):
        return pygame.Rect(self.result_x, self.result_y,
                           self.slot_size, self.slot_size)

    def _slot_at(self, pos):
        for i, rect in self._inventory_slot_rects():
            if rect.collidepoint(pos):
                return ("inventory", i)
        for i, rect in self._crafting_slot_rects():
            if rect.collidepoint(pos):
                return ("crafting", i)
        if self._result_rect().collidepoint(pos):
            return ("result", None)
        return None

    def _get_container(self, kind):
        return self.container if kind == "inventory" else self.crafting

    # -- pick up / place / split --------------------------------------------
    def _pick_up(self, kind, idx):
        container = self._get_container(kind)
        item = container.slots[idx]
        if item is None:
            return
        self.dragging = item
        self.drag_origin = (kind, idx)
        container.slots[idx] = None
        self._refresh_result()

    def _pick_up_half(self, kind, idx):
        container = self._get_container(kind)
        item = container.slots[idx]
        if item is None:
            return
        if item["amount"] < 2:
            self._pick_up(kind, idx)
            return
        mouse_amount = (item["amount"] + 1) // 2
        item["amount"] -= mouse_amount
        self.dragging = {"id": item["id"], "amount": mouse_amount}
        self.drag_origin = (kind, idx)
        self._refresh_result()

    def _place(self, kind, idx):
        container = self._get_container(kind)
        target = container.slots[idx]
        if target is None:
            container.slots[idx] = self.dragging
            self.dragging = None
            self.drag_origin = None
        elif (target["id"] == self.dragging["id"]
              and container.max_stack(target["id"]) > 1):
            cap = container.max_stack(target["id"])
            total = target["amount"] + self.dragging["amount"]
            if total <= cap:
                target["amount"] = total
                self.dragging = None
                self.drag_origin = None
            else:
                target["amount"] = cap
                self.dragging["amount"] = total - cap
        else:
            container.slots[idx] = self.dragging
            self.dragging = target
            self.drag_origin = (kind, idx)
        self._refresh_result()

    def _place_one(self, kind, idx):
        if self.dragging is None:
            return
        container = self._get_container(kind)
        target = container.slots[idx]
        if target is None:
            container.slots[idx] = {"id": self.dragging["id"], "amount": 1}
        elif (target["id"] == self.dragging["id"]
              and target["amount"] < container.max_stack(target["id"])):
            target["amount"] += 1
        else:
            return
        self.dragging["amount"] -= 1
        if self.dragging["amount"] <= 0:
            self.dragging = None
            self.drag_origin = None
        self._refresh_result()

    def _drop_to_world(self, pos):
        if self.dragging is None or self._game_ref is None:
            return
        game = self._game_ref
        world_x = pos[0] + game.camera.x
        world_y = pos[1] + game.camera.y
        drop = ItemDrop(world_x, world_y,
                        self.dragging["id"], self.dragging["amount"])
        game.drops.append(drop)
        self.dragging = None
        self.drag_origin = None

    # -- events --------------------------------------------------------------
    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                return self._handle_left_click(event.pos)
            if event.button == 3:
                return self._handle_right_click(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.dragging is not None:
                target = self._slot_at(event.pos)
                if target is not None:
                    kind, idx = target
                    if kind == "result":
                        self._try_craft()
                    else:
                        self._place(kind, idx)
                    return True
                if not self.rect.collidepoint(event.pos):
                    self._drop_to_world(event.pos)
                    return True
        return False

    def _handle_left_click(self, pos):
        target = self._slot_at(pos)
        if target is None:
            return False
        kind, idx = target
        if kind == "result":
            self._try_craft()
            return True
        if self.dragging is None:
            self._pick_up(kind, idx)
        else:
            self._place(kind, idx)
        return True

    def _handle_right_click(self, pos):
        target = self._slot_at(pos)
        if target is None:
            return False
        kind, idx = target
        if kind == "result":
            self._try_craft()
            return True
        if self.dragging is None:
            self._pick_up_half(kind, idx)
        else:
            self._place_one(kind, idx)
        return True

    # -- cleanup -------------------------------------------------------------
    def close(self):
        if self.dragging is not None:
            leftover = self.inventory.add(self.dragging["id"],
                                          self.dragging["amount"])
            if leftover > 0 and self._game_ref is not None:
                game = self._game_ref
                game.drops.append(ItemDrop(
                    game.player.x + PLAYER_WIDTH / 2,
                    game.player.y + game.player.height / 2,
                    self.dragging["id"], leftover))
            self.dragging = None
            self.drag_origin = None

        for i in range(9):
            slot = self.crafting.slots[i]
            if slot is None:
                continue
            leftover = self.inventory.add(slot["id"], slot["amount"])
            if leftover > 0 and self._game_ref is not None:
                game = self._game_ref
                game.drops.append(ItemDrop(
                    game.player.x + PLAYER_WIDTH / 2,
                    game.player.y + game.player.height / 2,
                    slot["id"], leftover))
            self.crafting.slots[i] = None
        self._refresh_result()

    # -- drawing -------------------------------------------------------------
    def _draw_slot(self, surface, rect, slot, selected=False):
        base_key = "slot_selected" if selected else "slot"
        base = IMAGES[base_key]
        if base.get_size() != (self.slot_size, self.slot_size):
            base = pygame.transform.scale(
                base, (self.slot_size, self.slot_size))
        surface.blit(base, rect.topleft)
        if slot is None:
            return
        item_def = ITEM_DEFS.get(slot["id"])
        if item_def is None or item_def.get("image") is None:
            return
        img = pygame.transform.scale(item_def["image"],
                                     (self.slot_size, self.slot_size))
        surface.blit(img, rect.topleft)
        if slot["amount"] > 1:
            text = self.font.render(str(slot["amount"]), True, (255, 255, 255))
            surface.blit(text,
                         (rect.right - text.get_width() - 2,
                          rect.bottom - text.get_height() - 1))

    def draw(self, surface):
        pygame.draw.rect(surface, (20, 20, 30), self.rect, border_radius=8)
        pygame.draw.rect(surface, (100, 100, 120), self.rect,
                         width=2, border_radius=8)

        for i, rect in self._inventory_slot_rects():
            selected = (i == getattr(self.container, "selected", -1))
            self._draw_slot(surface, rect, self.container.slots[i], selected)

        for i, rect in self._crafting_slot_rects():
            self._draw_slot(surface, rect, self.crafting.slots[i])

        ax = self.crafting_x + 3 * self.slot_size + 2
        ay = self.result_y + self.slot_size // 2
        pygame.draw.polygon(surface, (170, 170, 190),
                            [(ax, ay - 4), (ax + 6, ay), (ax, ay + 4)])

        result_rect = self._result_rect()
        self._draw_slot(surface, result_rect, self.crafting_result,
                        selected=True)

        if self.dragging:
            item_def = ITEM_DEFS.get(self.dragging["id"])
            if item_def and item_def.get("image"):
                img = pygame.transform.scale(
                    item_def["image"], (self.slot_size, self.slot_size))
                mx, my = self.mouse_pos
                surface.blit(img,
                             (mx - self.slot_size // 2,
                              my - self.slot_size // 2))
            return

        mx, my = self.mouse_pos
        target = self._slot_at((mx, my))
        if target is not None:
            kind, idx = target
            if kind == "result":
                slot = self.crafting_result
            else:
                slot = self._get_container(kind).slots[idx]
            if slot:
                item_def = ITEM_DEFS.get(slot["id"])
                if item_def:
                    draw_tooltip(surface, (mx + 10, my + 10),
                                 item_def["name"])


# =============================================================================
# DRAW HELPERS
# =============================================================================
def draw_world(surface, world, camera):
    cam_x = int(camera.x)
    cam_y = int(camera.y)
    start_tx = max(0, cam_x // TILE_SIZE)
    end_tx = min(world.width, (cam_x + camera.viewport_w) // TILE_SIZE + 2)
    start_ty = max(0, cam_y // TILE_SIZE)
    end_ty = min(world.height, (cam_y + camera.viewport_h) // TILE_SIZE + 2)
    for ty in range(start_ty, end_ty):
        row = world.tiles[ty]
        sy = ty * TILE_SIZE - cam_y
        for tx in range(start_tx, end_tx):
            tile_id = row[tx]
            if tile_id == World.AIR:
                continue
            tex = TILE_TEXTURES.get(tile_id)
            if tex is not None:
                surface.blit(tex, (tx * TILE_SIZE - cam_x, sy))


_CRACK_STAGES = [
    [(7, 8), (8, 7), (8, 9), (9, 8)],
    [(4, 4), (11, 11), (5, 11), (11, 5)],
    [(7, 4), (8, 5), (7, 11), (8, 12)],
    [(3, 8), (4, 7), (12, 8), (11, 7)],
]


def draw_mining_overlay(surface, camera, tx, ty, progress):
    if progress <= 0:
        return
    sx = tx * TILE_SIZE - int(camera.x)
    sy = ty * TILE_SIZE - int(camera.y)
    alpha = int(min(progress, 1.0) * 130)
    overlay = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, alpha))
    surface.blit(overlay, (sx, sy))

    stage = int(progress * len(_CRACK_STAGES))
    for i in range(min(stage, len(_CRACK_STAGES))):
        for (px, py) in _CRACK_STAGES[i]:
            gx, gy = sx + px, sy + py
            if 0 <= gx < surface.get_width() and 0 <= gy < surface.get_height():
                surface.set_at((gx, gy), (20, 15, 10))


def draw_hover_outline(surface, camera, world, world_mouse_pos, player):
    item = player.inventory.selected_item
    if item is None:
        return
    item_def = ITEM_DEFS.get(item["id"])
    if item_def is None:
        return
    tx = int(world_mouse_pos[0] // TILE_SIZE)
    ty = int(world_mouse_pos[1] // TILE_SIZE)
    if not world.in_bounds(tx, ty):
        return
    cx = (player.x + PLAYER_WIDTH / 2) / TILE_SIZE
    cy = (player.y + player.height / 2) / TILE_SIZE
    if abs(cx - tx) > REACH_X or abs(cy - ty) > REACH_Y:
        return
    tile_id = world.get_tile(tx, ty)
    can_place = item_def.get("type") == "block" and tile_id == World.AIR
    can_mine = item_def.get("can_break") and tile_id != World.AIR
    if not (can_place or can_mine):
        return
    sx = tx * TILE_SIZE - int(camera.x)
    sy = ty * TILE_SIZE - int(camera.y)
    rect = pygame.Rect(sx, sy, TILE_SIZE, TILE_SIZE)
    outline = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
    pygame.draw.rect(outline, (255, 255, 255, 180), outline.get_rect(), 1)
    surface.blit(outline, rect.topleft)


def draw_save_message(surface, timer):
    if timer <= 0:
        return
    fade = min(1.0, timer / 0.5)
    alpha = int(220 * fade)
    font = pygame.font.SysFont(None, 18)
    text_surf = font.render("Saved", True, (240, 240, 240))
    text_surf.set_alpha(alpha)
    padding = 5
    w = text_surf.get_width() + padding * 2
    h = text_surf.get_height() + padding * 2
    x = surface.get_width() - w - 8
    y = 8

    bg = pygame.Surface((w, h), pygame.SRCALPHA)
    bg.fill((20, 20, 30, alpha))
    pygame.draw.rect(bg, (100, 100, 100, alpha), bg.get_rect(), 1)
    surface.blit(bg, (x, y))
    surface.blit(text_surf, (x + padding, y + padding))


# =============================================================================
# GAME
# =============================================================================
class Game:
    def __init__(self):
        pygame.init()
        try:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        except pygame.error:
            self.screen = pygame.display.set_mode((1280, 720))
        pygame.display.set_caption("Rat Game")

        load_assets()

        self.renderer = Renderer(self.screen)

        # Placeholder objects -- load_game() or reset_game() will fill them in.
        self.world = World(1, 1)
        self.player = Player(self, self.world, 0, 0)
        self.camera = Camera(self.renderer.logical_w, self.renderer.logical_h)

        self.gui = GUIManager()
        self.hotbar = Hotbar(self.player.inventory,
                             (self.renderer.logical_w,
                              self.renderer.logical_h))
        self.gui.add(self.hotbar)
        self.inv_screen = InventoryScreen(
            self.player.inventory,
            (self.renderer.logical_w, self.renderer.logical_h))
        self.inv_screen.visible = False
        self.inv_screen._game_ref = self
        self.gui.add(self.inv_screen)

        self.drops = []
        self.particles = []
        self._last_break_sound = 0
        self.save_message_timer = 0.0

        if not self.load_game():
            self.reset_game()

        self.clock = pygame.time.Clock()

    # -- setup ---------------------------------------------------------------
    def reset_game(self):
        self.world = World(WORLD_TILES_W, WORLD_TILES_H)
        self.player.world = self.world

        spawn_tx = 5
        spawn_ty = 0
        while (spawn_ty < self.world.height
               and not self.world.is_solid(spawn_tx, spawn_ty)):
            spawn_ty += 1

        self.player.x = float(spawn_tx * TILE_SIZE)
        self.player.y = float(spawn_ty * TILE_SIZE - PLAYER_HEIGHT)
        self.player.vel_y = 0.0
        self.player.on_ground = False
        self.player.facing_right = True
        self.player.crouching = False

        self.player.inventory.slots = [None] * len(self.player.inventory.slots)
        self.player.inventory.selected = 0
        self.player.inventory.add(1, 1)

        self.inv_screen.crafting.slots = [None] * 9
        self.inv_screen.dragging = None
        self.inv_screen.drag_origin = None
        self.inv_screen._refresh_result()

        self.drops = []
        self.particles = []

        self.camera.snap(self.player.rect,
                         self.world.width * TILE_SIZE,
                         self.world.height * TILE_SIZE)

    # -- save / load ---------------------------------------------------------
    def save_game(self):
        data = {
            "version": 1,
            "player": {
                "x": self.player.x,
                "y": self.player.y,
                "facing_right": self.player.facing_right,
                "crouching": self.player.crouching,
            },
            "camera": {
                "x": self.camera.x,
                "y": self.camera.y,
            },
            "inventory": list(self.player.inventory.slots),
            "selected_slot": self.player.inventory.selected,
            "crafting": list(self.inv_screen.crafting.slots),
            "world": {
                "width": self.world.width,
                "height": self.world.height,
                "tiles": self.world.tiles,
            },
        }
        try:
            with open(SAVE_PATH, "w") as f:
                json.dump(data, f)
            self.save_message_timer = SAVE_MESSAGE_DURATION
        except OSError as exc:
            print(f"warning: could not save '{SAVE_PATH}': {exc}")

    def load_game(self):
        if not os.path.exists(SAVE_PATH):
            return False
        try:
            with open(SAVE_PATH, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warning: could not load '{SAVE_PATH}': {exc}")
            return False

        try:
            world_data = data["world"]
            new_world = World(int(world_data["width"]),
                              int(world_data["height"]))
            new_world.tiles = [list(row) for row in world_data["tiles"]]
            self.world = new_world
            self.player.world = new_world

            player_data = data["player"]
            self.player.x = float(player_data["x"])
            self.player.y = float(player_data["y"])
            self.player.vel_y = 0.0
            self.player.on_ground = False
            self.player.facing_right = bool(player_data.get("facing_right",
                                                            True))
            self.player.crouching = bool(player_data.get("crouching", False))

            inv_data = data.get("inventory", [])
            for i in range(len(self.player.inventory.slots)):
                entry = inv_data[i] if i < len(inv_data) else None
                if entry is None:
                    self.player.inventory.slots[i] = None
                else:
                    self.player.inventory.slots[i] = {
                        "id": int(entry["id"]),
                        "amount": int(entry["amount"]),
                    }
            self.player.inventory.selected = int(
                data.get("selected_slot", 0))

            craft_data = data.get("crafting", [])
            self.inv_screen.crafting.slots = [None] * 9
            for i in range(9):
                entry = craft_data[i] if i < len(craft_data) else None
                if entry is None:
                    continue
                self.inv_screen.crafting.slots[i] = {
                    "id": int(entry["id"]),
                    "amount": int(entry["amount"]),
                }
            self.inv_screen.dragging = None
            self.inv_screen.drag_origin = None
            self.inv_screen._refresh_result()

            cam_data = data.get("camera")
            if cam_data:
                self.camera.x = float(cam_data["x"])
                self.camera.y = float(cam_data["y"])
            else:
                self.camera.snap(self.player.rect,
                                 self.world.width * TILE_SIZE,
                                 self.world.height * TILE_SIZE)

            self.drops = []
            self.particles = []
            return True
        except (KeyError, TypeError, ValueError) as exc:
            print(f"warning: save file is malformed ({exc})")
            return False

    # -- helpers -------------------------------------------------------------
    def spawn_particle(self, x, y, color):
        ang = random.uniform(-math.pi, 0)
        speed = random.uniform(40, 140)
        self.particles.append(Particle(
            x, y,
            math.cos(ang) * speed,
            math.sin(ang) * speed,
            color,
            life=random.uniform(0.25, 0.6),
            size=random.choice([1, 2, 2])))

    def _play_break_sound(self):
        now = pygame.time.get_ticks()
        if now - self._last_break_sound >= BREAK_SOUND_COOLDOWN_MS:
            _play("break")
            self._last_break_sound = now

    def break_block(self, tx, ty):
        tile_id = self.world.get_tile(tx, ty)
        if tile_id == World.AIR:
            return
        if tile_id == World.OAK:
            self._break_tree(tx, ty)
            return

        tile_def = TILE_DEFS.get(tile_id)
        self.world.set_tile(tx, ty, World.AIR)
        self._play_break_sound()

        if tile_def and tile_def.get("drop_item"):
            cx = tx * TILE_SIZE + TILE_SIZE / 2
            cy = ty * TILE_SIZE + TILE_SIZE / 2
            self.drops.append(ItemDrop(cx, cy, tile_def["drop_item"], 1))

        if tile_def:
            for _ in range(6):
                self.spawn_particle(
                    tx * TILE_SIZE + random.uniform(1, TILE_SIZE - 1),
                    ty * TILE_SIZE + random.uniform(1, TILE_SIZE - 1),
                    tile_def["particle_color"])

    def _break_tree(self, tx, ty):
        oak_tiles = set()
        queue = [(tx, ty)]
        while queue:
            cx, cy = queue.pop()
            if (cx, cy) in oak_tiles:
                continue
            if self.world.get_tile(cx, cy) != World.OAK:
                continue
            oak_tiles.add((cx, cy))
            queue.append((cx, cy - 1))

        leaf_tiles = set()
        queue = []
        for ox, oy in oak_tiles:
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                queue.append((ox + dx, oy + dy))
        while queue:
            lx, ly = queue.pop()
            if (lx, ly) in leaf_tiles:
                continue
            if self.world.get_tile(lx, ly) != World.LEAVES:
                continue
            leaf_tiles.add((lx, ly))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                queue.append((lx + dx, ly + dy))

        all_tiles = oak_tiles | leaf_tiles
        for (bx, by) in all_tiles:
            self.world.set_tile(bx, by, World.AIR)

        for (bx, by) in all_tiles:
            tile = World.OAK if (bx, by) in oak_tiles else World.LEAVES
            tile_def = TILE_DEFS.get(tile)
            if tile_def:
                self.spawn_particle(
                    bx * TILE_SIZE + random.uniform(2, TILE_SIZE - 2),
                    by * TILE_SIZE + random.uniform(2, TILE_SIZE - 2),
                    tile_def["particle_color"])

        cx = tx * TILE_SIZE + TILE_SIZE / 2
        cy = ty * TILE_SIZE + TILE_SIZE / 2

        oak_def = TILE_DEFS.get(World.OAK)
        if oak_def and oak_def.get("drop_item") and oak_tiles:
            self.drops.append(ItemDrop(cx, cy, oak_def["drop_item"],
                                       len(oak_tiles)))

        leaf_def = TILE_DEFS.get(World.LEAVES)
        if leaf_def and leaf_def.get("drop_item") and leaf_tiles:
            self.drops.append(ItemDrop(cx + 4, cy, leaf_def["drop_item"],
                                       len(leaf_tiles)))

        self._play_break_sound()

    def toggle_inventory(self):
        if self.inv_screen.visible:
            self.inv_screen.close()
            self.inv_screen.visible = False
            self.hotbar.visible = True
        else:
            self.inv_screen.visible = True
            self.hotbar.visible = False

    # -- per-frame drop processing ------------------------------------------
    def _update_drops(self, dt):
        pcx = self.player.x + PLAYER_WIDTH / 2
        pcy = self.player.y + self.player.height / 2

        for drop in list(self.drops):
            drop.update(self.world, dt)
            dx = drop.x - pcx
            dy = drop.y - pcy
            dist_sq = dx * dx + dy * dy

            if drop.can_pickup and dist_sq < PICKUP_CONTACT_RADIUS ** 2:
                leftover = self.player.inventory.add(drop.item_id, drop.amount)
                if leftover == 0:
                    self.drops.remove(drop)
                else:
                    drop.amount = leftover
                continue

            if dist_sq < PICKUP_VACUUM_RADIUS ** 2:
                drop.in_range_time += dt
                if drop.in_range_time >= PICKUP_VACUUM_TIME:
                    leftover = self.player.inventory.add(drop.item_id,
                                                         drop.amount)
                    if leftover == 0:
                        self.drops.remove(drop)
                    else:
                        drop.amount = leftover
            else:
                drop.in_range_time = 0.0

    # -- main loop -----------------------------------------------------------
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0

            if self.save_message_timer > 0:
                self.save_message_timer -= dt

            screen_mouse = pygame.mouse.get_pos()
            logical_mouse = self.renderer.screen_to_logical(screen_mouse)
            world_mouse = (logical_mouse[0] + self.camera.x,
                           logical_mouse[1] + self.camera.y)

            converted = []
            for event in pygame.event.get():
                if event.type in (pygame.MOUSEBUTTONDOWN,
                                  pygame.MOUSEBUTTONUP,
                                  pygame.MOUSEMOTION) and hasattr(event, "pos"):
                    lx, ly = self.renderer.screen_to_logical(event.pos)
                    event = pygame.event.Event(
                        event.type, {**event.dict,
                                     "pos": (int(lx), int(ly))})
                converted.append(event)

            for event in converted:
                if event.type == pygame.QUIT:
                    running = False
                    continue
                if event.type == pygame.KEYDOWN:
                    mods = pygame.KMOD_CTRL | pygame.KMOD_META
                    if event.key == pygame.K_s and (event.mod & mods):
                        self.save_game()
                        continue
                    if event.key == pygame.K_ESCAPE:
                        if self.inv_screen.visible:
                            self.toggle_inventory()
                        else:
                            running = False
                        continue
                    if event.key in (pygame.K_e, pygame.K_TAB):
                        self.toggle_inventory()
                        continue

                if self.gui.handle_event(event):
                    continue
                if not self.inv_screen.visible:
                    self.player.handle_event(event, world_mouse)

            inventory_open = self.inv_screen.visible
            keys = pygame.key.get_pressed()
            mouse_buttons = pygame.mouse.get_pressed()
            mining = mouse_buttons[0] and not inventory_open

            self.player.update(keys, mining, world_mouse, dt,
                               pause_input=inventory_open)
            self.camera.follow(self.player.rect,
                               self.world.width * TILE_SIZE,
                               self.world.height * TILE_SIZE)

            self._update_drops(dt)

            for p in list(self.particles):
                p.update(dt)
                if not p.alive:
                    self.particles.remove(p)

            surf = self.renderer.surface
            surf.fill(SKY_COLOR)
            draw_world(surf, self.world, self.camera)

            for drop in self.drops:
                drop.draw(surf, self.camera)

            if self.player.mining_tx is not None:
                draw_mining_overlay(surf, self.camera,
                                    self.player.mining_tx,
                                    self.player.mining_ty,
                                    self.player.mining_progress)

            for p in self.particles:
                p.draw(surf, self.camera)

            self.player.draw(surf, self.camera)
            draw_hover_outline(surf, self.camera, self.world,
                               world_mouse, self.player)

            self.gui.mouse_pos = logical_mouse
            self.gui.draw(surf)

            draw_save_message(surf, self.save_message_timer)

            self.renderer.present()
            pygame.display.flip()

        pygame.quit()


def main():
    Game().run()
    sys.exit()


if __name__ == "__main__":
    main()
