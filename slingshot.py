# slingshot_physical.py
# Run: python slingshot_physical.py
# Requires: pygame

import math
import pygame
import sys

# ----------------- Config -----------------
WIDTH, HEIGHT = 1100, 600
BG = (30, 30, 30)
GROUND_HEIGHT_PX = 60

# anchor initial position (pixels). Right-click to move anchor.
ANCHOR = (150, HEIGHT - GROUND_HEIGHT_PX - 20)

# visual scale and physics
PIXELS_PER_METER = 50.0     # screen units per meter (change to scale distances)
GRAVITY = 9.81              # m/s^2

# spring + mass model for physical launch
SPRING_K = 120.0            # N/m (spring constant)
PROJECTILE_MASS = 0.5       # kg

# integration
ENABLE_AIR_DRAG = False     # set True to enable simple linear drag in sim
DRAG_COEFF = 0.1            # linear drag coefficient (a_drag = -k * v)
USE_PHYSICAL_LAUNCH = True  # if True, compute v0 from spring energy and mass

# UI
MARKER_RADIUS_PX = 8

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont("DejaVuSans", 16)
small_font = pygame.font.SysFont("DejaVuSans", 14)
big_font = pygame.font.SysFont("DejaVuSans", 18, bold=True)

# ----------------- State -----------------
projectile = None   # dict: x,y (m), vx,vy (m/s), alive(bool), shot_id
prev_state = None   # store last step for landing interpolation
landings = []       # list of markers: {x, speed, range, screen, shot_id}
dragging = False
mouse_pos = (0, 0)

# help button/modal
HELP_BTN_RECT = pygame.Rect(WIDTH - 110, 10, 100, 34)
help_visible = False

# global shot counter
SHOT_COUNTER = 0

# ----------------- Utility -----------------
def world_to_screen(wx, wy):
    """wx,wy in meters (wy height above ground). Returns screen px coords."""
    sx = int(wx * PIXELS_PER_METER)
    sy = int(HEIGHT - GROUND_HEIGHT_PX - (wy * PIXELS_PER_METER))
    return sx, sy

def screen_to_world(sx, sy):
    """screen px -> world meters (wy height above ground)."""
    wx = sx / PIXELS_PER_METER
    wy = (HEIGHT - GROUND_HEIGHT_PX - sy) / PIXELS_PER_METER
    return wx, wy

def predict_trajectory(x0, y0, vx0, vy0, steps=300, dt=0.02):
    pts = []
    for i in range(steps):
        t = i * dt
        xt = x0 + vx0 * t
        yt = y0 + vy0 * t - 0.5 * GRAVITY * t * t
        if yt < 0:
            break
        pts.append((xt, yt))
    return pts

def analytic_range_and_height(v, angle_rad, y0=0.0):
    vy = v * math.sin(angle_rad)
    vx = v * math.cos(angle_rad)
    a = -0.5 * GRAVITY
    b = vy
    c = y0
    disc = b*b - 4*a*c
    if disc < 0:
        return None, None
    t_hit = (-b + math.sqrt(disc)) / (2*a)
    if t_hit < 0:
        t_hit = (-b - math.sqrt(disc)) / (2*a)
    rng = vx * t_hit
    max_h = y0 + (vy*vy) / (2*GRAVITY)
    return rng, max_h

def draw_text(surface, text, x, y, f=font, color=(230,230,230)):
    surf = f.render(text, True, color)
    surface.blit(surf, (x, y))

