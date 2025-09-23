# slingshot_first_touch_marker.py
# Non-pymunk physics (analytic + simple bounce). Places landing marker at FIRST ground touch.
# Requires: pygame
# pip install pygame

import math
import time
import pygame
import sys

# ----------------- Config -----------------
WIDTH, HEIGHT = 1200, 650
BG = (30, 30, 30)
GROUND_HEIGHT_PX = 70
ANCHOR = (150, HEIGHT - GROUND_HEIGHT_PX - 20)

PIXELS_PER_METER = 50.0
GRAVITY = 9.81

SPRING_K = 120.0
PROJECTILE_MASS = 0.5
USE_PHYSICAL_LAUNCH = True

RESTITUTION = 0.6
BOUNCE_FRICTION = 0.9
REST_SPEED_THRESHOLD = 0.6

ENABLE_AIR_DRAG = False
DRAG_COEFF = 0.1

MARKER_RADIUS_PX = 9

DEFAULT_BALL_COLOR = (200, 80, 80)
BALL_GRADIENT = False

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont("DejaVuSans", 16)
small_font = pygame.font.SysFont("DejaVuSans", 13)
big_font = pygame.font.SysFont("DejaVuSans", 18, bold=True)

# ----------------- State -----------------
projectile = None   # dict with x,y (meters), vx,vy (m/s), alive, shot_id, start_time, first_touch_recorded
prev_state = None
landings = []       # list of markers: each = dict with x, speed, range, screen, shot_id, impact_speed, flight_time, max_height, bounces
dragging = False
mouse_pos = (0, 0)

HELP_BTN_RECT = pygame.Rect(WIDTH - 120, 12, 110, 34)
COLOR_BTN_RECT = pygame.Rect(WIDTH - 120, 56, 110, 34)

help_visible = False
color_modal_visible = False
gravity_custom_modal = False
gravity_input_text = ""

SHOT_COUNTER = 0

ball_color = DEFAULT_BALL_COLOR
ball_gradient = BALL_GRADIENT

# gravity presets UI
GRAV_PRESETS = [
    ("Earth", 9.81),
    ("Moon", 1.62),
    ("Mars", 3.71),
    ("Jupiter", 24.79),
    ("Custom", None)
]
preset_rects = []
px = 12
for name, val in GRAV_PRESETS:
    r = pygame.Rect(px, 12, 86, 30)
    preset_rects.append((name, val, r))
    px += 92
REST_BOX = pygame.Rect((px + 20, 12, 220, 30))

COLOR_PRESETS = [
    (200, 80, 80),
    (80, 200, 120),
    (80, 160, 220),
    (220, 180, 60),
    (200, 100, 200),
    (230, 230, 230),
    (30, 144, 255)
]

# ----------------- Utilities -----------------
def world_to_screen(wx, wy):
    sx = int(wx * PIXELS_PER_METER)
    sy = int(HEIGHT - GROUND_HEIGHT_PX - (wy * PIXELS_PER_METER))
    return sx, sy

def screen_to_world(sx, sy):
    wx = sx / PIXELS_PER_METER
    wy = (HEIGHT - GROUND_HEIGHT_PX - sy) / PIXELS_PER_METER
    return wx, wy

def draw_text(surface, text, x, y, f=font, color=(230,230,230)):
    surface.blit(f.render(text, True, color), (x, y))

def predict_trajectory(x0, y0, vx0, vy0, steps=400, dt=0.02):
    pts = []
    for i in range(steps):
        t = i * dt
        xt = x0 + vx0 * t
        yt = y0 + vy0 * t - 0.5 * GRAVITY * t * t
        if yt < 0:
            break
        pts.append((xt, yt))
    return pts

