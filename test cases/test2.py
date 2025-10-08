import math
import time
import pygame
import sys

# ---------------- Config ----------------
WIDTH, HEIGHT = 1500, 1000
BG = (30, 30, 30)
GROUND_H_PX = 70

PIXELS_PER_M = 50.0
PIXELS_PER_M_MIN = 8.0
PIXELS_PER_M_MAX = 1200.0

GRAVITY = 9.81

SPRING_K_BASE = 70.0
PULL_SCALE = 0.25
PROJECTILE_MASS = 0.5
USE_PHYSICAL_LAUNCH = True

RESTITUTION = 0.6
BOUNCE_FRICTION = 0.9
REST_SPEED_THRESHOLD = 0.12

ENABLE_AIR_DRAG = False
DRAG_COEFF_LINEAR = 0.1
AIR_DENSITY = 1.225
DRAG_COEFF_SPHERE = 0.47

MARKER_R = 9
BALL_RADIUS_M = 0.11

# ---------------- Pygame init ----------------
pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Slingshot — angle indicator")
clock = pygame.time.Clock()
font = pygame.font.SysFont("DejaVuSans", 16)
small = pygame.font.SysFont("DejaVuSans", 14)
big = pygame.font.SysFont("DejaVuSans", 18, bold=True)

# ---------------- Camera / Anchor ----------------
cam_off_x_m = 0.0
cam_off_y_m = 0.0

def world_to_screen(wx, wy):
    sx = int((wx - cam_off_x_m) * PIXELS_PER_M)
    sy = int(HEIGHT - GROUND_H_PX - (wy - cam_off_y_m) * PIXELS_PER_M)
    return sx, sy

def screen_to_world(sx, sy):
    wx = (sx / PIXELS_PER_M) + cam_off_x_m
    wy = ((HEIGHT - GROUND_H_PX - sy) / PIXELS_PER_M) + cam_off_y_m
    return wx, wy

ANCHOR_W = (0.0, 2.0)
if ANCHOR_W[1] < 0.0:
    ANCHOR_W = (ANCHOR_W[0], 0.0)

# ---------------- State ----------------
projectile = None
prev_state = None
landings = []
SHOT_COUNTER = 0

dragging = False
panning = False
pan_start_mouse = (0, 0)
pan_start_cam_x = 0.0
mouse_pos = (0, 0)
last_pull = None

help_visible = False
color_modal_visible = False
gravity_custom_modal = False
gravity_input_text = ""

ball_color = (200, 80, 80)
ball_gradient = False

ball_size_edit = False
ball_size_text = ""

BALL_MINUS_RECT = pygame.Rect(WIDTH - 320, 12, 36, 34)
BALL_SIZE_RECT = pygame.Rect(WIDTH - 280, 12, 120, 34)
BALL_PLUS_RECT = pygame.Rect(WIDTH - 156, 12, 36, 34)

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

HELP_RECT = pygame.Rect(WIDTH - 120, 56, 100, 34)
COLOR_RECT = pygame.Rect(WIDTH - 120, 12, 100, 34)

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
def draw_text(x, y, s, f=font, color=(230,230,230)):
    screen.blit(f.render(s, True, color), (x, y))

def record_landing_exact(prev, curr, anchor_x_m):
    y1 = prev['y']; y2 = curr['y']
    frac = (0.0 - y1) / (y2 - y1) if (y2 - y1) != 0 else 0.0
    frac = max(0.0, min(1.0, frac))
    x_l = prev['x'] + (curr['x'] - prev['x']) * frac
    vx_l = prev['vx'] + (curr['vx'] - prev['vx']) * frac
    vy_l = prev['vy'] + (curr['vy'] - prev['vy']) * frac
    speed = math.hypot(vx_l, vy_l)
    rng = x_l - anchor_x_m
    return x_l, speed, rng

def is_mouse_near(ptx, pty, sx, sy, r=MARKER_R+8):
    return (ptx - sx)**2 + (pty - sy)**2 <= r*r

