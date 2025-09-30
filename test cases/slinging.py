# slingshot_fixed_ui.py
# pip install pygame
# Run: python slingshot_fixed_ui.py

import math
import time
import pygame
import sys

# ---------------- Config ----------------
WIDTH, HEIGHT = 1500, 1000
BG = (30, 30, 30)
GROUND_H_PX = 70
ANCHOR = (150, HEIGHT - GROUND_H_PX - 20)

PIXELS_PER_M = 50.0
GRAVITY = 9.81

SPRING_K = 120.0
PROJECTILE_MASS = 0.5
USE_PHYSICAL_LAUNCH = True

RESTITUTION = 0.6
BOUNCE_FRICTION = 0.9
REST_SPEED_THRESHOLD = 0.6

ENABLE_AIR_DRAG = False
DRAG_COEFF = 0.1

MARKER_R = 9
BALL_RADIUS_M = 0.11

# ---------------- Pygame init ----------------
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Slingshot — fixed UI & first-touch markers")
clock = pygame.time.Clock()
font = pygame.font.SysFont("DejaVuSans", 16)
small = pygame.font.SysFont("DejaVuSans", 14)
big = pygame.font.SysFont("DejaVuSans", 18, bold=True)

# ---------------- State ----------------
projectile = None  # dict: x,y (m), vx,vy (m/s), alive, shot_id, ...
prev_state = None
landings = []
SHOT_COUNTER = 0

dragging = False
mouse_pos = (0, 0)
last_pull = None  # (wx, wy) in meters of last pull displacement (from anchor to mouse) — used for prediction when idle

help_visible = False
color_modal_visible = False
gravity_custom_modal = False
gravity_input_text = ""

ball_color = (200, 80, 80)
ball_gradient = False

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
    preset_rects.append((name, val, pygame.Rect(px, 12, 86, 30)))
    px += 92
REST_BOX = pygame.Rect(px + 20, 12, 240, 30)

HELP_RECT = pygame.Rect(WIDTH - 120, 12, 100, 34)
COLOR_RECT = pygame.Rect(WIDTH - 120, 56, 100, 34)

COLOR_PRESETS = [
    (200, 80, 80),
    (80, 200, 120),
    (80, 160, 220),
    (220, 180, 60),
    (200, 100, 200),
    (230, 230, 230),
    (30, 144, 255)
]

# ---------------- Utilities ----------------
def world_to_screen(wx, wy):
    sx = int(wx * PIXELS_PER_M)
    sy = int(HEIGHT - GROUND_H_PX - wy * PIXELS_PER_M)
    return sx, sy

def screen_to_world(sx, sy):
    wx = sx / PIXELS_PER_M
    wy = (HEIGHT - GROUND_H_PX - sy) / PIXELS_PER_M
    return wx, wy

def draw_text(x, y, s, f=font, color=(230,230,230)):
    screen.blit(f.render(s, True, color), (x, y))

def predict_trajectory(x0, y0, vx0, vy0, steps=1000, dt=0.01):
    pts = []
    for i in range(steps):
        t = i * dt
        xt = x0 + vx0 * t
        yt = y0 + vy0 * t - 0.5 * GRAVITY * t * t
        pts.append((xt, yt))
        if yt < -5.0:  # give a little extra to let bounce sim start below ground
            break
    return pts

def simulate_bounces_from_launch(x0, y0, vx0, vy0, restitution, friction, rest_speed, max_steps=20000, dt=0.01):
    """
    Simulate simple vertical bounces (no air drag here) using small time steps.
    Return predicted final landing x (meters) and bounce_count.
    Stop when speed < rest_speed or steps exhausted.
    """
    x = x0
    y = y0
    vx = vx0
    vy = vy0
    bounces = 0
    steps = 0
    max_iter = max_steps
    while steps < max_iter:
        steps += 1
        # integrate
        vy = vy - GRAVITY * dt
        x += vx * dt
        y += vy * dt
        # ground collision
        if y <= 0.0:
            # linear approximate: step back and find better contact? keep simple
            y = 0.0
            # count bounce only if vertical speed was downward before reflection
            # reflect
            if abs(vy) > 1e-6:
                bounces += 1
            vy = -vy * restitution
            vx = vx * friction
            # if speed small break
            speed = math.hypot(vx, vy)
            if speed < rest_speed:
                break
        # small safety: if x goes too far return
        if abs(x - x0) > 1e5:
            break
    return x, bounces

