# main app, wires modules. Run with: python -m slingshot
import math
import time
import pygame
from .config import *
from .camera import world_to_screen, screen_to_world, state as cam_state, set_ppm, pan_by_dx_pixels
from .physics import integrate, record_landing_exact, simulate_bounces_from_launch
from .input_handler import InputState, handle_wheel
from .ui import draw_text, draw_grid

# state
projectile = None
prev_state = None
landings = []     # stored in world coords: {'x':..., 'y':..., 'velocity':..., 'flight_time':..., 'range':..., 'shot_id':..., 'max_height':...}
SHOT_COUNTER = 0

# interactions
input_state = InputState()
mouse_pos = (0,0)
last_pull = None   # (pwx, pwy) in meters (world)

# fonts
pygame.font.init()
font = pygame.font.SysFont(FONT_NAME, 16)
small = pygame.font.SysFont(FONT_NAME, 14)
big = pygame.font.SysFont(FONT_NAME, 18, bold=True)

# anchor (world)
INIT_ANCHOR_PX = (150, HEIGHT - GROUND_H_PX - 20)
ANCHOR_W = screen_to_world(*INIT_ANCHOR_PX)
if ANCHOR_W[1] < 0.0:
    ANCHOR_W = (ANCHOR_W[0], 0.0)