def draw_grid(surface, meters_between_lines=1, label_every=5,
              line_color=(80,80,80), label_color=(180,180,180), alpha=60):
    grid_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    col = (*line_color, alpha)
    world_x_left = cam_off_x_m
    world_x_right = cam_off_x_m + WIDTH / PIXELS_PER_M
    world_y_bottom = 0.0
    world_y_top = world_y_bottom + (HEIGHT - GROUND_H_PX) / PIXELS_PER_M

    x = math.floor(world_x_left / meters_between_lines) * meters_between_lines
    while x <= world_x_right:
        sx, _ = world_to_screen(x, 0)
        pygame.draw.line(grid_surf, col, (sx, 0), (sx, HEIGHT - GROUND_H_PX), 1)
        if abs(x % label_every) < 1e-6:
            lbl = small.render(f"{x:.0f} m", True, label_color)
            grid_surf.blit(lbl, (sx+2, HEIGHT - GROUND_H_PX - 18))
        x += meters_between_lines

    y = math.floor(world_y_bottom / meters_between_lines) * meters_between_lines
    while y <= world_y_top:
        _, sy = world_to_screen(0, y)
        pygame.draw.line(grid_surf, col, (0, sy), (WIDTH, sy), 1)
        if abs(y % label_every) < 1e-6 and y > 0:
            lbl = small.render(f"{y:.0f} m", True, label_color)
            grid_surf.blit(lbl, (4, sy-14))
        y += meters_between_lines

    surface.blit(grid_surf, (0,0))

def compute_drag_accel(vx, vy):
    v = math.hypot(vx, vy)
    if v <= 1e-12:
        return 0.0, 0.0
    A = math.pi * (BALL_RADIUS_M ** 2)
    if ENABLE_AIR_DRAG:
        Fd = 0.5 * AIR_DENSITY * DRAG_COEFF_SPHERE * A * v * v
        axd = - (Fd / PROJECTILE_MASS) * (vx / v)
        ayd = - (Fd / PROJECTILE_MASS) * (vy / v)
    else:
        axd = -DRAG_COEFF_LINEAR * vx
        ayd = -DRAG_COEFF_LINEAR * vy
    return axd, ayd

def simulate_trajectory_points(x0, y0, vx0, vy0, dt_sim=0.02, max_time=20.0):
    pts = []
    x, y = x0, y0
    vx, vy = vx0, vy0
    steps = int(max_time / dt_sim)
    for _ in range(steps):
        pts.append((x, y))
        axd, ayd = compute_drag_accel(vx, vy)
        ax = axd
        ay = -GRAVITY + ayd
        vx += ax * dt_sim
        vy += ay * dt_sim
        x += vx * dt_sim
        y += vy * dt_sim
        if y <= 0.0:
            pts.append((x, 0.0))
            break
    return pts

def simulate_bounces_with_drag(x0, y0, vx0, vy0, restitution, friction, rest_speed, dt_sim=0.01, max_time=120.0):
    x, y = x0, y0
    vx, vy = vx0, vy0
    bounces = 0
    t = 0.0
    steps = int(max_time / dt_sim)
    for _ in range(steps):
        axd, ayd = compute_drag_accel(vx, vy)
        ax = axd
        ay = -GRAVITY + ayd
        vx += ax * dt_sim
        vy += ay * dt_sim
        x += vx * dt_sim
        y += vy * dt_sim
        t += dt_sim
        if y <= 0.0:
            y = 0.0
            if abs(vy) > 1e-6:
                bounces += 1
            vy = -vy * restitution
            vx = vx * friction
            speed = math.hypot(vx, vy)
            if speed < rest_speed:
                break
    return x, bounces, t

def angle_from_pull(pwx, pwy):
    ang = (math.degrees(math.atan2(pwy, pwx)) + 360.0) % 360.0
    return ang