# Add this helper function near your other Utilities
def draw_grid(spacing_m=1.0):
    """Draws a simple grid in world units (meters)."""
    spacing_px = int(spacing_m * PIXELS_PER_M)
    color = (60, 60, 60)
    # vertical lines
    for x in range(0, WIDTH, spacing_px):
        pygame.draw.line(screen, color, (x, 0), (x, HEIGHT - GROUND_H_PX))
    # horizontal lines (skip ground area)
    for y in range(0, HEIGHT - GROUND_H_PX, spacing_px):
        pygame.draw.line(screen, color, (0, y), (WIDTH, y))


def record_landing_exact(prev, curr, anchor_x_m):
    # linear time interpolation between prev and curr where y==0
    y1 = prev['y']; y2 = curr['y']
    if (y2 - y1) != 0:
        frac = (0.0 - y1) / (y2 - y1)
    else:
        frac = 0.0
    frac = max(0.0, min(1.0, frac))
    x_l = prev['x'] + (curr['x'] - prev['x']) * frac
    vx_l = prev['vx'] + (curr['vx'] - prev['vx']) * frac
    vy_l = prev['vy'] + (curr['vy'] - prev['vy']) * frac
    speed = math.hypot(vx_l, vy_l)
    rng = x_l - anchor_x_m
    sx, sy = world_to_screen(x_l, 0.0)
    return {'x': x_l, 'speed': speed, 'range': rng, 'screen': (sx, sy)}

def is_mouse_near(ptx, pty, sx, sy, r=MARKER_R+8):
    return (ptx - sx)**2 + (pty - sy)**2 <= r*r

def draw_grid(surface, meters_between_lines=1, label_every=5, 
              line_color=(80,80,80), label_color=(180,180,180), alpha=60):
    """Draw faint grid lines in world meters with optional labels."""
    grid_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    col = (*line_color, alpha)

    # World bounds
    world_x_left = 0.0
    world_x_right = WIDTH / PIXELS_PER_M
    world_y_bottom = - (GROUND_H_PX / PIXELS_PER_M)
    world_y_top = (HEIGHT - GROUND_H_PX) / PIXELS_PER_M

    # Vertical lines
    x = math.floor(world_x_left / meters_between_lines) * meters_between_lines
    while x <= world_x_right:
        sx, _ = world_to_screen(x, 0)
        pygame.draw.line(grid_surf, col, (sx, 0), (sx, HEIGHT - GROUND_H_PX), 1)
        if abs(x % label_every) < 1e-6:
            lbl = small.render(f"{x:.0f} m", True, label_color)
            grid_surf.blit(lbl, (sx+2, HEIGHT - GROUND_H_PX - 18))
        x += meters_between_lines

    # Horizontal lines
    y = math.floor(world_y_bottom / meters_between_lines) * meters_between_lines
    while y <= world_y_top:
        _, sy = world_to_screen(0, y)
        pygame.draw.line(grid_surf, col, (0, sy), (WIDTH, sy), 1)
        if abs(y % label_every) < 1e-6 and y > 0:
            lbl = small.render(f"{y:.0f} m", True, label_color)
            grid_surf.blit(lbl, (4, sy-14))
        y += meters_between_lines

    surface.blit(grid_surf, (0,0))


