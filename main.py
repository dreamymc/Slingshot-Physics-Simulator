import math
import time
import pygame
import sys

# ---------------- Config ----------------
WIDTH, HEIGHT = 1500, 1000
BG = (30, 30, 30)
GROUND_H_PX = 250

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
pygame.display.set_caption("Slingshot — improved angle connect")
clock = pygame.time.Clock()
font = pygame.font.SysFont("DejaVuSans", 16)
small = pygame.font.SysFont("DejaVuSans", 14)
big = pygame.font.SysFont("DejaVuSans", 18, bold=True)

# ---------------- Assets ----------------
import os
def load_image(name, colorkey=None):
    try:
        img = pygame.image.load(os.path.join("assets", name)).convert_alpha()
        if colorkey is not None:
            img.set_colorkey(colorkey)
        return img
    except Exception as e:
        print(f"Failed to load {name}: {e}")
        return pygame.Surface((32, 32))

bg_img = load_image("bg_sky.png")
ground_img = load_image("ground.png")
cannonball_img = load_image("cannonball.png", (0, 0, 0))
slingshot_img = load_image("slingshot.png", (0, 0, 0))

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
# last_pull stores (pwx, pwy, angle_deg)
last_pull = None

# Caching state
cached_bounce_pred = None
cached_bounce_params = None

cached_traj_pred = None
cached_traj_params = None

cached_grid_surf = None
cached_grid_params = None

settings_menu_open = False
draw_grid_enabled = False

GEAR_RECT = pygame.Rect(WIDTH - 50, 10, 40, 40)
MENU_W, MENU_H = 600, 400
MENU_X = (WIDTH - MENU_W) // 2
MENU_Y = (HEIGHT - MENU_H) // 2
MENU_RECT = pygame.Rect(MENU_X, MENU_Y, MENU_W, MENU_H)

GRAV_PRESETS = [
    ("Earth", 9.81), ("Moon", 1.62), ("Mars", 3.71),
    ("Jupiter", 24.79), ("Custom", None)
]
preset_rects = []
px = MENU_X + 20
for name, val in GRAV_PRESETS:
    preset_rects.append((name, val, pygame.Rect(px, MENU_Y + 60, 86, 30)))
    px += 92

REST_BOX = pygame.Rect(MENU_X + 20, MENU_Y + 110, 240, 30)
BALL_MINUS_RECT = pygame.Rect(MENU_X + 20, MENU_Y + 160, 36, 34)
BALL_SIZE_RECT = pygame.Rect(MENU_X + 60, MENU_Y + 160, 120, 34)
BALL_PLUS_RECT = pygame.Rect(MENU_X + 184, MENU_Y + 160, 36, 34)

CLEAR_SHOTS_RECT = pygame.Rect(MENU_X + 20, MENU_Y + 210, 180, 34)
TOGGLE_DRAG_RECT = pygame.Rect(MENU_X + 220, MENU_Y + 210, 180, 34)
TOGGLE_GRID_RECT = pygame.Rect(MENU_X + 20, MENU_Y + 260, 180, 34)

gravity_custom_modal = False
gravity_input_text = ""
ball_size_edit = False
ball_size_text = ""
help_visible = False
color_modal_visible = False
ball_color = (40, 40, 40)
ball_gradient = False
COLOR_PRESETS = []

# ---------------- Utilities ----------------
def draw_text(x, y, s, f=font, color=(230,230,230)):
    screen.blit(f.render(s, True, color), (x, y))

def record_landing_exact(prev, curr, anchor_x_m):
    y1 = prev['y']; y2 = curr['y']
    frac = (BALL_RADIUS_M - y1) / (y2 - y1) if (y2 - y1) != 0 else 0.0
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
    global cached_grid_surf, cached_grid_params
    
    params = (cam_off_x_m, cam_off_y_m, PIXELS_PER_M, WIDTH, HEIGHT, meters_between_lines, label_every)
    if cached_grid_surf is not None and cached_grid_params == params:
        surface.blit(cached_grid_surf, (0,0))
        return

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

    cached_grid_surf = grid_surf
    cached_grid_params = params
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
        if y <= BALL_RADIUS_M:
            pts.append((x, BALL_RADIUS_M))
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
        if y <= BALL_RADIUS_M:
            y = BALL_RADIUS_M
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