# draw a small arc (as polyline) from 0° baseline to angle_deg around anchor
def draw_angle_arc(anchor_px, anchor_py, angle_deg, radius_px=36, color=(220,180,80), width=3):
    # choose sweep direction: go shortest path from 0 to angle_deg
    a = angle_deg
    if a > 180:
        a -= 360.0
    steps = max(6, int(abs(a) / 6) + 2)
    points = []
    for i in range(steps + 1):
        t = i / steps
        theta = math.radians(t * a)  # theta in world angle (0 -> a)
        sx = anchor_px + math.cos(theta) * radius_px
        sy = anchor_py - math.sin(theta) * radius_px
        points.append((int(sx), int(sy)))
    if len(points) > 1:
        pygame.draw.lines(screen, color, False, points, width)
        pygame.draw.circle(screen, color, points[-1], 4)

# quadratic bezier helper (screen points)
def quad_bezier(p0, p1, p2, steps=12):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u*u*p0[0] + 2*u*t*p1[0] + t*t*p2[0]
        y = u*u*p0[1] + 2*u*t*p1[1] + t*t*p2[1]
        pts.append((int(x), int(y)))
    return pts

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
                elif ball_size_edit:
                    ball_size_edit = False
                    ball_size_text = ""
            elif ev.key == pygame.K_c:
                landings.clear()
            elif ev.key == pygame.K_LEFTBRACKET or ev.unicode == "[":
                RESTITUTION = max(0.0, RESTITUTION - 0.05)
            elif ev.key == pygame.K_RIGHTBRACKET or ev.unicode == "]":
                RESTITUTION = min(1.0, RESTITUTION + 0.05)
            elif gravity_custom_modal:
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
            elif ball_size_edit:
                if ev.key == pygame.K_BACKSPACE:
                    ball_size_text = ball_size_text[:-1]
                elif ev.key == pygame.K_RETURN or ev.key == pygame.K_KP_ENTER:
                    try:
                        v = float(ball_size_text.strip())
                        if v > 0:
                            BALL_RADIUS_M = v
                    except:
                        pass
                    ball_size_edit = False
                    ball_size_text = ""
                else:
                    if ev.unicode and (ev.unicode.isdigit() or ev.unicode in ".-"):
                        ball_size_text += ev.unicode

        elif ev.type == pygame.MOUSEBUTTONDOWN:
            mx, my = ev.pos
            if HELP_RECT.collidepoint(mx, my):
                help_visible = not help_visible
                continue
            if COLOR_RECT.collidepoint(mx, my):
                color_modal_visible = not color_modal_visible
                continue

            if BALL_MINUS_RECT.collidepoint(mx, my):
                BALL_RADIUS_M = max(0.01, BALL_RADIUS_M - 0.01)
                continue
            if BALL_PLUS_RECT.collidepoint(mx, my):
                BALL_RADIUS_M = BALL_RADIUS_M + 0.01
                continue
            if BALL_SIZE_RECT.collidepoint(mx, my):
                ball_size_edit = True
                ball_size_text = ""
                continue

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
                grect = pygame.Rect(x+18, oy+90, 120, 28)
                if grect.collidepoint(mx, my):
                    ball_gradient = not ball_gradient
                    color_modal_visible = False
                    continue
                modal_rect = pygame.Rect(x, y, W, H)
                if not modal_rect.collidepoint(mx, my):
                    color_modal_visible = False
                    continue

            for name, val, rect in preset_rects:
                if rect.collidepoint(mx, my):
                    if name == "Custom":
                        gravity_custom_modal = True
                        gravity_input_text = ""
                    else:
                        GRAVITY = val
                    break

            if ev.button == 1:
                ax_s, ay_s = world_to_screen(*ANCHOR_W)
                if (mx - ax_s)**2 + (my - ay_s)**2 < 14000:
                    dragging = True
                    mouse_pos = ev.pos
                else:
                    panning = True
                    pan_start_mouse = ev.pos
                    pan_start_cam_x = cam_off_x_m

            elif ev.button == 3:
                if my < HEIGHT - GROUND_H_PX - 6:
                    new_anchor = screen_to_world(mx, my)
                    if new_anchor[1] < 0.0:
                        new_anchor = (new_anchor[0], 0.0)
                    ANCHOR_W = new_anchor

        elif ev.type == pygame.MOUSEBUTTONUP:
            if ev.button == 1:
                if panning:
                    panning = False
                if dragging and (not help_visible and not color_modal_visible and not gravity_custom_modal):
                    dragging = False
                    SHOT_COUNTER += 1
                    shot_id = SHOT_COUNTER
                    ax_s, ay_s = world_to_screen(*ANCHOR_W)
                    mx, my = mouse_pos
                    pull_sx = ax_s - mx
                    pull_sy = ay_s - my
                    pull_wx = pull_sx / PIXELS_PER_M
                    pull_wy = -pull_sy / PIXELS_PER_M
                    displacement_m = math.hypot(pull_wx, pull_wy)
                    last_pull = (pull_wx, pull_wy)
                    effective_k = SPRING_K_BASE * PULL_SCALE
                    if USE_PHYSICAL_LAUNCH and displacement_m > 1e-9:
                        v0 = displacement_m * math.sqrt(max(1e-12, effective_k / PROJECTILE_MASS))
                    else:
                        v0 = displacement_m * 4.0 * math.sqrt(PULL_SCALE)
                    if displacement_m > 1e-9:
                        ux = pull_wx / displacement_m
                        uy = pull_wy / displacement_m
                    else:
                        ux, uy = 0.0, 0.0
                    vx0 = ux * v0
                    vy0 = uy * v0
                    x0, y0 = ANCHOR_W
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
            if panning:
                mx, my = ev.pos
                dx_px = mx - pan_start_mouse[0]
                cam_off_x_m = pan_start_cam_x - dx_px / PIXELS_PER_M

        elif ev.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            world_before = screen_to_world(mx, my)
            factor = 1.15 ** ev.y
            new_ppm = PIXELS_PER_M * factor
            new_ppm = max(PIXELS_PER_M_MIN, min(PIXELS_PER_M_MAX, new_ppm))
            if abs(new_ppm - PIXELS_PER_M) > 1e-9:
                PIXELS_PER_M = new_ppm
                cam_off_x_m = world_before[0] - (mx / PIXELS_PER_M)

    # ---------------- Physics update ----------------
    if projectile and projectile["alive"]:
        prev_state = {'x': projectile['x'], 'y': projectile['y'], 'vx': projectile['vx'], 'vy': projectile['vy']}
        vx = projectile['vx']; vy = projectile['vy']
        axd, ayd = compute_drag_accel(vx, vy)
        ax_tot = axd
        ay_tot = -GRAVITY + ayd
        projectile['vx'] += ax_tot * dt
        projectile['vy'] += ay_tot * dt
        projectile['x'] += projectile['vx'] * dt
        projectile['y'] += projectile['vy'] * dt
        if projectile['y'] > projectile.get('max_height', -1e9):
            projectile['max_height'] = projectile['y']
        if projectile['y'] <= 0.0:
            if prev_state is not None:
                x_l, speed, rng = record_landing_exact(prev_state, projectile, ANCHOR_W[0])
            else:
                x_l = projectile['x']; speed = math.hypot(projectile['vx'], projectile['vy']); rng = x_l - ANCHOR_W[0]
            if not projectile.get('first_touch_recorded', False):
                impact_speed = speed
                flight_time = time.time() - projectile.get('start_time', time.time())
                first_ld = {
                    'x': x_l,
                    'y': 0.0,
                    'velocity': impact_speed,
                    'flight_time': flight_time,
                    'range': rng,
                    'shot_id': projectile.get('shot_id'),
                    'max_height': projectile.get('max_height', 0.0)
                }
                landings.append(first_ld)
                projectile['first_touch_recorded'] = True
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
    pygame.draw.line(screen, (180,180,180), (0, ground_y_px), (WIDTH, ground_y_px), 3)
    pygame.draw.rect(screen, (50,50,50), (0, ground_y_px, WIDTH, GROUND_H_PX))

    for name, val, rect in preset_rects:
        pygame.draw.rect(screen, (80,80,80), rect, border_radius=6)
        screen.blit(small.render(name, True, (220,220,220)), (rect.x+8, rect.y+6))
        if val is not None and abs(GRAVITY - val) < 1e-4:
            pygame.draw.rect(screen, (120,180,120), rect, 3, border_radius=6)
        elif name == "Custom" and (not any(abs(GRAVITY - v) < 1e-4 for (_, v, _) in preset_rects if v is not None)):
            pygame.draw.rect(screen, (120,180,120), rect, 3, border_radius=6)

    pygame.draw.rect(screen, (70,70,70), REST_BOX, border_radius=6)
    draw_text(REST_BOX.x+8, REST_BOX.y+6, f"Restitution: {RESTITUTION:.2f}  ([ / ]) to change", small)

    pygame.draw.rect(screen, (100,100,100), BALL_MINUS_RECT, border_radius=6)
    pygame.draw.rect(screen, (100,100,100), BALL_PLUS_RECT, border_radius=6)
    pygame.draw.rect(screen, (60,60,60), BALL_SIZE_RECT, border_radius=6)
    screen.blit(big.render("-", True, (220,220,220)), (BALL_MINUS_RECT.x+10, BALL_MINUS_RECT.y+6))
    screen.blit(big.render("+", True, (220,220,220)), (BALL_PLUS_RECT.x+6, BALL_PLUS_RECT.y+6))
    screen.blit(small.render(f"Ball r: {BALL_RADIUS_M:.3f} m", True, (220,220,220)), (BALL_SIZE_RECT.x+8, BALL_SIZE_RECT.y+8))

    pygame.draw.rect(screen, (220,220,220), HELP_RECT, border_radius=6)
    pygame.draw.rect(screen, (30,30,30), (HELP_RECT.x+2, HELP_RECT.y+2, HELP_RECT.w-4, HELP_RECT.h-4), border_radius=6)
    screen.blit(font.render("Help", True, (230,230,230)), (HELP_RECT.x+30, HELP_RECT.y+8))
    pygame.draw.rect(screen, (220,220,220), COLOR_RECT, border_radius=6)
    pygame.draw.rect(screen, (30,30,30), (COLOR_RECT.x+2, COLOR_RECT.y+2, COLOR_RECT.w-4, COLOR_RECT.h-4), border_radius=6)
    screen.blit(font.render("Color", True, (230,230,230)), (COLOR_RECT.x+30, COLOR_RECT.y+8))

    ax_s, ay_s = world_to_screen(*ANCHOR_W)
    pygame.draw.circle(screen, (200,160,60), (ax_s, ay_s), 9)
    anchor_h = ANCHOR_W[1]
    pygame.draw.line(screen, (140,140,220), (ax_s, ay_s), (ax_s, ground_y_px), 2)
    pygame.draw.polygon(screen, (140,140,220), [(ax_s-6, ground_y_px+6), (ax_s+6, ground_y_px+6), (ax_s, ground_y_px-2)])
    draw_text(ax_s+12, ay_s-12, "Anchor height:", small)
    draw_text(ax_s+12, ay_s+6, f"{anchor_h:.2f} m", big)

    # LAST pull info box (no angle when not dragging)
    if last_pull is not None:
        pwx, pwy = last_pull
        disp = math.hypot(pwx, pwy)
        effective_k = SPRING_K_BASE * PULL_SCALE
        if USE_PHYSICAL_LAUNCH and disp > 1e-9:
            v0 = disp * math.sqrt(max(1e-12, effective_k / PROJECTILE_MASS))
        else:
            v0 = disp * 4.0 * math.sqrt(PULL_SCALE)
        txt1 = f"Last pull: {disp:.3f} m"
        txt2 = f"Init speed: {v0:.2f} m/s"
        txt3 = f"Force: {effective_k * disp:.1f} N"
        txt4 = f"Vec: ({pwx:.2f},{pwy:.2f}) m"
        surfaces = [small.render(txt1, True, (220,220,220)), small.render(txt2, True, (220,220,220)), small.render(txt3, True, (220,220,220)), small.render(txt4, True, (220,220,220))]
        box_w = max(s.get_width() for s in surfaces) + 12
        box_h = sum(s.get_height() for s in surfaces) + 12
        box_x = ax_s + 50
        box_y = ay_s + 10
        if box_x + box_w > WIDTH - 6:
            box_x = ax_s - 14 - box_w
        pygame.draw.rect(screen, (230,230,230), (box_x, box_y, box_w, box_h), border_radius=6)
        pygame.draw.rect(screen, (40,40,40), (box_x+1, box_y+1, box_w-2, box_h-2), border_radius=6)
        oy = box_y + 6
        for s in surfaces:
            screen.blit(s, (box_x+6, oy))
            oy += s.get_height()

    hud_y = 60
    # DRAW angle indicator only while dragging (disappears after firing)
    if dragging:
        mx, my = mouse_pos
        pygame.draw.line(screen, (180,180,180), (ax_s, ay_s), (mx, my), 2)
        pull_sx = ax_s - mx
        pull_sy = ay_s - my
        pull_wx = pull_sx / PIXELS_PER_M
        pull_wy = -pull_sy / PIXELS_PER_M
        disp = math.hypot(pull_wx, pull_wy)
        force_n = SPRING_K_BASE * PULL_SCALE * disp
        if USE_PHYSICAL_LAUNCH and disp > 1e-9:
            v0 = disp * math.sqrt(max(1e-12, (SPRING_K_BASE * PULL_SCALE) / PROJECTILE_MASS))
        else:
            v0 = disp * 4.0 * math.sqrt(PULL_SCALE)
        ux = pull_wx / disp if disp > 1e-9 else 0.0
        uy = pull_wy / disp if disp > 1e-9 else 0.0
        vx0 = ux * v0
        vy0 = uy * v0
        x0, y0 = ANCHOR_W

        angle_deg = angle_from_pull(pull_wx, pull_wy)

        # baseline horizontal line (0° reference) to the right
        base_len = 72
        pygame.draw.line(screen, (240,240,240), (ax_s - 4, ay_s), (ax_s + base_len, ay_s), 2)

        # arc between baseline and pull direction
        draw_angle_arc(ax_s, ay_s, angle_deg, radius_px=36)

        # connect arc end to trajectory with a curved connector
        pts = simulate_trajectory_points(x0, y0, vx0, vy0, dt_sim=0.02, max_time=20.0)
        if pts:
            # first trajectory world pt -> screen
            tx, ty = pts[0]
            tpx, tpy = world_to_screen(tx, ty)
            # compute arc end (same as draw_angle_arc last point)
            # normalize angle to shortest signed angle
            a = angle_deg
            if a > 180:
                a -= 360.0
            theta = math.radians(a)
            arc_end = (int(ax_s + math.cos(theta)*36), int(ay_s - math.sin(theta)*36))
            # control point mid between arc_end and traj point, offset outward for curve
            mid_x = (arc_end[0] + tpx)//2
            mid_y = (arc_end[1] + tpy)//2 - 30  # lift control point for curvature
            bez = quad_bezier(arc_end, (mid_x, mid_y), (tpx, tpy), steps=14)
            if len(bez) > 1:
                pygame.draw.lines(screen, (180,220,200), False, bez, 2)

        # numeric angle label
        draw_text(ax_s+12, ay_s-36, f"Angle: {angle_deg:.1f}°", small)

        # realistic preview points
        pts = simulate_trajectory_points(x0, y0, vx0, vy0, dt_sim=0.02, max_time=20.0)
        for (xt, yt) in pts:
            if yt < 0:
                sx, sy = world_to_screen(xt, 0.0)
                pygame.draw.circle(screen, (180,200,80), (sx, sy), 6)
                break
            sx, sy = world_to_screen(xt, yt)
            if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                pygame.draw.circle(screen, (100,200,200), (sx, sy), 3)

        draw_text(10, hud_y, f"Disp: {disp:.3f} m   Force: {force_n:.1f} N   Init speed: {v0:.2f} m/s", small)
        draw_text(10, hud_y + 18, f"Gravity: {GRAVITY:.2f} m/s²   Cd: {('on' if ENABLE_AIR_DRAG else 'off')}", small)

    # always show gravity and Cd status
    draw_text(750, 15, f"Gravity: {GRAVITY:.2f} m/s²   Cd: {('on' if ENABLE_AIR_DRAG else 'off')}", small)

    # projectile draw / HUD
    live_hud_y = 120
    if projectile and projectile['alive']:
        speed_now = math.hypot(projectile['vx'], projectile['vy'])
        angle_now = math.degrees(math.atan2(projectile['vy'], projectile['vx'])) if speed_now > 1e-9 else 0.0
        elapsed = time.time() - projectile['start_time']
        xw, yw = projectile['x'], projectile['y']
        draw_text(10, hud_y, f"Sim speed: {speed_now:.2f} m/s   Angle: {angle_now:.1f} deg", small)
        draw_text(10, hud_y + 18, f"Flight time: {elapsed:.2f} s   Pos: x={xw:.2f} m y={yw:.2f} m", small)
        draw_text(10, hud_y + 36, f"Max height so far: {projectile.get('max_height', 0.0):.2f} m", small)
        draw_text(10, hud_y + 54, f"Shot id: {projectile.get('shot_id')}", small)
        sx, sy = world_to_screen(projectile['x'], projectile['y'])
        r_px = int(BALL_RADIUS_M * PIXELS_PER_M)
        if r_px < 2:
            r_px = 2
        if ball_gradient:
            steps = max(6, r_px//2)
            for i in range(steps, 0, -1):
                frac = i/steps
                c = (int(ball_color[0]*frac + 20*(1-frac)), int(ball_color[1]*frac + 20*(1-frac)), int(ball_color[2]*frac + 20*(1-frac)))
                pygame.draw.circle(screen, c, (sx, sy), int(r_px*frac))
        else:
            pygame.draw.circle(screen, ball_color, (sx, sy), r_px)

    # landings markers
    mx, my = mouse_pos
    hover_index = None
    for i, ld in enumerate(landings):
        sx, sy = world_to_screen(ld['x'], ld.get('y', 0.0))
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

    if hover_index is not None:
        ld = landings[hover_index]
        sx, sy = world_to_screen(ld['x'], ld.get('y', 0.0))
        grid_disp = ld.get('x', 0.0)
        txts = [
            f"Shot: {ld['shot_id']}",
            f"Range: {ld['range']:.2f} m",
            f"Displacement: {grid_disp:.2f} m",
            f"Velocity: {ld.get('velocity', ld.get('speed', 0.0)):.2f} m/s",
            f"Flight time: {ld.get('flight_time', 0.0):.2f} s" if ld.get('flight_time') is not None else "Flight time: -",
            f"Max height: {ld.get('max_height', 0.0):.2f} m"
        ]
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

    # idle anchor prediction (shows only predicted stats, no angle)
    if projectile is None:
        ax_s, ay_s = world_to_screen(*ANCHOR_W)
        sx_anchor, sy_anchor = ax_s, ay_s
        if is_mouse_near(mx, my, sx_anchor, sy_anchor, r=26):
            if last_pull is not None:
                pwx, pwy = last_pull
                disp = math.hypot(pwx, pwy)
                effective_k = SPRING_K_BASE * PULL_SCALE
                if USE_PHYSICAL_LAUNCH and disp > 1e-9:
                    v0 = disp * math.sqrt(max(1e-12, effective_k / PROJECTILE_MASS))
                else:
                    v0 = disp * 4.0 * math.sqrt(PULL_SCALE)
                ux = pwx / disp if disp > 1e-9 else 0.0
                uy = pwy / disp if disp > 1e-9 else 0.0
                vx0 = ux * v0
                vy0 = uy * v0
                x0, y0 = ANCHOR_W

                pred_final_x, pred_bounces, pred_time = simulate_bounces_with_drag(
                    x0, y0, vx0, vy0, RESTITUTION, BOUNCE_FRICTION, REST_SPEED_THRESHOLD, dt_sim=0.01, max_time=120.0
                )
                pred_range = pred_final_x - x0
                txt1 = f"Predicted bounces: {pred_bounces}"
                txt2 = f"Predicted final X: {pred_final_x:.2f} m ({pred_range:.2f} m from anchor)"
                txt3 = f"Predicted total time: {pred_time:.2f} s"
                box_w = max(small.size(txt1)[0], small.size(txt2)[0], small.size(txt3)[0]) + 12
                box_h = 54
                box_x = sx_anchor + 14
                box_y = sy_anchor - box_h - 8
                pygame.draw.rect(screen, (230,230,230), (box_x, box_y, box_w, box_h), border_radius=6)
                pygame.draw.rect(screen, (40,40,40), (box_x+1, box_y+1, box_w-2, box_h-2), border_radius=6)
                draw_text(box_x+6, box_y+6, txt1, small, color=(220,220,220))
                draw_text(box_x+6, box_y+24, txt2, small, color=(220,220,220))
                draw_text(box_x+6, box_y+42, txt3, small, color=(220,220,220))
            else:
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

    # modals and HUD
    if gravity_custom_modal:
        W, H = 360, 64
        x = (WIDTH - W)//2; y = (HEIGHT - H)//2
        pygame.draw.rect(screen, (230,230,230), (x-4, y-4, W+8, H+8), border_radius=8)
        pygame.draw.rect(screen, (40,40,40), (x, y, W, H), border_radius=6)
        draw_text(x+12, y+8, "Enter custom gravity (m/s²) and press Enter:", small)
        txt_surf = big.render(gravity_input_text if gravity_input_text else "", True, (220,220,220))
        screen.blit(txt_surf, (x+12, y+32))

    if ball_size_edit:
        W, H = 300, 64
        x = (WIDTH - W)//2; y = (HEIGHT - H)//2
        pygame.draw.rect(screen, (230,230,230), (x-4, y-4, W+8, H+8), border_radius=8)
        pygame.draw.rect(screen, (40,40,40), (x, y, W, H), border_radius=6)
        draw_text(x+12, y+8, "Enter ball radius (m) and press Enter:", small)
        txt_surf = big.render(ball_size_text if ball_size_text else "", True, (220,220,220))
        screen.blit(txt_surf, (x+12, y+32))

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

    if help_visible:
        W, H = 540, 320
        x = (WIDTH - W)//2; y = (HEIGHT - H)//2
        pygame.draw.rect(screen, (230,230,230), (x-6, y-6, W+12, H+12), border_radius=10)
        pygame.draw.rect(screen, (20,20,20), (x, y, W, H), border_radius=8)
        lines = [
            "Controls:",
            "- Left click + drag on anchor: pull and release to shoot.",
            "- Right click: move anchor (clamped to ground).",
            "- Drag outside anchor: pan camera horizontally.",
            "- Mouse wheel: zoom (centered on mouse).",
            "- [ and ]: decrease / increase restitution (bounciness).",
            "- C: clear recorded landings.",
            "Toggles:",
            f"- Air drag (Cd): {'on' if ENABLE_AIR_DRAG else 'off'} (variable ENABLE_AIR_DRAG).",
            "Notes:",
            "- Force shown is k * displacement. Use PULL_SCALE to reduce strength.",
            "- Restitution reduces vertical velocity on bounce; lower values make bounces smaller.",
            "- REST_SPEED_THRESHOLD controls when the simulation stops bouncing.",
            "Press Esc to close this help."
        ]
        oy = y + 12
        for line in lines:
            draw_text(x+16, oy, line, small)
            oy += 20

    draw_text(WIDTH - 220, HEIGHT - 30, f"Zoom: {PIXELS_PER_M:.1f} px/m", small)

    pygame.display.flip()

pygame.quit()
sys.exit()
