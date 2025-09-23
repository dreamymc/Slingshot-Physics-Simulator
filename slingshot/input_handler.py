# lightweight input helpers (keeps app.py tidy)
import pygame
from .camera import pan_by_dx_pixels, set_ppm, screen_to_world

class InputState:
    def __init__(self):
        self.dragging = False
        self.panning = False
        self.pan_start_mouse = (0,0)
        self.pan_start_cam_x = 0.0
        self.mouse_pos = (0,0)

def handle_wheel(ev):
    mx, my = pygame.mouse.get_pos()
    factor = 1.15 ** ev.y
    new_ppm = None
    # user of this function should call set_ppm(new_ppm, (mx,my))
    return (mx, my, factor)