# draw angle arc that ends exactly at given screen end point (so it connects visually to trajectory)
def draw_angle_arc_to_point(anchor_px, anchor_py, end_px, end_py, color=(220,180,80), width=3):

    # vector from anchor to end, but invert screen Y for mathematical angle
    dx = end_px - anchor_px
    dy = anchor_py - end_py  # positive when end is above anchor
    # target angle in degrees [0,360)
    target_ang = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0

    # build sweep from 0 to target_ang (inclusive). If target_ang is very small (near 0)
    # there will still be a short arc. Use a variable number of samples proportional to angle.
    sweep_deg = target_ang
    steps = max(6, int(min(72, 1 + sweep_deg * 0.12)))  # more steps for larger sweeps
    pts = []
    radius = 36
    for i in range(steps):
        t = i / (steps - 1)
        ang_deg = t * sweep_deg
        ang_rad = math.radians(ang_deg)
        sx = anchor_px + math.cos(ang_rad) * radius
        sy = anchor_py - math.sin(ang_rad) * radius
        pts.append((int(sx), int(sy)))

    # ensure final arc point exactly matches the trajectory connector
    if pts:
        pts[-1] = (int(end_px), int(end_py))

    if len(pts) > 1:
        pygame.draw.lines(screen, color, False, pts, width)
        pygame.draw.circle(screen, color, pts[-1], 4)

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
                if settings_menu_open:
                    settings_menu_open = False
                elif gravity_custom_modal:
                    gravity_custom_modal = False
                    gravity_input_text = ""
                elif ball_size_edit:
                    ball_size_edit = False
                    ball_size_text = ""
            elif ev.key == pygame.K_g:
                draw_grid_enabled = not draw_grid_enabled
            elif ev.key == pygame.K_c:
                landings.clear()
            elif ev.key == pygame.K_d:
                ENABLE_AIR_DRAG = not ENABLE_AIR_DRAG
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
            ui_handled = False

            if settings_menu_open:
                if gravity_custom_modal:
                    ui_handled = True
                elif ball_size_edit:
                    ui_handled = True
                elif not MENU_RECT.collidepoint(mx, my) and not GEAR_RECT.collidepoint(mx, my):
                    settings_menu_open = False
                    ui_handled = True
                elif GEAR_RECT.collidepoint(mx, my):
                    settings_menu_open = False
                    ui_handled = True
                else:
                    ui_handled = True
                    if CLEAR_SHOTS_RECT.collidepoint(mx, my):
                        landings.clear()
                    elif TOGGLE_DRAG_RECT.collidepoint(mx, my):
                        ENABLE_AIR_DRAG = not ENABLE_AIR_DRAG
                    elif TOGGLE_GRID_RECT.collidepoint(mx, my):
                        draw_grid_enabled = not draw_grid_enabled
                    elif BALL_MINUS_RECT.collidepoint(mx, my):
                        BALL_RADIUS_M = max(0.01, BALL_RADIUS_M - 0.01)
                    elif BALL_PLUS_RECT.collidepoint(mx, my):
                        BALL_RADIUS_M = BALL_RADIUS_M + 0.01
                    elif BALL_SIZE_RECT.collidepoint(mx, my):
                        ball_size_edit = True
                        ball_size_text = ""
                    else:
                        for name, val, rect in preset_rects:
                            if rect.collidepoint(mx, my):
                                if name == "Custom":
                                    gravity_custom_modal = True
                                    gravity_input_text = ""
                                else:
                                    GRAVITY = val
                                break

            else:
                if GEAR_RECT.collidepoint(mx, my):
                    settings_menu_open = True
                    ui_handled = True

            if not ui_handled:
                if ev.button == 1:
                    ax_s, ay_s = world_to_screen(*ANCHOR_W)
                    if (mx - ax_s)**2 + (my - ay_s)**2 < 14000:
                        dragging = True
                        mouse_pos = ev.pos
                    else:
                        if my < HEIGHT - GROUND_H_PX - 6:
                            new_anchor = screen_to_world(mx, my)
                            if new_anchor[1] < 0.0:
                                new_anchor = (new_anchor[0], 0.0)
                            ANCHOR_W = new_anchor

                elif ev.button == 3:
                    panning = True
                    pan_start_mouse = ev.pos
                    pan_start_cam_x = cam_off_x_m

        elif ev.type == pygame.MOUSEBUTTONUP:
            if ev.button == 3:
                if panning:
                    panning = False
            elif ev.button == 1:
                if dragging and not settings_menu_open:
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
                    # compute angle and store with last_pull
                    angle_deg = angle_from_pull(pull_wx, pull_wy)
                    last_pull = (pull_wx, pull_wy, angle_deg)
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
                        "max_height": y0, "bounces": 0,
                        "launch_angle": angle_deg
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
        if projectile['y'] <= BALL_RADIUS_M:
            if prev_state is not None:
                x_l, speed, rng = record_landing_exact(prev_state, projectile, ANCHOR_W[0])
            else:
                x_l = projectile['x']; speed = math.hypot(projectile['vx'], projectile['vy']); rng = x_l - ANCHOR_W[0]
            if not projectile.get('first_touch_recorded', False):
                impact_speed = speed
                flight_time = time.time() - projectile.get('start_time', time.time())
                first_ld = {
                    'x': x_l,
                    'y': BALL_RADIUS_M,
                    'velocity': impact_speed,
                    'flight_time': flight_time,
                    'range': rng,
                    'shot_id': projectile.get('shot_id'),
                    'max_height': projectile.get('max_height', 0.0),
                    'angle': projectile.get('launch_angle', 0.0)
                }
                landings.append(first_ld)
                projectile['first_touch_recorded'] = True
            projectile['y'] = BALL_RADIUS_M
            projectile['vy'] = -projectile['vy'] * RESTITUTION
            projectile['vx'] = projectile['vx'] * BOUNCE_FRICTION
            projectile['bounces'] = projectile.get('bounces', 0) + 1
            speed_now = math.hypot(projectile['vx'], projectile['vy'])
            if speed_now < REST_SPEED_THRESHOLD:
                projectile['alive'] = False
                prev_state = None

    # ---------------- Draw ----------------
    if bg_img.get_width() > 32:
        bg_w = bg_img.get_width()
        bg_h = bg_img.get_height()
        scale_factor = HEIGHT / bg_h
        scaled_bg_w = int(bg_w * scale_factor)
        scaled_bg = pygame.transform.scale(bg_img, (scaled_bg_w, HEIGHT))
        para_x = int(-cam_off_x_m * PIXELS_PER_M * 0.2) % scaled_bg_w
        screen.blit(scaled_bg, (para_x, 0))
        if para_x > 0:
            screen.blit(scaled_bg, (para_x - scaled_bg_w, 0))
        if para_x + scaled_bg_w < WIDTH:
            screen.blit(scaled_bg, (para_x + scaled_bg_w, 0))
    else:
        screen.fill(BG)
        
    if draw_grid_enabled:
        draw_grid(screen, meters_between_lines=1, label_every=5, alpha=60)

    ground_y_px = HEIGHT - GROUND_H_PX
    if ground_img.get_width() > 32:
        gr_w = ground_img.get_width()
        gr_h = ground_img.get_height()
        scale_factor = GROUND_H_PX / gr_h
        scaled_gr_w = int(gr_w * scale_factor)
        scaled_gr = pygame.transform.scale(ground_img, (scaled_gr_w, GROUND_H_PX))
        gx_off = int(-cam_off_x_m * PIXELS_PER_M) % scaled_gr_w
        if gx_off > 0:
            gx_off -= scaled_gr_w
        curr_x = gx_off
        while curr_x < WIDTH:
            screen.blit(scaled_gr, (curr_x, ground_y_px))
            curr_x += scaled_gr_w
    else:
        pygame.draw.line(screen, (180,180,180), (0, ground_y_px), (WIDTH, ground_y_px), 3)
        pygame.draw.rect(screen, (50,50,50), (0, ground_y_px, WIDTH, GROUND_H_PX))

    # UI overlay is drawn later, so we just draw the slingshot layers here.

    ax_s, ay_s = world_to_screen(*ANCHOR_W)
    anchor_h = ANCHOR_W[1]

    sh_h, sh_w = 0, 0
    left_prong, right_prong = (ax_s, ay_s), (ax_s, ay_s)
    if slingshot_img.get_width() > 32:
        sh_h = max(10, ground_y_px - ay_s + 20)
        sh_w = int(slingshot_img.get_width() * (sh_h / slingshot_img.get_height()))
        scaled_sh = pygame.transform.scale(slingshot_img, (sh_w, sh_h))
        # Estimate prong locations based on image
        left_prong = (ax_s - int(sh_w * 0.25), ay_s - 10)
        right_prong = (ax_s + int(sh_w * 0.25), ay_s - 10)

    # 1. Back rubber band (Right prong to mouse/projectile)
    if dragging:
        mx, my = mouse_pos
        pygame.draw.line(screen, (40, 20, 10), right_prong, (mx, my), 5)
    
    # 2. Draw projectile while dragging (before shooting)
    if dragging:
        mx, my = mouse_pos
        r_px = max(2, int(BALL_RADIUS_M * PIXELS_PER_M))
        if cannonball_img.get_width() > 32:
            scaled_cb = pygame.transform.scale(cannonball_img, (r_px * 2, r_px * 2))
            screen.blit(scaled_cb, (mx - r_px, my - r_px))
        else:
            pygame.draw.circle(screen, (40,40,40), (mx, my), r_px)
        
        # Pouch
        pygame.draw.rect(screen, (50, 25, 10), (mx - 5, my - 8, 10, 16), border_radius=3)

    # 3. Front rubber band (Left prong to mouse/projectile)
    if dragging:
        mx, my = mouse_pos
        pygame.draw.line(screen, (60, 30, 15), left_prong, (mx, my), 6)

    # 4. Slingshot Base
    if slingshot_img.get_width() > 32:
        screen.blit(scaled_sh, (ax_s - sh_w // 2, ay_s - 10))
    else:
        pygame.draw.circle(screen, (200,160,60), (ax_s, ay_s), 9)
        pygame.draw.line(screen, (140,140,220), (ax_s, ay_s), (ax_s, ground_y_px), 2)
        pygame.draw.polygon(screen, (140,140,220), [(ax_s-6, ground_y_px+6), (ax_s+6, ground_y_px+6), (ax_s, ground_y_px-2)])

    # LAST pull info box (no angle when not dragging) -> show angle when available
    if last_pull is not None:
        pwx, pwy, pang = last_pull
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
        txt5 = f"Angle: {pang:.1f}°"
        surfaces = [
            small.render(txt1, True, (220,220,220)),
            small.render(txt2, True, (220,220,220)),
            small.render(txt3, True, (220,220,220)),
            small.render(txt4, True, (220,220,220)),
            small.render(txt5, True, (220,220,220)),
        ]
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

        # baseline horizontal line (0° reference) to the right (longer)
        base_len = 120
        pygame.draw.line(screen, (240,240,240), (ax_s - 4, ay_s), (ax_s + base_len, ay_s), 2)

        # realistic preview points
        traj_params = (x0, y0, vx0, vy0, GRAVITY, ENABLE_AIR_DRAG, BALL_RADIUS_M)
        if cached_traj_params != traj_params:
            cached_traj_pred = simulate_trajectory_points(x0, y0, vx0, vy0, dt_sim=0.02, max_time=20.0)
            cached_traj_params = traj_params
        pts = cached_traj_pred
        
        traj_screen = []
        for (xt, yt) in pts:
            sx, sy = world_to_screen(xt, yt)
            traj_screen.append((sx, sy))

        # pick a trajectory point near the start to connect to (prefer first visible > anchor)
        connector_target = None
        for p in traj_screen[1:]:
            if abs(p[0] - ax_s) > 2 or abs(p[1] - ay_s) > 2:
                connector_target = p
                break
        if connector_target is None and traj_screen:
            connector_target = traj_screen[-1]

        if connector_target is not None:
            end_px, end_py = connector_target
            # draw arc that ends exactly at the trajectory broken-line point
            draw_angle_arc_to_point(ax_s, ay_s, end_px, end_py, color=(220,180,80), width=3)

        # numeric angle label placed to the right and slightly above arc
        draw_text(ax_s + 28, ay_s - 44, f"Angle: {angle_deg:.1f}°", small)
        # draw Force text near the angle label
        draw_text(ax_s + 28, ay_s - 26, f"Force: {force_n:.1f} N", small)

        # draw the trajectory preview dots (fade out)
        for i, (xt, yt) in enumerate(pts):
            sx, sy = world_to_screen(xt, yt)
            if i == 0:
                continue
            if yt <= BALL_RADIUS_M + 1e-4:
                sx, sy = world_to_screen(xt, BALL_RADIUS_M)
                pygame.draw.circle(screen, (40, 40, 40), (sx, sy), 4)
                break
            if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                if i % 2 == 0: # only draw every other point for classic dotted look
                    alpha = max(50, 255 - i * 5)
                    s_tmp = pygame.Surface((6, 6), pygame.SRCALPHA)
                    pygame.draw.circle(s_tmp, (40, 40, 40, alpha), (3, 3), 3)
                    screen.blit(s_tmp, (sx - 3, sy - 3))

    # We do not draw floating text hud here anymore, moving to settings menu

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
        if cannonball_img.get_width() > 32:
            scaled_cb = pygame.transform.scale(cannonball_img, (r_px * 2, r_px * 2))
            screen.blit(scaled_cb, (sx - r_px, sy - r_px))
        else:
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
        # Draw a little crater
        crater_rect = pygame.Rect(sx - 10, sy - 4, 20, 8)
        pygame.draw.ellipse(screen, (30, 20, 10), crater_rect)
        pygame.draw.ellipse(screen, (10, 5, 0), (sx - 6, sy - 2, 12, 4))
        # Draw a tiny wooden peg
        pygame.draw.rect(screen, (139, 69, 19), (sx - 2, sy - 15, 4, 15))
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
            f"Max height: {ld.get('max_height', 0.0):.2f} m",
            f"Angle: {ld.get('angle', 0.0):.1f}°",
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

    # idle anchor prediction (no angle drawn)
    if projectile is None:
        ax_s, ay_s = world_to_screen(*ANCHOR_W)
        sx_anchor, sy_anchor = ax_s, ay_s
        if is_mouse_near(mx, my, sx_anchor, sy_anchor, r=26):
            if last_pull is not None:
                pwx, pwy, pang = last_pull
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

                pred_params = (x0, y0, vx0, vy0, RESTITUTION, BOUNCE_FRICTION, GRAVITY, ENABLE_AIR_DRAG, BALL_RADIUS_M)
                if cached_bounce_params != pred_params:
                    cached_bounce_pred = simulate_bounces_with_drag(
                        x0, y0, vx0, vy0, RESTITUTION, BOUNCE_FRICTION, REST_SPEED_THRESHOLD, dt_sim=0.01, max_time=120.0
                    )
                    cached_bounce_params = pred_params
                pred_final_x, pred_bounces, pred_time = cached_bounce_pred
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

    # ---------------- Settings Menu Overlay ----------------
    # Always draw gear icon
    pygame.draw.rect(screen, (80, 80, 80), GEAR_RECT, border_radius=8)
    pygame.draw.circle(screen, (200, 200, 200), GEAR_RECT.center, 10, 3)
    for i in range(8):
        angle = math.radians(i * 45)
        px1 = GEAR_RECT.centerx + int(math.cos(angle) * 10)
        py1 = GEAR_RECT.centery + int(math.sin(angle) * 10)
        px2 = GEAR_RECT.centerx + int(math.cos(angle) * 14)
        py2 = GEAR_RECT.centery + int(math.sin(angle) * 14)
        pygame.draw.line(screen, (200, 200, 200), (px1, py1), (px2, py2), 4)

    if settings_menu_open:
        # Darken screen
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        screen.blit(overlay, (0, 0))

        # Menu Background
        pygame.draw.rect(screen, (40, 40, 40), MENU_RECT, border_radius=12)
        pygame.draw.rect(screen, (200, 200, 200), MENU_RECT, 2, border_radius=12)
        draw_text(MENU_RECT.x + 20, MENU_RECT.y + 20, "SETTINGS", big)

        # Gravity presets
        draw_text(MENU_RECT.x + 20, MENU_RECT.y + 60, f"Gravity (m/s²): {GRAVITY:.2f}", small)
        for name, val, rect in preset_rects:
            pygame.draw.rect(screen, (80,80,80), rect, border_radius=6)
            screen.blit(small.render(name, True, (220,220,220)), (rect.x+8, rect.y+6))
            if val is not None and abs(GRAVITY - val) < 1e-4:
                pygame.draw.rect(screen, (120,180,120), rect, 3, border_radius=6)
            elif name == "Custom" and (not any(abs(GRAVITY - v) < 1e-4 for (_, v, _) in preset_rects if v is not None)):
                pygame.draw.rect(screen, (120,180,120), rect, 3, border_radius=6)
        
        # Restitution
        pygame.draw.rect(screen, (70,70,70), REST_BOX, border_radius=6)
        draw_text(REST_BOX.x+8, REST_BOX.y+6, f"Restitution (Bounciness): {RESTITUTION:.2f}", small)

        # Ball Size
        pygame.draw.rect(screen, (100,100,100), BALL_MINUS_RECT, border_radius=6)
        pygame.draw.rect(screen, (100,100,100), BALL_PLUS_RECT, border_radius=6)
        pygame.draw.rect(screen, (60,60,60), BALL_SIZE_RECT, border_radius=6)
        screen.blit(big.render("-", True, (220,220,220)), (BALL_MINUS_RECT.x+10, BALL_MINUS_RECT.y+6))
        screen.blit(big.render("+", True, (220,220,220)), (BALL_PLUS_RECT.x+6, BALL_PLUS_RECT.y+6))
        screen.blit(small.render(f"Ball r: {BALL_RADIUS_M:.3f} m", True, (220,220,220)), (BALL_SIZE_RECT.x+8, BALL_SIZE_RECT.y+8))

        # Toggles and Actions
        pygame.draw.rect(screen, (150, 60, 60), CLEAR_SHOTS_RECT, border_radius=6)
        draw_text(CLEAR_SHOTS_RECT.x+8, CLEAR_SHOTS_RECT.y+8, "Clear All Shots", small)

        pygame.draw.rect(screen, (70, 70, 70), TOGGLE_DRAG_RECT, border_radius=6)
        draw_text(TOGGLE_DRAG_RECT.x+8, TOGGLE_DRAG_RECT.y+8, f"Air Drag: {'ON' if ENABLE_AIR_DRAG else 'OFF'}", small)

        pygame.draw.rect(screen, (70, 70, 70), TOGGLE_GRID_RECT, border_radius=6)
        draw_text(TOGGLE_GRID_RECT.x+8, TOGGLE_GRID_RECT.y+8, f"Math Grid: {'ON' if draw_grid_enabled else 'OFF'}", small)

        # Modals inside Settings Menu
        if gravity_custom_modal:
            pygame.draw.rect(screen, (20,20,20), (MENU_X+50, MENU_Y+200, 400, 64), border_radius=6)
            draw_text(MENU_X+62, MENU_Y+208, "Enter custom gravity (m/s²) and press Enter:", small)
            screen.blit(big.render(gravity_input_text, True, (220,220,220)), (MENU_X+62, MENU_Y+232))

        if ball_size_edit:
            pygame.draw.rect(screen, (20,20,20), (MENU_X+50, MENU_Y+200, 400, 64), border_radius=6)
            draw_text(MENU_X+62, MENU_Y+208, "Enter ball radius (m) and press Enter:", small)
            screen.blit(big.render(ball_size_text, True, (220,220,220)), (MENU_X+62, MENU_Y+232))

        draw_text(MENU_RECT.x + 20, MENU_RECT.y + MENU_H - 30, "Press ESC or click gear to close menu.", small, (150, 150, 150))

    draw_text(WIDTH - 220, HEIGHT - 30, f"Zoom: {PIXELS_PER_M:.1f} px/m", small)

    pygame.display.flip()

pygame.quit()
sys.exit()
