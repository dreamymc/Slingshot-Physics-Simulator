# projectile integration and utilities
import math
from .config import GRAVITY

def integrate(projectile, dt, enable_air_drag=False, drag_coeff=0.1):
    vx = projectile["vx"]; vy = projectile["vy"]
    if enable_air_drag:
        axd = -drag_coeff * vx
        ayd = -drag_coeff * vy
    else:
        axd = 0.0; ayd = 0.0
    projectile["vx"] += axd * dt
    projectile["vy"] += (-GRAVITY + ayd) * dt
    projectile["x"] += projectile["vx"] * dt
    projectile["y"] += projectile["vy"] * dt
    if projectile["y"] > projectile.get("max_height", -1e9):
        projectile["max_height"] = projectile["y"]

def simulate_bounces_from_launch(x0, y0, vx0, vy0, restitution, friction, rest_speed, max_steps=20000, dt=0.01):
    x = x0; y = y0; vx = vx0; vy = vy0
    bounces = 0; steps = 0
    while steps < max_steps:
        steps += 1
        vy = vy - GRAVITY * dt
        x += vx * dt
        y += vy * dt
        if y <= 0.0:
            y = 0.0
            if abs(vy) > 1e-6:
                bounces += 1
            vy = -vy * restitution
            vx = vx * friction
            if math.hypot(vx, vy) < rest_speed:
                break
    return x, bounces

def record_landing_exact(prev, curr, anchor_x_m):
    # linear interpolation in time to find y==0 crossing; returns x_l, speed, range
    y1 = prev["y"]; y2 = curr["y"]
    if (y2 - y1) != 0:
        frac = (0.0 - y1) / (y2 - y1)
    else:
        frac = 0.0
    frac = max(0.0, min(1.0, frac))
    x_l = prev["x"] + (curr["x"] - prev["x"]) * frac
    vx_l = prev["vx"] + (curr["vx"] - prev["vx"]) * frac
    vy_l = prev["vy"] + (curr["vy"] - prev["vy"]) * frac
    speed = math.hypot(vx_l, vy_l)
    rng = x_l - anchor_x_m
    return x_l, speed, rng
