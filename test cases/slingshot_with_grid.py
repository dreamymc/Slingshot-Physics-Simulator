# slingshot_with_grid.py
# pip install pygame
import math, time, pygame, sys

# ---------------- Config ----------------
WIDTH, HEIGHT = 1200, 650
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

MARKER_R = 9
BALL_RADIUS_M = 0.11

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Slingshot with Grid")
clock = pygame.time.Clock()
font = pygame.font.SysFont("DejaVuSans", 16)
small = pygame.font.SysFont("DejaVuSans", 14)
big = pygame.font.SysFont("DejaVuSans", 18, bold=True)

# ---------------- State ----------------
projectile = None
prev_state = None
landings = []
SHOT_COUNTER = 0
dragging = False
mouse_pos = (0, 0)

# ---------------- Utilities ----------------
def world_to_screen(wx, wy):
    sx = int(wx * PIXELS_PER_M)
    sy = int(HEIGHT - GROUND_H_PX - wy * PIXELS_PER_M)
    return sx, sy

def screen_to_world(sx, sy):
    wx = sx / PIXELS_PER_M
    wy = (HEIGHT - GROUND_H_PX - sy) / PIXELS_PER_M
    return wx, wy

def draw_text(x, y, s, f=font, color=(220,220,220)):
    screen.blit(f.render(s, True, color), (x, y))

def draw_grid(surface,
              meters_between_lines=1,
              label_every_n_meters=5,
              line_color=(100,100,110),
              label_color=(220,220,220),
              alpha=60):
    """Draw faint meter grid using PIXELS_PER_M scale."""
    grid_surf = pygame.Surface((WIDTH, HEIGHT), flags=pygame.SRCALPHA)
    line_col = (*line_color, alpha)

    # World ranges
    world_x_left = 0.0
    world_x_right = WIDTH / PIXELS_PER_M
    world_y_bottom = - (GROUND_H_PX / PIXELS_PER_M)
    world_y_top = (HEIGHT - GROUND_H_PX) / PIXELS_PER_M

    # Align to spacing
    start_x = math.floor(world_x_left / meters_between_lines) * meters_between_lines
    end_x = math.ceil(world_x_right / meters_between_lines) * meters_between_lines
    start_y = math.floor(world_y_bottom / meters_between_lines) * meters_between_lines
    end_y = math.ceil(world_y_top / meters_between_lines) * meters_between_lines

    # Vertical lines
    m = start_x
    while m <= end_x:
        sx, _ = world_to_screen(m, 0)
        pygame.draw.line(grid_surf, line_col, (sx, 0), (sx, HEIGHT), 1)
        if (abs(m) % label_every_n_meters) < 1e-6:
            txt = small.render(f"{m:.0f} m", True, label_color)
            grid_surf.blit(txt, (sx + 2, HEIGHT - GROUND_H_PX - 18))
        m += meters_between_lines

    # Horizontal lines
    n = start_y
    while n <= end_y:
        _, sy = world_to_screen(0, n)
        pygame.draw.line(grid_surf, line_col, (0, sy), (WIDTH, sy), 1)
        if (abs(n) % label_every_n_meters) < 1e-6:
            txt = small.render(f"{n:.0f} m", True, label_color)
            grid_surf.blit(txt, (4, sy - 14))
        n += meters_between_lines

    surface.blit(grid_surf, (0,0))

def record_landing(prev, curr, anchor_x_m):
    y1, y2 = prev['y'], curr['y']
    frac = (0.0 - y1) / (y2 - y1) if (y2-y1)!=0 else 0
    frac = max(0.0, min(1.0, frac))
    x_l = prev['x'] + (curr['x'] - prev['x'])*frac
    vx_l = prev['vx'] + (curr['vx'] - prev['vx'])*frac
    vy_l = prev['vy'] + (curr['vy'] - prev['vy'])*frac
    speed = math.hypot(vx_l, vy_l)
    rng = x_l - anchor_x_m
    sx, sy = world_to_screen(x_l, 0.0)
    return {'x': x_l, 'velocity': speed, 'range': rng, 'screen': (sx, sy)}