def main():
    global projectile, prev_state, landings, SHOT_COUNTER, input_state, mouse_pos, last_pull, ANCHOR_W
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Slingshot — modular")
    clock = pygame.time.Clock()

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False

            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                if ev.key == pygame.K_c:
                    landings.clear()
                if ev.key == pygame.K_LEFTBRACKET or ev.unicode == "[":
                    globals()['RESTITUTION'] = max(0.0, RESTITUTION - 0.05)
                if ev.key == pygame.K_RIGHTBRACKET or ev.unicode == "]":
                    globals()['RESTITUTION'] = min(1.0, RESTITUTION + 0.05)

            elif ev.type == pygame.MOUSEBUTTONDOWN:
                mx, my = ev.pos
                ax_s, ay_s = world_to_screen(*ANCHOR_W)
                # left: pull if near anchor; else pan
                if ev.button == 1:
                    if (mx - ax_s)**2 + (my - ay_s)**2 < 14000:
                        input_state.dragging = True
                        input_state.mouse_pos = ev.pos
                    else:
                        input_state.panning = True
                        input_state.pan_start_mouse = ev.pos
                        input_state.pan_start_cam_x = cam_state["cam_x_m"]
                # right: move anchor (clamp y >= 0)
                elif ev.button == 3:
                    if my < HEIGHT - GROUND_H_PX - 6:
                        new_anchor = screen_to_world(mx, my)
                        if new_anchor[1] < 0.0:
                            new_anchor = (new_anchor[0], 0.0)
                        ANCHOR_W = new_anchor

            elif ev.type == pygame.MOUSEBUTTONUP:
                if ev.button == 1:
                    # finish panning
                    if input_state.panning:
                        input_state.panning = False
                    # finish pull -> shoot
                    if input_state.dragging:
                        input_state.dragging = False
                        SHOT_COUNTER += 1
                        shot_id = SHOT_COUNTER
                        ax_s, ay_s = world_to_screen(*ANCHOR_W)
                        mx, my = input_state.mouse_pos
                        pull_sx = ax_s - mx
                        pull_sy = ay_s - my
                        pull_wx = pull_sx / cam_state["ppm"]
                        pull_wy = -pull_sy / cam_state["ppm"]
                        displacement_m = math.hypot(pull_wx, pull_wy)
                        last_pull = (pull_wx, pull_wy)
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
                        x0, y0 = ANCHOR_W
                        projectile = {"x": x0, "y": y0, "vx": vx0, "vy": vy0,
                                      "alive": True, "shot_id": shot_id, "start_time": time.time(),
                                      "first_touch_recorded": False, "max_height": y0, "bounces": 0}
                        prev_state = None

            elif ev.type == pygame.MOUSEMOTION:
                mouse_pos = ev.pos
                if input_state.dragging:
                    input_state.mouse_pos = ev.pos
                if input_state.panning:
                    mx, my = ev.pos
                    dx_px = mx - input_state.pan_start_mouse[0]
                    cam_state["cam_x_m"] = input_state.pan_start_cam_x - dx_px / cam_state["ppm"]

            elif ev.type == pygame.MOUSEWHEEL:
                mx, my, factor = handle_wheel(ev)
                new_ppm = cam_state["ppm"] * factor
                set_ppm(new_ppm, anchor_screen_xy=(mx, my))

        # physics update
        if projectile and projectile.get("alive"):
            prev_state = {"x": projectile["x"], "y": projectile["y"], "vx": projectile["vx"], "vy": projectile["vy"]}
            integrate(projectile, dt, enable_air_drag=ENABLE_AIR_DRAG, drag_coeff=DRAG_COEFF)
            if projectile["y"] <= 0.0:
                if prev_state is not None:
                    x_l, speed, rng = record_landing_exact(prev_state, projectile, ANCHOR_W[0])
                else:
                    x_l = projectile["x"]; speed = math.hypot(projectile["vx"], projectile["vy"]); rng = x_l - ANCHOR_W[0]
                if not projectile.get("first_touch_recorded", False):
                    flight_time = time.time() - projectile.get("start_time", time.time())
                    first_ld = {"x": x_l, "y": 0.0, "velocity": speed, "flight_time": flight_time,
                                "range": rng, "shot_id": projectile.get("shot_id"), "max_height": projectile.get("max_height", 0.0)}
                    landings.append(first_ld)
                    projectile["first_touch_recorded"] = True
                projectile["y"] = 0.0
                projectile["vy"] = -projectile["vy"] * RESTITUTION
                projectile["vx"] = projectile["vx"] * BOUNCE_FRICTION
                projectile["bounces"] = projectile.get("bounces", 0) + 1
                if math.hypot(projectile["vx"], projectile["vy"]) < REST_SPEED_THRESHOLD:
                    projectile["alive"] = False
                    prev_state = None

        # draw
        screen.fill(BG)
        draw_grid(screen, world_to_screen, cam_state["ppm"], cam_state["cam_x_m"], meters_between_lines=1, label_every=5, alpha=60)

        ground_y_px = HEIGHT - GROUND_H_PX
        pygame.draw.line(screen, (180,180,180), (0, ground_y_px), (WIDTH, ground_y_px), 3)
        pygame.draw.rect(screen, (50,50,50), (0, ground_y_px, WIDTH, GROUND_H_PX))

        # anchor
        ax_s, ay_s = world_to_screen(*ANCHOR_W)
        pygame.draw.circle(screen, (200,160,60), (ax_s, ay_s), 9)
        pygame.draw.line(screen, (140,140,220), (ax_s, ay_s), (ax_s, ground_y_px), 2)
        pygame.draw.polygon(screen, (140,140,220), [(ax_s-6, ground_y_px+6), (ax_s+6, ground_y_px+6), (ax_s, ground_y_px-2)])
        draw_text(screen, ax_s+12, ay_s-12, "Anchor height:", small)
        draw_text(screen, ax_s+12, ay_s+6, f"{ANCHOR_W[1]:.2f} m", big)

        # last pull box (fixed left side)
        if last_pull is not None:
            pwx, pwy = last_pull
            disp = math.hypot(pwx, pwy)
            if USE_PHYSICAL_LAUNCH and disp > 1e-9:
                v0 = disp * math.sqrt(max(1e-12, SPRING_K / PROJECTILE_MASS))
            else:
                v0 = disp * 4.0
            txt1 = f"Last pull: {disp:.3f} m"
            txt2 = f"Init speed: {v0:.2f} m/s"
            txt3 = f"Vec: ({pwx:.2f},{pwy:.2f}) m"
            surfaces = [small.render(txt1, True, (220,220,220)), small.render(txt2, True, (220,220,220)), small.render(txt3, True, (220,220,220))]
            box_w = max(s.get_width() for s in surfaces) + 12
            box_h = sum(s.get_height() for s in surfaces) + 12
            # FIXED LEFT: change these two lines to reposition
            box_x = 8
            box_y = 80
            # clamp to screen
            if box_y + box_h > HEIGHT - 6:
                box_y = HEIGHT - 6 - box_h
            pygame.draw.rect(screen, (230,230,230), (box_x, box_y, box_w, box_h), border_radius=6)
            pygame.draw.rect(screen, (40,40,40), (box_x+1, box_y+1, box_w-2, box_h-2), border_radius=6)
            oy = box_y + 6
            for s in surfaces:
                screen.blit(s, (box_x+6, oy))
                oy += s.get_height()

        # projectile
        if projectile and projectile.get("alive"):
            sx, sy = world_to_screen(projectile["x"], projectile["y"])
            r_px = int(BALL_RADIUS_M * cam_state["ppm"])
            if r_px < 2: r_px = 2
            pygame.draw.circle(screen, (200,80,80), (sx, sy), r_px)

        # landings
        mx, my = mouse_pos
        hover_index = None
        for i, ld in enumerate(landings):
            sx, sy = world_to_screen(ld["x"], ld.get("y", 0.0))
            pygame.draw.circle(screen, (80,200,120), (sx, sy), MARKER_R)
            pygame.draw.line(screen, (120,220,150), (sx, sy), (sx, sy-36), 2)
            label = f"{ld['range']:.2f} m  [{ld['shot_id']}]"
            txt = small.render(label, True, (200,200,200))
            tx = sx + 12
            ty = sy - 30 - (i % 3) * 16
            if tx + txt.get_width() > WIDTH - 8:
                tx = sx - 12 - txt.get_width()
            screen.blit(txt, (tx, ty))
            if (mx - sx)**2 + (my - sy)**2 <= (MARKER_R+8)**2:
                hover_index = i

        if hover_index is not None:
            ld = landings[hover_index]
            sx, sy = world_to_screen(ld["x"], ld.get("y", 0.0))
            txts = [
                f"Shot: {ld['shot_id']}",
                f"Range: {ld['range']:.2f} m",
                f"Displacement: {ld['x']:.2f} m",
                f"Velocity: {ld.get('velocity', 0.0):.2f} m/s",
                f"Flight time: {ld.get('flight_time', 0.0):.2f} s",
                f"Max height: {ld.get('max_height', 0.0):.2f} m",
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

        draw_text(screen, WIDTH - 220, HEIGHT - 30, f"Zoom: {cam_state['ppm']:.1f} px/m", small)
        pygame.display.flip()

    pygame.quit()

if __name__ == "__main__":
    main()