# ---------------- Main loop ----------------
running = True
while running:
    dt = clock.tick(60) / 1000.0

    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            running = False
        elif ev.type == pygame.KEYDOWN:
            if ev.key == pygame.K_ESCAPE:
                if help_visible:
                    help_visible = False
                elif color_modal_visible:
                    color_modal_visible = False
                elif gravity_custom_modal:
                    gravity_custom_modal = False
                    gravity_input_text = ""
            elif ev.key == pygame.K_c:
                landings.clear()
            elif ev.key == pygame.K_LEFTBRACKET or ev.unicode == "[":
                RESTITUTION = max(0.0, RESTITUTION - 0.05)
            elif ev.key == pygame.K_RIGHTBRACKET or ev.unicode == "]":
                RESTITUTION = min(1.0, RESTITUTION + 0.05)
            elif gravity_custom_modal:
                # typing into GUI custom gravity box
                if ev.key == pygame.K_BACKSPACE:
                    gravity_input_text = gravity_input_text[:-1]
                elif ev.key == pygame.K_RETURN or ev.key == pygame.K_KP_ENTER:
                    try:
                        v = float(gravity_input_text.strip())
                        if v > 0:
                            GRAVITY = v
                    except:
                        pass
                    gravity_custom_modal = False
                    gravity_input_text = ""
                else:
                    if ev.unicode and (ev.unicode.isdigit() or ev.unicode in ".-"):
                        gravity_input_text += ev.unicode

        elif ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = ev.pos
            # help & color buttons
            if HELP_RECT.collidepoint(mx, my):
                help_visible = not help_visible
                continue
            if COLOR_RECT.collidepoint(mx, my):
                color_modal_visible = not color_modal_visible
                continue

            # color modal interactions
            if color_modal_visible:
                W, H = 420, 240
                x = (WIDTH - W) // 2
                y = (HEIGHT - H) // 2
                ox = x + 18; oy = y + 52
                for i, c in enumerate(COLOR_PRESETS):
                    rect = pygame.Rect(ox + (i%6)*(36+12), oy + (i//6)*(36+12), 36, 36)
                    if rect.collidepoint(mx, my):
                        ball_color = c
                        color_modal_visible = False
                        break
                # gradient toggle area
                grect = pygame.Rect(x+18, oy+90, 120, 28)
                if grect.collidepoint(mx, my):
                    ball_gradient = not ball_gradient
                    color_modal_visible = False
                    continue
                # click outside -> close
                modal_rect = pygame.Rect(x, y, W, H)
                if not modal_rect.collidepoint(mx, my):
                    color_modal_visible = False
                    continue

            # gravity preset clicks
            for name, val, rect in preset_rects:
                if rect.collidepoint(mx, my):
                    if name == "Custom":
                        gravity_custom_modal = True
                        gravity_input_text = ""
                    else:
                        GRAVITY = val
                    break

            # left click start drag if near anchor
            if ev.button == 1:
                ax, ay = ANCHOR
                if (mx - ax)**2 + (my - ay)**2 < 14000:
                    dragging = True
                    mouse_pos = ev.pos

            # right click move anchor
            elif ev.button == 3:
                if my < HEIGHT - GROUND_H_PX - 6:
                    ANCHOR = (mx, my)

        elif ev.type == pygame.MOUSEBUTTONUP:
            if ev.button == 1 and dragging and (not help_visible and not color_modal_visible and not gravity_custom_modal):
                dragging = False
                SHOT_COUNTER += 1
                shot_id = SHOT_COUNTER
                ax, ay = ANCHOR
                mx, my = mouse_pos
                pull_sx = ax - mx
                pull_sy = ay - my
                pull_wx = pull_sx / PIXELS_PER_M
                pull_wy = -pull_sy / PIXELS_PER_M
                displacement_m = math.hypot(pull_wx, pull_wy)
                last_pull = (pull_wx, pull_wy)  # store last pull for idle prediction
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
                projectile = {
                    "x": x0, "y": y0, "vx": vx0, "vy": vy0,
                    "alive": True, "shot_id": shot_id,
                    "start_time": time.time(), "first_touch_recorded": False,
                    "max_height": y0, "bounces": 0
                }
                prev_state = None

        elif ev.type == pygame.MOUSEMOTION:
            mouse_pos = ev.pos
            if dragging:
                mouse_pos = ev.pos

    # ---------------- Physics update ----------------
    if projectile and projectile["alive"]:
        prev_state = {'x': projectile['x'], 'y': projectile['y'], 'vx': projectile['vx'], 'vy': projectile['vy']}
        vx = projectile['vx']; vy = projectile['vy']
        if ENABLE_AIR_DRAG:
            axd = -DRAG_COEFF * vx
            ayd = -DRAG_COEFF * vy
        else:
            axd = 0.0; ayd = 0.0
        ax_tot = axd
        ay_tot = -GRAVITY + ayd
        projectile['vx'] += ax_tot * dt
        projectile['vy'] += ay_tot * dt
        projectile['x'] += projectile['vx'] * dt
        projectile['y'] += projectile['vy'] * dt

        if projectile['y'] > projectile.get('max_height', -1e9):
            projectile['max_height'] = projectile['y']

        # detect ground touch
        if projectile['y'] <= 0.0:
            if prev_state is not None:
                landing = record_landing_exact(prev_state, projectile, screen_to_world(*ANCHOR)[0])
            else:
                landing = {'x': projectile['x'], 'speed': math.hypot(projectile['vx'], projectile['vy']), 'range': projectile['x'] - screen_to_world(*ANCHOR)[0], 'screen': world_to_screen(projectile['x'], 0.0)}
            # FIRST TOUCH marker only
            if not projectile.get('first_touch_recorded', False):
                impact_speed = landing['speed']
                flight_time = time.time() - projectile.get('start_time', time.time())
                sx, sy = landing['screen']
                first_ld = {
                    'x': landing['x'],
                    'velocity': impact_speed,   # renamed to velocity
                    'flight_time': flight_time,
                    'range': landing['range'],
                    'screen': (sx, sy),
                    'shot_id': projectile.get('shot_id'),
                    'max_height': projectile.get('max_height', 0.0)
                }
                landings.append(first_ld)
                projectile['first_touch_recorded'] = True
            # bounce response
            projectile['y'] = 0.0
            projectile['vy'] = -projectile['vy'] * RESTITUTION
            projectile['vx'] = projectile['vx'] * BOUNCE_FRICTION
            projectile['bounces'] = projectile.get('bounces', 0) + 1
            speed_now = math.hypot(projectile['vx'], projectile['vy'])
            if speed_now < REST_SPEED_THRESHOLD:
                projectile['alive'] = False
                prev_state = None

    # ---------------- Draw ----------------
    screen.fill(BG)
    draw_grid(screen, meters_between_lines=1, label_every=5, alpha=60)

    ground_y_px = HEIGHT - GROUND_H_PX
    pygame.draw.rect(screen, (50,50,50), (0, ground_y_px, WIDTH, GROUND_H_PX))


    # gravity preset buttons
    for name, val, rect in preset_rects:
        pygame.draw.rect(screen, (80,80,80), rect, border_radius=6)
        screen.blit(small.render(name, True, (220,220,220)), (rect.x+8, rect.y+6))
        if val is not None and abs(GRAVITY - val) < 1e-4:
            pygame.draw.rect(screen, (120,180,120), rect, 3, border_radius=6)
        elif name == "Custom" and (not any(abs(GRAVITY - v) < 1e-4 for (_, v, _) in preset_rects if v is not None)):
            pygame.draw.rect(screen, (120,180,120), rect, 3, border_radius=6)

    # restitution info
    pygame.draw.rect(screen, (70,70,70), REST_BOX, border_radius=6)
    draw_text(REST_BOX.x+8, REST_BOX.y+6, f"Restitution: {RESTITUTION:.2f}  ([ / ]) to change", small)

    # anchor & height
    ax, ay = ANCHOR
    pygame.draw.circle(screen, (200,160,60), ANCHOR, 9)
    anchor_h = screen_to_world(ax, ay)[1]
    pygame.draw.line(screen, (140,140,220), (ax, ay), (ax, ground_y_px), 2)
    pygame.draw.polygon(screen, (140,140,220), [(ax-6, ground_y_px+6), (ax+6, ground_y_px+6), (ax, ground_y_px-2)])
    draw_text(ax+12, ay-12, "Anchor height:", small)
    draw_text(ax+12, ay+6, f"{anchor_h:.2f} m", big)

    # dragging preview; lower HUD so it doesn't overlap buttons (moved down)
    hud_y = 60
    if dragging:
        mx, my = mouse_pos
        pygame.draw.line(screen, (180,180,180), ANCHOR, (mx, my), 2)
        pull_sx = ax - mx
        pull_sy = ay - my
        pull_wx = pull_sx / PIXELS_PER_M
        pull_wy = -pull_sy / PIXELS_PER_M
        disp = math.hypot(pull_wx, pull_wy)
        force_n = SPRING_K * disp
        if USE_PHYSICAL_LAUNCH and disp > 1e-9:
            v0 = disp * math.sqrt(max(1e-12, SPRING_K / PROJECTILE_MASS))
        else:
            v0 = disp * 4.0
        ux = pull_wx / disp if disp > 1e-9 else 0.0
        uy = pull_wy / disp if disp > 1e-9 else 0.0
        vx0 = ux * v0
        vy0 = uy * v0
        # analytic preview
        x0, y0 = screen_to_world(ax, ay)
        for t in [i*0.02 for i in range(400)]:
            xt = x0 + vx0 * t
            yt = y0 + vy0 * t - 0.5 * GRAVITY * t * t
            if yt < 0:
                pred_x = xt
                sx, sy = world_to_screen(pred_x, 0.0)
                pygame.draw.circle(screen, (180,200,80), (sx, sy), 6)
                break
            sx, sy = world_to_screen(xt, yt)
            if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                pygame.draw.circle(screen, (100,200,200), (sx, sy), 3)
        draw_text(10, hud_y, f"Disp: {disp:.3f} m   Force: {force_n:.1f} N   Init speed: {v0:.2f} m/s", small)
        draw_text(10, hud_y + 18, f"Gravity: {GRAVITY:.2f} m/s²   Cd: {('on' if ENABLE_AIR_DRAG else 'off')}", small)

    # live flight HUD (when shot flying) -- placed below drag HUD
    live_hud_y = 120
    if projectile and projectile['alive']:
        speed_now = math.hypot(projectile['vx'], projectile['vy'])
        angle_now = math.degrees(math.atan2(projectile['vy'], projectile['vx'])) if speed_now > 1e-9 else 0.0
        elapsed = time.time() - projectile['start_time']
        xw, yw = projectile['x'], projectile['y']
        draw_text(10, live_hud_y, f"Sim speed: {speed_now:.2f} m/s   Angle: {angle_now:.1f} deg", small)
        draw_text(10, live_hud_y + 18, f"Flight time: {elapsed:.2f} s   Pos: x={xw:.2f} m y={yw:.2f} m", small)
        draw_text(10, live_hud_y + 36, f"Max height so far: {projectile.get('max_height', 0.0):.2f} m", small)
        draw_text(10, live_hud_y + 54, f"Shot id: {projectile.get('shot_id')}", small)
        # draw projectile
        sx, sy = world_to_screen(projectile['x'], projectile['y'])
        r_px = int(BALL_RADIUS_M * PIXELS_PER_M)
        if ball_gradient:
            steps = max(6, r_px//2)
            for i in range(steps, 0, -1):
                frac = i/steps
                c = (int(ball_color[0]*frac + 20*(1-frac)), int(ball_color[1]*frac + 20*(1-frac)), int(ball_color[2]*frac + 20*(1-frac)))
                pygame.draw.circle(screen, c, (sx, sy), int(r_px*frac))
        else:
            pygame.draw.circle(screen, ball_color, (sx, sy), r_px)

    # stored landings
    mx, my = mouse_pos
    hover_index = None
    for i, ld in enumerate(landings):
        sx, sy = ld['screen']
        pygame.draw.circle(screen, (80,200,120), (sx, sy), MARKER_R)
        pygame.draw.line(screen, (120,220,150), (sx, sy), (sx, sy-36), 2)
        label = f"{ld['range']:.2f} m  [{ld['shot_id']}]"
        txt = small.render(label, True, (200,200,200))
        tx = sx + 12
        ty = sy - 30 - (i % 3) * 16
        if tx + txt.get_width() > WIDTH - 8:
            tx = sx - 12 - txt.get_width()
        screen.blit(txt, (tx, ty))
        if is_mouse_near(mx, my, sx, sy):
            hover_index = i

    # hover tooltip shows recorded metrics; remove bounces at touch and rename impact -> Velocity
 # ---------------- hover tooltip (replace existing hover tooltip code) ----------------
    if hover_index is not None:
        ld = landings[hover_index]
        sx, sy = ld['screen']

        # GRID displacement = landing x coordinate in world meters (distance along grid from world origin)
        grid_disp = ld.get('x', 0.0)

        txts = [
            f"Shot: {ld['shot_id']}",
            f"Range: {ld['range']:.2f} m",
            f"Displacement: {grid_disp:.2f} m",               # <- grid displacement (no dx/dy)
            f"Velocity: {ld.get('velocity', ld.get('speed', 0.0)):.2f} m/s",
            f"Flight time: {ld.get('flight_time', 0.0):.2f} s" if ld.get('flight_time') is not None else "Flight time: -",
            f"Max height: {ld.get('max_height', 0.0):.2f} m"
        ]

        # render tooltip (keeps your existing rendering code)
        padding = 6
        surfaces = [small.render(t, True, (220,220,220)) for t in txts]
        box_w = max(s.get_width() for s in surfaces) + padding*2
        box_h = sum(s.get_height() for s in surfaces) + padding*2 + 8
        box_x = sx + 12
        box_y = sy - box_h - 10
        if box_x + box_w > WIDTH - 6:
            box_x = sx - 12 - box_w
        if box_y < 6:
            box_y = sy + 12
        pygame.draw.rect(screen, (230,230,230), (box_x, box_y, box_w, box_h), border_radius=6)
        pygame.draw.rect(screen, (40,40,40), (box_x+1, box_y+1, box_w-2, box_h-2), border_radius=6)
        oy = box_y + padding
        for s in surfaces:
            screen.blit(s, (box_x + padding, oy))
            oy += s.get_height()


    # temporary hover prediction on anchor when idle (projectile is None)
    # show predicted final location and predicted bounce count based on last_pull (if available)
    if projectile is None:
        ax, ay = ANCHOR
        sx_anchor, sy_anchor = ax, ay
        if is_mouse_near(mx, my, sx_anchor, sy_anchor, r=26):
            if last_pull is not None:
                pwx, pwy = last_pull
                disp = math.hypot(pwx, pwy)
                if USE_PHYSICAL_LAUNCH and disp > 1e-9:
                    v0 = disp * math.sqrt(max(1e-12, SPRING_K / PROJECTILE_MASS))
                else:
                    v0 = disp * 4.0
                ux = pwx / disp if disp > 1e-9 else 0.0
                uy = pwy / disp if disp > 1e-9 else 0.0
                vx0 = ux * v0
                vy0 = uy * v0
                x0, y0 = screen_to_world(ax, ay)
                pred_final_x, pred_bounces = simulate_bounces_from_launch(x0, y0, vx0, vy0, RESTITUTION, BOUNCE_FRICTION, REST_SPEED_THRESHOLD)
                pred_range = pred_final_x - x0
                # show small tooltip near anchor
                txt1 = f"Predicted bounces: {pred_bounces}"
                txt2 = f"Predicted final X: {pred_final_x:.2f} m ({pred_range:.2f} m from anchor)"
                box_w = max(small.size(txt1)[0], small.size(txt2)[0]) + 12
                box_h = 40
                box_x = sx_anchor + 14
                box_y = sy_anchor - box_h - 8
                pygame.draw.rect(screen, (230,230,230), (box_x, box_y, box_w, box_h), border_radius=6)
                pygame.draw.rect(screen, (40,40,40), (box_x+1, box_y+1, box_w-2, box_h-2), border_radius=6)
                draw_text(box_x+6, box_y+6, txt1, small, color=(220,220,220))
                draw_text(box_x+6, box_y+20, txt2, small, color=(220,220,220))
            else:
                # no last pull yet
                txt1 = "Predicted bounces: -"
                txt2 = "Predicted final X: -"
                box_w = max(small.size(txt1)[0], small.size(txt2)[0]) + 12
                box_h = 40
                box_x = sx_anchor + 14
                box_y = sy_anchor - box_h - 8
                pygame.draw.rect(screen, (230,230,230), (box_x, box_y, box_w, box_h), border_radius=6)
                pygame.draw.rect(screen, (40,40,40), (box_x+1, box_y+1, box_w-2, box_h-2), border_radius=6)
                draw_text(box_x+6, box_y+6, txt1, small, color=(220,220,220))
                draw_text(box_x+6, box_y+20, txt2, small, color=(220,220,220))

    # help & color buttons
    pygame.draw.rect(screen, (220,220,220), HELP_RECT, border_radius=6)
    pygame.draw.rect(screen, (30,30,30), (HELP_RECT.x+2, HELP_RECT.y+2, HELP_RECT.w-4, HELP_RECT.h-4), border_radius=6)
    screen.blit(font.render("Help", True, (230,230,230)), (HELP_RECT.x+30, HELP_RECT.y+8))
    pygame.draw.rect(screen, (220,220,220), COLOR_RECT, border_radius=6)
    pygame.draw.rect(screen, (30,30,30), (COLOR_RECT.x+2, COLOR_RECT.y+2, COLOR_RECT.w-4, COLOR_RECT.h-4), border_radius=6)
    screen.blit(font.render("Color", True, (230,230,230)), (COLOR_RECT.x+30, COLOR_RECT.y+8))

    # gravity custom modal input
    if gravity_custom_modal:
        W, H = 360, 64
        x = (WIDTH - W)//2; y = (HEIGHT - H)//2
        pygame.draw.rect(screen, (230,230,230), (x-4, y-4, W+8, H+8), border_radius=8)
        pygame.draw.rect(screen, (40,40,40), (x, y, W, H), border_radius=6)
        draw_text(x+12, y+8, "Enter custom gravity (m/s²) and press Enter:", small)
        txt_surf = big.render(gravity_input_text if gravity_input_text else "", True, (220,220,220))
        screen.blit(txt_surf, (x+12, y+32))

    # color modal
    if color_modal_visible:
        W, H = 420, 240
        x = (WIDTH - W)//2; y = (HEIGHT - H)//2
        pygame.draw.rect(screen, (230,230,230), (x-4, y-4, W+8, H+8), border_radius=8)
        pygame.draw.rect(screen, (40,40,40), (x, y, W, H), border_radius=6)
        screen.blit(big.render("Ball Color & Style", True, (230,230,230)), (x+16, y+12))
        ox = x+18; oy = y+52
        for i, c in enumerate(COLOR_PRESETS):
            rect = pygame.Rect(ox + (i%6)*(36+12), oy + (i//6)*(36+12), 36, 36)
            pygame.draw.rect(screen, c, rect, border_radius=6)
            pygame.draw.rect(screen, (200,200,200), rect, 2, border_radius=6)

    pygame.display.flip()

pygame.quit()
sys.exit()
