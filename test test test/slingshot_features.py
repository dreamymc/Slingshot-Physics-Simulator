# slingshot_features.py
# Features:
# - Right-click to move anchor (start point)
# - Vertical height marker from anchor to ground (meters)
# - Pull force (Newtons) computed and shown during drag (simple spring model F = k * x)
# - Landing markers aggregate trials when landings are close (counts stored)

import math
import pygame
import sys

# --- Config ---
WIDTH, HEIGHT = 1100, 600
BG = (30, 30, 30)
GROUND_HEIGHT_PX = 60                # ground thickness in px
# initial anchor (px). Right-click will move this.
ANCHOR = (150, HEIGHT - GROUND_HEIGHT_PX - 20)
PIXELS_PER_METER = 50.0              # scale: 1 meter -> PIXELS_PER_METER pixels
GRAVITY = 9.81                       # m/s^2
SPEED_FACTOR = 4.0                   # multiply pull vector to get initial speed
ENABLE_AIR_DRAG = False
DRAG_COEFF = 0.1

# Force model (spring constant) for pull force display:
# Force (N) = SPRING_K (N/m) * displacement_m (m)
SPRING_K = 120.0    # tune this to get numbers in a reasonable range

# landing aggregation threshold (meters). If landing within this x-distance of existing
# marker, increment that marker's trials.
MERGE_THRESHOLD_M = 0.5

MARKER_RADIUS_PX = 8

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
clock = pygame.time.Clock()
font = pygame.font.SysFont("DejaVuSans", 16)
small_font = pygame.font.SysFont("DejaVuSans", 14)
big_font = pygame.font.SysFont("DejaVuSans", 18, bold=True)

projectile = None
prev_state = None
landings = []  # list of dicts: {x, speed, range, screen, trials}
dragging = False
mouse_pos = (0, 0)

def world_to_screen(wx, wy):
    sx = int(wx * PIXELS_PER_METER)
    sy = int(HEIGHT - GROUND_HEIGHT_PX - (wy * PIXELS_PER_METER))
    return sx, sy

def screen_to_world(sx, sy):
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
    surface.blit(surf, (x,y))

def record_landing_exact(prev, curr, anchor_x_m):
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
    return {'x': x_landing, 'speed': speed, 'range': range_from_anchor, 'screen': (sx, sy), 'trials': 1}

def find_or_merge_landing(landing):
    # if existing landing within MERGE_THRESHOLD_M meters, merge (increment trials, update last speed)
    for ld in landings:
        if abs(ld['x'] - landing['x']) <= MERGE_THRESHOLD_M:
            ld['trials'] += 1
            ld['speed'] = landing['speed']   # update to last impact speed
            ld['range'] = landing['range']
            ld['screen'] = landing['screen']
            return
    landings.append(landing)

def is_mouse_near_marker(mx, my, marker_screen, radius=MARKER_RADIUS_PX+8):
    sx, sy = marker_screen
    return (mx - sx)**2 + (my - sy)**2 <= radius**2

