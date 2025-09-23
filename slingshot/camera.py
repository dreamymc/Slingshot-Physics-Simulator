# camera: world <-> screen conversions and pan/zoom control
from .config import WIDTH, HEIGHT, GROUND_H_PX, DEFAULT_PPM, PPM_MIN, PPM_MAX

state = {
    "ppm": DEFAULT_PPM,
    "cam_x_m": 0.0,
    "cam_y_m": 0.0,  # keep ground locked (0.0)
}

def world_to_screen(wx, wy):
    sx = int((wx - state["cam_x_m"]) * state["ppm"])
    sy = int(HEIGHT - GROUND_H_PX - (wy - state["cam_y_m"]) * state["ppm"])
    return sx, sy

def screen_to_world(sx, sy):
    wx = (sx / state["ppm"]) + state["cam_x_m"]
    wy = ((HEIGHT - GROUND_H_PX - sy) / state["ppm"]) + state["cam_y_m"]
    return wx, wy

def set_ppm(new_ppm, anchor_screen_xy=None):
    new_ppm = max(PPM_MIN, min(PPM_MAX, new_ppm))
    if anchor_screen_xy is not None:
        sx, sy = anchor_screen_xy
        wx_before, wy_before = screen_to_world(sx, sy)
        state["ppm"] = new_ppm
        state["cam_x_m"] = wx_before - (sx / state["ppm"])
        # cam_y_m unchanged (ground locked)
    else:
        state["ppm"] = new_ppm

def pan_by_dx_pixels(dx_px):
    state["cam_x_m"] -= dx_px / state["ppm"]