def record_landing_exact(prev, curr, anchor_x_m):
    """
    Linear time interpolation between prev and curr to find where y==0.
    prev and curr are dicts with x,y,vx,vy in meters / m/s.
    """
    y1 = prev['y']; y2 = curr['y']
    if y1 == y2:
        frac = 0.0
    else:
        frac = (0.0 - y1) / (y2 - y1)
    frac = max(0.0, min(1.0, frac))
    x_landing = prev['x'] + (curr['x'] - prev['x']) * frac
    vx_landing = prev['vx'] + (curr['vx'] - prev['vx']) * frac
    vy_landing = prev['vy'] + (curr['vy'] - prev['vy']) * frac
    speed = math.hypot(vx_landing, vy_landing)
    range_from_anchor = x_landing - anchor_x_m
    sx, sy = world_to_screen(x_landing, 0.0)
    return {'x': x_landing, 'speed': speed, 'range': range_from_anchor, 'screen': (sx, sy)}

def is_mouse_near_marker(mx, my, marker_screen, radius=MARKER_RADIUS_PX + 8):
    sx, sy = marker_screen
    return (mx - sx)**2 + (my - sy)**2 <= radius**2

def draw_radial_gradient_circle(surface, center, radius, color):
    cx, cy = center
    r = int(radius)
    r_steps = max(6, r//2)
    for i in range(r_steps, 0, -1):
        frac = i / r_steps
        c = (
            int(color[0] * frac + 40 * (1-frac)),
            int(color[1] * frac + 40 * (1-frac)),
            int(color[2] * frac + 40 * (1-frac))
        )
        pygame.draw.circle(surface, c, (cx, cy), int(radius * frac))

# ----------------- Main loop -----------------
running = True
while running:
    dt = clock.tick(60) / 1000.0
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                if help_visible:
                    help_visible = False
                elif color_modal_visible:
                    color_modal_visible = False
                elif gravity_custom_modal:
                    gravity_custom_modal = False
                    gravity_input_text = ""
            elif event.key == pygame.K_c:
                landings.clear()
            elif event.key == pygame.K_LEFTBRACKET or event.unicode == "[":
                RESTITUTION = max(0.0, RESTITUTION - 0.05)
            elif event.key == pygame.K_RIGHTBRACKET or event.unicode == "]":
                RESTITUTION = min(1.0, RESTITUTION + 0.05)
            elif gravity_custom_modal:
                if event.key == pygame.K_BACKSPACE:
                    gravity_input_text = gravity_input_text[:-1]
                elif event.key == pygame.K_RETURN or event.key == pygame.K_KP_ENTER:
                    try:
                        val = float(gravity_input_text.strip())
                        if val > 0:
                            GRAVITY = val
                    except:
                        pass
                    gravity_custom_modal = False
                    gravity_input_text = ""
                else:
                    if event.unicode and (event.unicode.isdigit() or event.unicode in ".-"):
                        gravity_input_text += event.unicode

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos

            if HELP_BTN_RECT.collidepoint(mx, my):
                help_visible = not help_visible
                continue

            if COLOR_BTN_RECT.collidepoint(mx, my):
                color_modal_visible = not color_modal_visible
                continue

            if color_modal_visible:
                cp_x = (WIDTH - 420) // 2 + 18
                cp_y = (HEIGHT - 240) // 2 + 50
                clicked = False
                for i, c in enumerate(COLOR_PRESETS):
                    rect = pygame.Rect(cp_x + (i%6)*(36+12), cp_y + (i//6)*(36+12), 36, 36)
                    if rect.collidepoint(mx, my):
                        ball_color = c
                        clicked = True
                        color_modal_visible = False
                        break
                grect = pygame.Rect((WIDTH - 420) // 2 + 18, cp_y + 90, 120, 28)
                if grect.collidepoint(mx, my):
                    ball_gradient = not ball_gradient
                    clicked = True
                    color_modal_visible = False
                if clicked:
                    continue
                modal_rect = pygame.Rect((WIDTH - 420)//2, (HEIGHT - 240)//2, 420, 240)
                if not modal_rect.collidepoint(mx, my):
                    color_modal_visible = False
                    continue

            if not gravity_custom_modal and not color_modal_visible and not help_visible:
                for name, val, rect in preset_rects:
                    if rect.collidepoint(mx, my):
                        if name == "Custom":
                            gravity_custom_modal = True
                            gravity_input_text = ""
                        else:
                            GRAVITY = val
                        break

            if event.button == 1 and not (help_visible or color_modal_visible or gravity_custom_modal):
                ax, ay = ANCHOR
                if (mx - ax)**2 + (my - ay)**2 < 14000:
                    dragging = True
                    mouse_pos = event.pos

            elif event.button == 3 and not (help_visible or color_modal_visible or gravity_custom_modal):
                if my < HEIGHT - GROUND_HEIGHT_PX - 6:
                    ANCHOR = (mx, my)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and dragging and not (help_visible or color_modal_visible or gravity_custom_modal):
                SHOT_COUNTER += 1
                shot_id = SHOT_COUNTER

                dragging = False
                ax, ay = ANCHOR
                mx, my = mouse_pos
                pull_sx = ax - mx
                pull_sy = ay - my
                pull_wx = pull_sx / PIXELS_PER_METER
                pull_wy = -pull_sy / PIXELS_PER_METER
                displacement_m = math.hypot(pull_wx, pull_wy)
                if USE_PHYSICAL_LAUNCH and displacement_m > 1e-9:
                    v0 = displacement_m * math.sqrt(max(1e-12, SPRING_K / PROJECTILE_MASS))
                else:
                    v0 = displacement_m * 4.0
                if displacement_m > 1e-9:
                    ux = pull_wx / displacement_m
                    uy = pull_wy / displacement_m
                else:
                    ux, uy = 0.0, 0.0
                vx0 = ux * v0
                vy0 = uy * v0
                x0, y0 = screen_to_world(ax, ay)
                # start_time for flight time, first_touch_recorded flag
                projectile = {
                    "x": x0,
                    "y": y0,
                    "vx": vx0,
                    "vy": vy0,
                    "alive": True,
                    "shot_id": shot_id,
                    "start_time": time.time(),
                    "first_touch_recorded": False,
                    "max_height": y0,
                    "bounces": 0,
                }
                prev_state = None

        elif event.type == pygame.MOUSEMOTION:
            mouse_pos = event.pos
            if dragging:
                mouse_pos = event.pos

    # ----------------- Physics update -----------------
    if projectile and projectile["alive"]:
        prev_state = {'x': projectile['x'], 'y': projectile['y'], 'vx': projectile['vx'], 'vy': projectile['vy'], 'shot_id': projectile.get('shot_id')}
        vx = projectile["vx"]
        vy = projectile["vy"]

        if ENABLE_AIR_DRAG:
            axd = -DRAG_COEFF * vx
            ayd = -DRAG_COEFF * vy
        else:
            axd = 0.0
            ayd = 0.0
        ax_tot = axd
        ay_tot = -GRAVITY + ayd

        projectile["vx"] += ax_tot * dt
        projectile["vy"] += ay_tot * dt
        projectile["x"] += projectile["vx"] * dt
        projectile["y"] += projectile["vy"] * dt

        # update max height
        if projectile["y"] > projectile.get("max_height", -1e9):
            projectile["max_height"] = projectile["y"]

        # detect ground touch (y <= 0)
        if projectile["y"] <= 0.0:
            # compute exact impact values by interpolation between prev and curr
            if prev_state is not None:
                landing = record_landing_exact(prev_state, projectile, screen_to_world(*ANCHOR)[0])
            else:
                landing = {'x': projectile['x'], 'speed': math.hypot(projectile['vx'], projectile['vy']), 'range': projectile['x'] - screen_to_world(*ANCHOR)[0], 'screen': world_to_screen(projectile['x'], 0.0)}

            # If this is the FIRST touch for this shot, record a FIRST-TOUCH landing marker
            if not projectile.get("first_touch_recorded", False):
                impact_speed = landing['speed']
                flight_time = time.time() - projectile.get("start_time", time.time())
                sx, sy = landing['screen']
                first_ld = {
                    'x': landing['x'],
                    'speed': landing['speed'],
                    'impact_speed': impact_speed,
                    'flight_time': flight_time,
                    'range': landing['range'],
                    'screen': (sx, sy),
                    'shot_id': projectile.get('shot_id'),
                    'max_height': projectile.get('max_height', 0.0),
                    'bounces': projectile.get('bounces', 0)
                }
                landings.append(first_ld)
                projectile["first_touch_recorded"] = True
                # note: we DO NOT stop or prevent subsequent bounces; marker remains the first-touch record

            # Now do bounce response as before (so ball still bounces)
            # set position at ground (y=0)
            projectile['y'] = 0.0
            # reflect vertical velocity and apply restitution
            projectile['vy'] = -projectile['vy'] * RESTITUTION
            # apply horizontal damping to simulate friction on bounce
            projectile['vx'] = projectile['vx'] * BOUNCE_FRICTION
            # increment bounces counter
            projectile['bounces'] = projectile.get('bounces', 0) + 1

            # if resultant speed is small, end shot (final rest)
            speed_now = math.hypot(projectile['vx'], projectile['vy'])
            if speed_now < REST_SPEED_THRESHOLD:
                # mark as finished (do not overwrite first-touch landing)
                projectile['alive'] = False
                prev_state = None

    # ----------------- Draw -----------------
    screen.fill(BG)
    ground_y = HEIGHT - GROUND_HEIGHT_PX
    pygame.draw.rect(screen, (50,50,50), (0, ground_y, WIDTH, GROUND_HEIGHT_PX))
    pygame.draw.line(screen, (160,160,160), (0, ground_y), (WIDTH, ground_y), 2)

    # gravity presets
    for name, val, rect in preset_rects:
        pygame.draw.rect(screen, (80,80,80), rect, border_radius=6)
        label = small_font.render(name, True, (220,220,220))
        screen.blit(label, (rect.x + 8, rect.y + 6))
        if val is not None and abs(GRAVITY - val) < 1e-4:
            pygame.draw.rect(screen, (120,180,120), rect, 3, border_radius=6)
        elif name == "Custom" and (not any(abs(GRAVITY - v) < 1e-4 for (_, v, _) in preset_rects if v is not None)):
            pygame.draw.rect(screen, (120,180,120), rect, 3, border_radius=6)

    pygame.draw.rect(screen, (70,70,70), REST_BOX, border_radius=6)
    draw_text(screen, f"Restitution: {RESTITUTION:.2f}   ([ / ]) to change", REST_BOX.x + 8, REST_BOX.y + 7, f=small_font)

    # anchor/height
    ax, ay = ANCHOR
    pygame.draw.circle(screen, (200,160,60), ANCHOR, 9)
    anchor_world_x, anchor_world_y = screen_to_world(ax, ay)
    pygame.draw.line(screen, (140,140,220), (ax, ay), (ax, ground_y), 2)
    pygame.draw.polygon(screen, (140,140,220), [(ax-6, ground_y+6), (ax+6, ground_y+6), (ax, ground_y-2)])
    draw_text(screen, "Anchor height:", ax + 12, ay - 10, f=small_font)
    draw_text(screen, f"{anchor_world_y:.2f} m", ax + 12, ay + 6, f=big_font)

    # dragging preview & live info
    if dragging:
        mx, my = mouse_pos
        pygame.draw.line(screen, (180,180,180), ANCHOR, (mx, my), 2)
        pull_sx = ax - mx
        pull_sy = ay - my
        pull_wx = pull_sx / PIXELS_PER_METER
        pull_wy = -pull_sy / PIXELS_PER_METER
        displacement_m = math.hypot(pull_wx, pull_wy)
        force_n = SPRING_K * displacement_m
        if USE_PHYSICAL_LAUNCH and displacement_m > 1e-9:
            v0_disp = displacement_m * math.sqrt(max(1e-12, SPRING_K / PROJECTILE_MASS))
        else:
            v0_disp = displacement_m * 4.0
        ux = (pull_wx / displacement_m) if displacement_m > 1e-9 else 0.0
        uy = (pull_wy / displacement_m) if displacement_m > 1e-9 else 0.0
        vx0 = ux * v0_disp
        vy0 = uy * v0_disp

        traj = predict_trajectory(screen_to_world(ax, ay)[0], screen_to_world(ax, ay)[1], vx0, vy0, steps=400, dt=0.02)
        for p in traj:
            sx, sy = world_to_screen(p[0], p[1])
            if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                pygame.draw.circle(screen, (100,200,200), (sx, sy), 3)
        speed = math.hypot(vx0, vy0)
        angle = math.degrees(math.atan2(vy0, vx0)) if speed > 1e-9 else 0.0
        info_lines = [
            f"Displacement: {displacement_m:.2f} m",
            f"Estimated force: {force_n:.1f} N",
            f"Initial speed: {speed:.2f} m/s",
            f"Angle: {angle:.1f} deg",
            f"Gravity: {GRAVITY:.2f} m/s²"
        ]
        for i, line in enumerate(info_lines):
            draw_text(screen, line, 10, 8 + i*18)

    # draw projectile
    if projectile:
        sx, sy = world_to_screen(projectile["x"], projectile["y"])
        if projectile["alive"]:
            if ball_gradient:
                draw_radial_gradient_circle(screen, (sx, sy), 11, ball_color)
            else:
                pygame.draw.circle(screen, ball_color, (sx, sy), 11)
            speed = math.hypot(projectile["vx"], projectile["vy"])
            draw_text(screen, f"Sim speed: {speed:.2f} m/s", 10, 120)
            draw_text(screen, f"Shot id: {projectile.get('shot_id')}", 10, 140)
        else:
            pygame.draw.circle(screen, ball_color, (sx, sy), 6)

    # draw landing markers and tooltips
    mx, my = mouse_pos
    hover_shown = False
    for i, ld in enumerate(landings):
        sx, sy = ld['screen']
        pygame.draw.circle(screen, (80,200,120), (sx, sy), MARKER_RADIUS_PX)
        pygame.draw.line(screen, (120,220,150), (sx, sy), (sx, sy-34), 2)
        # compact label
        label = f"{ld['range']:.2f} m  [{ld['shot_id']}]"
        txt = small_font.render(label, True, (200,200,200))
        tx = sx + 10
        ty = sy - 26 - (i % 3) * 16
        if tx + txt.get_width() > WIDTH - 8:
            tx = sx - 12 - txt.get_width()
        screen.blit(txt, (tx, ty))

        if is_mouse_near_marker(mx, my, (sx, sy)):
            hover_shown = True
            txt1 = f"Range: {ld['range']:.2f} m"
            txt2 = f"Impact speed: {ld.get('impact_speed', ld['speed']):.2f} m/s"
            txt3 = f"Flight time: {ld.get('flight_time', 0.0):.2f} s"
            txt4 = f"Max height: {ld.get('max_height', 0.0):.2f} m"
            txt5 = f"Bounces (at touch): {ld.get('bounces', 0)}"
            padding = 6
            s1 = small_font.render(txt1, True, (0,0,0))
            s2 = small_font.render(txt2, True, (0,0,0))
            s3 = small_font.render(txt3, True, (0,0,0))
            s4 = small_font.render(txt4, True, (0,0,0))
            s5 = small_font.render(txt5, True, (0,0,0))
            box_w = max(s1.get_width(), s2.get_width(), s3.get_width(), s4.get_width(), s5.get_width()) + padding*2
            box_h = s1.get_height() + s2.get_height() + s3.get_height() + s4.get_height() + s5.get_height() + padding*2 + 6
            box_x = sx + 12
            box_y = sy - box_h - 8
            if box_x + box_w > WIDTH - 6:
                box_x = sx - 12 - box_w
            if box_y < 6:
                box_y = sy + 12
            pygame.draw.rect(screen, (230,230,230), (box_x, box_y, box_w, box_h), border_radius=4)
            pygame.draw.rect(screen, (40,40,40), (box_x+1, box_y+1, box_w-2, box_h-2), border_radius=4)
            draw_text(screen, txt1, box_x + padding, box_y + padding, f=small_font, color=(220,220,220))
            draw_text(screen, txt2, box_x + padding, box_y + padding + s1.get_height(), f=small_font, color=(220,220,220))
            draw_text(screen, txt3, box_x + padding, box_y + padding + s1.get_height() + s2.get_height(), f=small_font, color=(220,220,220))
            draw_text(screen, txt4, box_x + padding, box_y + padding + s1.get_height() + s2.get_height() + s3.get_height(), f=small_font, color=(220,220,220))
            draw_text(screen, txt5, box_x + padding, box_y + padding + s1.get_height() + s2.get_height() + s3.get_height() + s4.get_height(), f=small_font, color=(220,220,220))

    # help & color
    pygame.draw.rect(screen, (220,220,220), HELP_BTN_RECT, border_radius=6)
    pygame.draw.rect(screen, (30,30,30), (HELP_BTN_RECT.x+2, HELP_BTN_RECT.y+2, HELP_BTN_RECT.w-4, HELP_BTN_RECT.h-4), border_radius=6)
    screen.blit(font.render("Help", True, (230,230,230)), (HELP_BTN_RECT.x + 30, HELP_BTN_RECT.y + 8))

    pygame.draw.rect(screen, (220,220,220), COLOR_BTN_RECT, border_radius=6)
    pygame.draw.rect(screen, (30,30,30), (COLOR_BTN_RECT.x+2, COLOR_BTN_RECT.y+2, COLOR_BTN_RECT.w-4, COLOR_BTN_RECT.h-4), border_radius=6)
    screen.blit(font.render("Color", True, (230,230,230)), (COLOR_BTN_RECT.x + 30, COLOR_BTN_RECT.y + 8))

    draw_text(screen, f"Gravity: {GRAVITY:.2f} m/s²", REST_BOX.x + REST_BOX.w + 16, REST_BOX.y + 7, f=small_font)
    draw_text(screen, f"Restitution: {RESTITUTION:.2f}", REST_BOX.x + 8, REST_BOX.y + 7, f=small_font)
    draw_text(screen, "Right-click to move anchor. Press C to clear landings.", 10, HEIGHT - 40, f=small_font)

    if help_visible:
        # small help overlay
        W, H = 520, 300
        x = (WIDTH - W) // 2
        y = (HEIGHT - H) // 2
        pygame.draw.rect(screen, (230,230,230), (x-4, y-4, W+8, H+8), border_radius=8)
        pygame.draw.rect(screen, (40,40,40), (x, y, W, H), border_radius=6)
        lines = [
            "Controls",
            "",
            "- Right-click above ground: move anchor (launch point).",
            "- Left-click near anchor, drag, release: launch projectile.",
            "- Hover a landing marker to see details recorded at first touch.",
            "- Gravity presets on top-left; click Custom then type a number for custom gravity.",
            "- Press C to clear markers.",
        ]
        oy = y + 56
        for line in lines:
            screen.blit(small_font.render(line, True, (200,200,200)), (x + 18, oy))
            oy += 20

    if color_modal_visible:
        W, H = 420, 240
        x = (WIDTH - W) // 2
        y = (HEIGHT - H) // 2
        pygame.draw.rect(screen, (230,230,230), (x-4, y-4, W+8, H+8), border_radius=8)
        pygame.draw.rect(screen, (40,40,40), (x, y, W, H), border_radius=6)
        title = big_font.render("Ball Color & Style", True, (230,230,230))
        screen.blit(title, (x + 16, y + 12))
        gap = 12
        ox = x + 18
        oy = y + 50
        for i, c in enumerate(COLOR_PRESETS):
            rect = pygame.Rect(ox + (i%6)*(36+gap), oy + (i//6)*(36+gap), 36, 36)
            pygame.draw.rect(screen, c, rect, border_radius=6)
            pygame.draw.rect(screen, (200,200,200), rect, 2, border_radius=6)
            if rect.collidepoint(mouse_pos) and pygame.mouse.get_pressed()[0]:
                ball_color = c
                color_modal_visible = False

    pygame.display.flip()

pygame.quit()
sys.exit()