# main loop
while True:
    dt = clock.tick(60) / 1000.0
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()

        # left click: start drag if near anchor
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            ax, ay = ANCHOR
            if (mx-ax)**2 + (my-ay)**2 < 12000:
                dragging = True
                mouse_pos = event.pos

        # left up: launch
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if dragging:
                dragging = False
                ax, ay = ANCHOR
                mx, my = mouse_pos
                pull_sx = ax - mx
                pull_sy = ay - my
                pull_wx = pull_sx / PIXELS_PER_METER
                pull_wy = -pull_sy / PIXELS_PER_METER
                vx0 = pull_wx * SPEED_FACTOR
                vy0 = pull_wy * SPEED_FACTOR
                x0, y0 = screen_to_world(ax, ay)
                projectile = {"x": x0, "y": y0, "vx": vx0, "vy": vy0, "alive": True}
                prev_state = None

        # right click: move anchor to clicked location (only if above ground)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            mx, my = event.pos
            # ensure anchor remains above ground surface
            if my < HEIGHT - GROUND_HEIGHT_PX - 6:
                ANCHOR = (mx, my)
                # do not move existing projectile; new anchor used for subsequent shots

        elif event.type == pygame.MOUSEMOTION:
            mouse_pos = event.pos
            if dragging:
                mouse_pos = event.pos

    # update projectile with prev_state tracking
    if projectile and projectile["alive"]:
        # save previous copy BEFORE update
        prev_state = {'x': projectile['x'], 'y': projectile['y'], 'vx': projectile['vx'], 'vy': projectile['vy']}
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

        if projectile["y"] <= 0.0:
            anchor_x_m = screen_to_world(*ANCHOR)[0]
            if prev_state is not None:
                landing = record_landing_exact(prev_state, projectile, anchor_x_m)
            else:
                landing = {'x': projectile['x'], 'speed': math.hypot(projectile['vx'], projectile['vy']),
                           'range': projectile['x'] - anchor_x_m, 'screen': world_to_screen(projectile['x'], 0.0), 'trials': 1}
            find_or_merge_landing(landing)
            projectile["alive"] = False
            prev_state = None

    # draw scene
    screen.fill(BG)
    ground_y = HEIGHT - GROUND_HEIGHT_PX
    pygame.draw.rect(screen, (50,50,50), (0, ground_y, WIDTH, GROUND_HEIGHT_PX))
    pygame.draw.line(screen, (160,160,160), (0, ground_y), (WIDTH, ground_y), 2)

    # draw anchor
    ax, ay = ANCHOR
    pygame.draw.circle(screen, (200,160,60), ANCHOR, 9)
    # vertical height marker from anchor down to ground and height text
    anchor_world_x, anchor_world_y = screen_to_world(ax, ay)
    hx1, hy1 = ax, ay
    hx2, hy2 = ax, ground_y
    pygame.draw.line(screen, (140,140,220), (hx1, hy1), (hx2, hy2), 2)
    # small arrow/triangle at ground
    pygame.draw.polygon(screen, (140,140,220), [(ax-6, ground_y+6), (ax+6, ground_y+6), (ax, ground_y-2)])
    height_text = f"{anchor_world_y:.2f} m"
    draw_text(screen, "Anchor height:", ax + 12, ay - 10, f=small_font)
    draw_text(screen, height_text, ax + 12, ay + 6, f=big_font)

    # dragging preview & force computation
    if dragging:
        mx, my = mouse_pos
        pygame.draw.line(screen, (180,180,180), ANCHOR, (mx, my), 2)
        pull_sx = ax - mx
        pull_sy = ay - my
        pull_wx = pull_sx / PIXELS_PER_METER
        pull_wy = -pull_sy / PIXELS_PER_METER
        displacement_m = math.hypot(pull_wx, pull_wy)
        # simple spring force
        force_n = SPRING_K * displacement_m
        vx0 = pull_wx * SPEED_FACTOR
        vy0 = pull_wy * SPEED_FACTOR
        x0, y0 = screen_to_world(ax, ay)
        traj = predict_trajectory(x0, y0, vx0, vy0, steps=350, dt=0.02)
        for p in traj:
            sx, sy = world_to_screen(p[0], p[1])
            if 0 <= sx < WIDTH and 0 <= sy < HEIGHT:
                pygame.draw.circle(screen, (100,200,200), (sx, sy), 3)
        speed = math.hypot(vx0, vy0)
        angle = math.degrees(math.atan2(vy0, vx0)) if speed > 1e-9 else 0.0
        info_lines = [
            f"Pull (m): {pull_wx:.2f}, {pull_wy:.2f}",
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
            angle = math.degrees(math.atan2(projectile["vy"], projectile["vx"])) if speed>1e-9 else 0.0
            draw_text(screen, f"Sim speed: {speed:.2f} m/s", 10, 120)
            draw_text(screen, f"Sim angle: {angle:.1f} deg", 10, 138)
            draw_text(screen, f"Sim pos: x={projectile['x']:.2f} m y={projectile['y']:.2f} m", 10, 156)

    # draw landing markers and tooltips
    mouse_x, mouse_y = mouse_pos
    hover_shown = False
    for i, ld in enumerate(landings):
        sx, sy = ld['screen']
        pygame.draw.circle(screen, (80,200,120), (sx, sy), MARKER_RADIUS_PX)
        pygame.draw.line(screen, (120,220,150), (sx, sy), (sx, sy-34), 2)
        # hover tooltip
        if is_mouse_near_marker(mouse_x, mouse_y, (sx, sy)):
            hover_shown = True
            txt1 = f"Range: {ld['range']:.2f} m"
            txt2 = f"Impact: {ld['speed']:.2f} m/s"
            txt3 = f"Trials: {ld['trials']}"
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

    # compact labels when not hovering
    if landings and not hover_shown:
        for j, ld in enumerate(landings):
            sx, sy = ld['screen']
            label = f"{ld['range']:.2f} m ({ld['trials']})"
            txt_surf = small_font.render(label, True, (200,200,200))
            tx = sx + 10
            ty = sy - 26 - (j % 3) * 16
            if tx + txt_surf.get_width() > WIDTH - 8:
                tx = sx - 12 - txt_surf.get_width()
            screen.blit(txt_surf, (tx, ty))

    # instructions
    draw_text(screen, "Left-click near anchor and drag to launch.", 10, HEIGHT - 120)
    draw_text(screen, "Right-click anywhere above the ground to move anchor.", 10, HEIGHT - 100)
    draw_text(screen, "Hover markers to see Range, Impact speed, and Trials.", 10, HEIGHT - 80)
    draw_text(screen, f"Force model: F = k*x   (k={SPRING_K} N/m)  Merge threshold: {MERGE_THRESHOLD_M} m", 10, HEIGHT - 56)

    pygame.display.flip()
