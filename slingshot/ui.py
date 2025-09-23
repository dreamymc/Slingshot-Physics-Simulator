# UI drawing helpers
import pygame
from .config import WIDTH, HEIGHT, GROUND_H_PX, MARKER_R, FONT_NAME

def draw_text(screen, x, y, s, font, color=(230,230,230)):
    screen.blit(font.render(s, True, color), (x, y))

def draw_grid(screen, world_to_screen, ppm, cam_x_m, meters_between_lines=1, label_every=5, alpha=60):
    small = pygame.font.SysFont(FONT_NAME, 14)
    grid_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    col = (80,80,80, alpha)

    world_x_left = cam_x_m
    world_x_right = cam_x_m + WIDTH / ppm
    world_y_bottom = 0.0
    world_y_top = world_y_bottom + (HEIGHT - GROUND_H_PX) / ppm

    # vertical lines
    x = int(world_x_left // meters_between_lines * meters_between_lines)
    x = int((world_x_left // meters_between_lines) * meters_between_lines)
    # use a simple loop
    curr = (int(world_x_left / meters_between_lines) * meters_between_lines)
    while curr <= world_x_right + 1e-6:
        sx, _ = world_to_screen(curr, 0)
        pygame.draw.line(grid_surf, col, (sx, 0), (sx, HEIGHT - GROUND_H_PX), 1)
        if abs(curr % label_every) < 1e-6:
            lbl = small.render(f"{curr:.0f} m", True, (180,180,180))
            grid_surf.blit(lbl, (sx+2, HEIGHT - GROUND_H_PX - 18))
        curr += meters_between_lines

    # horizontal lines from ground upward
    y = 0.0
    while y <= world_y_top + 1e-6:
        _, sy = world_to_screen(0, y)
        pygame.draw.line(grid_surf, col, (0, sy), (WIDTH, sy), 1)
        if abs(y % label_every) < 1e-6 and y > 0:
            lbl = small.render(f"{y:.0f} m", True, (180,180,180))
            grid_surf.blit(lbl, (4, sy-14))
        y += meters_between_lines

    screen.blit(grid_surf, (0,0))
