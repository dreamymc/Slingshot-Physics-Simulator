🎯 Slingshot Physics Simulator

A 2D physics-based projectile simulator built with Pygame.
This program models a slingshot launching projectiles under realistic physics, including gravity, restitution (bounciness), friction, and optional air drag. It also provides an interactive interface to explore trajectories, tweak physical constants, and visualize motion with a clean HUD.

🚀 Features

Interactive Slingshot
Click and drag from the anchor point to pull back and launch projectiles.

Realistic Physics

Gravity presets: 🌍 Earth, 🌕 Moon, ♂️ Mars, ♃ Jupiter, or custom.

Spring-based launch force (with tunable strength).

Bouncing and rolling with adjustable restitution and friction.

Optional quadratic air drag for realism.

Visual HUD & Controls

Live velocity, angle, flight time, max height, and impact info.

Landing markers with shot IDs and ranges.

Adjustable ball radius and color (with gradient option).

Zoomable & pannable camera.

On-screen grid with metric labels.

Trajectory Preview
While pulling back, the predicted flight path and landing point are displayed.

📦 Requirements

Python 3.8+

Pygame
 (pip install pygame)

▶️ How to Run
python slingshot.py

🎮 Controls
Mouse

Left Click + Drag — Pull slingshot and launch.

Right Click — Move the slingshot anchor.

Scroll Wheel — Zoom in/out (focuses on mouse position).

Drag outside anchor — Pan camera.

Keyboard

Esc — Close modals or exit help.

[[] / []] — Decrease/increase restitution (bounciness).

C — Clear landing markers.

⚙️ Adjustable Settings

Ball Radius: via + / – buttons or text input.

Ball Color: preset picker with gradient option.

Gravity: choose preset or enter a custom value.

Restitution: fine-tune bounce realism.

Air Drag: toggle in code (ENABLE_AIR_DRAG).

📊 Physics Model

Spring Launch:

𝑣
0
=
Δ
𝑥
⋅
𝑘
eff
𝑚
v
0
	​

=Δx⋅
m
k
eff
	​

	​

	​


Forces:

Gravity: 
𝐹
=
𝑚
𝑔
F=mg

Drag: 
𝐹
𝑑
=
1
2
𝜌
𝐶
𝑑
𝐴
𝑣
2
F
d
	​

=
2
1
	​

ρC
d
	​

Av
2
 (if enabled)

Bounce: velocity reflection scaled by restitution & friction

Rest Threshold: motion stops if speed < 0.12 m/s.

🖼️ Preview

When you pull back the slingshot:

Blue dots = predicted path

Yellow marker = predicted landing point

Green markers = past landings with distance labels

📌 Notes

Designed for educational & visualization purposes.

Physics constants are tunable for experimenting with different worlds.

Runs smoothly at 60 FPS with a dynamic integrator.