def record_landing_exact(prev, curr, anchor_x_m):
    """
    prev and curr are dicts with x,y,vx,vy (meters, m/s).
    Interpolate in time between prev and curr to find the fraction where y==0.
    Return landing dict {x, speed, range, screen}.
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

def draw_help_modal():
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
        "- Hover a landing marker to see details: Range (m), Impact (m/s), Shot ID.",
        "- Press 'C' to clear landings.",
        "",
        "Notes",
        "- Force shown uses a simple spring model F = k * x (N).",
        "- Initial speed uses energy-based conversion if 'USE_PHYSICAL_LAUNCH' is True.",
        "- Enable air drag or replace integrator for more realistic physics.",
    ]
    title = big_font.render("Help & Controls", True, (230,230,230))
    screen.blit(title, (x + 16, y + 12))
    oy = y + 52
    for line in lines:
        surf = small_font.render(line, True, (200,200,200))
        screen.blit(surf, (x + 18, oy))
        oy += surf.get_height() + 6
    hint = small_font.render("Click Help button again or press ESC to close.", True, (140,140,140))
    screen.blit(hint, (x + 18, y + H - 30))

# ----------------- Main Loop -----------------
running = True
while running:
    dt = clock.tick(60) / 1000.0
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE and help_visible:
                help_visible = False
            elif event.key == pygame.K_c:
                landings.clear()

        elif event.type == pygame.MOUSEBUTTONDOWN:
            mx, my = event.pos
            # help button
            if HELP_BTN_RECT.collidepoint(mx, my):
                help_visible = not help_visible
                continue

            # left click start drag if near anchor
            if event.button == 1:
                ax, ay = ANCHOR
                if (mx - ax)**2 + (my - ay)**2 < 12000:
                    dragging = True
                    mouse_pos = event.pos

            # right click: move anchor if above ground
            elif event.button == 3:
                if my < HEIGHT - GROUND_HEIGHT_PX - 6:
                    ANCHOR = (mx, my)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and dragging:
                # new shot id
                SHOT_COUNTER += 1
                shot_id = SHOT_COUNTER

                dragging = False
                ax, ay = ANCHOR
                mx, my = mouse_pos
                pull_sx = ax - mx
                pull_sy = ay - my
                # pull in meters
                pull_wx = pull_sx / PIXELS_PER_METER
                pull_wy = -pull_sy / PIXELS_PER_METER
                displacement_m = math.hypot(pull_wx, pull_wy)

                # compute initial speed and direction
                if USE_PHYSICAL_LAUNCH and displacement_m > 1e-9:
                    # energy conversion: 0.5*k*x^2 -> 0.5*m*v^2 => v = x * sqrt(k/m)
                    v0 = displacement_m * math.sqrt(max(1e-12, SPRING_K / PROJECTILE_MASS))
                else:
                    # fallback: small constant mapping for very small displacement
                    v0 = displacement_m * 4.0

                # direction unit vector (from anchor toward pulled position)
                if displacement_m > 1e-9:
                    ux = pull_wx / displacement_m
                    uy = pull_wy / displacement_m
                else:
                    ux, uy = 0.0, 0.0

                vx0 = ux * v0
                vy0 = uy * v0

                x0, y0 = screen_to_world(ax, ay)
                projectile = {"x": x0, "y": y0, "vx": vx0, "vy": vy0, "alive": True, "shot_id": shot_id}
                prev_state = None

        elif event.type == pygame.MOUSEMOTION:
            mouse_pos = event.pos
            if dragging:
                mouse_pos = event.pos

    # update projectile
    if projectile and projectile["alive"]:
        # store previous BEFORE updating
        prev_state = {'x': projectile['x'], 'y': projectile['y'], 'vx': projectile['vx'], 'vy': projectile['vy'], 'shot_id': projectile.get('shot_id')}
        vx = projectile["vx"]
        vy = projectile["vy"]
        if ENABLE_AIR_DRAG:
            axd = -DRAG_COEFF * vx
            ayd = -DRAG_COEFF * vy
        else:
            axd = 0.0
            ayd = 0.0
        ax_total = axd
        ay_total = -GRAVITY + ayd

        projectile["vx"] += ax_total * dt
        projectile["vy"] += ay_total * dt
        projectile["x"] += projectile["vx"] * dt
        projectile["y"] += projectile["vy"] * dt

        # landing detection
        if projectile["y"] <= 0.0:
            anchor_x_m = screen_to_world(*ANCHOR)[0]
            if prev_state is not None:
                landing = record_landing_exact(prev_state, projectile, anchor_x_m)
            else:
                landing = {'x': projectile['x'], 'speed': math.hypot(projectile['vx'], projectile['vy']), 'range': projectile['x'] - anchor_x_m, 'screen': world_to_screen(projectile['x'], 0.0)}
            # store per-shot marker (no merging)
            new_ld = {
                'x': landing['x'],
                'speed': landing['speed'],
                'range': landing['range'],
                'screen': landing['screen'],
                'shot_id': projectile.get('shot_id')
            }
            landings.append(new_ld)
            projectile["alive"] = False
            prev_state = None

    # ---------- draw ----------
    screen.fill(BG)
    ground_y = HEIGHT - GROUND_HEIGHT_PX
    pygame.draw.rect(screen, (50,50,50), (0, ground_y, WIDTH, GROUND_HEIGHT_PX))
    pygame.draw.line(screen, (160,160,160), (0, ground_y), (WIDTH, ground_y), 2)

    # anchor and height marker
    ax, ay = ANCHOR
    pygame.draw.circle(screen, (200,160,60), ANCHOR, 9)
    anchor_world_x, anchor_world_y = screen_to_world(ax, ay)
    pygame.draw.line(screen, (140,140,220), (ax, ay), (ax, ground_y), 2)
    pygame.draw.polygon(screen, (140,140,220), [(ax-6, ground_y+6), (ax+6, ground_y+6), (ax, ground_y-2)])
    draw_text(screen, "Anchor height:", ax + 12, ay - 10, f=small_font)
    draw_text(screen, f"{anchor_world_y:.2f} m", ax + 12, ay + 6, f=big_font)

    # dragging preview & physics readouts
    if dragging:
        mx, my = mouse_pos
        pygame.draw.line(screen, (180,180,180), ANCHOR, (mx, my), 2)
        pull_sx = ax - mx
        pull_sy = ay - my
        pull_wx = pull_sx / PIXELS_PER_METER
        pull_wy = -pull_sy / PIXELS_PER_METER
        displacement_m = math.hypot(pull_wx, pull_wy)
        # force magnitude (spring)
        force_n = SPRING_K * displacement_m
        # initial speed (energy mapping)
        if USE_PHYSICAL_LAUNCH and displacement_m > 1e-9:
            v0_disp = displacement_m * math.sqrt(max(1e-12, SPRING_K / PROJECTILE_MASS))
        else:
            v0_disp = displacement_m * 4.0
        # direction
        ux = (pull_wx / displacement_m) if displacement_m > 1e-9 else 0.0
        uy = (pull_wy / displacement_m) if displacement_m > 1e-9 else 0.0
        vx0 = ux * v0_disp
        vy0 = uy * v0_disp

        x0, y0 = screen_to_world(ax, ay)
        traj = predict_trajectory(x0, y0, vx0, vy0, steps=400, dt=0.02)
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
        ]
        for i, line in enumerate(info_lines):
            draw_text(screen, line, 10, 8 + i*18)

    # draw projectile
    if projectile:
        sx, sy = world_to_screen(projectile["x"], projectile["y"])
        pygame.draw.circle(screen, (200,80,80), (sx, sy), 10)
        if projectile["alive"]:
            speed = math.hypot(projectile["vx"], projectile["vy"])
            angle = math.degrees(math.atan2(projectile["vy"], projectile["vx"])) if speed > 1e-9 else 0.0
            draw_text(screen, f"Sim speed: {speed:.2f} m/s", 10, 120)
            draw_text(screen, f"Sim angle: {angle:.1f} deg", 10, 138)
            draw_text(screen, f"Shot id: {projectile.get('shot_id')}", 10, 156)

    # draw landing markers (one per shot) and tooltips
    mouse_x, mouse_y = mouse_pos
    hover_shown = False
    for i, ld in enumerate(landings):
        sx, sy = ld['screen']
        pygame.draw.circle(screen, (80,200,120), (sx, sy), MARKER_RADIUS_PX)
        pygame.draw.line(screen, (120,220,150), (sx, sy), (sx, sy-34), 2)

        if is_mouse_near_marker(mouse_x, mouse_y, (sx, sy)):
            hover_shown = True
            txt1 = f"Range: {ld['range']:.2f} m"
            txt2 = f"Impact: {ld['speed']:.2f} m/s"
            txt3 = f"Shot: {ld['shot_id']}"
            padding = 6
            line1_surf = small_font.render(txt1, True, (0,0,0))
            line2_surf = small_font.render(txt2, True, (0,0,0))
            line3_surf = small_font.render(txt3, True, (0,0,0))
            box_w = max(line1_surf.get_width(), line2_surf.get_width(), line3_surf.get_width()) + padding*2
            box_h = line1_surf.get_height() + line2_surf.get_height() + line3_surf.get_height() + padding*2 + 4
            box_x = sx + 12
            box_y = sy - box_h - 8
            if box_x + box_w > WIDTH - 6:
                box_x = sx - 12 - box_w
            if box_y < 6:
                box_y = sy + 12
            pygame.draw.rect(screen, (230,230,230), (box_x, box_y, box_w, box_h), border_radius=4)
            pygame.draw.rect(screen, (40,40,40), (box_x+1, box_y+1, box_w-2, box_h-2), border_radius=4)
            draw_text(screen, txt1, box_x + padding, box_y + padding, f=small_font, color=(220,220,220))
            draw_text(screen, txt2, box_x + padding, box_y + padding + line1_surf.get_height(), f=small_font, color=(220,220,220))
            draw_text(screen, txt3, box_x + padding, box_y + padding + line1_surf.get_height() + line2_surf.get_height(), f=small_font, color=(220,220,220))

        else:
            # compact label: range and shot id
            label = f"{ld['range']:.2f} m  [{ld['shot_id']}]"
            txt_surf = small_font.render(label, True, (200,200,200))
            tx = sx + 10
            ty = sy - 26 - (i % 3) * 16
            if tx + txt_surf.get_width() > WIDTH - 8:
                tx = sx - 12 - txt_surf.get_width()
            screen.blit(txt_surf, (tx, ty))

    # draw help button (top-right)
    pygame.draw.rect(screen, (220,220,220), HELP_BTN_RECT, border_radius=6)
    pygame.draw.rect(screen, (30,30,30), (HELP_BTN_RECT.x+2, HELP_BTN_RECT.y+2, HELP_BTN_RECT.w-4, HELP_BTN_RECT.h-4), border_radius=6)
    help_label = font.render("Help", True, (230,230,230))
    screen.blit(help_label, (HELP_BTN_RECT.x + 26, HELP_BTN_RECT.y + 8))

    # bottom compact hint
    draw_text(screen, "Right-click to move anchor. Press C to clear landings.", 10, HEIGHT - 40, f=small_font)

    # help modal
    if help_visible:
        draw_help_modal()

    pygame.display.flip()

pygame.quit()
sys.exit()
