#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
РЫЦАРЬ И ДРАКОН — небольшая инди-игра на Python + pygame.

Запуск:
    pip install pygame-ce     (или pygame)
    python knight_game.py

Прохождение: тренировка -> 8 промежуточных боссов -> финальный дракон.
После каждой победы — награда в монетах и визит в лавку торговца Брома
(зелья лечения и усиления, покупка сопровождается мини-диалогом).
Инвентарь: стальной меч, лук, 120 стрел (колчан пополняется перед боем), зелья.
Прицел — курсор мыши. Все клавиши (в т.ч. зелья: W — лечение, S — усиление)
переназначаются в Настройки -> Управление. Прогресс сохраняется
в knight_save.json, настройки — в knight_settings.json.
"""
import array
import json
import math
import os
import random
import sys

import pygame

# ----------------------------------------------------------------------------
# Константы
# ----------------------------------------------------------------------------
W, H = 1280, 720
FPS = 60
GROUND_Y = 620
GRAV = 1800.0
ARROW_G = 420.0
START_ARROWS = 120
FINAL_STAGE = 9            # 0 — тренировка, 1–8 — боссы, 9 — дракон
MAX_POTIONS = 9
BUFF_TIME = 20.0
FPS_OPTIONS = [30, 60, 90, 120, 144, 240, 0]  # 0 = без ограничения

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(BASE_DIR, "knight_settings.json")
SAVE_PATH = os.path.join(BASE_DIR, "knight_save.json")

ACTIONS = [
    ("left", "Идти влево"),
    ("right", "Идти вправо"),
    ("jump", "Прыжок"),
    ("attack", "Атака / выстрел"),
    ("sword", "Достать меч"),
    ("bow", "Достать лук"),
    ("heal", "Зелье лечения"),
    ("buff", "Зелье усиления"),
]
DEFAULT_BINDS = {
    "left": ("k", pygame.K_a),
    "right": ("k", pygame.K_d),
    "jump": ("k", pygame.K_SPACE),
    "attack": ("m", 1),
    "sword": ("k", pygame.K_1),
    "bow": ("k", pygame.K_2),
    "heal": ("k", pygame.K_w),
    "buff": ("k", pygame.K_s),
}

SHOP_ITEMS = {
    "heal": {"name": "Зелье лечения", "price": 40, "desc": "Восстанавливает 50 здоровья"},
    "buff": {"name": "Зелье усиления", "price": 70, "desc": "20 с: урон ×1.5, скорость ×1.25"},
}


# ----------------------------------------------------------------------------
# Вспомогательные функции
# ----------------------------------------------------------------------------
def clamp(v, a, b):
    return max(a, min(b, v))


def lerp(a, b, t):
    return a + (b - a) * t


def sign(v):
    return 1 if v >= 0 else -1


def circle_rect(cx, cy, r, rect):
    nx = clamp(cx, rect.left, rect.right)
    ny = clamp(cy, rect.top, rect.bottom)
    return (cx - nx) ** 2 + (cy - ny) ** 2 <= r * r


def bind_name(b, short=False):
    kind, code = b
    if kind == "m":
        if short:
            return {1: "ЛКМ", 2: "СКМ", 3: "ПКМ"}.get(code, "Мышь%d" % code)
        return {1: "Левая кнопка мыши", 2: "Колёсико (СКМ)",
                3: "Правая кнопка мыши"}.get(code, "Кнопка мыши %d" % code)
    n = pygame.key.name(code)
    return n.upper() if n else str(code)


def load_font(size, bold=False):
    for name in ("segoeui", "arial", "dejavusans", "liberationsans", "notosans",
                 "freesans", "ubuntu", "helvetica", "tahoma", "verdana"):
        try:
            path = pygame.font.match_font(name, bold=bold)
        except Exception:
            path = None
        if path:
            return pygame.font.Font(path, size)
    return pygame.font.Font(None, int(size * 1.25))


def draw_text(surf, font, text, pos, color=(255, 255, 255), anchor="topleft", shadow=True):
    img = font.render(text, True, color)
    r = img.get_rect()
    setattr(r, anchor, pos)
    if shadow:
        surf.blit(font.render(text, True, (0, 0, 0)), r.move(2, 2))
    surf.blit(img, r)
    return r


def panel(surf, rect, color=(10, 10, 24, 170), radius=10, border=None):
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(s, color, s.get_rect(), border_radius=radius)
    if border:
        pygame.draw.rect(s, border, s.get_rect(), 2, border_radius=radius)
    surf.blit(s, rect.topleft)


def vgradient(w, h, top, bot):
    s = pygame.Surface((w, h))
    for y in range(h):
        t = y / max(1, h - 1)
        c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
        pygame.draw.line(s, c, (0, y), (w, y))
    return s


# ----------------------------------------------------------------------------
# Настройки
# ----------------------------------------------------------------------------
class Settings:
    def __init__(self):
        self.binds = dict(DEFAULT_BINDS)
        self.volume = 0.6
        self.fullscreen = False
        self.show_fps = False
        self.fps_limit = FPS
        self.completed = False   # игра пройдена (открывает «быстрый старт»)
        self.load()

    def load(self):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.volume = clamp(float(d.get("volume", self.volume)), 0.0, 1.0)
            self.fullscreen = bool(d.get("fullscreen", self.fullscreen))
            self.show_fps = bool(d.get("show_fps", self.show_fps))
            self.completed = bool(d.get("completed", False))
            fl = int(d.get("fps_limit", self.fps_limit))
            self.fps_limit = fl if fl in FPS_OPTIONS else FPS
            for a, v in d.get("binds", {}).items():
                if a in DEFAULT_BINDS and isinstance(v, list) and len(v) == 2 and v[0] in ("k", "m"):
                    self.binds[a] = (v[0], int(v[1]))
        except Exception:
            pass

    def save(self):
        try:
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump({
                    "volume": self.volume,
                    "fullscreen": self.fullscreen,
                    "show_fps": self.show_fps,
                    "fps_limit": self.fps_limit,
                    "completed": self.completed,
                    "binds": {a: list(b) for a, b in self.binds.items()},
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def reset_binds(self):
        self.binds = dict(DEFAULT_BINDS)


# ----------------------------------------------------------------------------
# Ввод (учитывает переназначенные клавиши и кнопки мыши)
# ----------------------------------------------------------------------------
class Input:
    def __init__(self, settings):
        self.s = settings
        self.cur = {a: False for a, _ in ACTIONS}
        self.prev = dict(self.cur)

    def update(self):
        keys = pygame.key.get_pressed()
        mb = pygame.mouse.get_pressed(3)
        for a, _ in ACTIONS:
            kind, code = self.s.binds[a]
            self.prev[a] = self.cur[a]
            try:
                self.cur[a] = bool(keys[code]) if kind == "k" else bool(mb[code - 1])
            except Exception:
                self.cur[a] = False

    def down(self, a):
        return self.cur[a]

    def pressed(self, a):
        return self.cur[a] and not self.prev[a]


# ----------------------------------------------------------------------------
# Звук (синтезируется кодом, без внешних файлов)
# ----------------------------------------------------------------------------
class Audio:
    def __init__(self, settings):
        self.s = settings
        self.sounds = {}
        self.ok = False
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            self.channels = pygame.mixer.get_init()[2]
            rnd = random.Random(1)
            mk = lambda *a, **k: self._make(rnd, *a, **k)
            self.sounds = {
                "shoot": mk(950, 260, 0.16, 0.35, 0.25),
                "hit": mk(320, 110, 0.12, 0.5, 0.5),
                "sword": mk(700, 180, 0.2, 0.35, 0.7),
                "hurt": mk(240, 70, 0.3, 0.45, 0.15, "square"),
                "roar": mk(120, 45, 1.0, 0.5, 0.35, "square"),
                "fire": mk(260, 90, 0.3, 0.35, 0.8),
                "click": mk(900, 900, 0.04, 0.3, 0.0),
                "ding": mk(1300, 1300, 0.3, 0.3, 0.0),
                "portal": mk(300, 900, 0.6, 0.3, 0.0),
                "boom": mk(160, 40, 0.5, 0.5, 0.8),
                "coin": mk(1000, 1600, 0.18, 0.3, 0.0),
                "heal": mk(400, 900, 0.35, 0.3, 0.0),
                "buff": mk(200, 700, 0.4, 0.35, 0.1, "square"),
            }
            self.ok = True
        except Exception:
            self.ok = False

    def _make(self, rnd, f0, f1, dur, vol, noise, wave="sine"):
        sr = 22050
        n = int(sr * dur)
        buf = array.array("h")
        phase = 0.0
        for i in range(n):
            t = i / n
            f = f0 + (f1 - f0) * t
            phase += 2 * math.pi * f / sr
            sv = math.sin(phase)
            v = sv if wave == "sine" else (1.0 if sv > 0 else -1.0)
            v = v * (1 - noise) + rnd.uniform(-1, 1) * noise
            v *= (1 - t) ** 1.5
            s = int(v * vol * 32767)
            buf.append(s)
            if self.channels == 2:
                buf.append(s)
        return pygame.mixer.Sound(buffer=buf.tobytes())

    def play(self, name, vol=1.0):
        if not self.ok:
            return
        s = self.sounds.get(name)
        if s:
            s.set_volume(clamp(self.s.volume * vol, 0, 1))
            s.play()


# ----------------------------------------------------------------------------
# Игровые объекты
# ----------------------------------------------------------------------------
class Arrow:
    def __init__(self, x, y, vx, vy, dmg, power):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.dmg = dmg
        self.power = power
        self.stuck = False
        self.attach = None  # (мишень, смещение по x) — стрела движется вместе с целью
        self.dead = False
        self.timer = 0.0
        self.angle = math.atan2(vy, vx)

    def draw(self, surf):
        if not self.stuck:
            self.angle = math.atan2(self.vy, self.vx)
        dx, dy = math.cos(self.angle), math.sin(self.angle)
        tail = (self.x - dx * 46, self.y - dy * 46)
        pygame.draw.line(surf, (205, 175, 115), tail, (self.x, self.y), 3)
        px, py = -dy, dx
        tip = [(self.x + dx * 4, self.y + dy * 4),
               (self.x - dx * 8 + px * 4, self.y - dy * 8 + py * 4),
               (self.x - dx * 8 - px * 4, self.y - dy * 8 - py * 4)]
        pygame.draw.polygon(surf, (190, 195, 205), tip)
        for k in (-1, 1):
            a = (tail[0] + dx * 10, tail[1] + dy * 10)
            b = (tail[0] - dx * 2 + px * 5 * k, tail[1] - dy * 2 + py * 5 * k)
            pygame.draw.line(surf, (200, 50, 50), a, b, 2)


STYLE_COL = {
    "fire": (255, 150, 40), "meteor": (255, 110, 40), "knife": (210, 210, 225),
    "goo": (110, 220, 110), "wave": (176, 150, 110), "rock": (150, 140, 130),
    "ice": (170, 225, 255), "poison": (150, 230, 90), "crescent": (170, 130, 255),
    "skull": (200, 255, 200), "orb": (180, 110, 255), "firewave": (255, 140, 40),
}


class Fireball:
    """Снаряд врага. style определяет вид и поведение."""

    def __init__(self, x, y, vx, vy, dmg=12, r=14, style="fire", gravity=0.0, ground=False,
                 life=6.0, homing=0.0, shootable=False, pierce=False, solid=True):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.dmg, self.r = dmg, r
        self.style = style
        self.gravity = gravity
        self.ground = ground          # скользит по земле (ударные волны)
        self.life = life
        self.homing = homing          # скорость поворота (рад/с), 0 — не самонаводится
        self.shootable = shootable    # можно сбить стрелой или мечом
        self.pierce = pierce          # не исчезает при попадании в игрока
        self.solid = solid            # взрывается о землю и платформы
        self.dead = False

    def draw(self, surf, t):
        x, y, r, st = int(self.x), int(self.y), self.r, self.style
        a = math.atan2(self.vy, self.vx)
        dx, dy = math.cos(a), math.sin(a)
        if st in ("fire", "meteor"):
            rr = r + int(math.sin(t * 25) * 2)
            pygame.draw.circle(surf, (200, 60, 20), (x, y), rr + 5)
            pygame.draw.circle(surf, (255, 140, 30), (x, y), rr)
            pygame.draw.circle(surf, (255, 235, 130), (x, y), max(3, rr - 7))
        elif st == "knife":
            pygame.draw.line(surf, (120, 90, 60), (x - dx * 14, y - dy * 14), (x, y), 4)
            pygame.draw.polygon(surf, (225, 228, 235), [(x + dx * 18, y + dy * 18),
                                                        (x - dy * 5, y + dx * 5), (x + dy * 5, y - dx * 5)])
        elif st in ("goo", "poison"):
            col = (110, 220, 110) if st == "goo" else (146, 208, 70)
            pygame.draw.circle(surf, col, (x, y), r)
            pygame.draw.circle(surf, (50, 120, 50), (x, y), r, 2)
            pygame.draw.circle(surf, (230, 255, 230), (x - r // 3, y - r // 3), max(2, r // 4))
        elif st == "rock":
            pygame.draw.circle(surf, (124, 116, 108), (x, y), r)
            pygame.draw.circle(surf, (78, 72, 68), (x, y), r, 3)
            pygame.draw.line(surf, (78, 72, 68), (x - r // 2, y - r // 3), (x + r // 3, y + r // 2), 2)
        elif st == "ice":
            pts = [(x + dx * r * 1.8, y + dy * r * 1.8), (x - dy * r * 0.6, y + dx * r * 0.6),
                   (x - dx * r * 1.2, y - dy * r * 1.2), (x + dy * r * 0.6, y - dx * r * 0.6)]
            pygame.draw.polygon(surf, (190, 235, 255), pts)
            pygame.draw.polygon(surf, (255, 255, 255), pts, 2)
        elif st == "wave":
            pygame.draw.ellipse(surf, (176, 150, 110), (x - int(r * 1.3), y - r, int(r * 2.6), r * 2))
            pygame.draw.ellipse(surf, (110, 92, 66), (x - int(r * 1.3), y - r, int(r * 2.6), r * 2), 3)
        elif st == "firewave":
            for k in range(-2, 3):
                bx = x + k * r * 0.55
                h = r * (1.6 - abs(k) * 0.3) + math.sin(t * 20 + k) * 4
                pygame.draw.polygon(surf, (255, 140, 40), [(bx - 10, y + r), (bx + 10, y + r), (bx, y + r - h * 1.4)])
                pygame.draw.polygon(surf, (255, 230, 120), [(bx - 5, y + r), (bx + 5, y + r), (bx, y + r - h * 0.8)])
        elif st == "crescent":
            rect = pygame.Rect(x - r, y - int(r * 1.6), r * 2, int(r * 3.2))
            if self.vx >= 0:
                pygame.draw.arc(surf, (170, 130, 255), rect, -1.0, 1.0, 8)
                pygame.draw.arc(surf, (230, 210, 255), rect, -0.9, 0.9, 3)
            else:
                pygame.draw.arc(surf, (170, 130, 255), rect, math.pi - 1.0, math.pi + 1.0, 8)
                pygame.draw.arc(surf, (230, 210, 255), rect, math.pi - 0.9, math.pi + 0.9, 3)
        elif st == "skull":
            pygame.draw.circle(surf, (120, 255, 160), (x, y), r + 3, 2)
            pygame.draw.circle(surf, (228, 244, 228), (x, y), r)
            pygame.draw.rect(surf, (228, 244, 228), (x - r // 2, y + r // 2, r, r // 2))
            pygame.draw.circle(surf, (30, 40, 30), (x - r // 3, y - 2), 4)
            pygame.draw.circle(surf, (30, 40, 30), (x + r // 3, y - 2), 4)
        elif st == "orb":
            pygame.draw.circle(surf, (150, 90, 230), (x, y), r + 2)
            pygame.draw.circle(surf, (226, 192, 255), (x, y), max(3, r - 4))
        else:
            pygame.draw.circle(surf, (255, 255, 255), (x, y), r)


class Player:
    def __init__(self, x, bag=None):
        self.bag = bag if bag is not None else {"gold": 0, "heal": 0, "buff": 0}
        self.buff_t = 0.0
        self.x, self.y = float(x), float(GROUND_Y)
        self.vx = self.vy = 0.0
        self.on_ground = True
        self.hp = self.max_hp = 100
        self.inv = 0.0
        self.stun = 0.0
        self.weapon = "sword"
        self.arrows = START_ARROWS
        self.draw_t = 0.0
        self.shoot_cd = 0.0
        self.swing = -1.0
        self.swing_cd = 0.0
        self.swing_id = 0
        self.facing = 1
        self.anim = 0.0
        self.mouse = (W // 2, H // 2)

    def rect(self):
        return pygame.Rect(int(self.x - 17), int(self.y - 60), 34, 60)

    def shoulder(self):
        return (self.x, self.y - 38)

    def sword_active(self):
        return 0.06 <= self.swing <= 0.2

    def sword_rect(self):
        left = self.x + 10 if self.facing > 0 else self.x - 100
        return pygame.Rect(int(left), int(self.y - 90), 90, 90)

    def dmg_mult(self):
        return 1.5 if self.buff_t > 0 else 1.0

    def speed_mult(self):
        return 1.25 if self.buff_t > 0 else 1.0

    def power(self):
        return min(1.0, self.draw_t / 0.7)

    def hurt(self, dmg, src_x, w):
        if self.inv > 0 or self.hp <= 0:
            return
        self.hp = max(0, self.hp - dmg)
        self.inv = 1.0
        self.stun = 0.3
        self.vx = sign(self.x - src_x) * 340
        self.vy = -380
        self.on_ground = False
        self.draw_t = 0.0
        w.hurt_flash = 0.35
        w.audio.play("hurt")
        w.particles_burst(self.x, self.y - 30, 14, (200, 40, 40), 220, 0.6)
        w.popup("-%d" % dmg, self.x, self.y - 80, (255, 90, 90))

    def update(self, dt, inp, w, mouse):
        self.mouse = mouse
        self.inv = max(0.0, self.inv - dt)
        self.stun = max(0.0, self.stun - dt)
        self.swing_cd -= dt
        self.shoot_cd -= dt
        self.buff_t = max(0.0, self.buff_t - dt)
        if self.swing >= 0:
            self.swing += dt
            if self.swing > 0.3:
                self.swing = -1.0
        ctrl = self.stun <= 0

        # движение
        move = 0
        if ctrl:
            move = (1 if inp.down("right") else 0) - (1 if inp.down("left") else 0)
            k = min(1.0, dt * (14 if self.on_ground else 7))
            self.vx += (move * 270 * self.speed_mult() - self.vx) * k
        else:
            self.vx *= (1 - min(1.0, dt * 3))
        if ctrl and inp.pressed("jump") and self.on_ground:
            self.vy = -720
            self.on_ground = False
            w.particles_burst(self.x, self.y, 6, (190, 170, 130), 90, 0.4, grav=200)
        if not inp.down("jump") and self.vy < -300:
            self.vy += GRAV * dt * 1.2

        if self.swing < 0:
            self.facing = 1 if mouse[0] >= self.x else -1
        if self.on_ground:
            self.anim += dt * abs(self.vx) / 26.0

        # выбор оружия
        if inp.pressed("sword") and self.weapon != "sword":
            self.weapon = "sword"
            self.draw_t = 0.0
            w.audio.play("click")
        elif inp.pressed("bow") and self.weapon != "bow":
            self.weapon = "bow"
            self.swing = -1.0
            w.audio.play("click")

        # зелья
        if inp.pressed("heal"):
            if self.bag["heal"] <= 0:
                w.popup("Нет зелий лечения!", self.x, self.y - 90, (255, 200, 90))
            elif self.hp >= self.max_hp:
                w.popup("Здоровье полное", self.x, self.y - 90, (200, 255, 200))
            else:
                self.bag["heal"] -= 1
                gain = min(50, self.max_hp - self.hp)
                self.hp += gain
                w.audio.play("heal")
                w.particles_burst(self.x, self.y - 30, 14, (110, 240, 130), 200, 0.7, grav=-100)
                w.popup("+%d" % gain, self.x, self.y - 90, (120, 255, 140))
        if inp.pressed("buff"):
            if self.bag["buff"] <= 0:
                w.popup("Нет зелий усиления!", self.x, self.y - 90, (255, 200, 90))
            elif self.buff_t > 0:
                w.popup("Усиление уже действует", self.x, self.y - 90, (255, 230, 150))
            else:
                self.bag["buff"] -= 1
                self.buff_t = BUFF_TIME
                w.audio.play("buff")
                w.particles_burst(self.x, self.y - 30, 18, (255, 210, 80), 220, 0.8, grav=-100)
                w.popup("Усиление!", self.x, self.y - 90, (255, 220, 90))

        # атака
        allowed = ctrl and w.time > 0.3
        if self.weapon == "sword":
            if allowed and inp.pressed("attack") and self.swing < 0 and self.swing_cd <= 0:
                self.swing = 0.0
                self.swing_cd = 0.4
                self.swing_id += 1
                w.audio.play("sword")
        else:
            if allowed and inp.down("attack") and self.arrows > 0:
                if self.shoot_cd <= 0:
                    self.draw_t = min(self.draw_t + dt * (1.3 if self.buff_t > 0 else 1.0), 1.0)
            else:
                if self.draw_t > 0:
                    if self.draw_t >= 0.06 and self.arrows > 0 and ctrl:
                        self.fire(w)
                    self.draw_t = 0.0
            if allowed and inp.pressed("attack") and self.arrows <= 0:
                w.popup("Нет стрел!", self.x, self.y - 90, (255, 200, 90))

        # физика
        prev_y = self.y
        self.vy += GRAV * dt
        self.x = clamp(self.x + self.vx * dt, 24, W - 24)
        self.y += self.vy * dt
        self.on_ground = False
        if self.y >= GROUND_Y:
            self.y = GROUND_Y
            self.vy = 0.0
            self.on_ground = True
        elif self.vy >= 0:
            for p in w.platforms:
                if p.left - 8 < self.x < p.right + 8 and prev_y <= p.top + 6 and self.y >= p.top:
                    self.y = float(p.top)
                    self.vy = 0.0
                    self.on_ground = True
                    break

        if self.sword_active():
            w.level.on_sword(self.sword_rect(), self.swing_id, w)
            w.sword_projectiles(self.sword_rect())

    def fire(self, w):
        sx, sy = self.shoulder()
        ang = math.atan2(self.mouse[1] - sy, self.mouse[0] - sx)
        power = self.power()
        speed = 560 + 900 * power
        dmg = (6 + 16 * power) * self.dmg_mult()
        w.arrows.append(Arrow(sx + math.cos(ang) * 30, sy + math.sin(ang) * 30,
                              math.cos(ang) * speed, math.sin(ang) * speed, dmg, power))
        self.arrows -= 1
        self.shoot_cd = 0.18
        w.audio.play("shoot")

    # ---------------- отрисовка ----------------
    def draw_preview(self, surf, w):
        """Пунктирная траектория при натянутой тетиве (обрывается на первом препятствии)."""
        if self.weapon != "bow" or self.draw_t < 0.08:
            return
        sx, sy = self.shoulder()
        ang = math.atan2(self.mouse[1] - sy, self.mouse[0] - sx)
        power = self.power()
        speed = 560 + 900 * power
        vx, vy = math.cos(ang) * speed, math.sin(ang) * speed
        px, py = sx + math.cos(ang) * 30, sy + math.sin(ang) * 30
        step = 0.008
        for i in range(1, 150):
            t = i * step
            x = px + vx * t
            y = py + vy * t + 0.5 * ARROW_G * t * t
            if x < 0 or x > W or y > GROUND_Y or w.blocked(x, y):
                pygame.draw.circle(surf, (255, 255, 255), (int(x), int(min(y, GROUND_Y))), 5, 1)
                break
            if i % 6 == 0:
                pygame.draw.circle(surf, (255, 255, 255), (int(x), int(y)), 2)

    def draw(self, surf):
        if self.inv > 0 and int(self.inv * 20) % 2 == 0:
            return
        x, y = int(self.x), int(self.y)
        f = self.facing
        if self.buff_t > 0:
            pulse = 38 + int(math.sin(self.buff_t * 9) * 4)
            pygame.draw.circle(surf, (255, 210, 80), (x, y - 30), pulse, 2)
            pygame.draw.circle(surf, (255, 240, 160), (x, y - 30), pulse - 8, 1)
        moving = self.on_ground and abs(self.vx) > 30
        ls = math.sin(self.anim) * 8 if moving else (5 if not self.on_ground else 0)
        # ноги
        pygame.draw.rect(surf, (70, 72, 90), (x - 13 + ls, y - 20, 11, 20), border_radius=3)
        pygame.draw.rect(surf, (70, 72, 90), (x + 2 - ls, y - 20, 11, 20), border_radius=3)
        pygame.draw.rect(surf, (40, 40, 52), (x - 14 + ls, y - 6, 13, 6), border_radius=2)
        pygame.draw.rect(surf, (40, 40, 52), (x + 1 - ls, y - 6, 13, 6), border_radius=2)
        # щит за спиной
        pygame.draw.ellipse(surf, (45, 70, 140), (x - f * 20 - 9, y - 44, 18, 26))
        pygame.draw.ellipse(surf, (220, 190, 70), (x - f * 20 - 9, y - 44, 18, 26), 2)
        # корпус
        pygame.draw.rect(surf, (172, 178, 192), (x - 16, y - 42, 32, 24), border_radius=5)
        pygame.draw.rect(surf, (50, 90, 170), (x - 8, y - 42, 16, 24))
        pygame.draw.line(surf, (230, 200, 80), (x, y - 40), (x, y - 22), 2)
        pygame.draw.line(surf, (230, 200, 80), (x - 5, y - 34), (x + 5, y - 34), 2)
        pygame.draw.rect(surf, (110, 85, 55), (x - 16, y - 21, 32, 4))
        # голова
        pygame.draw.polygon(surf, (200, 45, 45), [(x - f * 2, y - 61), (x - f * 18, y - 66), (x - f * 13, y - 52)])
        pygame.draw.circle(surf, (192, 197, 212), (x, y - 51), 10)
        pygame.draw.rect(surf, (30, 30, 40), (x + (f * 3 if f > 0 else -9), y - 54, 6, 3))
        # оружие
        sx, sy = self.shoulder()
        if self.weapon == "sword":
            self._draw_sword(surf, sx, sy)
        else:
            self._draw_bow(surf, sx, sy)

    def _draw_sword(self, surf, sx, sy):
        f = self.facing
        hx, hy = sx + f * 12, sy + 2
        if self.swing >= 0:
            t = clamp(self.swing / 0.28, 0, 1)
            th = math.radians(lerp(-120, 60, t))
            # след от взмаха
            fan = pygame.Surface((200, 200), pygame.SRCALPHA)
            pts = [(100, 100)]
            steps = 10
            for i in range(steps + 1):
                a = math.radians(lerp(-120, math.degrees(th), i / steps))
                pts.append((100 + f * math.cos(a) * 78, 100 + math.sin(a) * 78))
            if len(pts) > 2:
                pygame.draw.polygon(fan, (255, 255, 255, 70), pts)
            surf.blit(fan, (hx - 100, hy - 100))
        else:
            th = math.radians(-62)
        dx, dy = f * math.cos(th), math.sin(th)
        tip = (hx + dx * 58, hy + dy * 58)
        pygame.draw.line(surf, (110, 115, 130), (hx, hy), tip, 7)
        pygame.draw.line(surf, (232, 236, 245), (hx, hy), tip, 4)
        gx, gy = hx + dx * 8, hy + dy * 8
        pygame.draw.line(surf, (220, 180, 60), (gx - dy * 8, gy + dx * 8), (gx + dy * 8, gy - dx * 8), 4)
        pygame.draw.circle(surf, (220, 180, 60), (int(hx - dx * 4), int(hy - dy * 4)), 3)
        pygame.draw.line(surf, (172, 178, 192), (sx, sy), (hx, hy), 6)

    def _draw_bow(self, surf, sx, sy):
        ang = math.atan2(self.mouse[1] - sy, self.mouse[0] - sx)
        ux, uy = math.cos(ang), math.sin(ang)
        vx, vy = -uy, ux
        pull = self.power()
        pts = []
        for i in range(-4, 5):
            t = i / 4.0
            pts.append((sx + ux * (24 - 15 * t * t) + vx * t * 32,
                        sy + uy * (24 - 15 * t * t) + vy * t * 32))
        nock = (sx + ux * (10 - 14 * pull), sy + uy * (10 - 14 * pull))
        pygame.draw.line(surf, (172, 178, 192), (sx, sy), (sx + ux * 22, sy + uy * 22), 6)
        pygame.draw.lines(surf, (120, 78, 40), False, pts, 5)
        pygame.draw.line(surf, (235, 235, 225), pts[0], nock, 1)
        pygame.draw.line(surf, (235, 235, 225), pts[-1], nock, 1)
        if self.arrows > 0:
            tipx, tipy = nock[0] + ux * 46, nock[1] + uy * 46
            pygame.draw.line(surf, (205, 175, 115), nock, (tipx, tipy), 3)
            pygame.draw.polygon(surf, (190, 195, 205),
                                [(tipx + ux * 7, tipy + uy * 7),
                                 (tipx + vx * 4, tipy + vy * 4),
                                 (tipx - vx * 4, tipy - vy * 4)])


# ----------------------------------------------------------------------------
# Боссы
# ----------------------------------------------------------------------------
WARN_COL = {"rock": (210, 190, 130), "ice": (150, 215, 255), "meteor": (255, 120, 50)}


def lob(x0, y0, x1, y1, T, g):
    """Начальная скорость для дуги из (x0, y0) в (x1, y1) за T секунд при гравитации g."""
    return (x1 - x0) / T, (y1 - y0 - 0.5 * g * T * T) / T


class Boss:
    name = "Босс"
    difficulty = 1
    reward = 40
    max_hp = 100
    blood = (200, 60, 50)
    dying_time = 2.2
    flying = False

    def __init__(self):
        self.hp = float(self.max_hp)
        self.t = 0.0
        self.flash = 0.0
        self.state = "alive"
        self.mode = "idle"
        self.mt = 0.0
        self.intro = 1.2
        self.x = W * 0.72
        self.y = float(GROUND_Y)
        self.vx = 0.0
        self.vy = 0.0
        self.on_ground = True
        self.f = -1
        self.ghost = False
        self.last_swing = -1
        self.done = False
        self.dt_t = 0.0
        self.expl_cd = 0.0
        self.warns = []

    # ---- общее ----
    def center(self):
        return (self.x, self.y - 60)

    def hitboxes(self):
        return []

    def hint(self):
        return ""

    def low(self):
        return self.hp < self.max_hp * 0.5

    def invulnerable(self):
        return self.state == "dying" or self.intro > 0 or self.ghost

    def face(self, w):
        if abs(w.player.x - self.x) > 30:
            self.f = 1 if w.player.x > self.x else -1

    def gravity(self, dt):
        was = self.on_ground
        self.vy += GRAV * dt
        self.y += self.vy * dt
        self.on_ground = False
        if self.y >= GROUND_Y:
            self.y = float(GROUND_Y)
            self.vy = 0.0
            self.on_ground = True
        return (not was) and self.on_ground

    def C(self, c):
        k = min(1.0, self.flash / 0.12) * 0.75 if self.flash > 0 else 0.0
        return tuple(int(c[i] + (255 - c[i]) * k) for i in range(3))

    def touch(self, w, rect, dmg, src=None):
        p = w.player
        if rect.colliderect(p.rect()):
            p.hurt(dmg, self.x if src is None else src, w)

    def hit(self, dmg, head, w):
        if self.invulnerable():
            return False
        d = dmg * (2 if head else 1)
        self.hp -= d
        self.flash = 0.12
        cx, cy = self.center()
        if head:
            for r, kind in self.hitboxes():
                if kind == "head":
                    cx, cy = r.center
                    break
        w.popup(("Крит! %d" if head else "%d") % int(d), cx, cy - 40,
                (255, 220, 70) if head else (255, 255, 255))
        w.particles_burst(cx, cy, 8, self.blood, 200, 0.5)
        w.audio.play("hit")
        if self.hp <= 0:
            self.hp = 0.0
            self.die(w)
        return True

    def die(self, w):
        self.state = "dying"
        self.dt_t = 0.0
        self.warns = []
        w.fireballs.clear()
        self.on_die(w)
        w.audio.play("roar")

    def on_die(self, w):
        pass

    # ---- предупреждения (падающие камни, лёд, метеоры) ----
    def tick_warns(self, dt, w):
        keep = []
        for wr in self.warns:
            wr[1] -= dt
            if wr[1] > 0:
                keep.append(wr)
                continue
            x, kind = wr[0], wr[2]
            if kind == "rock":
                w.fireballs.append(Fireball(x, -30, 0, 60, dmg=14, r=18, style="rock", gravity=1300))
            elif kind == "ice":
                w.fireballs.append(Fireball(x, -30, 0, 200, dmg=12, r=12, style="ice", gravity=900))
            elif kind == "meteor":
                w.fireballs.append(Fireball(x, -40, random.uniform(-60, 60), 300, dmg=16, r=20,
                                            style="meteor", gravity=900))
        self.warns = keep

    def draw_warns(self, surf):
        for x, t, kind in self.warns:
            col = WARN_COL.get(kind, (255, 255, 255))
            a = 35 + int(55 * clamp(1.0 - t, 0.0, 1.0))
            panel(surf, pygame.Rect(int(x - 22), 0, 44, GROUND_Y), (col[0], col[1], col[2], a), 0)
            pygame.draw.ellipse(surf, col, (int(x - 30), GROUND_Y - 8, 60, 16), 3)

    # ---- обновление ----
    def update(self, dt, w):
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        if self.state == "dying":
            self._dying(dt, w)
            return
        self.tick_warns(dt, w)
        if self.intro > 0:
            self.intro -= dt
            if not self.flying:
                self.gravity(dt)
            return
        self.think(dt, w)
        self.x = clamp(self.x, 50, W - 50)

    def think(self, dt, w):
        pass

    def dying_motion(self, dt):
        if not self.flying:
            self.gravity(dt)

    def _dying(self, dt, w):
        self.dt_t += dt
        self.dying_motion(dt)
        self.expl_cd -= dt
        if self.expl_cd <= 0:
            self.expl_cd = 0.12
            cx, cy = self.center()
            w.particles_burst(cx + random.uniform(-60, 60), cy + random.uniform(-60, 50), 10,
                              random.choice([(255, 160, 40), (255, 80, 30), (255, 230, 120)]), 260, 0.8)
            if random.random() < 0.3:
                w.audio.play("boom", 0.5)
        if self.dt_t > self.dying_time and not self.done:
            self.done = True
            w.finished = "win" if w.level.final else "clear"

    # ---- отрисовка ----
    def draw(self, surf, w):
        if self.state == "dying" and self.dt_t > self.dying_time - 0.6 and int(self.dt_t * 24) % 2 == 0:
            return
        self.draw_body(surf, w)
        self.draw_warns(surf)

    def ghost_alpha(self):
        if self.mode == "vanish":
            return int(255 * clamp(self.mt / 0.5, 0.0, 1.0))
        return int(255 * clamp(1.0 - self.mt / 0.5, 0.0, 1.0))

    def draw_body(self, surf, w):
        if self.ghost:
            tmp = pygame.Surface((300, 340), pygame.SRCALPHA)
            self.paint(tmp, 150, 170, w)
            tmp.set_alpha(self.ghost_alpha())
            surf.blit(tmp, (int(self.x) - 150, int(self.y) - 170))
        else:
            self.paint(surf, int(self.x), int(self.y), w)

    def paint(self, surf, ox, oy, w):
        pass


# ----------------------------------------------------------------------------
# 1. Слизень-великан
# ----------------------------------------------------------------------------
class SlimeBoss(Boss):
    name = "Слизень-великан"
    difficulty = 1
    reward = 40
    max_hp = 130
    blood = (90, 210, 100)

    def __init__(self):
        super().__init__()
        self.x = 900.0
        self.st = 0.0
        self.hops = 0
        self.air = False

    def center(self):
        return (self.x, self.y - 55)

    def body_rect(self):
        return pygame.Rect(int(self.x - 72), int(self.y - 112), 144, 112)

    def hitboxes(self):
        x, y = int(self.x), int(self.y)
        return [(pygame.Rect(x - 28, y - 100, 56, 48), "head"), (self.body_rect(), "body")]

    def hint(self):
        return "Цельтесь в жёлтое ядро — двойной урон!"

    def think(self, dt, w):
        p = w.player
        landed = self.gravity(dt)
        enraged = self.low()
        if self.air:
            self.x = clamp(self.x + self.vx * dt, 80, W - 80)
        if landed and self.air:
            self.air = False
            self.vx = 0.0
            self.st = 0.0
            w.particles_burst(self.x, GROUND_Y, 16, (110, 210, 120), 260, 0.6, grav=300)
            w.audio.play("boom", 0.6)
            self.hops += 1
            if self.hops % 3 == 0:
                n = 5 if enraged else 3
                for i in range(n):
                    vx = (i - (n - 1) / 2.0) * 190
                    w.fireballs.append(Fireball(self.x, self.y - 100, vx, -620, dmg=9, r=11,
                                                style="goo", gravity=900))
        elif self.on_ground:
            self.st += dt
            if self.st >= (0.55 if enraged else 0.9):
                dist = abs(p.x - self.x)
                self.vx = sign(p.x - self.x) * clamp(dist * 1.1 + 60, 220, 440)
                self.vy = -860.0
                self.on_ground = False
                self.air = True
                self.st = 0.0
        self.touch(w, self.body_rect().inflate(-16, -16), 13)

    def paint(self, surf, ox, oy, w):
        k = math.sin(self.t * 6) * 0.05
        if self.on_ground:
            sw, sh = int(150 * (1 + k)), int(112 * (1 - k))
        else:
            sw, sh = 128, 138
        body = pygame.Rect(ox - sw // 2, oy - sh, sw, sh)
        pygame.draw.ellipse(surf, self.C((70, 185, 90)), body)
        pygame.draw.ellipse(surf, self.C((38, 135, 62)), body, 4)
        pygame.draw.ellipse(surf, self.C((170, 235, 178)),
                            pygame.Rect(ox - int(sw * 0.36), oy - int(sh * 0.9), int(sw * 0.3), int(sh * 0.2)))
        cy = oy - int(sh * 0.42)
        pygame.draw.circle(surf, self.C((250, 215, 80)), (ox, cy), 24)
        pygame.draw.circle(surf, self.C((255, 245, 170)), (ox, cy), 12)
        look = clamp((w.player.x - self.x) / 60.0, -1, 1) * 4
        for ex in (-26, 26):
            ec = (ox + ex, oy - int(sh * 0.72))
            pygame.draw.circle(surf, (255, 255, 255), ec, 10)
            pygame.draw.circle(surf, (20, 20, 30), (int(ec[0] + look), ec[1]), 5)


# ----------------------------------------------------------------------------
# 2. Гоблин-разбойник
# ----------------------------------------------------------------------------
class GoblinBoss(Boss):
    name = "Гоблин-разбойник"
    difficulty = 1
    reward = 55
    max_hp = 170
    blood = (110, 200, 80)

    def __init__(self):
        super().__init__()
        self.x = 1000.0
        self.mode = "run"
        self.tx = 700.0
        self.knife_cd = 1.5
        self.dash_cd = 5.0
        self.dir = -1

    def center(self):
        return (self.x, self.y - 50)

    def body_rect(self):
        return pygame.Rect(int(self.x - 24), int(self.y - 90), 48, 90)

    def hitboxes(self):
        x, y = int(self.x), int(self.y)
        return [(pygame.Rect(x - 20, y - 124, 40, 34), "head"), (self.body_rect(), "body")]

    def hint(self):
        return "Гоблин выдохся — бейте!" if self.mode == "rest" else ""

    def throw(self, w, n):
        p = w.player
        sx, sy = self.x + self.f * 20, self.y - 70
        base = math.atan2(p.y - 35 - sy, p.x - sx)
        for i in range(n):
            a = base + (i - (n - 1) / 2.0) * 0.18
            w.fireballs.append(Fireball(sx, sy, math.cos(a) * 560, math.sin(a) * 560,
                                        dmg=10, r=9, style="knife"))
        w.audio.play("sword", 0.5)

    def think(self, dt, w):
        p = w.player
        low = self.low()
        self.gravity(dt)
        if self.mode != "dash":
            self.face(w)
        if self.mode == "run":
            dx = self.tx - self.x
            if abs(dx) < 12:
                nx = self.x
                for _ in range(8):
                    nx = random.uniform(120, W - 120)
                    if abs(nx - p.x) > 280:
                        break
                self.tx = nx
                if self.on_ground and random.random() < 0.35:
                    self.vy = -740.0
                    self.on_ground = False
            else:
                self.x += math.copysign(min(abs(dx), (380 if low else 330) * dt), dx)
            self.knife_cd -= dt
            if self.knife_cd <= 0:
                self.throw(w, 2 if low else 1)
                self.knife_cd = 0.95 if low else 1.4
            self.dash_cd -= dt
            if self.dash_cd <= 0:
                self.mode = "windup"
                self.mt = 0.55
        elif self.mode == "windup":
            self.mt -= dt
            self.flash = max(self.flash, 0.07)
            if self.mt <= 0:
                self.mode = "dash"
                self.mt = 1.2
                self.dir = self.f
        elif self.mode == "dash":
            self.x += self.dir * (760 if low else 700) * dt
            self.mt -= dt
            self.touch(w, self.body_rect(), 18)
            if self.x < 70 or self.x > W - 70 or self.mt <= 0:
                self.x = clamp(self.x, 70, W - 70)
                self.mode = "rest"
                self.mt = 1.0
                self.dash_cd = 4.5
        elif self.mode == "rest":
            self.mt -= dt
            if self.mt <= 0:
                self.mode = "run"
                self.tx = self.x

    def paint(self, surf, ox, oy, w):
        f = self.f
        run = math.sin(self.t * 14) * 8 if (self.mode in ("run", "dash") and self.on_ground) else 0
        pygame.draw.rect(surf, self.C((90, 60, 40)), (ox - 14 + run, oy - 34, 10, 34))
        pygame.draw.rect(surf, self.C((90, 60, 40)), (ox + 4 - run, oy - 34, 10, 34))
        pygame.draw.rect(surf, self.C((120, 82, 52)), (ox - 22, oy - 82, 44, 50), border_radius=6)
        pygame.draw.rect(surf, self.C((60, 40, 26)), (ox - 22, oy - 52, 44, 6))
        skin = self.C((110, 190, 80))
        pygame.draw.polygon(surf, skin, [(ox - 16, oy - 104), (ox - 48, oy - 118), (ox - 16, oy - 92)])
        pygame.draw.polygon(surf, skin, [(ox + 16, oy - 104), (ox + 48, oy - 118), (ox + 16, oy - 92)])
        pygame.draw.circle(surf, skin, (ox, oy - 100), 20)
        pygame.draw.polygon(surf, self.C((96, 64, 40)), [(ox - 23, oy - 104), (ox, oy - 136), (ox + 23, oy - 104)])
        pygame.draw.circle(surf, (255, 230, 60), (ox + f * 8, oy - 102), 4)
        pygame.draw.circle(surf, (255, 230, 60), (ox - f * 4, oy - 102), 4)
        pygame.draw.line(surf, (60, 40, 30), (ox - 8, oy - 90), (ox + 8, oy - 90), 2)
        tip = (ox + f * (60 if self.mode == "windup" else 52), oy - (96 if self.mode == "windup" else 76))
        pygame.draw.line(surf, (225, 228, 235), (ox + f * 22, oy - 62), tip, 5)
        pygame.draw.line(surf, (100, 70, 40), (ox + f * 16, oy - 60), (ox + f * 26, oy - 66), 6)


# ----------------------------------------------------------------------------
# 3. Скелет-рыцарь
# ----------------------------------------------------------------------------
class SkeletonBoss(Boss):
    name = "Скелет-рыцарь"
    difficulty = 2
    reward = 80
    max_hp = 240
    blood = (232, 232, 216)

    def __init__(self):
        super().__init__()
        self.x = 950.0
        self.mode = "walk"
        self.charge_cd = 7.0
        self.cdir = -1
        self.hit_done = False

    def shield_up(self):
        return self.mode in ("walk", "charge")

    def body_rect(self):
        return pygame.Rect(int(self.x - 26), int(self.y - 104), 52, 104)

    def hitboxes(self):
        x, y, f = int(self.x), int(self.y), self.f
        lst = []
        if self.shield_up():
            lst.append((pygame.Rect(int(x + f * 30 - 14), y - 104, 28, 84), "block"))
        lst.append((pygame.Rect(x - 17, y - 134, 34, 34), "head"))
        lst.append((self.body_rect(), "body"))
        return lst

    def hint(self):
        if self.mode in ("windup", "swing", "recover"):
            return "Щит опущен — атакуйте!"
        return "Щит закрывает торс — цельтесь в голову!"

    def think(self, dt, w):
        p = w.player
        low = self.low()
        self.gravity(dt)
        if self.mode in ("walk", "recover"):
            self.face(w)
        if self.mode == "walk":
            dx = p.x - self.x
            if abs(dx) > 115:
                self.x += sign(dx) * (190 if low else 150) * dt
            else:
                self.mode = "windup"
                self.mt = 0.5
            self.charge_cd -= dt
            if self.charge_cd <= 0 and abs(dx) > 260:
                self.mode = "charge"
                self.mt = 0.9
                self.charge_cd = 7.0
                self.cdir = self.f
            self.touch(w, self.body_rect(), 10)
        elif self.mode == "windup":
            self.mt -= dt
            self.flash = max(self.flash, 0.07)
            if self.mt <= 0:
                self.mode = "swing"
                self.mt = 0.22
                self.hit_done = False
        elif self.mode == "swing":
            self.mt -= dt
            if not self.hit_done:
                left = self.x + 10 if self.f > 0 else self.x - 140
                r = pygame.Rect(int(left), int(self.y - 110), 130, 110)
                if r.colliderect(p.rect()):
                    p.hurt(20, self.x, w)
                    self.hit_done = True
            if self.mt <= 0:
                self.mode = "recover"
                self.mt = 0.8
        elif self.mode == "recover":
            self.mt -= dt
            if self.mt <= 0:
                self.mode = "walk"
        elif self.mode == "charge":
            self.x += self.cdir * 560 * dt
            self.mt -= dt
            self.touch(w, self.body_rect(), 16)
            if self.x < 70 or self.x > W - 70 or self.mt <= 0:
                self.mode = "recover"
                self.mt = 0.9

    def paint(self, surf, ox, oy, w):
        f = self.f
        bone, dark, steel = self.C((226, 226, 210)), self.C((70, 70, 84)), self.C((150, 158, 176))
        step = math.sin(self.t * 9) * 7 if self.mode in ("walk", "charge") else 0
        pygame.draw.rect(surf, bone, (ox - 14 + step, oy - 40, 9, 40))
        pygame.draw.rect(surf, bone, (ox + 5 - step, oy - 40, 9, 40))
        pygame.draw.rect(surf, dark, (ox - 17 + step, oy - 8, 15, 8))
        pygame.draw.rect(surf, dark, (ox + 2 - step, oy - 8, 15, 8))
        pygame.draw.rect(surf, dark, (ox - 20, oy - 46, 40, 8))
        pygame.draw.rect(surf, bone, (ox - 18, oy - 100, 36, 54), border_radius=6)
        for i in range(4):
            pygame.draw.line(surf, dark, (ox - 14, oy - 92 + i * 11), (ox + 14, oy - 92 + i * 11), 3)
        pygame.draw.rect(surf, steel, (ox - 26, oy - 102, 52, 16), border_radius=6)
        pygame.draw.circle(surf, bone, (ox, oy - 116), 17)
        pygame.draw.polygon(surf, steel, [(ox - 18, oy - 116), (ox - 14, oy - 140), (ox + 14, oy - 140), (ox + 18, oy - 116)])
        pygame.draw.polygon(surf, (190, 40, 40), [(ox, oy - 140), (ox - f * 22, oy - 150), (ox - f * 14, oy - 128)])
        pygame.draw.circle(surf, (255, 70, 40), (ox + f * 7, oy - 114), 4)
        hand = (ox + f * 18, oy - 84)
        if self.mode == "windup":
            tip = (ox + f * 24, oy - 196)
        elif self.mode == "swing":
            tip = (ox + f * 118, oy - 62)
        else:
            tip = (ox + f * 44, oy - 150)
        pygame.draw.line(surf, steel, hand, tip, 8)
        pygame.draw.line(surf, (236, 240, 250), hand, tip, 3)
        if self.shield_up():
            sx = ox + f * 30
            pts = [(sx - 14, oy - 104), (sx + 14, oy - 104), (sx + 14, oy - 62), (sx, oy - 20), (sx - 14, oy - 62)]
            pygame.draw.polygon(surf, self.C((60, 84, 150)), pts)
            pygame.draw.polygon(surf, (225, 190, 70), pts, 3)


# ----------------------------------------------------------------------------
# 4. Каменный голем
# ----------------------------------------------------------------------------
class GolemBoss(Boss):
    name = "Каменный голем"
    difficulty = 2
    reward = 100
    max_hp = 340
    blood = (170, 160, 150)

    def __init__(self):
        super().__init__()
        self.x = 950.0
        self.mode = "walk"
        self.slam_cd = 3.0
        self.throw_cd = 5.0

    def center(self):
        return (self.x, self.y - 100)

    def body_rect(self):
        return pygame.Rect(int(self.x - 72), int(self.y - 175), 144, 175)

    def hitboxes(self):
        x, y = int(self.x), int(self.y)
        return [(pygame.Rect(x - 24, y - 136, 48, 46), "head"),
                (pygame.Rect(x - 32, y - 224, 64, 52), "body"), (self.body_rect(), "body")]

    def hint(self):
        return "Бейте по светящемуся ядру на груди!"

    def slam(self, w):
        p = w.player
        for d in (-1, 1):
            w.fireballs.append(Fireball(self.x + d * 70, GROUND_Y - 22, d * 340, 0, dmg=16, r=22,
                                        style="wave", ground=True, pierce=True, life=5.0))
        n = 5 if self.low() else 3
        for _ in range(n):
            self.warns.append([clamp(p.x + random.uniform(-260, 260), 60, W - 60), 0.85, "rock"])
        w.particles_burst(self.x, GROUND_Y, 26, (170, 150, 120), 320, 0.8, grav=300)
        w.audio.play("boom")

    def think(self, dt, w):
        p = w.player
        low = self.low()
        self.gravity(dt)
        self.face(w)
        if self.mode == "walk":
            dx = p.x - self.x
            if abs(dx) > 60:
                self.x += sign(dx) * (110 if low else 85) * dt
            self.touch(w, self.body_rect(), 12)
            self.slam_cd -= dt
            self.throw_cd -= dt
            if self.slam_cd <= 0:
                self.mode = "slam_wind"
                self.mt = 0.85
            elif self.throw_cd <= 0:
                self.mode = "throw_wind"
                self.mt = 0.6
        elif self.mode == "slam_wind":
            self.mt -= dt
            self.flash = max(self.flash, 0.05)
            if self.mt <= 0:
                self.slam(w)
                self.mode = "recover"
                self.mt = 0.9
                self.slam_cd = 2.8 if low else 3.8
        elif self.mode == "throw_wind":
            self.mt -= dt
            if self.mt <= 0:
                hx, hy = self.x + self.f * 50, self.y - 200
                vx, vy = lob(hx, hy, p.x, p.y - 40, 0.95, 750)
                w.fireballs.append(Fireball(hx, hy, vx, vy, dmg=18, r=24, style="rock", gravity=750))
                w.audio.play("sword", 0.6)
                self.mode = "recover"
                self.mt = 0.7
                self.throw_cd = 5.0
        elif self.mode == "recover":
            self.mt -= dt
            if self.mt <= 0:
                self.mode = "walk"

    def paint(self, surf, ox, oy, w):
        f = self.f
        rock, dark = self.C((122, 118, 112)), self.C((84, 80, 76))
        pygame.draw.rect(surf, dark, (ox - 52, oy - 62, 42, 62), border_radius=8)
        pygame.draw.rect(surf, dark, (ox + 10, oy - 62, 42, 62), border_radius=8)
        up = self.mode == "slam_wind"
        for sd in (-1, 1):
            raised = up or (self.mode == "throw_wind" and sd == f)
            ay = oy - 260 if raised else oy - 150
            pygame.draw.rect(surf, rock, (ox + sd * 80 - 17, ay, 34, 100), border_radius=10)
            pygame.draw.circle(surf, dark, (ox + sd * 80, ay + (0 if raised else 100)), 22)
            pygame.draw.circle(surf, rock, (ox + sd * 78, oy - 162), 28)
        pygame.draw.rect(surf, rock, (ox - 72, oy - 175, 144, 125), border_radius=14)
        pygame.draw.rect(surf, dark, (ox - 72, oy - 175, 144, 125), 4, border_radius=14)
        pygame.draw.rect(surf, rock, (ox - 32, oy - 224, 64, 52), border_radius=10)
        pygame.draw.rect(surf, dark, (ox - 32, oy - 224, 64, 52), 3, border_radius=10)
        pygame.draw.rect(surf, (255, 170, 40), (ox - 22, oy - 206, 16, 8))
        pygame.draw.rect(surf, (255, 170, 40), (ox + 6, oy - 206, 16, 8))
        pulse = 18 + int(math.sin(self.t * 5) * 3)
        pygame.draw.circle(surf, (200, 80, 20), (ox, oy - 113), pulse + 6)
        pygame.draw.circle(surf, self.C((255, 170, 40)), (ox, oy - 113), pulse)
        pygame.draw.circle(surf, (255, 240, 170), (ox, oy - 113), pulse - 9)
        pygame.draw.line(surf, dark, (ox - 60, oy - 90), (ox - 30, oy - 70), 3)
        pygame.draw.line(surf, dark, (ox + 60, oy - 150), (ox + 40, oy - 120), 3)
        for mx, my in ((-50, -170), (40, -60)):
            pygame.draw.circle(surf, (80, 130, 70), (ox + mx, oy + my), 7)


# ----------------------------------------------------------------------------
# 5. Ледяная ведьма
# ----------------------------------------------------------------------------
class WitchBoss(Boss):
    name = "Ледяная ведьма"
    difficulty = 3
    reward = 130
    max_hp = 270
    blood = (150, 210, 255)
    flying = True

    def __init__(self):
        super().__init__()
        self.x, self.by = 900.0, 320.0
        self.y = self.by
        self.tx = 900.0
        self.mode = "float"
        self.cast_cd = 1.5
        self.casts = 0

    def center(self):
        return (self.x, self.y)

    def hitboxes(self):
        x, y = int(self.x), int(self.y)
        return [(pygame.Rect(x - 18, y - 80, 36, 34), "head"),
                (pygame.Rect(x - 34, y - 46, 68, 104), "body")]

    def hint(self):
        return "Ведьма исчезает и появляется — ждите, когда она проявится"

    def fan(self, w):
        n = 7 if self.low() else 5
        sx, sy = self.x, self.y - 20
        base = math.atan2(w.player.y - 35 - sy, w.player.x - sx)
        for i in range(n):
            a = base + (i - (n - 1) / 2.0) * 0.2
            w.fireballs.append(Fireball(sx, sy, math.cos(a) * 430, math.sin(a) * 430,
                                        dmg=11, r=10, style="ice"))
        w.audio.play("fire", 0.6)

    def rain(self, w):
        n = 8 if self.low() else 6
        self.warns.append([clamp(w.player.x, 60, W - 60), 0.9, "ice"])
        for _ in range(n - 1):
            self.warns.append([random.uniform(60, W - 60), 0.9, "ice"])
        w.audio.play("fire", 0.6)

    def think(self, dt, w):
        p = w.player
        low = self.low()
        if self.mode == "float":
            self.y = self.by + math.sin(self.t * 2.2) * 14
            dx = self.tx - self.x
            if abs(dx) > 4:
                self.x += math.copysign(min(abs(dx), 120 * dt), dx)
            self.face(w)
            self.cast_cd -= dt
            if self.cast_cd <= 0:
                self.casts += 1
                if self.casts % 3 == 0:
                    self.rain(w)
                else:
                    self.fan(w)
                self.cast_cd = 1.3 if low else 1.9
                if self.casts % 4 == 0:
                    self.mode = "vanish"
                    self.mt = 0.5
                    self.ghost = True
        elif self.mode == "vanish":
            self.mt -= dt
            if self.mt <= 0:
                for _ in range(10):
                    nx = random.uniform(150, W - 150)
                    if abs(nx - p.x) > 350:
                        break
                self.x, self.tx = nx, nx
                self.by = random.uniform(240, 420)
                self.y = self.by
                self.mode = "appear"
                self.mt = 0.5
        elif self.mode == "appear":
            self.mt -= dt
            if self.mt <= 0:
                self.mode = "float"
                self.ghost = False
                self.fan(w)
                self.cast_cd = 1.2

    def paint(self, surf, ox, oy, w):
        f = self.f
        robe, trim = self.C((110, 160, 225)), self.C((220, 240, 255))
        wob = math.sin(self.t * 3) * 5
        pygame.draw.polygon(surf, robe, [(ox - 24, oy - 44), (ox + 24, oy - 44), (ox + 46 + wob, oy + 62), (ox - 46 - wob, oy + 62)])
        pygame.draw.polygon(surf, trim, [(ox - 46 - wob, oy + 62), (ox + 46 + wob, oy + 62), (ox + 40 + wob, oy + 52), (ox - 40 - wob, oy + 52)])
        pygame.draw.circle(surf, self.C((236, 244, 255)), (ox, oy - 62), 16)
        for k in (-1, 1):
            pygame.draw.line(surf, (240, 248, 255), (ox + k * 14, oy - 62), (ox + k * 22, oy - 20), 4)
        pygame.draw.circle(surf, (60, 220, 255), (ox + f * 6, oy - 63), 3)
        pygame.draw.circle(surf, (60, 220, 255), (ox - f * 5, oy - 63), 3)
        pygame.draw.polygon(surf, self.C((50, 80, 160)), [(ox - 30, oy - 70), (ox + 30, oy - 70), (ox + 6, oy - 138)])
        pygame.draw.ellipse(surf, self.C((50, 80, 160)), (ox - 34, oy - 78, 68, 16))
        sx = ox + f * 36
        pygame.draw.line(surf, (200, 230, 255), (sx, oy + 50), (sx, oy - 60), 4)
        pygame.draw.polygon(surf, (210, 245, 255), [(sx, oy - 90), (sx - 9, oy - 68), (sx, oy - 58), (sx + 9, oy - 68)])
        pygame.draw.line(surf, trim, (ox + f * 18, oy - 30), (sx, oy - 20), 6)


# ----------------------------------------------------------------------------
# 6. Гигантский паук
# ----------------------------------------------------------------------------
class SpiderBoss(Boss):
    name = "Гигантский паук"
    difficulty = 3
    reward = 150
    max_hp = 310
    blood = (160, 230, 90)
    flying = True

    def __init__(self):
        super().__init__()
        self.x, self.y = 900.0, 150.0
        self.mode = "crawl"
        self.tx = 600.0
        self.spit_cd = 1.8
        self.drop_cd = 6.0

    def center(self):
        return (self.x, self.y)

    def body_rect(self):
        return pygame.Rect(int(self.x - 62), int(self.y - 40), 124, 80)

    def hitboxes(self):
        x, y = int(self.x), int(self.y)
        return [(pygame.Rect(x - 24, y - 20, 48, 44), "head"), (self.body_rect(), "body")]

    def hint(self):
        if self.mode == "land":
            return "Паук на земле — бейте красную метку!"
        return "Паук готовится упасть — отойдите!" if self.mode == "tele" else ""

    def spit(self, w):
        p = w.player
        sx, sy = self.x, self.y + 20
        times = (0.7, 0.85, 1.0) if self.low() else (0.85,)
        for T in times:
            vx, vy = lob(sx, sy, p.x, p.y - 40, T, 520)
            w.fireballs.append(Fireball(sx, sy, vx, vy, dmg=11, r=13, style="poison", gravity=520))
        w.audio.play("fire", 0.5)

    def think(self, dt, w):
        p = w.player
        low = self.low()
        if self.mode == "crawl":
            self.y = 150 + math.sin(self.t * 3) * 8
            dx = self.tx - self.x
            if abs(dx) < 10:
                self.tx = random.uniform(150, W - 150)
            else:
                self.x += math.copysign(min(abs(dx), (300 if low else 230) * dt), dx)
            self.spit_cd -= dt
            if self.spit_cd <= 0:
                self.spit(w)
                self.spit_cd = 1.1 if low else 1.6
            self.drop_cd -= dt
            if self.drop_cd <= 0:
                self.mode = "tele"
                self.mt = 0.9
        elif self.mode == "tele":
            self.mt -= dt
            if self.mt > 0.3:
                self.x += (p.x - self.x) * min(1.0, dt * 7)
            self.x += math.sin(self.t * 60) * 1.5
            if self.mt <= 0:
                self.mode = "drop"
        elif self.mode == "drop":
            self.y += 1150 * dt
            self.touch(w, self.body_rect().inflate(-10, -10), 22)
            if self.y >= GROUND_Y - 44:
                self.y = float(GROUND_Y - 44)
                self.mode = "land"
                self.mt = 1.3
                w.particles_burst(self.x, GROUND_Y, 22, (150, 120, 90), 300, 0.7, grav=300)
                w.audio.play("boom")
        elif self.mode == "land":
            self.mt -= dt
            self.touch(w, self.body_rect().inflate(-10, -10), 12)
            if self.mt <= 0:
                self.mode = "climb"
        elif self.mode == "climb":
            self.y -= 420 * dt
            if self.y <= 150:
                self.y = 150.0
                self.mode = "crawl"
                self.drop_cd = 4.5 if low else 6.0

    def paint(self, surf, ox, oy, w):
        f = self.f
        body, dark = self.C((54, 34, 64)), self.C((30, 18, 38))
        pygame.draw.line(surf, (225, 225, 235), (ox, 0), (ox, oy - 30), 2)
        for i in range(4):
            for sd in (-1, 1):
                k = (i - 1.5) * 28
                sw = math.sin(self.t * 7 + i * 1.3 * sd) * 8
                knee = (ox + sd * (60 + abs(k) * 0.3), oy - 40 + k * 0.4 + sw)
                foot = (ox + sd * (100 + i * 6), oy + 38 + (i - 1.5) * 6)
                pygame.draw.line(surf, dark, (ox + sd * 30, oy + k * 0.2), knee, 7)
                pygame.draw.line(surf, dark, knee, foot, 5)
        pygame.draw.ellipse(surf, body, (ox - 62 - f * 14, oy - 40, 124, 80))
        pygame.draw.ellipse(surf, dark, (ox - 62 - f * 14, oy - 40, 124, 80), 3)
        pygame.draw.polygon(surf, (210, 40, 40), [(ox - 12 - f * 14, oy - 14), (ox + 12 - f * 14, oy - 14), (ox - f * 14, oy), (ox + 12 - f * 14, oy + 14), (ox - 12 - f * 14, oy + 14), (ox - f * 14, oy)])
        pygame.draw.circle(surf, body, (ox + f * 46, oy - 4), 28)
        for ex, ey, er in ((8, -12, 6), (22, -10, 5), (4, 0, 4), (24, 2, 4)):
            pygame.draw.circle(surf, (255, 60, 60), (ox + f * (38 + ex // 2), oy + ey), er)
        for sd in (-1, 1):
            pygame.draw.line(surf, (230, 230, 220), (ox + f * 66, oy + 10 + sd * 5), (ox + f * 82, oy + 26 + sd * 4), 4)


# ----------------------------------------------------------------------------
# 7. Чёрный рыцарь
# ----------------------------------------------------------------------------
class DarkKnightBoss(Boss):
    name = "Чёрный рыцарь"
    difficulty = 4
    reward = 190
    max_hp = 400
    blood = (170, 120, 255)

    def __init__(self):
        super().__init__()
        self.x = 950.0
        self.mode = "approach"
        self.evade_cd = 1.0
        self.hit_done = False
        self.combo = 0
        self.wave_high = False
        self.dir = -1

    def body_rect(self):
        return pygame.Rect(int(self.x - 24), int(self.y - 100), 48, 100)

    def hitboxes(self):
        x, y = int(self.x), int(self.y)
        return [(pygame.Rect(x - 18, y - 132, 36, 32), "head"), (self.body_rect(), "body")]

    def hint(self):
        return "Полумесяцы бывают низкие и высокие — прыгайте или пригибайтесь!"

    def crescents(self, w):
        yy = [self.y - 34, self.y - 112] if self.low() else [self.y - (112 if self.wave_high else 34)]
        self.wave_high = not self.wave_high
        for y in yy:
            w.fireballs.append(Fireball(self.x + self.f * 50, y, self.f * 540, 0, dmg=16, r=22,
                                        style="crescent", pierce=True, solid=False, life=4.0))
        w.audio.play("sword", 0.7)

    def think(self, dt, w):
        p = w.player
        low = self.low()
        landed = self.gravity(dt)
        self.evade_cd -= dt
        if self.mode in ("approach", "recover"):
            self.face(w)
        if self.mode == "approach" and self.evade_cd <= 0 and self.on_ground:
            for a in w.arrows:
                if (not a.stuck and abs(a.x - self.x) < 260 and abs(a.y - (self.y - 60)) < 90
                        and a.vx * (self.x - a.x) > 0):
                    if random.random() < 0.55:
                        self.vy = -780.0
                        self.on_ground = False
                    self.evade_cd = 2.5
                    break
        if self.mode == "approach":
            dx = p.x - self.x
            if abs(dx) > 170:
                self.x += sign(dx) * (300 if low else 260) * dt
            self.mt += dt
            if abs(dx) <= 200 or self.mt > 2.4:
                r = random.random()
                self.mt = 0.0
                if r < 0.4:
                    self.mode, self.mt = "windup_slash", 0.35
                elif r < 0.75:
                    self.mode, self.mt = "windup_wave", 0.45
                else:
                    self.mode, self.mt = "windup_leap", 0.55
        elif self.mode == "windup_slash":
            self.mt -= dt
            self.flash = max(self.flash, 0.07)
            if self.mt <= 0:
                self.mode, self.mt = "slash", 0.22
                self.hit_done = False
                self.dir = self.f
        elif self.mode == "slash":
            self.x += self.dir * 520 * dt
            self.mt -= dt
            left = self.x + 10 if self.dir > 0 else self.x - 130
            r = pygame.Rect(int(left), int(self.y - 110), 120, 110)
            if not self.hit_done and r.colliderect(p.rect()):
                p.hurt(20, self.x, w)
                self.hit_done = True
            if self.mt <= 0:
                if low and self.combo < 1:
                    self.combo += 1
                    self.mode, self.mt = "windup_slash", 0.2
                else:
                    self.combo = 0
                    self.mode, self.mt = "recover", 0.6
        elif self.mode == "windup_wave":
            self.mt -= dt
            self.flash = max(self.flash, 0.07)
            if self.mt <= 0:
                self.crescents(w)
                self.mode, self.mt = "recover", 0.5
        elif self.mode == "windup_leap":
            self.mt -= dt
            self.flash = max(self.flash, 0.07)
            if self.mt <= 0:
                self.vy = -980.0
                self.vx = clamp((p.x - self.x) * 1.1, -560, 560)
                self.on_ground = False
                self.mode = "leap"
        elif self.mode == "leap":
            self.x += self.vx * dt
            if landed:
                self.vx = 0.0
                w.particles_burst(self.x, GROUND_Y, 20, (150, 120, 190), 300, 0.7, grav=300)
                w.audio.play("boom")
                self.touch(w, pygame.Rect(int(self.x - 110), int(self.y - 40), 220, 60), 22)
                if low:
                    for d in (-1, 1):
                        w.fireballs.append(Fireball(self.x + d * 60, GROUND_Y - 20, d * 360, 0, dmg=14, r=20,
                                                    style="wave", ground=True, pierce=True, life=4.0))
                self.mode, self.mt = "recover", 0.8
        elif self.mode == "recover":
            self.mt -= dt
            if self.mt <= 0:
                self.mode, self.mt = "approach", 0.0

    def paint(self, surf, ox, oy, w):
        f = self.f
        arm, glow = self.C((44, 40, 62)), self.C((140, 90, 230))
        step = math.sin(self.t * 10) * 7 if self.mode == "approach" and self.on_ground else 0
        pygame.draw.rect(surf, arm, (ox - 15 + step, oy - 44, 12, 44))
        pygame.draw.rect(surf, arm, (ox + 3 - step, oy - 44, 12, 44))
        pygame.draw.polygon(surf, self.C((64, 30, 90)), [(ox - f * 14, oy - 92), (ox - f * 44, oy - 8), (ox - f * 8, oy - 20)])
        pygame.draw.rect(surf, arm, (ox - 24, oy - 100, 48, 58), border_radius=8)
        pygame.draw.rect(surf, glow, (ox - 24, oy - 100, 48, 58), 2, border_radius=8)
        pygame.draw.circle(surf, arm, (ox - 26, oy - 94), 12)
        pygame.draw.circle(surf, arm, (ox + 26, oy - 94), 12)
        pygame.draw.circle(surf, arm, (ox, oy - 114), 18)
        pygame.draw.polygon(surf, arm, [(ox - 14, oy - 126), (ox - 28, oy - 150), (ox - 8, oy - 128)])
        pygame.draw.polygon(surf, arm, [(ox + 14, oy - 126), (ox + 28, oy - 150), (ox + 8, oy - 128)])
        pygame.draw.rect(surf, (255, 90, 255), (ox + (f * 4 if f > 0 else -14), oy - 118, 10, 4))
        hand = (ox + f * 20, oy - 76)
        if self.mode in ("windup_slash", "windup_wave"):
            tip = (ox + f * 26, oy - 200)
        elif self.mode == "slash":
            tip = (ox + f * 110, oy - 60)
        elif self.mode == "windup_leap":
            tip = (ox + f * 70, oy - 20)
        else:
            tip = (ox + f * 56, oy - 150)
        pygame.draw.line(surf, glow, hand, tip, 11)
        pygame.draw.line(surf, (30, 24, 40), hand, tip, 7)
        pygame.draw.line(surf, (200, 160, 255), hand, tip, 2)


# ----------------------------------------------------------------------------
# 8. Король-лич
# ----------------------------------------------------------------------------
class LichBoss(Boss):
    name = "Король-лич"
    difficulty = 5
    reward = 250
    max_hp = 460
    blood = (190, 120, 255)
    flying = True

    def __init__(self):
        super().__init__()
        self.x, self.by = 900.0, 330.0
        self.y = self.by
        self.tx = 900.0
        self.mode = "float"
        self.cd = 1.6
        self.idx = 0
        self.beams = []
        self.ring_rot = 0.0

    def center(self):
        return (self.x, self.y)

    def hitboxes(self):
        x, y = int(self.x), int(self.y)
        return [(pygame.Rect(x - 22, y - 92, 44, 38), "head"),
                (pygame.Rect(x - 36, y - 56, 72, 130), "body")]

    def hint(self):
        return "Сбивайте летящие черепа стрелой или мечом"

    def on_die(self, w):
        self.beams = []

    def update_beams(self, dt, w):
        keep = []
        for b in self.beams:
            if b[1] > 0:
                b[1] -= dt
            else:
                b[2] -= dt
                r = pygame.Rect(int(b[0] - 28), 0, 56, GROUND_Y)
                if r.colliderect(w.player.rect()):
                    w.player.hurt(24, b[0], w)
            if b[2] > 0:
                keep.append(b)
        self.beams = keep

    def think(self, dt, w):
        p = w.player
        low = self.low()
        self.update_beams(dt, w)
        if self.mode == "float":
            self.y = self.by + math.sin(self.t * 1.8) * 16
            dx = self.tx - self.x
            if abs(dx) < 6:
                self.tx = random.uniform(220, W - 220)
            else:
                self.x += math.copysign(min(abs(dx), 90 * dt), dx)
            self.face(w)
            self.cd -= dt
            if self.cd <= 0:
                atk = ("skulls", "beams", "ring", "teleport")[self.idx % 4]
                self.idx += 1
                self.cd = 1.3 if low else 1.9
                if atk == "skulls":
                    n = 5 if low else 3
                    for i in range(n):
                        a = -math.pi / 2 + (i - (n - 1) / 2.0) * 0.7
                        w.fireballs.append(Fireball(self.x + (i - (n - 1) / 2.0) * 40, self.y - 60,
                                                    math.cos(a) * 240, math.sin(a) * 240, dmg=14, r=16,
                                                    style="skull", homing=1.6, shootable=True,
                                                    solid=False, life=7.0))
                    w.audio.play("roar", 0.4)
                elif atk == "beams":
                    n = 5 if low else 3
                    xs = [clamp(p.x, 60, W - 60)] + [random.uniform(60, W - 60) for _ in range(n - 1)]
                    for x in xs:
                        self.beams.append([x, 1.0, 0.4])
                    w.audio.play("fire", 0.6)
                elif atk == "ring":
                    n = 16 if low else 12
                    self.ring_rot += 0.5
                    for i in range(n):
                        a = self.ring_rot + i * math.tau / n
                        w.fireballs.append(Fireball(self.x, self.y - 20, math.cos(a) * 250, math.sin(a) * 250,
                                                    dmg=10, r=11, style="orb", solid=False, life=5.0))
                    w.audio.play("fire", 0.6)
                else:
                    self.mode = "vanish"
                    self.mt = 0.5
                    self.ghost = True
        elif self.mode == "vanish":
            self.mt -= dt
            if self.mt <= 0:
                nx = self.x
                for _ in range(10):
                    nx = random.uniform(150, W - 150)
                    if abs(nx - p.x) > 350:
                        break
                self.x, self.tx = nx, nx
                self.by = random.uniform(240, 400)
                self.y = self.by
                self.mode = "appear"
                self.mt = 0.5
        elif self.mode == "appear":
            self.mt -= dt
            if self.mt <= 0:
                self.mode = "float"
                self.ghost = False
                self.cd = 0.8

    def draw_body(self, surf, w):
        for x, warn, act in self.beams:
            if warn > 0:
                a = 30 + int(50 * clamp(1.0 - warn, 0.0, 1.0))
                panel(surf, pygame.Rect(int(x - 28), 0, 56, GROUND_Y), (190, 90, 255, a), 0)
                pygame.draw.line(surf, (230, 190, 255), (int(x), 0), (int(x), GROUND_Y), 1)
            else:
                panel(surf, pygame.Rect(int(x - 28), 0, 56, GROUND_Y), (210, 150, 255, 210), 0)
                panel(surf, pygame.Rect(int(x - 10), 0, 20, GROUND_Y), (255, 245, 255, 240), 0)
        Boss.draw_body(self, surf, w)

    def paint(self, surf, ox, oy, w):
        f = self.f
        robe, trim = self.C((60, 30, 96)), self.C((150, 90, 230))
        wob = math.sin(self.t * 3) * 6
        pygame.draw.polygon(surf, robe, [(ox - 30, oy - 54), (ox + 30, oy - 54), (ox + 52 + wob, oy + 74), (ox - 52 - wob, oy + 74)])
        pygame.draw.polygon(surf, trim, [(ox - 52 - wob, oy + 74), (ox - 30, oy + 60), (ox, oy + 74), (ox + 30, oy + 60), (ox + 52 + wob, oy + 74)])
        for i in range(4):
            pygame.draw.line(surf, (200, 180, 230), (ox - 14, oy - 40 + i * 11), (ox + 14, oy - 40 + i * 11), 3)
        pygame.draw.circle(surf, self.C((232, 232, 220)), (ox, oy - 72), 20)
        pygame.draw.rect(surf, self.C((232, 232, 220)), (ox - 12, oy - 58, 24, 10))
        pygame.draw.circle(surf, (20, 10, 30), (ox - 7, oy - 74), 5)
        pygame.draw.circle(surf, (20, 10, 30), (ox + 7, oy - 74), 5)
        pygame.draw.circle(surf, (190, 100, 255), (ox - 7, oy - 74), 2)
        pygame.draw.circle(surf, (190, 100, 255), (ox + 7, oy - 74), 2)
        crown = [(ox - 18, oy - 88), (ox - 18, oy - 108), (ox - 9, oy - 96), (ox, oy - 112), (ox + 9, oy - 96), (ox + 18, oy - 108), (ox + 18, oy - 88)]
        pygame.draw.polygon(surf, (230, 190, 60), crown)
        sx = ox + f * 46
        pygame.draw.line(surf, (110, 80, 60), (sx, oy + 60), (sx, oy - 70), 5)
        pygame.draw.circle(surf, (190, 100, 255), (sx, oy - 80), 12 + int(math.sin(self.t * 6) * 2))
        pygame.draw.circle(surf, (240, 210, 255), (sx, oy - 80), 6)
        pygame.draw.line(surf, trim, (ox + f * 22, oy - 34), (sx, oy - 30), 7)


# ----------------------------------------------------------------------------
# Финальный босс — Дракон (две фазы: после половины здоровья впадает в ярость)
# ----------------------------------------------------------------------------
class Dragon(Boss):
    name = "Огненный дракон"
    difficulty = 5
    reward = 1000
    max_hp = 760
    blood = (230, 60, 40)
    dying_time = 3.0
    flying = True

    def __init__(self):
        super().__init__()
        self.intro = 0.0
        self.state = "enter"      # состояние дракона (alive/dying — через ту же переменную)
        self.x, self.y = W / 2.0, -180.0
        self.t = 0.0              # таймер текущего состояния
        self.clock = 0.0          # общее время (для анимации)
        self.flap = 0.0
        self.mouth = 0.0
        self.tx = W / 2
        self.volleys = 0
        self.cycle = 0
        self.fire_cd = 1.0
        self.claw_cd = 1.0
        self.claw_t = -1.0
        self.dive_x = 0.0
        self.land_x = 260.0
        self.dives_left = 0
        self.prep_time = 1.1
        self.rage = False
        self.meteor_cd = 2.5
        self.wave_cd = 2.0
        self.ring_done = False

    def invulnerable(self):
        return self.state in ("enter", "roar", "dying")

    def center(self):
        return (self.x, self.y)

    # ---- хитбоксы ----
    def head_pos(self):
        bob = math.sin(self.clock * 3) * 4
        return (self.x + self.f * 125, self.y - 34 + bob)

    def body_rect(self):
        return pygame.Rect(int(self.x - 95), int(self.y - 48), 190, 96)

    def head_rect(self):
        hx, hy = self.head_pos()
        return pygame.Rect(int(hx - 38), int(hy - 28), 76, 56)

    def claw_rect(self):
        return pygame.Rect(int(self.x + self.f * 140 - 90), GROUND_Y - 150, 180, 150)

    def hitboxes(self):
        return [(self.head_rect(), "head"), (self.body_rect(), "body")]

    def hint(self):
        if self.state in ("ground", "recover"):
            return "Дракон приземлился — атакуйте мечом!"
        if self.state == "dive_prep":
            return "ОСТОРОЖНО! Дракон готовится к пике!"
        if self.state == "roar":
            return "Дракон в ярости!"
        if self.rage and self.state == "fly":
            return "Следите за красными метками — падают метеориты!"
        return ""

    # ---- атаки ----
    def volley(self, w, n=3, spread=0.25, speed=360):
        hx, hy = self.head_pos()
        p = w.player
        tx = p.x + (p.vx * 0.35 if self.rage else 0.0)
        base = math.atan2(p.y - 30 - hy, tx - hx)
        offs = [0.0] if n == 1 else [(-spread + 2 * spread * i / (n - 1)) for i in range(n)]
        for o in offs:
            a = base + o
            w.fireballs.append(Fireball(hx + self.f * 30, hy + 6, math.cos(a) * speed, math.sin(a) * speed,
                                        dmg=13, r=14, style="fire"))
        self.mouth = 0.45
        w.audio.play("fire")

    def fire_ring(self, w, n=10):
        for i in range(n):
            a = i * math.tau / n
            w.fireballs.append(Fireball(self.x, self.y - 20, math.cos(a) * 300, math.sin(a) * 300,
                                        dmg=13, r=13, style="fire", life=4.0))
        w.audio.play("fire")

    def fire_waves(self, w):
        for d in (-1, 1):
            w.fireballs.append(Fireball(self.x + d * 110, GROUND_Y - 20, d * 340, 0, dmg=16, r=20,
                                        style="firewave", ground=True, pierce=True, life=5.0))

    def pick_tx(self):
        for _ in range(10):
            nx = random.randint(200, 1080)
            if abs(nx - self.x) > 250:
                return nx
        return random.choice([220, 1060])

    # ---- обновление ----
    def update(self, dt, w):
        self.clock += dt
        self.flash = max(0.0, self.flash - dt)
        if self.state == "dying":
            self._dying(dt, w)
            return
        self.tick_warns(dt, w)
        self.t += dt
        self.mouth = max(0.0, self.mouth - dt)
        self.claw_cd -= dt
        self.fire_cd -= dt
        p = w.player
        st = self.state
        rage = self.rage
        flapping = st in ("enter", "fly", "roar", "dive_prep", "takeoff", "land", "dive")
        self.flap += dt * (9 if flapping else 1.5)
        if st not in ("dive", "dying") and abs(p.x - self.x) > 40:
            self.f = 1 if p.x > self.x else -1
        gy = GROUND_Y - 72

        # переход в ярость
        if not rage and st == "fly" and self.hp <= self.max_hp * 0.5:
            self.rage = rage = True
            self.state = st = "roar"
            self.t = 0.0
            self.ring_done = False
            w.audio.play("roar")
            w.popup("ЯРОСТЬ!", self.x, 120, (255, 90, 60))

        if st == "enter":
            self.y += 260 * dt
            if self.y >= 190:
                self.y = 190.0
                self.state = "fly"
                self.t = 0.0
                self.tx = random.choice([260, 1020])
                self.fire_cd = 1.2
                w.audio.play("roar")
                w.popup("РРРРРРР!", self.x, 130, (255, 120, 60))
        elif st == "roar":
            self.y += (190 + math.sin(self.t * 12) * 8 - self.y) * min(1.0, dt * 4)
            self.mouth = 0.2
            if self.t > 1.4 and not self.ring_done:
                self.ring_done = True
                self.fire_ring(w, 12)
            if self.t > 1.8:
                self.state = "fly"
                self.t = 0.0
                self.fire_cd = 0.8
        elif st == "fly":
            ty = 190 + math.sin(self.t * 2.2) * 20
            self.y += (ty - self.y) * min(1.0, dt * 3)
            dx = self.tx - self.x
            if abs(dx) < 8:
                self.tx = self.pick_tx()
            else:
                self.x += math.copysign(min(abs(dx), (290 if rage else 200) * dt), dx)
            if self.fire_cd <= 0:
                if rage:
                    self.volley(w, 5, 0.4, 400)
                else:
                    self.volley(w, 3, 0.25, 360)
                self.volleys += 1
                self.fire_cd = 1.2 if rage else 1.6
                if self.volleys >= (2 if rage else 3):
                    self.volleys = 0
                    self.cycle += 1
                    self.t = 0.0
                    if self.cycle % 2 == 1:
                        self.state = "dive_prep"
                        self.dives_left = 2 if rage else 1
                        self.prep_time = 0.8 if rage else 1.1
                    else:
                        self.state = "land"
                        self.land_x = random.choice([260, 1020])
            if rage:
                self.meteor_cd -= dt
                if self.meteor_cd <= 0:
                    self.meteor_cd = 3.0
                    for off in (-170, 0, 170):
                        mx = clamp(p.x + off + random.uniform(-60, 60), 60, W - 60)
                        self.warns.append([mx, 0.9, "meteor"])
        elif st == "dive_prep":
            self.y += (110 - self.y) * min(1.0, dt * 5)
            self.x += (p.x - self.x) * min(1.0, dt * 2.5)
            if self.t > self.prep_time:
                self.dive_x = p.x
                self.state = "dive"
                self.t = 0.0
                w.audio.play("roar", 0.6)
        elif st == "dive":
            dx, dy = self.dive_x - self.x, gy - self.y
            dist = math.hypot(dx, dy)
            step = min(dist, (1000 if rage else 860) * dt)
            if dist > 0:
                self.x += dx / dist * step
                self.y += dy / dist * step
            self.touch(w, self.body_rect(), 28)
            if dist < 6:
                self.state = "recover"
                self.t = 0.0
                w.particles_burst(self.x, GROUND_Y, 24, (150, 120, 90), 300, 0.7, grav=300)
                w.audio.play("boom")
                if rage:
                    self.fire_waves(w)
        elif st == "recover":
            self.touch(w, self.body_rect(), 18)
            if self.t > (0.45 if rage else 0.8):
                self.dives_left -= 1
                self.t = 0.0
                if self.dives_left > 0:
                    self.state = "dive_prep"
                    self.prep_time = 0.6
                else:
                    self.state = "takeoff"
        elif st == "takeoff":
            self.y -= 340 * dt
            if self.y <= 190:
                self.y = 190.0
                self.state = "fly"
                self.t = 0.0
                self.tx = self.pick_tx()
                self.fire_cd = 1.0
                self.volleys = 0
        elif st == "land":
            dx = self.land_x - self.x
            self.x += math.copysign(min(abs(dx), 280 * dt), dx)
            self.y = min(gy, self.y + 280 * dt)
            if abs(dx) < 4 and self.y >= gy - 1:
                self.y = float(gy)
                self.state = "ground"
                self.t = 0.0
                self.claw_cd = 1.0
                self.fire_cd = 1.5
                self.wave_cd = 1.2
                self.claw_t = -1.0
                w.particles_burst(self.x, GROUND_Y, 24, (150, 120, 90), 300, 0.7, grav=300)
                w.audio.play("boom")
        elif st == "ground":
            self.y = float(gy)
            self.touch(w, self.body_rect(), 15)
            if self.claw_t >= 0:
                self.claw_t += dt
                if self.claw_t >= (0.3 if rage else 0.4):
                    if self.claw_rect().colliderect(p.rect()):
                        p.hurt(22, self.x + self.f * 100, w)
                    w.particles_burst(self.x + self.f * 140, GROUND_Y - 10, 10, (150, 120, 90), 200, 0.5)
                    self.claw_t = -1.0
                    self.claw_cd = 1.2
            elif self.claw_cd <= 0 and self.claw_rect().inflate(30, 0).colliderect(p.rect()):
                self.claw_t = 0.0
            elif self.fire_cd <= 0:
                if rage:
                    self.volley(w, 2, 0.15, 450)
                    self.fire_cd = 1.4
                else:
                    self.volley(w, 1, 0, 430)
                    self.fire_cd = 1.9
            if rage:
                self.wave_cd -= dt
                if self.wave_cd <= 0:
                    self.wave_cd = 2.6
                    self.fire_waves(w)
                    w.audio.play("fire", 0.6)
            if self.t > (7.0 if rage else 6.0):
                self.state = "takeoff"
                self.t = 0.0

    def dying_motion(self, dt):
        self.y = min(GROUND_Y - 72, self.y + 120 * dt)

    # ---- отрисовка ----
    def _wing(self, surf, ax, ay, col, edge, phase):
        f = self.f
        flying = self.state not in ("ground", "recover")
        flap = math.sin(self.flap + phase)
        up = (-70 - 55 * flap) if flying else -35
        p1 = (ax - f * 30, ay + up)
        p2 = (ax - f * 125, ay + up * 0.55 + 20)
        p3 = (ax - f * 105, ay + up * 0.1 + 55)
        p4 = (ax - f * 55, ay + 34)
        pygame.draw.polygon(surf, col, [(ax, ay), p1, p2, p3, p4])
        for tip in (p1, p2, p3):
            pygame.draw.line(surf, edge, (ax, ay), tip, 4)

    def draw_body(self, surf, w):
        f, x, y = self.f, self.x, self.y
        if self.state == "dive_prep" and self.t > 0.2:
            alpha = 50 + int(40 * math.sin(self.clock * 20))
            panel(surf, pygame.Rect(int(self.x - 50), 0, 100, GROUND_Y), (255, 40, 30, alpha), 0)
        fl = min(1.0, self.flash / 0.12) if self.flash > 0 else 0.0

        def C(c):
            return tuple(int(c[i] + (255 - c[i]) * fl * 0.75) for i in range(3))

        body = C((196, 40, 30) if self.rage else (150, 34, 34))
        dark = C((120, 24, 24) if self.rage else (105, 22, 28))
        belly = C((226, 168, 90))
        wing_c = C((150, 30, 36) if self.rage else (125, 28, 40))
        grounded = self.state in ("ground", "recover")
        for i in range(9):
            s = i / 8.0
            px = x - f * (80 + s * 170)
            py = y + 20 + math.sin(self.clock * 3 - s * 3) * 14 * s + s * (0 if grounded else 25)
            if grounded:
                py = min(py, GROUND_Y - 14 - 8 * (1 - s))
            pygame.draw.circle(surf, dark, (int(px), int(py)), int(22 * (1 - s) + 4))
        self._wing(surf, x - f * 20, y - 38, C((95, 20, 32)), dark, 0.6)
        for lx in (-48, 38):
            leg_len = 28 if grounded else 18
            pygame.draw.rect(surf, dark, (x + lx - 11, y + 30, 22, leg_len), border_radius=6)
            for c in (-1, 0, 1):
                pygame.draw.line(surf, (235, 230, 215), (x + lx + c * 7, y + 30 + leg_len),
                                 (x + lx + c * 7 + f * 5, y + 36 + leg_len), 3)
        pygame.draw.ellipse(surf, body, (x - 100, y - 50, 200, 100))
        pygame.draw.ellipse(surf, belly, (x - 78, y + 4, 156, 40))
        for i in range(5):
            pygame.draw.arc(surf, dark, (x - 70 + i * 28, y - 40, 30, 26), 0.3, 2.8, 3)
        hx, hy = self.head_pos()
        n0 = (x + f * 80, y - 18)
        for i in range(9):
            s = i / 8.0
            px = n0[0] + (hx - n0[0]) * s
            py = n0[1] + (hy - n0[1]) * s - math.sin(s * math.pi) * 10
            pygame.draw.circle(surf, body, (int(px), int(py)), int(25 - 9 * s))
        pygame.draw.ellipse(surf, body, (hx - 36, hy - 26, 72, 52))
        pygame.draw.ellipse(surf, body, (hx + f * 30 - 30, hy - 8, 60, 30))
        if self.mouth > 0:
            pygame.draw.ellipse(surf, (60, 10, 14), (hx + f * 30 - 26, hy + 2, 52, 22))
            pygame.draw.circle(surf, (255, 170, 50), (int(hx + f * 52), int(hy + 12)), 9)
            pygame.draw.ellipse(surf, dark, (hx + f * 28 - 28, hy + 16, 56, 18))
        else:
            pygame.draw.ellipse(surf, dark, (hx + f * 30 - 26, hy + 8, 52, 14))
        pygame.draw.polygon(surf, (235, 230, 215), [(hx - f * 8, hy - 20), (hx - f * 40, hy - 54), (hx - f * 22, hy - 16)])
        pygame.draw.polygon(surf, (235, 230, 215), [(hx + f * 8, hy - 22), (hx - f * 20, hy - 56), (hx - f * 4, hy - 18)])
        ex, ey = int(hx + f * 12), int(hy - 8)
        pygame.draw.circle(surf, (255, 90, 40) if self.rage else (255, 220, 40), (ex, ey), 7)
        pygame.draw.ellipse(surf, (20, 0, 0), (ex - 2, ey - 6, 4, 12))
        pygame.draw.circle(surf, (40, 8, 10), (int(hx + f * 54), int(hy + 2)), 3)
        self._wing(surf, x + f * 5, y - 40, wing_c, dark, 0.0)
        if self.claw_t >= 0:
            panel(surf, self.claw_rect(), (255, 60, 40, 80), 8)


# ----------------------------------------------------------------------------
# Фоны
# ----------------------------------------------------------------------------
def make_bg1():
    rnd = random.Random(7)
    s = vgradient(W, H, (96, 160, 232), (214, 234, 250))
    pygame.draw.circle(s, (255, 244, 190), (1040, 110), 46)
    halo = pygame.Surface((220, 220), pygame.SRCALPHA)
    pygame.draw.circle(halo, (255, 244, 190, 60), (110, 110), 110)
    s.blit(halo, (930, 0))
    for cx, cy in ((200, 110), (620, 70), (860, 160), (1180, 220)):
        for dx, dy, rw in ((0, 0, 110), (-50, 12, 80), (55, 14, 90)):
            pygame.draw.ellipse(s, (255, 255, 255), (cx + dx - rw // 2, cy + dy - 18, rw, 40))
    for col, base, amp in (((150, 170, 205), 480, 90), ((120, 148, 180), 540, 70)):
        pts = [(0, GROUND_Y)]
        x = 0
        while x <= W + 80:
            pts.append((x, base - rnd.randint(0, amp)))
            x += rnd.randint(70, 130)
        pts.append((W, GROUND_Y))
        pygame.draw.polygon(s, col, pts)
    # замок
    stone, dk = (136, 140, 156), (104, 108, 124)
    pygame.draw.rect(s, stone, (470, 440, 380, GROUND_Y - 440))
    for tx in (440, 800):
        pygame.draw.rect(s, dk, (tx, 380, 70, GROUND_Y - 380))
        for i in range(5):
            pygame.draw.rect(s, dk, (tx + i * 15, 362, 10, 20))
        pygame.draw.polygon(s, (170, 50, 50), [(tx - 8, 380), (tx + 35, 320), (tx + 78, 380)])
    for i in range(12):
        pygame.draw.rect(s, stone, (470 + i * 32, 424, 20, 18))
    pygame.draw.rect(s, (50, 40, 44), (620, 510, 80, GROUND_Y - 510), border_top_left_radius=40, border_top_right_radius=40)
    for wx in (520, 760):
        pygame.draw.rect(s, (60, 70, 100), (wx, 480, 18, 36), border_radius=8)
    pygame.draw.line(s, (60, 60, 60), (475, 320 + 42), (475, 280 + 42), 3)
    # деревья
    for tx, sc in ((90, 1.0), (360, 0.8), (1120, 1.1), (990, 0.7)):
        pygame.draw.rect(s, (96, 66, 40), (tx - 8 * sc, GROUND_Y - 90 * sc, 16 * sc, 90 * sc))
        for dx, dy, r in ((0, -110, 50), (-32, -85, 36), (32, -85, 36)):
            pygame.draw.circle(s, (56, 130, 62), (int(tx + dx * sc), int(GROUND_Y + dy * sc)), int(r * sc))
    # земля
    pygame.draw.rect(s, (112, 84, 52), (0, GROUND_Y, W, H - GROUND_Y))
    pygame.draw.rect(s, (84, 164, 72), (0, GROUND_Y, W, 14))
    for _ in range(160):
        gx = rnd.randint(0, W)
        pygame.draw.line(s, (60, 140, 58), (gx, GROUND_Y), (gx + rnd.randint(-3, 3), GROUND_Y - rnd.randint(4, 10)), 2)
    for _ in range(40):
        pygame.draw.ellipse(s, (96, 72, 46), (rnd.randint(0, W), rnd.randint(GROUND_Y + 24, H - 10), rnd.randint(14, 40), rnd.randint(6, 14)))
    return s


def make_bg2():
    rnd = random.Random(13)
    s = vgradient(W, H, (22, 6, 22), (150, 40, 28))
    halo = pygame.Surface((420, 420), pygame.SRCALPHA)
    pygame.draw.circle(halo, (255, 90, 40, 50), (210, 210), 210)
    s.blit(halo, (690, -40))
    pygame.draw.circle(s, (214, 70, 44), (900, 170), 92)
    pygame.draw.circle(s, (186, 52, 38), (870, 150), 18)
    pygame.draw.circle(s, (186, 52, 38), (925, 205), 12)
    for col, base, amp in (((62, 20, 30), 420, 150), ((34, 12, 20), 520, 110)):
        pts = [(0, GROUND_Y)]
        x = 0
        while x <= W + 80:
            pts.append((x, base - rnd.randint(0, amp)))
            x += rnd.randint(50, 110)
        pts.append((W, GROUND_Y))
        pygame.draw.polygon(s, col, pts)
    glow = pygame.Surface((W, 120), pygame.SRCALPHA)
    for i in range(120):
        pygame.draw.line(glow, (255, 110, 30, int(90 * (i / 120) ** 2)), (0, i), (W, i))
    s.blit(glow, (0, GROUND_Y - 120))
    for px in (20, 1200):
        pygame.draw.rect(s, (66, 54, 64), (px, 300, 60, GROUND_Y - 300))
        pygame.draw.rect(s, (84, 70, 80), (px - 8, 290, 76, 22), border_radius=4)
        for k in range(4):
            pygame.draw.line(s, (40, 32, 40), (px + 4, 330 + k * 70), (px + 56, 340 + k * 70), 2)
    pygame.draw.rect(s, (44, 32, 40), (0, GROUND_Y, W, H - GROUND_Y))
    pygame.draw.rect(s, (70, 52, 60), (0, GROUND_Y, W, 10))
    for _ in range(26):
        x = rnd.randint(0, W)
        y = GROUND_Y + rnd.randint(14, 90)
        pts = [(x, y)]
        for _ in range(4):
            x += rnd.randint(-30, 30)
            y += rnd.randint(8, 22)
            pts.append((x, min(y, H)))
        pygame.draw.lines(s, (255, 120, 30), False, pts, 2)
    return s


THEMES = {
    "swamp": dict(sky=((60, 92, 74), (160, 192, 134)), far=(80, 112, 86), near=(56, 88, 66),
                  ground=(70, 60, 42), top=(64, 112, 62), orb=((236, 240, 190), (1040, 120), 40),
                  decor="swamp", plat=((98, 80, 56), (72, 122, 70), (50, 40, 28))),
    "forest": dict(sky=((40, 90, 82), (150, 202, 152)), far=(50, 100, 82), near=(30, 70, 56),
                   ground=(80, 58, 36), top=(60, 132, 60), orb=((255, 244, 190), (200, 110), 38),
                   decor="trees", plat=((110, 80, 50), (70, 140, 66), (60, 42, 26))),
    "crypt": dict(sky=((24, 20, 34), (74, 58, 88)), far=(52, 46, 66), near=(36, 32, 48),
                  ground=(58, 54, 66), top=(92, 86, 102), orb=None,
                  decor="pillars", plat=((92, 88, 104), (128, 122, 142), (40, 36, 50))),
    "mountain": dict(sky=((122, 152, 192), (226, 204, 172)), far=(134, 134, 154), near=(100, 100, 116),
                     ground=(110, 100, 90), top=(142, 132, 120), orb=((255, 236, 190), (240, 130), 44),
                     decor="rocks", plat=((118, 112, 106), (154, 148, 140), (60, 56, 52))),
    "ice": dict(sky=((140, 190, 236), (232, 246, 255)), far=(192, 216, 242), near=(152, 186, 222),
                ground=(210, 230, 246), top=(246, 251, 255), orb=((255, 255, 240), (1000, 120), 40),
                decor="icicles", plat=((168, 204, 236), (238, 250, 255), (96, 136, 180))),
    "cave": dict(sky=((14, 12, 20), (48, 38, 58)), far=(32, 28, 42), near=(24, 20, 32),
                 ground=(52, 44, 54), top=(74, 62, 74), orb=None,
                 decor="stalactites", plat=((84, 70, 76), (116, 98, 106), (36, 28, 34))),
    "night": dict(sky=((10, 10, 30), (44, 38, 86)), far=(32, 32, 62), near=(22, 22, 46),
                  ground=(40, 40, 58), top=(72, 72, 94), orb=((240, 240, 255), (240, 130), 46),
                  decor="castle", plat=((74, 74, 100), (108, 108, 138), (30, 30, 44))),
    "graveyard": dict(sky=((20, 30, 36), (74, 98, 92)), far=(42, 58, 58), near=(28, 40, 40),
                      ground=(44, 52, 40), top=(72, 92, 62), orb=((210, 240, 220), (1000, 120), 34),
                      decor="tombs", plat=((74, 80, 72), (104, 112, 100), (34, 38, 32))),
}


def make_bg_theme(name):
    th = THEMES[name]
    rnd = random.Random(sum(ord(c) for c in name))
    s = vgradient(W, H, th["sky"][0], th["sky"][1])
    if th.get("orb"):
        col, pos, rad = th["orb"]
        halo = pygame.Surface((rad * 6, rad * 6), pygame.SRCALPHA)
        pygame.draw.circle(halo, (col[0], col[1], col[2], 45), (rad * 3, rad * 3), rad * 3)
        s.blit(halo, (pos[0] - rad * 3, pos[1] - rad * 3))
        pygame.draw.circle(s, col, pos, rad)
    for col, base, amp in ((th["far"], 470, 120), (th["near"], 540, 90)):
        pts = [(0, GROUND_Y)]
        x = 0
        while x <= W + 80:
            pts.append((x, base - rnd.randint(0, amp)))
            x += rnd.randint(70, 130)
        pts.append((W, GROUND_Y))
        pygame.draw.polygon(s, col, pts)
    d = th["decor"]
    near = th["near"]
    dark = tuple(max(0, c - 22) for c in near)
    if d == "swamp":
        for tx in (110, 400, 760, 1130):
            pygame.draw.polygon(s, (52, 40, 32), [(tx - 12, GROUND_Y), (tx + 12, GROUND_Y), (tx + 5, GROUND_Y - 190), (tx - 5, GROUND_Y - 190)])
            for k in range(3):
                by = GROUND_Y - 190 + k * 40
                pygame.draw.line(s, (52, 40, 32), (tx, by + 30), (tx + rnd.choice([-1, 1]) * 60, by - 10), 5)
        for _ in range(26):
            rx = rnd.randint(0, W)
            pygame.draw.line(s, (60, 100, 60), (rx, GROUND_Y), (rx + rnd.randint(-6, 6), GROUND_Y - rnd.randint(24, 60)), 3)
    elif d == "trees":
        for tx in range(30, W, 110):
            sc = rnd.uniform(0.8, 1.3)
            pygame.draw.rect(s, (60, 40, 28), (tx - 9 * sc, GROUND_Y - 130 * sc, 18 * sc, 130 * sc))
            for dx, dy, r in ((0, -150, 56), (-34, -112, 40), (34, -112, 40)):
                pygame.draw.circle(s, (28 + rnd.randint(0, 20), 80 + rnd.randint(0, 30), 50), (int(tx + dx * sc), int(GROUND_Y + dy * sc)), int(r * sc))
    elif d == "pillars":
        for px in (90, 330, 640, 950, 1190):
            pygame.draw.rect(s, (66, 60, 80), (px - 26, 120, 52, GROUND_Y - 120))
            pygame.draw.rect(s, (84, 78, 98), (px - 36, 106, 72, 24), border_radius=4)
            pygame.draw.rect(s, (84, 78, 98), (px - 36, GROUND_Y - 20, 72, 20), border_radius=4)
            for k in range(5):
                pygame.draw.line(s, (48, 44, 60), (px - 20, 170 + k * 80), (px + 20, 180 + k * 80), 2)
        for cx in (200, 500, 800, 1100):
            pygame.draw.line(s, (90, 90, 100), (cx, 0), (cx, 90), 2)
            pygame.draw.circle(s, (255, 190, 90), (cx, 100), 9)
    elif d == "rocks":
        for rx, rw, rh in ((80, 220, 150), (420, 160, 110), (760, 240, 170), (1120, 200, 130)):
            pygame.draw.polygon(s, (96, 92, 98), [(rx - rw // 2, GROUND_Y), (rx - rw // 4, GROUND_Y - rh), (rx + rw // 5, GROUND_Y - rh - 20), (rx + rw // 2, GROUND_Y)])
            pygame.draw.polygon(s, (126, 122, 128), [(rx - rw // 4, GROUND_Y - rh), (rx + rw // 5, GROUND_Y - rh - 20), (rx, GROUND_Y - rh * 0.6)])
    elif d == "icicles":
        for _ in range(20):
            ix = rnd.randint(0, W)
            iw, ih = rnd.randint(20, 40), rnd.randint(50, 130)
            pygame.draw.polygon(s, (200, 230, 250), [(ix, 0), (ix + iw, 0), (ix + iw // 2, ih)])
        for cx in (150, 520, 880, 1180):
            for k in range(3):
                pygame.draw.polygon(s, (190, 225, 250), [(cx + k * 26 - 14, GROUND_Y), (cx + k * 26 + 14, GROUND_Y), (cx + k * 26, GROUND_Y - 80 - k * 20)])
    elif d == "stalactites":
        pygame.draw.rect(s, (18, 14, 24), (0, 0, W, 60))
        for _ in range(26):
            ix = rnd.randint(0, W)
            iw, ih = rnd.randint(26, 60), rnd.randint(60, 190)
            pygame.draw.polygon(s, (28, 22, 36), [(ix, 40), (ix + iw, 40), (ix + iw // 2, ih)])
        for _ in range(9):
            gx = rnd.randint(40, W - 40)
            pygame.draw.polygon(s, (36, 30, 44), [(gx - 22, GROUND_Y), (gx + 22, GROUND_Y), (gx, GROUND_Y - rnd.randint(50, 120))])
            pygame.draw.circle(s, (110, 220, 190), (gx + 30, GROUND_Y - 12), 5)
    elif d == "castle":
        for bx, bw, bh in ((300, 160, 250), (560, 220, 330), (860, 170, 270)):
            pygame.draw.rect(s, (22, 22, 40), (bx, GROUND_Y - bh, bw, bh))
            for k in range(bw // 28):
                pygame.draw.rect(s, (22, 22, 40), (bx + k * 28 + 4, GROUND_Y - bh - 16, 16, 18))
            for wy in range(GROUND_Y - bh + 40, GROUND_Y - 40, 70):
                pygame.draw.rect(s, (230, 190, 90), (bx + bw // 2 - 8, wy, 16, 28), border_radius=6)
        pygame.draw.polygon(s, (22, 22, 40), [(540, GROUND_Y - 330), (670, GROUND_Y - 330), (605, GROUND_Y - 430)])
    elif d == "tombs":
        for tx in range(60, W, 140):
            h = rnd.randint(50, 90)
            pygame.draw.rect(s, (80, 88, 84), (tx - 22, GROUND_Y - h, 44, h), border_top_left_radius=22, border_top_right_radius=22)
            pygame.draw.line(s, (50, 56, 52), (tx, GROUND_Y - h + 14), (tx, GROUND_Y - h + 38), 3)
            pygame.draw.line(s, (50, 56, 52), (tx - 9, GROUND_Y - h + 24), (tx + 9, GROUND_Y - h + 24), 3)
        for tx in (240, 700, 1090):
            pygame.draw.polygon(s, (30, 30, 28), [(tx - 10, GROUND_Y), (tx + 10, GROUND_Y), (tx + 4, GROUND_Y - 200), (tx - 4, GROUND_Y - 200)])
            for k in range(3):
                pygame.draw.line(s, (30, 30, 28), (tx, GROUND_Y - 180 + k * 40), (tx + rnd.choice([-1, 1]) * 50, GROUND_Y - 220 + k * 40), 4)
        mist = pygame.Surface((W, 120), pygame.SRCALPHA)
        for k in range(120):
            pygame.draw.line(mist, (170, 210, 190, int(50 * (k / 120.0))), (0, k), (W, k))
        s.blit(mist, (0, GROUND_Y - 120))
    pygame.draw.rect(s, th["ground"], (0, GROUND_Y, W, H - GROUND_Y))
    pygame.draw.rect(s, th["top"], (0, GROUND_Y, W, 12))
    gd = tuple(max(0, c - 16) for c in th["ground"])
    for _ in range(40):
        pygame.draw.ellipse(s, gd, (rnd.randint(0, W), rnd.randint(GROUND_Y + 24, H - 10), rnd.randint(14, 40), rnd.randint(6, 14)))
    return s


def make_bg_market():
    rnd = random.Random(21)
    s = vgradient(W, H, (50, 34, 86), (236, 150, 104))
    for bx, bw, bh in ((0, 200, 330), (210, 150, 270), (370, 180, 360), (560, 140, 250), (1120, 160, 340), (1090, 90, 260)):
        pygame.draw.rect(s, (46, 30, 62), (bx, GROUND_Y - bh, bw, bh))
        pygame.draw.polygon(s, (60, 36, 70), [(bx - 8, GROUND_Y - bh), (bx + bw + 8, GROUND_Y - bh), (bx + bw // 2, GROUND_Y - bh - 70)])
        for wy in range(GROUND_Y - bh + 30, GROUND_Y - 60, 60):
            for wx in range(bx + 20, bx + bw - 30, 46):
                if rnd.random() < 0.6:
                    pygame.draw.rect(s, (255, 214, 120), (wx, wy, 18, 26), border_radius=4)
    pygame.draw.line(s, (90, 60, 50), (0, 120), (W, 150), 2)
    for k in range(0, W, 60):
        yy = 120 + int(k * 30 / W)
        pygame.draw.polygon(s, rnd.choice([(220, 60, 60), (240, 200, 70), (70, 150, 220)]), [(k, yy), (k + 24, yy), (k + 12, yy + 28)])
    pygame.draw.rect(s, (92, 78, 90), (0, GROUND_Y, W, H - GROUND_Y))
    pygame.draw.rect(s, (120, 104, 114), (0, GROUND_Y, W, 10))
    for _ in range(70):
        pygame.draw.ellipse(s, (74, 62, 74), (rnd.randint(0, W), rnd.randint(GROUND_Y + 14, H - 10), rnd.randint(30, 70), rnd.randint(10, 22)), 2)
    return s


def draw_platform(surf, r, theme):
    if theme == "meadow":
        pygame.draw.rect(surf, (118, 90, 60), r, border_radius=4)
        pygame.draw.rect(surf, (84, 164, 72), (r.x, r.y, r.w, 6), border_radius=3)
        pygame.draw.rect(surf, (70, 50, 34), r, 2, border_radius=4)
        for x in range(r.x + 20, r.right - 10, 40):
            pygame.draw.line(surf, (92, 68, 44), (x, r.y + 8), (x, r.bottom - 2), 2)
    elif theme in THEMES:
        fill, top, edge = THEMES[theme]["plat"]
        pygame.draw.rect(surf, fill, r, border_radius=4)
        pygame.draw.rect(surf, top, (r.x, r.y, r.w, 6), border_radius=3)
        pygame.draw.rect(surf, edge, r, 2, border_radius=4)
    else:
        pygame.draw.rect(surf, (74, 58, 68), r, border_radius=4)
        pygame.draw.rect(surf, (104, 84, 96), (r.x, r.y, r.w, 6), border_radius=3)
        pygame.draw.rect(surf, (30, 22, 30), r, 2, border_radius=4)


# ----------------------------------------------------------------------------
# Уровень 1 — тренировка
# ----------------------------------------------------------------------------
class Level1:
    kind = "training"
    final = False
    reward = 50
    title = "Уровень 1 — Тренировочный двор"

    def __init__(self):
        self.platforms = [pygame.Rect(180, 500, 200, 18), pygame.Rect(520, 420, 180, 18),
                          pygame.Rect(840, 500, 170, 18), pygame.Rect(1030, 400, 150, 18)]
        self.targets = [
            {"cx": 300, "x": 300, "y": 360, "r": 30, "amp": 0, "hit": False},
            {"cx": 610, "x": 610, "y": 280, "r": 30, "amp": 0, "hit": False},
            {"cx": 940, "x": 940, "y": 380, "r": 30, "amp": 0, "hit": False},
            {"cx": 800, "x": 800, "y": 170, "r": 26, "amp": 180, "hit": False},
            {"cx": 1110, "x": 1110, "y": 290, "r": 30, "amp": 0, "hit": False},
        ]
        self.dummies = [{"x": x, "hp": 60, "flash": 0.0, "dead": False, "swing": -1} for x in (480, 760, 1100)]
        self.portal = pygame.Rect(1190, GROUND_Y - 120, 70, 120)
        self.open = False
        self.t = 0.0

    # --- информация для HUD
    def hits(self):
        return sum(1 for t in self.targets if t["hit"])

    def kills(self):
        return sum(1 for d in self.dummies if d["dead"])

    def dummy_rect(self, d):
        return pygame.Rect(d["x"] - 30, GROUND_Y - 145, 60, 145)

    def damage_dummy(self, d, dmg, w):
        d["hp"] -= dmg
        d["flash"] = 0.18
        w.audio.play("hit")
        w.particles_burst(d["x"], GROUND_Y - 80, 8, (214, 186, 110), 180, 0.5)
        w.popup("%d" % int(dmg), d["x"], GROUND_Y - 160, (255, 255, 255))
        if d["hp"] <= 0 and not d["dead"]:
            d["dead"] = True
            w.particles_burst(d["x"], GROUND_Y - 70, 30, (214, 186, 110), 320, 0.9)
            w.popup("Манекен разрушен!", d["x"], GROUND_Y - 190, (140, 255, 140))
            w.audio.play("ding")

    def on_sword(self, rect, sid, w):
        for d in self.dummies:
            if not d["dead"] and d["swing"] != sid and rect.colliderect(self.dummy_rect(d)):
                d["swing"] = sid
                self.damage_dummy(d, 22 * w.player.dmg_mult(), w)
        for t in self.targets:
            if not t["hit"] and circle_rect(t["x"], t["y"], t["r"], rect):
                self._target_hit(t, False, w)

    def _target_hit(self, t, bull, w):
        t["hit"] = True
        w.audio.play("ding")
        w.popup("В яблочко!" if bull else "Мишень поражена!", t["x"], t["y"] - 50,
                (255, 220, 70) if bull else (140, 255, 140))
        w.particles_burst(t["x"], t["y"], 12, (255, 230, 120), 200, 0.6)

    def blocks(self, x, y):
        for t in self.targets:
            if math.hypot(x - t["x"], y - t["y"]) <= t["r"]:
                return True
        return any(not d["dead"] and self.dummy_rect(d).collidepoint(x, y) for d in self.dummies)

    def on_arrow(self, a, w):
        for t in self.targets:
            d = math.hypot(a.x - t["x"], a.y - t["y"])
            if d <= t["r"]:
                if not t["hit"]:
                    self._target_hit(t, d <= t["r"] * 0.3, w)
                a.attach = (t, a.x - t["x"])
                return "stick"
        for d in self.dummies:
            if not d["dead"] and self.dummy_rect(d).collidepoint(a.x, a.y):
                self.damage_dummy(d, a.dmg, w)
                return "remove"
        return None

    def update(self, dt, w):
        self.t += dt
        for t in self.targets:
            if t["amp"]:
                t["x"] = t["cx"] + math.sin(self.t * 1.1) * t["amp"]
        for d in self.dummies:
            d["flash"] = max(0.0, d["flash"] - dt)
        if not self.open and self.hits() == len(self.targets) and self.kills() == len(self.dummies):
            self.open = True
            w.audio.play("portal")
            w.popup("Портал открыт! Идите вправо →", W // 2, 160, (170, 200, 255))
        if self.open and self.portal.colliderect(w.player.rect()):
            w.finished = "clear"

    def draw(self, surf, w):
        surf.blit(w.game.get_bg("meadow"), (0, 0))
        for p in self.platforms:
            draw_platform(surf, p, "meadow")
        for t in self.targets:
            self._draw_target(surf, t)
        for d in self.dummies:
            self._draw_dummy(surf, d)
        self._draw_portal(surf)

    def _draw_target(self, surf, t):
        x, y, r = int(t["x"]), int(t["y"]), t["r"]
        pygame.draw.line(surf, (110, 90, 60), (x, 0), (x, y - r), 2)
        pygame.draw.circle(surf, (110, 76, 44), (x, y), r + 4)
        for k, col in enumerate(((235, 235, 235), (200, 40, 40), (235, 235, 235), (200, 40, 40))):
            pygame.draw.circle(surf, col, (x, y), int(r * (1 - k * 0.25)))
        if t["hit"]:
            pygame.draw.circle(surf, (60, 220, 90), (x, y), r + 4, 4)
            pygame.draw.lines(surf, (40, 200, 70), False, [(x - 10, y), (x - 3, y + 8), (x + 12, y - 9)], 5)

    def _draw_dummy(self, surf, d):
        x = d["x"]
        sh = math.sin(d["flash"] * 60) * 4 if d["flash"] > 0 else 0
        gy = GROUND_Y
        if d["dead"]:
            pygame.draw.rect(surf, (120, 88, 52), (x - 40, gy - 8, 80, 8))
            pygame.draw.ellipse(surf, (214, 186, 110), (x - 26, gy - 20, 52, 20))
            pygame.draw.circle(surf, (214, 186, 110), (x + 44, gy - 8), 10)
            return
        pygame.draw.rect(surf, (116, 82, 48), (x - 5 + sh, gy - 125, 10, 125))
        pygame.draw.rect(surf, (116, 82, 48), (x - 36 + sh, gy - 98, 72, 9))
        pygame.draw.ellipse(surf, (214, 186, 110), (x - 22 + sh, gy - 112, 44, 62))
        pygame.draw.ellipse(surf, (150, 120, 70), (x - 22 + sh, gy - 112, 44, 62), 2)
        pygame.draw.line(surf, (110, 80, 50), (x - 12 + sh, gy - 92), (x + 12 + sh, gy - 72), 2)
        pygame.draw.line(surf, (110, 80, 50), (x + 12 + sh, gy - 92), (x - 12 + sh, gy - 72), 2)
        pygame.draw.circle(surf, (222, 196, 124), (int(x + sh), gy - 130), 17)
        pygame.draw.circle(surf, (40, 30, 20), (int(x + sh - 6), gy - 133), 2)
        pygame.draw.circle(surf, (40, 30, 20), (int(x + sh + 6), gy - 133), 2)
        if d["hp"] < 60:
            pygame.draw.rect(surf, (40, 10, 10), (x - 25, gy - 160, 50, 6))
            pygame.draw.rect(surf, (210, 50, 50), (x - 25, gy - 160, int(50 * d["hp"] / 60), 6))

    def _draw_portal(self, surf):
        r = self.portal
        pygame.draw.rect(surf, (100, 102, 118), (r.x - 14, r.y - 16, r.w + 28, r.h + 16),
                         border_top_left_radius=44, border_top_right_radius=44)
        if self.open:
            pygame.draw.rect(surf, (30, 14, 80), r, border_top_left_radius=35, border_top_right_radius=35)
            for i in range(6):
                k = i / 6.0
                ang = self.t * 2 + i
                rr = pygame.Rect(0, 0, int(r.w * (1 - k) - 6), int(r.h * (1 - k * 0.6) - 8))
                rr.center = (r.centerx + int(math.cos(ang) * 4), r.centery + int(math.sin(ang) * 4) + 4)
                col = (int(90 + 100 * k), int(120 + 100 * k), 255)
                pygame.draw.ellipse(surf, col, rr, 3)
        else:
            pygame.draw.rect(surf, (36, 34, 44), r, border_top_left_radius=35, border_top_right_radius=35)
            for x in range(r.x + 8, r.right, 14):
                pygame.draw.line(surf, (70, 66, 80), (x, r.y + 10), (x, r.bottom), 3)


# ----------------------------------------------------------------------------
# Боевые арены (8 промежуточных боссов + финальный дракон)
# ----------------------------------------------------------------------------
class BossLevel:
    kind = "boss"

    def __init__(self, stage, boss, theme, platforms, title, final=False):
        self.stage = stage
        self.boss = boss
        self.theme = theme
        self.platforms = platforms
        self.title = title
        self.final = final
        self.reward = boss.reward
        self.t = 0.0

    def blocks(self, x, y):
        b = self.boss
        if b.state == "dying" or b.ghost:
            return False
        return any(r.collidepoint(x, y) for r, _ in b.hitboxes())

    def on_arrow(self, a, w):
        b = self.boss
        if b.state == "dying" or b.ghost:
            return None
        for rect, kind in b.hitboxes():
            if rect.collidepoint(a.x, a.y):
                if kind == "block":
                    w.particles_burst(a.x, a.y, 6, (255, 230, 150), 180, 0.3)
                    w.audio.play("hit", 0.5)
                    if random.random() < 0.4:
                        w.popup("Блок!", a.x, a.y - 20, (200, 200, 220))
                    return "remove"
                if not b.hit(a.dmg, kind == "head", w):
                    w.particles_burst(a.x, a.y, 6, (255, 220, 120), 160, 0.3)
                return "remove"
        return None

    def on_sword(self, rect, sid, w):
        b = self.boss
        if b.last_swing == sid or b.state == "dying" or b.ghost:
            return
        mult = 1.0
        hit = False
        for r, kind in b.hitboxes():
            if rect.colliderect(r):
                if kind == "block":
                    mult = 0.5
                    continue
                hit = True
                break
        if hit:
            b.last_swing = sid
            b.hit(28 * mult * w.player.dmg_mult(), False, w)

    def update(self, dt, w):
        self.t += dt
        self.boss.update(dt, w)
        th = self.theme
        if th == "volcano" and random.random() < dt * 14:
            w.particles.append([random.uniform(0, W), GROUND_Y + 6, random.uniform(-20, 20),
                                random.uniform(-120, -50), 2.5, 2.5, (255, 140, 40), 2, -20])
        elif th == "ice" and random.random() < dt * 10:
            w.particles.append([random.uniform(0, W), -5, random.uniform(-25, 25),
                                random.uniform(50, 110), 8.0, 8.0, (255, 255, 255), 2, 0])
        elif th in ("graveyard", "crypt") and random.random() < dt * 4:
            w.particles.append([random.uniform(0, W), GROUND_Y, random.uniform(-10, 10),
                                -30, 4.0, 4.0, (120, 255, 160), 2, -5])

    def draw(self, surf, w):
        surf.blit(w.game.get_bg(self.theme), (0, 0))
        for p in self.platforms:
            draw_platform(surf, p, self.theme)
        self.boss.draw(surf, w)


LAYOUTS = [
    [(140, 500, 180, 18), (520, 430, 180, 18), (960, 500, 180, 18)],
    [(100, 490, 160, 18), (340, 400, 150, 18), (790, 400, 150, 18), (1020, 490, 160, 18)],
    [(200, 500, 200, 18), (540, 390, 200, 18), (880, 500, 200, 18)],
    [(120, 480, 150, 18), (565, 510, 150, 18), (1010, 480, 150, 18)],
]
BOSS_CLASSES = [SlimeBoss, GoblinBoss, SkeletonBoss, GolemBoss, WitchBoss, SpiderBoss, DarkKnightBoss, LichBoss]
BOSS_THEMES = ["swamp", "forest", "crypt", "mountain", "ice", "cave", "night", "graveyard"]


def stage_title(stage):
    if stage == 0:
        return "Уровень 1 — Тренировочный двор"
    if stage < FINAL_STAGE:
        return "Бой %d из %d — %s" % (stage, len(BOSS_CLASSES), BOSS_CLASSES[stage - 1].name)
    return "Финал — Логово дракона"


def make_level(stage):
    if stage == 0:
        return Level1()
    if stage < FINAL_STAGE:
        i = stage - 1
        plats = [pygame.Rect(*t) for t in LAYOUTS[i % len(LAYOUTS)]]
        return BossLevel(stage, BOSS_CLASSES[i](), BOSS_THEMES[i], plats, stage_title(stage))
    plats = [pygame.Rect(*t) for t in LAYOUTS[0]]
    return BossLevel(stage, Dragon(), "volcano", plats, stage_title(stage), final=True)


# ----------------------------------------------------------------------------
# Мир (текущая игровая сессия)
# ----------------------------------------------------------------------------
class World:
    def __init__(self, game, stage):
        self.game = game
        self.audio = game.audio
        self.stage = stage
        self.level = make_level(stage)
        self.player = Player(90 if stage == 0 else 120, game.inv)
        self.arrows = []
        self.fireballs = []
        self.particles = []
        self.popups = []
        self.time = 0.0
        self.banner_t = 3.5
        self.hurt_flash = 0.0
        self.finished = None

    @property
    def platforms(self):
        return self.level.platforms

    def blocked(self, x, y):
        """Точка внутри препятствия (платформа, цель, манекен, босс)?"""
        if any(pl.collidepoint(x, y) for pl in self.platforms):
            return True
        return self.level.blocks(x, y)

    def popup(self, text, x, y, color=(255, 255, 255)):
        self.popups.append([text, x, y, 1.3, color])

    def particles_burst(self, x, y, n, color, speed=200, life=0.6, size=4, grav=500):
        for _ in range(n):
            a = random.uniform(0, math.tau)
            s = random.uniform(0.2, 1.0) * speed
            lf = life * random.uniform(0.6, 1.1)
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s - speed * 0.2,
                                   lf, lf, color, random.uniform(2, size), grav])

    def sword_projectiles(self, rect):
        """Меч сбивает «сбиваемые» снаряды (черепа лича)."""
        for f in self.fireballs:
            if f.shootable and not f.dead and circle_rect(f.x, f.y, f.r, rect):
                f.dead = True
                self.particles_burst(f.x, f.y, 10, STYLE_COL.get(f.style, (255, 255, 255)), 200, 0.5)
                self.audio.play("hit", 0.6)

    def update(self, dt, inp, mouse):
        self.time += dt
        self.banner_t -= dt
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        p = self.player
        p.update(dt, inp, self, mouse)
        self.level.update(dt, self)

        # стрелы
        for a in self.arrows:
            if a.stuck:
                if a.attach:
                    a.x = a.attach[0]["x"] + a.attach[1]
                a.timer += dt
                if a.timer > 5:
                    a.dead = True
                continue
            for _ in range(3):
                h = dt / 3
                a.vy += ARROW_G * h
                a.x += a.vx * h
                a.y += a.vy * h
                shot = None
                for fb in self.fireballs:
                    if fb.shootable and not fb.dead and math.hypot(a.x - fb.x, a.y - fb.y) <= fb.r + 6:
                        shot = fb
                        break
                if shot:
                    shot.dead = True
                    a.dead = True
                    self.particles_burst(shot.x, shot.y, 10, STYLE_COL.get(shot.style, (255, 255, 255)), 200, 0.5)
                    self.audio.play("hit", 0.6)
                    self.popup("Сбит!", shot.x, shot.y - 20, (200, 255, 200))
                    break
                r = self.level.on_arrow(a, self)
                if r == "remove":
                    a.dead = True
                    break
                if r == "stick":
                    a.stuck = True
                    break
                if a.y >= GROUND_Y or any(pl.collidepoint(a.x, a.y) for pl in self.platforms):
                    a.stuck = True
                    self.particles_burst(a.x, a.y, 4, (190, 170, 130), 80, 0.3, grav=200)
                    break
                if a.x < -60 or a.x > W + 60 or a.y < -500:
                    a.dead = True
                    break
        self.arrows = [a for a in self.arrows if not a.dead]

        # снаряды врагов
        for f in self.fireballs:
            if f.dead:
                continue
            if f.homing:
                tgt = math.atan2(p.y - 35 - f.y, p.x - f.x)
                cur = math.atan2(f.vy, f.vx)
                diff = (tgt - cur + math.pi) % math.tau - math.pi
                cur += clamp(diff, -f.homing * dt, f.homing * dt)
                sp = math.hypot(f.vx, f.vy)
                f.vx, f.vy = math.cos(cur) * sp, math.sin(cur) * sp
            f.vy += f.gravity * dt
            f.x += f.vx * dt
            f.y += f.vy * dt
            f.life -= dt
            if random.random() < 0.5:
                self.particles.append([f.x, f.y, random.uniform(-30, 30), random.uniform(-30, 30),
                                       0.35, 0.35, STYLE_COL.get(f.style, (255, 150, 40)), 4, 0])
            boom = f.life <= 0
            if f.ground:
                f.y = GROUND_Y - f.r
            elif f.solid:
                if f.y + f.r >= GROUND_Y or any(pl.collidepoint(f.x, f.y) for pl in self.platforms):
                    boom = True
            if circle_rect(f.x, f.y, f.r, p.rect()):
                p.hurt(f.dmg, f.x - f.vx * 0.01, self)
                if not f.pierce:
                    boom = True
            if f.x < -80 or f.x > W + 80 or f.y < -400 or f.y > H + 60:
                f.dead = True
            if boom:
                f.dead = True
                self.particles_burst(f.x, f.y, 14, STYLE_COL.get(f.style, (255, 150, 40)), 220, 0.5)
        self.fireballs = [f for f in self.fireballs if not f.dead]

        # частицы и подписи
        for q in self.particles:
            q[4] -= dt
            q[0] += q[2] * dt
            q[1] += q[3] * dt
            q[3] += q[8] * dt
        self.particles = [q for q in self.particles if q[4] > 0]
        for t in self.popups:
            t[3] -= dt
            t[2] -= 28 * dt
        self.popups = [t for t in self.popups if t[3] > 0]

        if p.hp <= 0 and self.finished is None:
            self.finished = "dead"

    def draw(self, surf, t):
        self.level.draw(surf, self)
        self.player.draw(surf)
        for a in self.arrows:
            a.draw(surf)
        for f in self.fireballs:
            f.draw(surf, self.time)
        for q in self.particles:
            k = q[4] / q[5]
            pygame.draw.circle(surf, q[6], (int(q[0]), int(q[1])), max(1, int(q[7] * k)))
        self.player.draw_preview(surf, self)
        fs = self.game.f_small
        for text, x, y, life, col in self.popups:
            draw_text(surf, fs, text, (int(x), int(y)), col, "center")
        if self.hurt_flash > 0:
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((200, 0, 0, int(110 * self.hurt_flash / 0.35)))
            surf.blit(ov, (0, 0))


# ----------------------------------------------------------------------------
# Игра: меню, лавка, диалоги, настройки, HUD, главный цикл
# ----------------------------------------------------------------------------
# ----------------------------------------------------------------------------
# Сюжет: кат-сцены (вступление у короля и финал со свадьбой)
# ----------------------------------------------------------------------------
CUT_FLOOR = 500

INTRO_STEPS = [
    {"scene": "throne", "who": "Король",
     "text": "Рыцарь! Беда пришла в наше королевство. Прошлой ночью огромный дракон спустился с гор и унёс мою дочь — принцессу Элару."},
    {"scene": "throne", "who": "Король",
     "text": "Он утащил её в своё логово, в вулканическую долину за болотами, лесами и горами. Дорога туда опасна: путь к дракону стерегут восемь свирепых чудовищ."},
    {"scene": "throne", "who": "Рыцарь",
     "text": "Ваше величество, я не позволю дракону держать принцессу в плену. Я готов отправиться в путь."},
    {"scene": "throne", "who": "Король",
     "text": "Для начала загляни на тренировочный двор: дракон не прощает слабости. Возьми стальной меч, лук и 120 стрел. А золото, что добудешь в боях, трать в лавке торговца Брома."},
    {"scene": "throne", "who": "Рыцарь",
     "text": "Клянусь честью: принцесса вернётся домой."},
    {"scene": "throne", "who": "Король",
     "text": "Да хранят тебя небеса, рыцарь! Верни мне дочь — и, быть может, судьба подарит тебе нечто большее, чем награда."},
]

ENDING_STEPS = [
    {"scene": "lair", "px": 930, "who": "Принцесса Элара",
     "text": "Дракон повержен… Я не верила, что кто-то дойдёт до его логова. Спасибо тебе, храбрый рыцарь!"},
    {"scene": "lair", "px": 930, "who": "Рыцарь",
     "text": "Принцесса Элара, вы в безопасности. Идёмте домой — король вас заждался."},
    {"scene": "lair", "px": 700, "who": "Принцесса Элара",
     "text": "Я видела отсюда вспышки огня и слышала рёв, и всё это время знала: ты не отступишь."},
    {"scene": "chapel", "who": "Рассказчик",
     "text": "Прошло несколько недель. Над королевством звонили колокола — весь город собрался на свадьбу."},
    {"scene": "chapel", "who": "Король", "hearts": True,
     "text": "Рыцарь, ты вернул мне дочь, а королевству — мир. Нет награды достойнее, чем её рука. Объявляю вас мужем и женой!"},
    {"scene": "chapel", "who": "Принцесса Элара", "hearts": True,
     "text": "Я согласна — и в горе, и в радости."},
    {"scene": "chapel", "who": "Рыцарь", "hearts": True,
     "text": "И в битвах с драконами тоже."},
    {"scene": "chapel", "who": "Торговец Бром", "wave": True,
     "text": "Дарю молодожёнам по зелью лечения — на случай семейных ссор!"},
    {"scene": "chapel", "who": "Рассказчик", "kiss": True,
     "text": "И жили они долго и счастливо. А над королевством больше никогда не поднималось драконье пламя."},
]


def blit_fig(s, fn, x, y, k=2.0, **kw):
    """Рисует фигуру во временной поверхности и масштабирует (ноги в точке x, y)."""
    tmp = pygame.Surface((200, 240), pygame.SRCALPHA)
    fn(tmp, 100, 220, **kw)
    img = pygame.transform.smoothscale(tmp, (int(200 * k), int(240 * k)))
    s.blit(img, (int(x - 100 * k), int(y - 220 * k)))


def draw_knight_fig(s, x, y, f=1, t=0.0, helmet=True, wedding=False, walk=0.0):
    steel = (172, 178, 192)
    sw = int(math.sin(walk) * 7) if walk else 0
    pygame.draw.rect(s, (70, 72, 90), (x - 13 + sw, y - 20, 11, 20), border_radius=3)
    pygame.draw.rect(s, (70, 72, 90), (x + 2 - sw, y - 20, 11, 20), border_radius=3)
    pygame.draw.rect(s, (40, 40, 52), (x - 14 + sw, y - 6, 13, 6), border_radius=2)
    pygame.draw.rect(s, (40, 40, 52), (x + 1 - sw, y - 6, 13, 6), border_radius=2)
    if not wedding:
        pygame.draw.ellipse(s, (45, 70, 140), (x - f * 20 - 9, y - 44, 18, 26))
        pygame.draw.ellipse(s, (220, 190, 70), (x - f * 20 - 9, y - 44, 18, 26), 2)
        pygame.draw.rect(s, steel, (x - 16, y - 42, 32, 24), border_radius=5)
        pygame.draw.rect(s, (50, 90, 170), (x - 8, y - 42, 16, 24))
    else:
        pygame.draw.rect(s, (244, 240, 230), (x - 16, y - 42, 32, 24), border_radius=5)
        pygame.draw.rect(s, (220, 180, 60), (x - 16, y - 42, 32, 24), 2, border_radius=5)
        pygame.draw.polygon(s, (170, 40, 60), [(x - f * 14, y - 42), (x - f * 30, y - 6), (x - f * 8, y - 18)])
    pygame.draw.line(s, (230, 200, 80), (x, y - 40), (x, y - 22), 2)
    pygame.draw.line(s, (230, 200, 80), (x - 5, y - 34), (x + 5, y - 34), 2)
    pygame.draw.rect(s, (110, 85, 55), (x - 16, y - 21, 32, 4))
    pygame.draw.line(s, (232, 236, 245), (x - f * 17, y - 22), (x - f * 24, y + 2), 4)
    if helmet:
        pygame.draw.polygon(s, (200, 45, 45), [(x - f * 2, y - 61), (x - f * 18, y - 66), (x - f * 13, y - 52)])
        pygame.draw.circle(s, (192, 197, 212), (x, y - 51), 10)
        pygame.draw.rect(s, (30, 30, 40), (x + (f * 3 if f > 0 else -9), y - 54, 6, 3))
    else:
        pygame.draw.circle(s, (232, 192, 152), (x, y - 51), 10)
        pygame.draw.polygon(s, (96, 62, 38), [(x - 10, y - 52), (x - 8, y - 63), (x + 8, y - 63), (x + 10, y - 52), (x + 4, y - 58)])
        pygame.draw.circle(s, (40, 30, 30), (x + f * 4, y - 51), 1)
        pygame.draw.circle(s, (40, 30, 30), (x - f * 2, y - 51), 1)
        pygame.draw.line(s, (150, 80, 70), (x - 2, y - 46), (x + 3, y - 46), 1)


def draw_princess(s, x, y, f=1, t=0.0, wedding=False, walk=0.0):
    sway = int(math.sin(walk) * 4) if walk else 0
    step = int(math.sin(walk) * 6) if walk else 0
    dress = (246, 244, 250) if wedding else (232, 120, 176)
    trim = (220, 180, 60) if wedding else (250, 210, 230)
    hair = (236, 196, 92)
    pygame.draw.polygon(s, hair, [(x - 14, y - 104), (x + 14, y - 104), (x + 19, y - 50), (x - 19, y - 50)])
    pygame.draw.ellipse(s, (120, 70, 90), (x - 18 + step, y - 4, 14, 7))
    pygame.draw.ellipse(s, (120, 70, 90), (x + 4 - step, y - 4, 14, 7))
    pygame.draw.polygon(s, dress, [(x - 12, y - 62), (x + 12, y - 62), (x + 38 + sway, y - 3), (x - 38 + sway, y - 3)])
    pygame.draw.polygon(s, trim, [(x - 38 + sway, y - 3), (x + 38 + sway, y - 3), (x + 36 + sway, y - 9), (x - 36 + sway, y - 9)])
    pygame.draw.rect(s, dress, (x - 12, y - 92, 24, 32), border_radius=5)
    pygame.draw.rect(s, trim, (x - 12, y - 64, 24, 4))
    pygame.draw.circle(s, (232, 192, 152), (x, y - 104), 13)
    pygame.draw.polygon(s, hair, [(x - 13, y - 106), (x - 8, y - 118), (x + 8, y - 118), (x + 13, y - 106), (x + 4, y - 112)])
    pygame.draw.circle(s, (50, 40, 40), (x + f * 4, y - 104), 1)
    pygame.draw.circle(s, (50, 40, 40), (x - f * 3, y - 104), 1)
    pygame.draw.line(s, (200, 90, 100), (x - 3, y - 98), (x + 3, y - 98), 1)
    for dx in (-7, 0, 7):
        pygame.draw.polygon(s, (240, 200, 60), [(x + dx - 3, y - 117), (x + dx + 3, y - 117), (x + dx, y - 125)])
    if wedding:
        # фата рисуется на отдельном слое и накладывается через blit: так прозрачность
        # смешивается с телом, а не «выедает» его (draw.polygon на SRCALPHA затирает пиксели)
        veil = pygame.Surface(s.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(veil, (255, 255, 255, 120), [(x - 12, y - 118), (x + 12, y - 118), (x + 30 * -f, y - 20), (x + 8 * -f, y - 20)])
        s.blit(veil, (0, 0))
        for dx, dy in ((0, 0), (6, 3), (-5, 4)):
            pygame.draw.circle(s, (240, 120, 160), (x + f * 16 + dx, y - 56 + dy), 4)
    else:
        pygame.draw.line(s, dress, (x + f * 10, y - 86), (x + f * 20, y - 66), 5)


def draw_king(s, x, y, t=0.0):
    robe = (168, 30, 44)
    pygame.draw.polygon(s, robe, [(x - 22, y - 92), (x + 22, y - 92), (x + 34, y), (x - 34, y)])
    pygame.draw.line(s, (230, 190, 60), (x, y - 84), (x, y - 8), 3)
    pygame.draw.rect(s, (240, 236, 226), (x - 24, y - 96, 48, 12), border_radius=6)
    for dx in (-16, -6, 6, 16):
        pygame.draw.circle(s, (30, 30, 36), (x + dx, y - 90), 2)
    pygame.draw.line(s, (200, 150, 110), (x - 22, y - 80), (x - 30, y - 50), 6)
    pygame.draw.circle(s, (232, 192, 152), (x, y - 110), 14)
    pygame.draw.polygon(s, (236, 236, 236), [(x - 13, y - 108), (x + 13, y - 108), (x + 9, y - 84), (x, y - 76), (x - 9, y - 84)])
    pygame.draw.line(s, (230, 230, 230), (x - 8, y - 106), (x + 8, y - 106), 3)
    pygame.draw.circle(s, (40, 30, 30), (x - 5, y - 113), 1)
    pygame.draw.circle(s, (40, 30, 30), (x + 5, y - 113), 1)
    pygame.draw.polygon(s, (236, 190, 60), [(x - 13, y - 122), (x - 13, y - 140), (x - 6, y - 130), (x, y - 144),
                                            (x + 6, y - 130), (x + 13, y - 140), (x + 13, y - 122)])
    pygame.draw.circle(s, (210, 40, 50), (x, y - 126), 3)
    pygame.draw.line(s, (236, 190, 60), (x + 32, y - 16), (x + 32, y - 112), 3)
    pygame.draw.circle(s, (80, 140, 230), (x + 32, y - 116), 7)


def draw_guest(s, x, y, col, t=0.0, k=1.4, merchant=False, wave=False):
    r = int(9 * k)
    pygame.draw.rect(s, col, (x - int(10 * k), y - int(26 * k), int(20 * k), int(26 * k)), border_radius=int(4 * k))
    pygame.draw.circle(s, (232, 192, 152), (x, y - int(34 * k)), r)
    if merchant:
        pygame.draw.polygon(s, (60, 80, 150), [(x - int(12 * k), y - int(38 * k)), (x + int(12 * k), y - int(38 * k)), (x + 2, y - int(62 * k))])
        pygame.draw.polygon(s, (236, 236, 236), [(x - int(8 * k), y - int(32 * k)), (x + int(8 * k), y - int(32 * k)), (x, y - int(16 * k))])
    else:
        pygame.draw.circle(s, (90, 60, 40), (x, y - int(38 * k)), r, 3)
    if wave:
        ang = math.sin(t * 9) * 0.5
        pygame.draw.line(s, (232, 192, 152), (x + int(8 * k), y - int(22 * k)),
                         (x + int(8 * k) + int(math.sin(ang) * 16 * k) + int(10 * k), y - int(46 * k)), 4)


def draw_throne(s, x, y):
    pygame.draw.rect(s, (110, 24, 36), (x - 70, y - 210, 140, 210), border_radius=10)
    pygame.draw.circle(s, (110, 24, 36), (x, y - 210), 70)
    pygame.draw.rect(s, (230, 190, 60), (x - 70, y - 210, 140, 210), 4, border_radius=10)
    pygame.draw.circle(s, (230, 190, 60), (x, y - 210), 70, 4)
    pygame.draw.rect(s, (230, 190, 60), (x - 78, y - 44, 156, 44), border_radius=6)
    pygame.draw.rect(s, (170, 30, 44), (x - 62, y - 56, 124, 24), border_radius=8)


def draw_altar(s, x, y, t=0.0):
    pygame.draw.line(s, (230, 190, 60), (x, y - 210), (x, y - 140), 6)
    pygame.draw.line(s, (230, 190, 60), (x - 22, y - 186), (x + 22, y - 186), 6)
    pygame.draw.rect(s, (246, 244, 250), (x - 100, y - 62, 200, 62), border_radius=4)
    pygame.draw.rect(s, (220, 180, 60), (x - 100, y - 62, 200, 62), 3, border_radius=4)
    for cx in (-80, 80):
        pygame.draw.rect(s, (250, 246, 230), (x + cx - 5, y - 92, 10, 30))
        fl = 5 + int(math.sin(t * 14 + cx) * 1.5)
        pygame.draw.circle(s, (255, 190, 70), (x + cx, y - 98), fl)
        pygame.draw.circle(s, (255, 240, 170), (x + cx, y - 98), max(2, fl - 3))


def draw_dead_dragon(s, x, y, t=0.0):
    pygame.draw.polygon(s, (60, 16, 20), [(x - 20, y - 50), (x + 50, y - 120), (x + 140, y - 40)])
    pygame.draw.ellipse(s, (96, 24, 28), (x - 130, y - 90, 280, 90))
    pygame.draw.ellipse(s, (150, 106, 66), (x - 90, y - 38, 200, 30))
    pygame.draw.ellipse(s, (96, 24, 28), (x + 110, y - 66, 110, 60))
    pygame.draw.line(s, (20, 0, 0), (x + 160, y - 42), (x + 176, y - 36), 3)
    pygame.draw.polygon(s, (230, 224, 210), [(x + 120, y - 62), (x + 100, y - 100), (x + 140, y - 66)])
    for i in range(5):
        sy = y - 90 - ((t * 34 + i * 28) % 130)
        pygame.draw.circle(s, (86, 84, 90), (int(x - 40 + i * 44 + math.sin(t + i) * 6), int(sy)), 10 + i % 3 * 3)


def draw_cage(s, x, y, open_amt):
    for i in range(-3, 3):
        pygame.draw.line(s, (180, 170, 120), (x + i * 20, y), (x + i * 20, y - 170), 4)
    top = (x + 60 + int(50 * open_amt), y - 170 + int(40 * open_amt))
    pygame.draw.line(s, (180, 170, 120), (x + 60, y), top, 4)
    pygame.draw.ellipse(s, (180, 170, 120), (x - 66, y - 184, 132, 28), 4)
    pygame.draw.rect(s, (110, 100, 70), (x - 70, y - 6, 140, 10))


def draw_torch(s, x, y, t):
    pygame.draw.rect(s, (70, 56, 50), (x - 4, y, 8, 40), border_radius=3)
    pygame.draw.rect(s, (100, 80, 60), (x - 9, y - 4, 18, 8), border_radius=3)
    fl = 10 + int(math.sin(t * 17 + x) * 2 + math.sin(t * 9) * 2)
    glow = pygame.Surface((160, 160), pygame.SRCALPHA)
    pygame.draw.circle(glow, (255, 170, 70, 40 + int(math.sin(t * 11) * 8)), (80, 80), 70)
    s.blit(glow, (x - 80, y - 100))
    pygame.draw.polygon(s, (255, 150, 40), [(x - 7, y - 4), (x + 7, y - 4), (x, y - 4 - fl * 2)])
    pygame.draw.polygon(s, (255, 230, 130), [(x - 3, y - 4), (x + 3, y - 4), (x, y - 4 - fl)])


def draw_heart(s, x, y, r, col):
    pygame.draw.circle(s, col, (x - r // 2, y), r // 2 + 1)
    pygame.draw.circle(s, col, (x + r // 2, y), r // 2 + 1)
    pygame.draw.polygon(s, col, [(x - r - 1, y + 1), (x + r + 1, y + 1), (x, y + r + 2)])


def make_bg_throne():
    rnd = random.Random(5)
    s = vgradient(W, H, (46, 36, 46), (104, 78, 64))
    for yy in range(0, 440, 44):
        pygame.draw.line(s, (62, 48, 56), (0, yy), (W, yy), 1)
        for xx in range((yy // 44 % 2) * 40, W, 80):
            pygame.draw.line(s, (62, 48, 56), (xx, yy), (xx, yy + 44), 1)
    for wx in (200, 480, 760, 1040):
        beam = pygame.Surface((220, 420), pygame.SRCALPHA)
        pygame.draw.polygon(beam, (255, 240, 190, 26), [(70, 0), (150, 0), (220, 420), (0, 420)])
        s.blit(beam, (wx - 110, 120))
        pygame.draw.rect(s, (150, 190, 240), (wx - 40, 90, 80, 200))
        pygame.draw.circle(s, (150, 190, 240), (wx, 90), 40)
        pygame.draw.rect(s, (70, 56, 60), (wx - 40, 90, 80, 200), 6)
        pygame.draw.circle(s, (70, 56, 60), (wx, 90), 40, 6)
        pygame.draw.line(s, (70, 56, 60), (wx, 50), (wx, 290), 4)
        pygame.draw.line(s, (70, 56, 60), (wx - 40, 180), (wx + 40, 180), 4)
    for bx in (340, 620, 900, 1180):
        pygame.draw.rect(s, (150, 28, 40), (bx - 24, 40, 48, 190))
        pygame.draw.polygon(s, (150, 28, 40), [(bx - 24, 230), (bx, 258), (bx + 24, 230)])
        pygame.draw.circle(s, (230, 190, 60), (bx, 120), 14, 3)
        pygame.draw.line(s, (230, 190, 60), (bx, 100), (bx, 140), 3)
    for px in (50, 1230):
        pygame.draw.rect(s, (90, 76, 84), (px - 30, 0, 60, 500))
        pygame.draw.rect(s, (110, 94, 102), (px - 40, 440, 80, 60))
    pygame.draw.rect(s, (70, 56, 62), (0, 450, W, H - 450))
    pygame.draw.rect(s, (150, 28, 40), (0, 466, W, 58))
    pygame.draw.rect(s, (230, 190, 60), (0, 466, W, 5))
    pygame.draw.rect(s, (230, 190, 60), (0, 519, W, 5))
    for yy in range(524, H, 36):
        pygame.draw.line(s, (56, 44, 50), (0, yy), (W, yy), 2)
    pygame.draw.rect(s, (120, 104, 112), (760, 480, 360, 26))
    pygame.draw.rect(s, (140, 124, 132), (800, 454, 280, 26))
    return s


def make_bg_chapel():
    rnd = random.Random(9)
    s = vgradient(W, H, (62, 50, 90), (206, 176, 146))
    cx, cy, R = 640, 190, 120
    pygame.draw.circle(s, (40, 34, 60), (cx, cy), R + 10)
    cols = [(220, 80, 80), (80, 120, 220), (240, 200, 80), (100, 200, 120)]
    for i in range(12):
        a0, a1 = i * math.tau / 12, (i + 1) * math.tau / 12
        pts = [(cx, cy)] + [(cx + math.cos(a0 + (a1 - a0) * k / 4) * R, cy + math.sin(a0 + (a1 - a0) * k / 4) * R) for k in range(5)]
        pygame.draw.polygon(s, cols[i % 4], pts)
    pygame.draw.circle(s, (40, 34, 60), (cx, cy), R, 5)
    pygame.draw.circle(s, (250, 240, 200), (cx, cy), 26)
    beam = pygame.Surface((520, 400), pygame.SRCALPHA)
    pygame.draw.polygon(beam, (255, 240, 200, 30), [(200, 0), (320, 0), (520, 400), (0, 400)])
    s.blit(beam, (cx - 260, 250))
    for px in (110, 330, 950, 1170):
        pygame.draw.rect(s, (156, 146, 156), (px - 28, 110, 56, 360))
        pygame.draw.rect(s, (176, 166, 176), (px - 38, 96, 76, 24), border_radius=4)
        for k in range(12):
            pygame.draw.circle(s, rnd.choice([(240, 120, 160), (255, 255, 255), (250, 210, 90)]), (px - 26 + (k % 2) * 52, 150 + k * 24), 5)
    pygame.draw.rect(s, (150, 128, 118), (0, 450, W, H - 450))
    for yy in range(458, H, 38):
        pygame.draw.line(s, (126, 106, 98), (0, yy), (W, yy), 2)
    pygame.draw.polygon(s, (170, 40, 60), [(540, H), (740, H), (700, 450), (580, 450)])
    pygame.draw.polygon(s, (230, 190, 60), [(540, H), (548, H), (584, 450), (580, 450)])
    pygame.draw.polygon(s, (230, 190, 60), [(740, H), (732, H), (696, 450), (700, 450)])
    for side in (0, 1):
        for row, (yy, ww) in enumerate(((466, 300), (512, 340))):
            px = 130 if side == 0 else W - 130 - ww
            pygame.draw.rect(s, (110, 76, 50), (px, yy, ww, 24), border_radius=4)
            pygame.draw.rect(s, (80, 54, 36), (px, yy, ww, 24), 2, border_radius=4)
    return s


def wrap_text(font, text, width):
    lines, cur = [], ""
    for wd in text.split(" "):
        t = (cur + " " + wd).strip()
        if font.size(t)[0] <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    return lines


def draw_potion(surf, cx, cy, color, scale=1.0):
    r = int(14 * scale)
    pygame.draw.rect(surf, (210, 215, 225), (cx - int(5 * scale), cy - int(24 * scale), int(10 * scale), int(14 * scale)))
    pygame.draw.rect(surf, (150, 100, 60), (cx - int(6 * scale), cy - int(28 * scale), int(12 * scale), int(6 * scale)))
    pygame.draw.circle(surf, (225, 232, 242), (cx, cy), r + 2)
    pygame.draw.circle(surf, color, (cx, cy + 2), r - 1)
    pygame.draw.circle(surf, (255, 255, 255), (cx - r // 3, cy - r // 3), max(2, r // 5))


HEAL_PITCH = [
    "А-а, ценитель жизни! Зелье лечения: выпьешь — и раны затянутся быстрее, чем дракон успеет чихнуть. Всего %d монет.",
    "Красное, как закат, и приятнее на вкус, чем походная похлёбка. Восстанавливает 50 здоровья. %d монет!",
    "Говорят, одного глотка хватило, чтобы вернуть воина с того света. Сам не проверял, но %d монет — цена честная.",
]
BUFF_PITCH = [
    "Синее, искрится и слегка кусается. На 20 секунд удары станут сильнее, а ноги — быстрее. %d монет.",
    "Осторожно, рыцарь: после глотка захочется драться со всем подряд. %d монет — и оно твоё.",
    "Мой секретный рецепт! Основа — драконий перец и немного здравого смысла. Совсем немного. %d монет.",
]
KNIGHT_LINES = [
    "Беру. Надеюсь, на вкус не хуже, чем на вид.",
    "То, что нужно перед боем.",
    "Давай сюда. Мне ещё чудовищ побеждать.",
]
POOR_LINES = [
    "Эй, рыцарь, тут не благотворительность! Не хватает ещё %d монет.",
    "Хм… в твоём кошельке гуляет ветер. Победи ещё пару чудовищ и возвращайся — не хватает %d монет.",
]
GREETINGS = [
    "О, храбрый рыцарь! Заходи в лавку Брома — лучшие зелья по эту сторону гор!",
    "Слышал, ты расправился с чудовищем! Монеты звенят, самое время потратить их с умом.",
    "Добро пожаловать! Запомни: лечить раны дороже, чем покупать зелья.",
]


class Game:
    def __init__(self):
        pygame.mixer.pre_init(22050, -16, 1, 512)
        pygame.init()
        pygame.display.set_caption("Рыцарь и Дракон")
        self.settings = Settings()
        self.screen = None
        self.apply_display()
        self.clock = pygame.time.Clock()
        self.f_title = load_font(76, True)
        self.f_big = load_font(40, True)
        self.f = load_font(26)
        self.f_small = load_font(20)
        self.f_tiny = load_font(16)
        self.audio = Audio(self.settings)
        self.input = Input(self.settings)
        self.bg_cache = {}
        self.inv = {"gold": 0, "heal": 0, "buff": 0}
        self.inv_snapshot = dict(self.inv)
        self.stage = 0
        self.next_stage = 1
        self.last_reward = 0
        self.progress = self.load_progress()
        self.state = "menu"
        self.sel = 0
        self.world = None
        self.bind_wait = None
        self.settings_return = "menu"
        self.notice = ""
        self.notice_t = 0.0
        self.time = 0.0
        self.dialog = None
        self.dialog_t = 0.0
        self.dsel = 0
        self.cut_end = None
        self.fx = []
        self.scene_name = None
        self.scene_t = 0.0
        self.cut_px = 930.0
        self.door = 0.0
        self.kiss = 0.0
        self.princess_walk = False
        self.set_state("menu")

    # ---------- служебное ----------
    def apply_display(self):
        flags = pygame.SCALED
        if self.settings.fullscreen:
            flags |= pygame.FULLSCREEN
        try:
            self.screen = pygame.display.set_mode((W, H), flags)
        except Exception:
            self.screen = pygame.display.set_mode((W, H))

    def get_bg(self, theme):
        bg = self.bg_cache.get(theme)
        if bg is None:
            if theme == "meadow":
                bg = make_bg1()
            elif theme == "volcano":
                bg = make_bg2()
            elif theme == "market":
                bg = make_bg_market()
            elif theme == "throne":
                bg = make_bg_throne()
            elif theme == "chapel":
                bg = make_bg_chapel()
            else:
                bg = make_bg_theme(theme)
            self.bg_cache[theme] = bg
        return bg

    def set_state(self, s):
        self.state = s
        self.sel = 0
        self.bind_wait = None
        self.dialog = None
        pygame.mouse.set_visible(s != "play")

    def quit(self):
        self.settings.save()
        pygame.quit()
        sys.exit()

    def note(self, text):
        self.notice = text
        self.notice_t = 3.0

    # ---------- прогресс ----------
    def load_progress(self):
        try:
            with open(SAVE_PATH, "r", encoding="utf-8") as f:
                d = json.load(f)
            stage = int(d["stage"])
            if 1 <= stage <= FINAL_STAGE:
                return {"stage": stage, "gold": max(0, int(d.get("gold", 0))),
                        "heal": clamp(int(d.get("heal", 0)), 0, MAX_POTIONS),
                        "buff": clamp(int(d.get("buff", 0)), 0, MAX_POTIONS)}
        except Exception:
            pass
        return None

    def save_progress(self, stage):
        self.progress = {"stage": stage, "gold": self.inv["gold"], "heal": self.inv["heal"], "buff": self.inv["buff"]}
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.progress, f)
        except Exception:
            pass

    def delete_save(self):
        self.progress = None
        try:
            os.remove(SAVE_PATH)
        except Exception:
            pass

    def new_game(self):
        self.inv.update(gold=0, heal=0, buff=0)
        self.start_cutscene(INTRO_STEPS, lambda: self.start_stage(0))

    def start_cutscene(self, steps, on_end):
        self.set_state("cutscene")
        self.cut_end = on_end
        self.fx = []
        self.scene_name = None
        self.scene_t = 0.0
        self.cut_px = 930.0
        self.door = 0.0
        self.kiss = 0.0
        self.talk(steps)
        self.dialog_t = -(2.0 if steps[0].get("scene") == "chapel" else 1.4)

    def finish_cutscene(self):
        end, self.cut_end = self.cut_end, None
        self.fx = []
        self.scene_name = None
        if end:
            end()

    def continue_game(self):
        pr = self.progress
        if not pr:
            return self.new_game()
        self.inv.update(gold=pr["gold"], heal=pr["heal"], buff=pr["buff"])
        self.next_stage = pr["stage"]
        self.open_shop()

    def start_final(self):
        self.inv.update(gold=0, heal=3, buff=2)
        self.start_stage(FINAL_STAGE)

    def start_stage(self, i):
        self.stage = i
        self.inv_snapshot = dict(self.inv)
        self.world = World(self, i)
        self.set_state("play")

    def retry(self):
        self.inv.update(self.inv_snapshot)
        self.start_stage(self.stage)

    def on_clear(self):
        lv = self.world.level
        self.last_reward = lv.reward
        self.inv["gold"] += lv.reward
        self.next_stage = self.stage + 1
        self.save_progress(self.next_stage)
        self.audio.play("coin")
        self.set_state("clear")

    def on_win(self):
        lv = self.world.level
        self.last_reward = lv.reward
        self.inv["gold"] += lv.reward
        self.delete_save()
        self.settings.completed = True
        self.settings.save()
        self.audio.play("coin")
        self.start_cutscene(ENDING_STEPS, lambda: self.set_state("win"))

    # ---------- лавка и диалоги ----------
    def talk(self, steps):
        self.dialog = {"steps": steps, "i": 0}
        self.dialog_t = 0.0
        self.dsel = 0

    def dialog_step(self):
        return self.dialog["steps"][self.dialog["i"]]

    def dialog_done(self):
        return int(self.dialog_t * 55) >= len(self.dialog_step()["text"])

    def dialog_advance(self):
        d = self.dialog
        d["i"] += 1
        self.dialog_t = 0.0
        self.dsel = 0
        if d["i"] >= len(d["steps"]):
            self.dialog = None

    def dialog_choose(self, idx):
        label, fn = self.dialog_step()["choices"][idx]
        self.dialog = None
        fn()

    def choice_rects(self, n):
        box = pygame.Rect(60, 516, 1160, 170)
        return [pygame.Rect(box.x + 24 + i * 356, box.bottom - 58, 340, 42) for i in range(n)]

    def open_shop(self):
        self.set_state("shop")
        ns = self.next_stage
        if ns == 1:
            first = "Новенький? Тренировочный двор остался позади, а впереди настоящие чудовища. Мои зелья тебе пригодятся!"
        else:
            first = random.choice(GREETINGS)
        steps = [{"who": "Торговец Бром", "text": first}]
        hk = bind_name(self.settings.binds["heal"], True)
        bk = bind_name(self.settings.binds["buff"], True)
        if ns == FINAL_STAGE:
            steps.append({"who": "Торговец Бром",
                          "text": "Постой… ты идёшь к дракону?! Тогда бери побольше зелий. Лечение — на [%s], усиление — на [%s]." % (hk, bk)})
        self.talk(steps)

    def begin_purchase(self, key):
        it = SHOP_ITEMS[key]
        price = it["price"]
        who = "Торговец Бром"
        if self.inv[key] >= MAX_POTIONS:
            self.talk([{"who": who, "text": "Твоя сумка уже трещит по швам, рыцарь! Сначала используй то, что есть."}])
        elif self.inv["gold"] < price:
            self.talk([{"who": who, "text": random.choice(POOR_LINES) % (price - self.inv["gold"])}])
        else:
            pitch = random.choice(HEAL_PITCH if key == "heal" else BUFF_PITCH) % price
            self.talk([{"who": who, "text": pitch,
                        "choices": [("Беру! (-%d)" % price, lambda: self.confirm_purchase(key)),
                                    ("Пожалуй, не сейчас", self.decline_purchase)]}])

    def confirm_purchase(self, key):
        it = SHOP_ITEMS[key]
        self.inv["gold"] -= it["price"]
        self.inv[key] += 1
        self.save_progress(self.next_stage)
        self.audio.play("coin")
        kb = bind_name(self.settings.binds[key], True)
        what = "Выпей его в бою, нажав [%s]. Здоровья тебе!" % kb if key == "heal" else \
            "Нажми [%s], когда придёт время показать чудовищам, кто здесь главный." % kb
        self.talk([{"who": "Рыцарь", "text": random.choice(KNIGHT_LINES)},
                   {"who": "Торговец Бром", "text": "Держи! " + what}])

    def decline_purchase(self):
        self.talk([{"who": "Торговец Бром", "text": "Как знаешь. Моё предложение остаётся в силе."}])

    # ---------- пункты меню ----------
    def items(self):
        s, st = self.state, self.settings

        def B(label, fn):
            return {"kind": "button", "label": label, "fn": fn}

        if s == "menu":
            its = []
            if self.progress:
                n = self.progress["stage"]
                lbl = "Продолжить (финал)" if n >= FINAL_STAGE else "Продолжить (бой %d)" % n
                its += [B(lbl, self.continue_game), B("Новая игра", self.new_game)]
            else:
                its.append(B("Играть", self.new_game))
            if st.completed:
                its.append(B("Сразу к дракону (быстрый старт)", self.start_final))
            its += [B("Настройки", lambda: self.open_settings("menu")),
                    B("Выход", self.quit)]
            return its
        if s == "pause":
            return [B("Продолжить", lambda: self.set_state("play")),
                    B("Настройки", lambda: self.open_settings("pause")),
                    B("В главное меню", lambda: self.set_state("menu"))]
        if s == "over":
            return [B("Попробовать снова", self.retry),
                    B("В главное меню", lambda: self.set_state("menu"))]
        if s == "win":
            return [B("Играть снова", self.new_game),
                    B("В главное меню", lambda: self.set_state("menu"))]
        if s == "clear":
            return [B("В лавку торговца", self.open_shop),
                    B("В главное меню", lambda: self.set_state("menu"))]
        if s == "shop":
            def row(key):
                it = SHOP_ITEMS[key]
                return {"kind": "button", "label": it["name"],
                        "sub": "%s — в сумке: %d" % (it["desc"], self.inv[key]),
                        "right": "%d мон." % it["price"],
                        "fn": (lambda k=key: self.begin_purchase(k))}
            return [row("heal"), row("buff"),
                    {"kind": "button", "label": "В бой!", "sub": stage_title(self.next_stage),
                     "fn": lambda: self.start_stage(self.next_stage)},
                    B("В главное меню", lambda: self.set_state("menu"))]
        if s == "settings":
            def set_vol(v):
                st.volume = clamp(v, 0.0, 1.0)
                st.save()

            def tog_fs():
                st.fullscreen = not st.fullscreen
                st.save()
                self.apply_display()

            def tog_fps():
                st.show_fps = not st.show_fps
                st.save()

            def step_fps(d=1):
                i = FPS_OPTIONS.index(st.fps_limit) if st.fps_limit in FPS_OPTIONS else 1
                st.fps_limit = FPS_OPTIONS[(i + d) % len(FPS_OPTIONS)]
                st.save()
            return [
                {"kind": "slider", "label": "Громкость", "get": lambda: st.volume, "set": set_vol},
                {"kind": "toggle", "label": "Полный экран (F11)", "fn": tog_fs,
                 "value": lambda: "Вкл" if st.fullscreen else "Выкл"},
                {"kind": "toggle", "label": "Частота кадров (FPS)", "fn": step_fps, "adjust": step_fps,
                 "value": lambda: "Без лимита" if st.fps_limit == 0 else str(st.fps_limit)},
                {"kind": "toggle", "label": "Показывать FPS", "fn": tog_fps,
                 "value": lambda: "Вкл" if st.show_fps else "Выкл"},
                B("Управление (клавиши)", lambda: self.set_state("controls")),
                B("Назад", self.back),
            ]
        if s == "controls":
            its = []
            for a, label in ACTIONS:
                its.append({"kind": "bind", "action": a, "label": label,
                            "value": (lambda a=a: bind_name(st.binds[a]))})

            def reset():
                st.reset_binds()
                st.save()
                self.note("Клавиши сброшены по умолчанию")
            its.append(B("Сбросить по умолчанию", reset))
            its.append(B("Назад", self.back))
            return its
        return []

    def open_settings(self, ret):
        self.settings_return = ret
        self.set_state("settings")

    def back(self):
        s = self.state
        if s == "settings":
            self.set_state(self.settings_return)
        elif s == "controls":
            self.set_state("settings")
        elif s == "pause":
            self.set_state("play")
        elif s == "over":
            self.set_state("menu")

    def item_rects(self, items):
        n = len(items)
        if self.state == "controls":
            bw, bh, gap, top = 720, 42, 6, 168
        elif self.state == "shop":
            bw, bh, gap, top = 560, 68, 14, 150
        else:
            bw, bh, gap = 560, 56, 16
            total = n * bh + (n - 1) * gap
            top = 330 if self.state == "menu" else max(190, (H - total) // 2 + 40)
        x = 70 if self.state == "shop" else (W - bw) // 2
        return [pygame.Rect(x, top + i * (bh + gap), bw, bh) for i in range(n)]

    def slider_rect(self, r):
        return pygame.Rect(r.right - 260, r.centery - 6, 230, 12)

    def activate(self, item, pos=None, rect=None):
        k = item["kind"]
        if k == "slider":
            if pos and rect:
                sr = self.slider_rect(rect).inflate(16, 24)
                if sr.collidepoint(pos):
                    bar = self.slider_rect(rect)
                    item["set"](clamp((pos[0] - bar.x) / bar.w, 0, 1))
                    self.audio.play("click")
            return
        self.audio.play("click")
        if k == "bind":
            self.bind_wait = item["action"]
        else:
            item["fn"]()

    # ---------- события ----------
    def handle_event(self, e):
        if e.type == pygame.QUIT:
            self.quit()
        if e.type == pygame.KEYDOWN and e.key == pygame.K_F11:
            self.settings.fullscreen = not self.settings.fullscreen
            self.settings.save()
            self.apply_display()
            return
        if self.state == "play":
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                self.set_state("pause")
            elif e.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
                self.set_state("pause")
            return
        if self.state not in ("menu", "pause", "over", "win", "clear", "shop", "cutscene", "settings", "controls"):
            return

        # диалог в лавке
        if self.state in ("shop", "cutscene") and self.dialog:
            st = self.dialog_step()
            done = self.dialog_done()
            ch = st.get("choices")
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.dialog = None
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    if not done:
                        self.dialog_t = 999.0
                    elif ch:
                        self.dialog_choose(self.dsel)
                    else:
                        self.dialog_advance()
                elif done and ch and e.key in (pygame.K_LEFT, pygame.K_UP):
                    self.dsel = (self.dsel - 1) % len(ch)
                elif done and ch and e.key in (pygame.K_RIGHT, pygame.K_DOWN):
                    self.dsel = (self.dsel + 1) % len(ch)
            elif e.type == pygame.MOUSEMOTION and ch and done:
                for i, r in enumerate(self.choice_rects(len(ch))):
                    if r.collidepoint(e.pos):
                        self.dsel = i
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if not done:
                    self.dialog_t = 999.0
                elif ch:
                    for i, r in enumerate(self.choice_rects(len(ch))):
                        if r.collidepoint(e.pos):
                            self.dialog_choose(i)
                            break
                else:
                    self.dialog_advance()
            if self.state == "cutscene" and self.dialog is None:
                self.finish_cutscene()
            return

        # ожидание новой клавиши
        if self.bind_wait is not None:
            new = None
            if e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.bind_wait = None
                    return
                new = ("k", e.key)
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button in (1, 2, 3):
                new = ("m", e.button)
            if new:
                self.rebind(self.bind_wait, new)
                self.bind_wait = None
            return

        items = self.items()
        rects = self.item_rects(items)
        if not items:
            return
        self.sel = clamp(self.sel, 0, len(items) - 1)
        if e.type == pygame.KEYDOWN:
            if e.key == pygame.K_ESCAPE:
                self.back()
            elif e.key == pygame.K_UP:
                self.sel = (self.sel - 1) % len(items)
            elif e.key == pygame.K_DOWN:
                self.sel = (self.sel + 1) % len(items)
            elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.activate(items[self.sel])
            elif e.key in (pygame.K_LEFT, pygame.K_RIGHT):
                it = items[self.sel]
                if it["kind"] == "slider":
                    it["set"](round(it["get"]() + (0.1 if e.key == pygame.K_RIGHT else -0.1), 2))
                    self.audio.play("click")
                elif "adjust" in it:
                    it["adjust"](1 if e.key == pygame.K_RIGHT else -1)
                    self.audio.play("click")
        elif e.type == pygame.MOUSEMOTION:
            for i, r in enumerate(rects):
                if r.collidepoint(e.pos):
                    self.sel = i
        elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            for i, r in enumerate(rects):
                if r.collidepoint(e.pos):
                    self.sel = i
                    self.activate(items[i], e.pos, r)
                    break

    def rebind(self, action, new):
        b = self.settings.binds
        for a in b:
            if a != action and b[a] == new:
                b[a] = b[action]
                self.note("Клавиша уже использовалась — действия поменялись местами")
        b[action] = new
        self.settings.save()

    # ---------- обновление ----------
    def update(self, dt):
        self.time += dt
        self.notice_t = max(0.0, self.notice_t - dt)
        if self.state in ("shop", "cutscene") and self.dialog:
            self.dialog_t += dt
        if self.state == "cutscene":
            self.update_cutscene(dt)
        if self.state == "play" and self.world:
            w = self.world
            w.update(dt, self.input, pygame.mouse.get_pos())
            fin = w.finished
            if fin == "clear":
                self.on_clear()
            elif fin == "dead":
                self.set_state("over")
            elif fin == "win":
                self.on_win()

    # ---------- отрисовка ----------
    def draw(self):
        s = self.screen
        st = self.state
        if st == "menu":
            s.blit(self.get_bg("meadow"), (0, 0))
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 20, 130))
            s.blit(ov, (0, 0))
            draw_text(s, self.f_title, "РЫЦАРЬ И ДРАКОН", (W // 2, 120), (245, 215, 110), "center")
            draw_text(s, self.f, "Спаси принцессу из лап дракона", (W // 2, 195), (230, 230, 240), "center")
            if self.progress:
                draw_text(s, self.f_small, "Сохранение: монет %d, зелий лечения %d, усиления %d" %
                          (self.progress["gold"], self.progress["heal"], self.progress["buff"]),
                          (W // 2, 250), (245, 215, 110), "center")
            self.draw_items()
            draw_text(s, self.f_tiny, "Esc — пауза/назад   •   F11 — полный экран", (W // 2, H - 30), (200, 200, 215), "center")
        elif st == "shop":
            self.draw_shop()
        elif st == "cutscene":
            self.draw_cutscene()
        elif st in ("play", "pause", "over", "win", "clear") and self.world:
            self.world.draw(s, self.time)
            if st == "play":
                self.draw_hud()
                self.draw_crosshair()
            else:
                ov = pygame.Surface((W, H), pygame.SRCALPHA)
                col = {"pause": (0, 0, 20, 150), "over": (60, 0, 0, 170),
                       "win": (40, 30, 0, 150), "clear": (0, 24, 10, 150)}[st]
                ov.fill(col)
                s.blit(ov, (0, 0))
                lv = self.world.level
                if st == "pause":
                    draw_text(s, self.f_big, "Пауза", (W // 2, 130), (245, 215, 110), "center")
                elif st == "over":
                    draw_text(s, self.f_title, "Вы пали в бою", (W // 2, 130), (245, 215, 110), "center")
                    draw_text(s, self.f, "Зелья и монеты вернутся к началу боя — попробуйте снова!", (W // 2, 205), (255, 220, 220), "center")
                elif st == "clear":
                    name = (lv.boss.name + " повержен!") if hasattr(lv, "boss") else "Тренировка пройдена!"
                    draw_text(s, self.f_title, "ПОБЕДА!", (W // 2, 100), (245, 215, 110), "center")
                    draw_text(s, self.f_big, name, (W // 2, 175), (255, 255, 255), "center")
                    draw_text(s, self.f, "Награда: +%d монет" % self.last_reward, (W // 2, 232), (255, 220, 90), "center")
                    draw_text(s, self.f, "Всего монет: %d" % self.inv["gold"], (W // 2, 270), (255, 255, 255), "center")
                elif st == "win":
                    draw_text(s, self.f_title, "ПОБЕДА!", (W // 2, 110), (245, 215, 110), "center")
                    draw_text(s, self.f, "Дракон повержен, принцесса спасена, а в королевстве сыграли свадьбу!", (W // 2, 190), (255, 255, 255), "center")
                    draw_text(s, self.f, "Награда: +%d монет   •   Всего монет: %d" % (self.last_reward, self.inv["gold"]),
                              (W // 2, 232), (255, 220, 90), "center")
                    draw_text(s, self.f_small, "В главном меню открыт «быстрый старт» — сразу к бою с драконом",
                              (W // 2, 270), (200, 230, 255), "center")
                self.draw_items()
        elif st in ("settings", "controls"):
            s.blit(self.get_bg("meadow"), (0, 0))
            ov = pygame.Surface((W, H), pygame.SRCALPHA)
            ov.fill((0, 0, 20, 175))
            s.blit(ov, (0, 0))
            draw_text(s, self.f_big, "Настройки" if st == "settings" else "Управление", (W // 2, 85),
                      (245, 215, 110), "center")
            if st == "controls":
                draw_text(s, self.f_small, "Выберите действие и нажмите любую клавишу или кнопку мыши (Esc — отмена)",
                          (W // 2, 130), (220, 220, 235), "center")
            self.draw_items()
        if self.notice_t > 0:
            draw_text(s, self.f_small, self.notice, (W // 2, H - 50), (255, 220, 120), "center")
        if self.settings.show_fps:
            draw_text(s, self.f_tiny, "FPS: %d" % self.clock.get_fps(), (W - 10, H - 8), (255, 255, 255), "bottomright")

    def draw_items(self):
        s = self.screen
        items = self.items()
        rects = self.item_rects(items)
        self.sel = clamp(self.sel, 0, max(0, len(items) - 1))
        blocked = self.state == "shop" and self.dialog is not None
        for i, (it, r) in enumerate(zip(items, rects)):
            selected = i == self.sel and not blocked
            waiting = it["kind"] == "bind" and self.bind_wait == it["action"]
            fill = (70, 56, 24, 235) if (selected or waiting) else (20, 22, 40, 215)
            border = (245, 215, 110) if (selected or waiting) else (90, 96, 130)
            panel(s, r, fill, 10, border)
            if it["kind"] == "button":
                if "sub" in it:
                    draw_text(s, self.f, it["label"], (r.x + 20, r.centery - 12), (255, 255, 255), "midleft")
                    draw_text(s, self.f_tiny, it["sub"], (r.x + 20, r.centery + 16), (200, 205, 225), "midleft")
                elif "right" in it:
                    draw_text(s, self.f, it["label"], (r.x + 20, r.centery), (255, 255, 255), "midleft")
                else:
                    draw_text(s, self.f, it["label"], r.center, (255, 255, 255), "center")
                if "right" in it:
                    draw_text(s, self.f, it["right"], (r.right - 20, r.centery), (255, 220, 90), "midright")
            else:
                draw_text(s, self.f, it["label"], (r.x + 20, r.centery), (255, 255, 255), "midleft")
                if it["kind"] == "slider":
                    bar = self.slider_rect(r)
                    pygame.draw.rect(s, (50, 54, 80), bar, border_radius=6)
                    v = it["get"]()
                    pygame.draw.rect(s, (245, 215, 110), (bar.x, bar.y, int(bar.w * v), bar.h), border_radius=6)
                    pygame.draw.circle(s, (255, 255, 255), (bar.x + int(bar.w * v), bar.centery), 10)
                    draw_text(s, self.f_small, "%d%%" % round(v * 100), (bar.x - 14, r.centery), (255, 255, 255), "midright")
                elif it["kind"] == "toggle":
                    draw_text(s, self.f, it["value"](), (r.right - 24, r.centery), (245, 215, 110), "midright")
                elif it["kind"] == "bind":
                    txt = "Нажмите клавишу…" if waiting else it["value"]()
                    draw_text(s, self.f, txt, (r.right - 24, r.centery),
                              (255, 255, 160) if waiting else (245, 215, 110), "midright")

    # ---------- лавка ----------
    def draw_merchant(self, s):
        t = self.time
        bob = int(math.sin(t * 2) * 3)
        for i in range(10):
            col = (190, 50, 50) if i % 2 == 0 else (236, 226, 206)
            pygame.draw.rect(s, col, (660 + i * 58, 226, 58, 62))
            pygame.draw.circle(s, col, (689 + i * 58, 288), 29)
        for px in (672, 1216):
            pygame.draw.rect(s, (96, 66, 44), (px - 6, 290, 12, 240))
        pygame.draw.rect(s, (66, 46, 40), (694, 300, 524, 200))
        for sy in (360, 440):
            pygame.draw.rect(s, (112, 80, 54), (694, sy, 524, 10))
        cols = [(210, 50, 60), (60, 110, 230), (80, 200, 100), (170, 80, 220)]
        for i in range(8):
            draw_potion(s, 730 + i * 62, 352, cols[i % 4], 0.8)
            draw_potion(s, 760 + i * 62, 432, cols[(i + 2) % 4], 0.8)
        pygame.draw.polygon(s, (96, 70, 120), [(902, 540), (1022, 540), (1002, 420 + bob), (922, 420 + bob)])
        pygame.draw.circle(s, (232, 192, 152), (962, 390 + bob), 34)
        pygame.draw.polygon(s, (232, 232, 232), [(934, 402 + bob), (990, 402 + bob), (962, 464 + bob)])
        pygame.draw.polygon(s, (60, 80, 150), [(922, 372 + bob), (1002, 372 + bob), (964, 300 + bob)])
        pygame.draw.ellipse(s, (60, 80, 150), (908, 360 + bob, 108, 22))
        pygame.draw.circle(s, (30, 30, 40), (950, 392 + bob), 4)
        pygame.draw.circle(s, (30, 30, 40), (974, 392 + bob), 4)
        pygame.draw.circle(s, (214, 140, 120), (962, 404 + bob), 6)
        pygame.draw.rect(s, (124, 88, 56), (680, 500, 560, 120), border_radius=6)
        pygame.draw.rect(s, (150, 108, 70), (668, 488, 584, 20), border_radius=6)
        draw_potion(s, 760, 484, (210, 50, 60), 1.5)
        draw_potion(s, 830, 484, (60, 110, 230), 1.5)
        glow = pygame.Surface((160, 160), pygame.SRCALPHA)
        pygame.draw.circle(glow, (255, 200, 90, 70), (80, 80), 80)
        s.blit(glow, (1110, 240))
        pygame.draw.rect(s, (60, 50, 44), (1180, 292, 20, 28), border_radius=4)
        pygame.draw.circle(s, (255, 214, 120), (1190, 306), 8)

    def draw_shop(self):
        s = self.screen
        s.blit(self.get_bg("market"), (0, 0))
        self.draw_merchant(s)
        draw_text(s, self.f_big, "Лавка торговца Брома", (70, 60), (245, 215, 110), "topleft")
        pygame.draw.circle(s, (240, 200, 60), (W - 190, 82), 14)
        pygame.draw.circle(s, (200, 150, 30), (W - 190, 82), 14, 3)
        draw_text(s, self.f_big, "%d" % self.inv["gold"], (W - 164, 82), (255, 230, 120), "midleft")
        self.draw_items()
        if self.dialog:
            self.draw_dialog()

    def draw_dialog(self):
        s = self.screen
        st = self.dialog_step()
        box = pygame.Rect(60, 516, 1160, 170)
        panel(s, box, (14, 12, 26, 240), 14, (245, 215, 110))
        plate = pygame.Rect(box.x + 20, box.y - 18, 250, 36)
        panel(s, plate, (90, 66, 20, 250), 10, (245, 215, 110))
        draw_text(s, self.f_small, st["who"], plate.center, (255, 240, 200), "center")
        lines = wrap_text(self.f, st["text"], box.w - 60)
        remaining = int(self.dialog_t * 55)
        for i, ln in enumerate(lines):
            part = ln[:max(0, remaining)]
            remaining -= len(ln) + 1
            if part:
                draw_text(s, self.f, part, (box.x + 28, box.y + 32 + i * 32), (255, 255, 255), "topleft")
        if self.dialog_done():
            ch = st.get("choices")
            if ch:
                for i, r in enumerate(self.choice_rects(len(ch))):
                    sel = i == self.dsel
                    panel(s, r, (70, 56, 24, 240) if sel else (24, 26, 46, 230), 10,
                          (245, 215, 110) if sel else (90, 96, 130))
                    draw_text(s, self.f_small, ch[i][0], r.center, (255, 255, 255), "center")
            else:
                draw_text(s, self.f_tiny, "Enter / ЛКМ — дальше", (box.right - 20, box.bottom - 14), (200, 205, 225), "bottomright")

    # ---------- кат-сцены ----------
    def cut_speaker(self, step):
        return {"Король": "king", "Рыцарь": "knight", "Принцесса Элара": "princess",
                "Торговец Бром": "merchant"}.get(step.get("who"))

    def update_cutscene(self, dt):
        if not self.dialog:
            return
        step = self.dialog_step()
        sc = step.get("scene", "throne")
        if sc != self.scene_name:
            self.scene_name = sc
            self.scene_t = 0.0
            self.fx = []
            self.cut_px = 930.0
            self.door = 0.0
            self.kiss = 0.0
            self.dialog_t = -(2.0 if sc == "chapel" else 1.4)   # пауза на «выход» героев
            if sc == "throne":
                for _ in range(30):
                    self.fx.append([random.uniform(150, 1130), random.uniform(120, 470), 0, -6.0,
                                    random.uniform(0, 6.28), (255, 240, 200), "mote", 1e9])
        else:
            self.scene_t += dt
        # принцесса выходит из клетки
        tx = step.get("px", self.cut_px)
        want_open = 1.0 if step.get("px", 930) < 900 else 0.0
        self.door += clamp(want_open - self.door, -dt * 2, dt * 2)
        d = tx - self.cut_px
        self.princess_walk = abs(d) > 2 and self.door > 0.6
        if self.princess_walk:
            self.cut_px += math.copysign(min(abs(d), 130 * dt), d)
        self.kiss += clamp((1.0 if step.get("kiss") else 0.0) - self.kiss, -dt * 0.6, dt * 0.6)
        self.update_fx(dt, step)

    def update_fx(self, dt, step):
        sc = self.scene_name
        if sc == "lair" and random.random() < dt * 22:
            self.fx.append([random.uniform(0, W), random.uniform(470, 520), random.uniform(-15, 15),
                            random.uniform(-120, -50), random.uniform(0, 6.28), (255, 150, 50), "ember", 3.0])
        elif sc == "chapel":
            if random.random() < dt * 16:
                self.fx.append([random.uniform(0, W), -10.0, random.uniform(-20, 20), random.uniform(40, 80),
                                random.uniform(0, 6.28),
                                random.choice([(255, 190, 210), (255, 255, 255), (250, 150, 180)]), "petal", 20.0])
            if (step.get("hearts") or self.kiss > 0.4) and random.random() < dt * 7:
                mx = 640 + random.uniform(-70, 70)
                self.fx.append([mx, CUT_FLOOR - 150, 0, random.uniform(-80, -45), random.uniform(0, 6.28),
                                (255, 90, 130), "heart", 2.4])
        for p in self.fx:
            p[4] += dt * 3
            p[7] -= dt
            k = p[6]
            if k == "petal":
                p[0] += (p[2] + math.sin(p[4]) * 30) * dt
                p[1] += p[3] * dt
            elif k == "mote":
                p[0] += math.sin(p[4] * 0.7) * 10 * dt
                p[1] += p[3] * dt
                if p[1] < 110:
                    p[1] = 470.0
            elif k == "ember":
                p[0] += (p[2] + math.sin(p[4]) * 20) * dt
                p[1] += p[3] * dt
            else:
                p[0] += math.sin(p[4]) * 25 * dt
                p[1] += p[3] * dt
        self.fx = [p for p in self.fx if p[7] > 0 and -30 < p[1] < H + 20]

    def draw_fx(self, s):
        for x, y, vx, vy, ph, col, kind, life in self.fx:
            if kind == "petal":
                pygame.draw.ellipse(s, col, (int(x), int(y), 9, 5))
            elif kind == "mote":
                pygame.draw.circle(s, col, (int(x), int(y)), 1 + int(abs(math.sin(ph)) * 2))
            elif kind == "ember":
                pygame.draw.circle(s, col, (int(x), int(y)), 2)
            else:
                draw_heart(s, int(x), int(y), 6 + int(abs(math.sin(ph)) * 4), col)

    def draw_scene(self, s, step):
        sc = step.get("scene", "throne")
        t, st = self.time, max(0.0, self.scene_t)
        sp = self.cut_speaker(step)
        talking = self.dialog_t >= 0 and not self.dialog_done()

        def bounce(who):
            return -abs(math.sin(t * 13)) * 5 if (talking and sp == who) else 0

        def breathe(ph):
            return 1.0 + 0.012 * math.sin(t * 2.2 + ph)

        def ease(p):
            p = clamp(p, 0.0, 1.0)
            return p * p * (3 - 2 * p)

        if sc == "throne":
            s.blit(self.get_bg("throne"), (0, 0))
            draw_torch(s, 130, 300, t)
            draw_torch(s, 1150, 300, t)
            draw_throne(s, 900, CUT_FLOOR)
            blit_fig(s, draw_king, 900, CUT_FLOOR - 34 + bounce("king"), 2.1 * breathe(0.0), t=t)
            walking = st < 1.4
            kx = lerp(-120, 380, ease(st / 1.4))
            wk = t * 11 if walking else 0.0
            ky = CUT_FLOOR - (abs(math.sin(wk)) * 5 if walking else 0) + bounce("knight")
            blit_fig(s, draw_knight_fig, kx, ky, 2.1 * breathe(1.0), f=1, t=t, helmet=True, walk=wk)
        elif sc == "lair":
            s.fill((44, 32, 40))
            s.blit(self.get_bg("volcano"), (0, -120))
            draw_dead_dragon(s, 200, CUT_FLOOR + 8, t)
            walking = st < 1.4
            kx = lerp(-120, 520, ease(st / 1.4))
            wk = t * 11 if walking else 0.0
            ky = CUT_FLOOR - (abs(math.sin(wk)) * 5 if walking else 0) + bounce("knight")
            blit_fig(s, draw_knight_fig, kx, ky, 2.1 * breathe(1.0), f=1, t=t, helmet=True, walk=wk)
            pw = t * 9 if self.princess_walk else 0.0
            py = CUT_FLOOR - (abs(math.sin(pw)) * 4 if self.princess_walk else 0) + bounce("princess")
            blit_fig(s, draw_princess, self.cut_px, py, 2.1 * breathe(2.0), f=-1, t=t, walk=pw)
            draw_cage(s, 930, CUT_FLOOR, self.door)
        else:
            s.blit(self.get_bg("chapel"), (0, 0))
            blit_fig(s, draw_king, 640, CUT_FLOOR - 28 + bounce("king"), 1.9 * breathe(0.5), t=t)
            draw_altar(s, 640, CUT_FLOOR - 22, t)
            guests = [(250, 484, (90, 120, 190)), (330, 540, (170, 90, 90)), (150, 484, (110, 160, 110)),
                      (1010, 484, (150, 110, 170)), (1090, 484, (200, 160, 80)), (940, 540, (90, 150, 170))]
            for gx, gy, col in guests:
                draw_guest(s, gx, gy + int(math.sin(t * 2.5 + gx) * 2), col, t)
            draw_guest(s, 400, 500 + bounce("merchant"), (60, 80, 150), t, k=1.5, merchant=True,
                       wave=step.get("wave", False))
            e = ease(st / 2.0)
            walking = st < 2.0
            kk = self.kiss
            kx = lerp(-120, 585, e) + 32 * kk
            px = lerp(1400, 700, e) - 28 * kk
            wk = t * 10 if walking else 0.0
            hop = abs(math.sin(wk)) * 5 if walking else 0
            blit_fig(s, draw_knight_fig, kx, CUT_FLOOR - hop + bounce("knight"), 2.1 * breathe(1.0), f=1, t=t,
                     helmet=False, wedding=True, walk=wk)
            blit_fig(s, draw_princess, px, CUT_FLOOR - hop + bounce("princess"), 2.1 * breathe(2.0), f=-1, t=t,
                     wedding=True, walk=wk)
        self.draw_fx(s)

    def draw_cutscene(self):
        s = self.screen
        if self.dialog:
            self.draw_scene(s, self.dialog_step())
            a = int(255 * clamp(1.0 - self.scene_t / 0.8, 0.0, 1.0))
            if a > 0:
                ov = pygame.Surface((W, H), pygame.SRCALPHA)
                ov.fill((0, 0, 0, a))
                s.blit(ov, (0, 0))
            self.draw_dialog()
        draw_text(s, self.f_tiny, "Esc — пропустить", (W - 16, 14), (225, 225, 240), "topright")

    # ---------- HUD ----------
    def draw_crosshair(self):
        s = self.screen
        mx, my = pygame.mouse.get_pos()
        p = self.world.player
        if p.weapon == "bow":
            rad = int(24 - 14 * p.power())
            col = (255, 90, 70) if p.power() >= 1 else (255, 255, 255)
        else:
            rad, col = 14, (255, 255, 255)
        pygame.draw.circle(s, (0, 0, 0), (mx, my), rad + 1, 3)
        pygame.draw.circle(s, col, (mx, my), rad, 2)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pygame.draw.line(s, col, (mx + dx * (rad - 4), my + dy * (rad - 4)),
                             (mx + dx * (rad + 7), my + dy * (rad + 7)), 2)
        pygame.draw.circle(s, col, (mx, my), 2)

    def draw_hud(self):
        s = self.screen
        w = self.world
        p = w.player
        lv = w.level
        bar = pygame.Rect(16, 16, 260, 26)
        panel(s, bar.inflate(8, 8), (10, 10, 24, 190), 8)
        pygame.draw.rect(s, (60, 14, 14), bar, border_radius=5)
        pygame.draw.rect(s, (214, 54, 54), (bar.x, bar.y, int(bar.w * p.hp / p.max_hp), bar.h), border_radius=5)
        draw_text(s, self.f_small, "Здоровье: %d" % p.hp, bar.center, (255, 255, 255), "center")
        # монеты
        gr = pygame.Rect(12, 52, 150, 30)
        panel(s, gr, (10, 10, 24, 190), 8)
        pygame.draw.circle(s, (240, 200, 60), (gr.x + 18, gr.centery), 9)
        pygame.draw.circle(s, (200, 150, 30), (gr.x + 18, gr.centery), 9, 2)
        draw_text(s, self.f_small, "%d" % self.inv["gold"], (gr.x + 36, gr.centery), (255, 230, 120), "midleft")

        # подсказки по управлению
        if w.stage == 0 or w.time < 9:
            b = {a: bind_name(self.settings.binds[a], True) for a, _ in ACTIONS}
            lines = ["Ходьба: %s / %s    Прыжок: %s" % (b["left"], b["right"], b["jump"]),
                     "Атака: %s    Меч: %s    Лук: %s" % (b["attack"], b["sword"], b["bow"]),
                     "Зелья: %s — лечение, %s — усиление" % (b["heal"], b["buff"]),
                     "С луком удерживайте атаку — тетива натягивается,",
                     "отпустите — выстрел. Пауза: Esc"]
            r = pygame.Rect(16, 92, 400, 24 * len(lines) + 12)
            panel(s, r, (10, 10, 24, 150), 8)
            for i, ln in enumerate(lines):
                draw_text(s, self.f_tiny, ln, (r.x + 10, r.y + 8 + i * 24), (235, 235, 245), shadow=False)

        # усиление
        if p.buff_t > 0:
            br = pygame.Rect(16, H - 168, 230, 28)
            panel(s, br, (40, 30, 6, 220), 8, (255, 210, 80))
            pygame.draw.rect(s, (255, 200, 60), (br.x + 4, br.bottom - 8, int((br.w - 8) * p.buff_t / BUFF_TIME), 4))
            draw_text(s, self.f_tiny, "Усиление: %d с" % int(p.buff_t + 0.99), (br.x + 10, br.y + 8), (255, 235, 160), shadow=False)

        # инвентарь
        slots = [("sword", "Стальной меч", "sword"), ("bow", "Лук", "bow"), (None, "Стрелы", None),
                 ("heal", "Лечение", "heal"), ("buff", "Усиление", "buff")]
        for i, (wid, name, act) in enumerate(slots):
            r = pygame.Rect(16 + i * 98, H - 128, 84, 84)
            sel = wid in ("sword", "bow") and p.weapon == wid
            panel(s, r, (30, 26, 12, 230) if sel else (10, 10, 24, 190), 10,
                  (245, 215, 110) if sel else (90, 96, 130))
            if wid == "sword":
                pygame.draw.line(s, (230, 235, 245), (r.x + 22, r.bottom - 22), (r.right - 20, r.y + 20), 6)
                pygame.draw.line(s, (220, 180, 60), (r.x + 26, r.bottom - 36), (r.x + 40, r.bottom - 22), 5)
            elif wid == "bow":
                pts = [(r.centerx - 20 + 22 * (1 - (k / 4.0) ** 2), r.centery + k * 8) for k in range(-4, 5)]
                pygame.draw.lines(s, (150, 100, 55), False, pts, 5)
                pygame.draw.line(s, (235, 235, 225), pts[0], pts[-1], 1)
                pygame.draw.line(s, (205, 175, 115), (r.x + 20, r.centery), (r.right - 16, r.centery), 2)
            elif wid in ("heal", "buff"):
                have = self.inv[wid]
                col = (214, 54, 64) if wid == "heal" else (70, 120, 240)
                if have == 0:
                    col = (90, 90, 100)
                draw_potion(s, r.centerx, r.centery + 6, col, 1.1)
                draw_text(s, self.f, "×%d" % have, (r.right - 6, r.bottom - 4), (255, 255, 255), "bottomright")
            else:
                for k in range(4):
                    ox = r.x + 20 + k * 10
                    pygame.draw.line(s, (205, 175, 115), (ox, r.bottom - 18), (ox + 14, r.y + 20), 3)
                    pygame.draw.polygon(s, (190, 195, 205), [(ox + 16, r.y + 14), (ox + 10, r.y + 24), (ox + 20, r.y + 24)])
                draw_text(s, self.f, "×%d" % p.arrows, (r.right - 6, r.bottom - 4), (255, 255, 255), "bottomright")
            if act:
                draw_text(s, self.f_tiny, bind_name(self.settings.binds[act], True), (r.x + 6, r.y + 4),
                          (245, 215, 110), shadow=True)
            draw_text(s, self.f_tiny, name, (r.centerx, r.bottom + 4), (235, 235, 245), "midtop")

        # цели уровня / полоса здоровья босса
        if lv.kind == "training":
            r = pygame.Rect(W - 290, 16, 274, 108)
            panel(s, r, (10, 10, 24, 170), 8)
            draw_text(s, self.f_small, "Задание: тренировка", (r.x + 12, r.y + 8), (245, 215, 110))
            draw_text(s, self.f_small, "Мишени (лук): %d/%d" % (lv.hits(), len(lv.targets)), (r.x + 12, r.y + 38))
            draw_text(s, self.f_small, "Манекены (меч): %d/%d" % (lv.kills(), len(lv.dummies)), (r.x + 12, r.y + 64))
            if lv.open:
                draw_text(s, self.f_tiny, "Портал открыт — идите вправо!", (r.x + 12, r.y + 90), (150, 200, 255))
        else:
            d = lv.boss
            br = pygame.Rect(W // 2 - 300, 48, 600, 20)
            draw_text(s, self.f_small, d.name, (W // 2, 14), (255, 190, 120), "midtop")
            pygame.draw.rect(s, (30, 8, 8), br.inflate(6, 6), border_radius=8)
            pygame.draw.rect(s, (70, 14, 14), br, border_radius=6)
            pygame.draw.rect(s, (220, 60, 40), (br.x, br.y, int(br.w * d.hp / d.max_hp), br.h), border_radius=6)
            draw_text(s, self.f_tiny, "Сложность: %d/5   •   Награда: %d монет" % (d.difficulty, d.reward),
                      (W // 2, 74), (225, 225, 235), "midtop")
            hint = d.hint()
            if hint:
                draw_text(s, self.f_small, hint, (W // 2, 96), (255, 235, 150), "midtop")

        # баннер уровня
        if w.banner_t > 0:
            a = int(255 * clamp(min(w.banner_t, 1.0), 0, 1))
            img = self.f_big.render(lv.title, True, (255, 240, 200))
            img.set_alpha(a)
            s.blit(img, img.get_rect(center=(W // 2, 150 if w.stage else 120)))

    # ---------- главный цикл ----------
    def run(self):
        while True:
            dt = min(self.clock.tick(self.settings.fps_limit) / 1000.0, 1 / 30.0)
            for e in pygame.event.get():
                self.handle_event(e)
            self.input.update()
            self.update(dt)
            self.draw()
            pygame.display.flip()


if __name__ == "__main__":
    Game().run()