# 🎯 Slingshot Physics Simulator

A **2D physics-based projectile simulator** built with **Pygame**.  
This program models a slingshot launching projectiles under **realistic physics**, including **gravity, restitution (bounciness), friction, and optional air drag**. It also provides an interactive interface to explore trajectories, tweak physical constants, and visualize motion with a clean HUD.

---

## 🚀 Features

- **Interactive Slingshot**  
  Click and drag from the anchor point to pull back and launch projectiles.  

- **Realistic Physics**  
  - Gravity presets: 🌍 Earth, 🌕 Moon, ♂️ Mars, ♃ Jupiter, or custom.  
  - Spring-based launch force (with tunable strength).  
  - Bouncing and rolling with adjustable restitution and friction.  
  - Optional quadratic air drag for realism.  

- **Visual HUD & Controls**  
  - Live velocity, angle, flight time, max height, and impact info.  
  - Landing markers with shot IDs and ranges.  
  - Adjustable ball radius and color (with gradient option).  
  - Zoomable & pannable camera.  
  - On-screen grid with metric labels.  

- **Trajectory Preview**  
  While pulling back, the predicted flight path and landing point are displayed.

---

## 📦 Requirements

- Python **3.8+**
- [Pygame](https://www.pygame.org/)  
  ```bash
  pip install pygame