# ---------------- Main loop ----------------
running = True
while running:
    dt = clock.tick(60) / 1000.0
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT:
            running = False
        elif ev.type == pygame.MOUSEBUTTONDOWN:
            if ev.button == 1:
                ax, ay = ANCHOR
                if (ev.pos[0]-ax)**2+(ev.pos[1]-ay)**2 < 16000:
                    dragging = True
                    mouse_pos = ev.pos
        elif ev.type == pygame.MOUSEBUTTONUP:
            if ev.button == 1 and dragging:
                dragging = False
                SHOT_COUNTER += 1
                ax, ay = ANCHOR
                mx, my = mouse_pos
                pull_sx, pull_sy = ax - mx, ay - my
                pull_wx, pull_wy = pull_sx/PIXELS_PER_M, -pull_sy/PIXELS_PER_M
                disp = math.hypot(pull_wx, pull_wy)
                if USE_PHYSICAL_LAUNCH and disp>1e-9:
                    v0 = disp*math.sqrt(max(1e-12,SPRING_K/PROJECTILE_MASS))
                else: v0 = disp*4.0
                ux, uy = (pull_wx/disp, pull_wy/disp) if disp>1e-9 else (0,0)
                vx0, vy0 = ux*v0, uy*v0
                x0,y0 = screen_to_world(ax,ay)
                projectile = {"x":x0,"y":y0,"vx":vx0,"vy":vy0,
                              "alive":True,"shot_id":SHOT_COUNTER,
                              "first_touch":False}
                prev_state = None
        elif ev.type == pygame.MOUSEMOTION:
            mouse_pos = ev.pos

    # physics
    if projectile and projectile["alive"]:
        prev_state = {'x':projectile['x'],'y':projectile['y'],
                      'vx':projectile['vx'],'vy':projectile['vy']}
        projectile['vy'] -= GRAVITY*dt
        projectile['x'] += projectile['vx']*dt
        projectile['y'] += projectile['vy']*dt
        if projectile['y']<=0.0:
            landing = record_landing(prev_state, projectile, screen_to_world(*ANCHOR)[0])
            if not projectile["first_touch"]:
                landings.append(landing|{"shot_id":projectile["shot_id"]})
                projectile["first_touch"]=True
            projectile['y']=0.0
            projectile['vy']=-projectile['vy']*RESTITUTION
            projectile['vx']=projectile['vx']*BOUNCE_FRICTION
            if math.hypot(projectile['vx'],projectile['vy'])<REST_SPEED_THRESHOLD:
                projectile['alive']=False

    # ---------------- Draw ----------------
    screen.fill(BG)
    draw_grid(screen, meters_between_lines=1, label_every_n_meters=5, alpha=60)

    # ground
    gy = HEIGHT-GROUND_H_PX
    pygame.draw.rect(screen,(50,50,50),(0,gy,WIDTH,GROUND_H_PX))
    pygame.draw.line(screen,(200,200,200),(0,gy),(WIDTH,gy),2)

    # anchor
    ax, ay = ANCHOR
    pygame.draw.circle(screen,(220,180,60),ANCHOR,9)

    # dragging preview
    if dragging:
        mx,my=mouse_pos
        pygame.draw.line(screen,(180,180,180),ANCHOR,(mx,my),2)

    # draw projectile
    if projectile:
        sx,sy=world_to_screen(projectile['x'],projectile['y'])
        pygame.draw.circle(screen,(200,80,80),(sx,sy),int(BALL_RADIUS_M*PIXELS_PER_M))

    # landings
    for ld in landings:
        sx,sy=ld['screen']
        pygame.draw.circle(screen,(80,200,120),(sx,sy),MARKER_R)
        txt=f"{ld['range']:.2f} m  [Shot {ld['shot_id']}]"
        screen.blit(small.render(txt,True,(220,220,220)),(sx+10,sy-20))

    pygame.display.flip()

pygame.quit(); sys.exit()
