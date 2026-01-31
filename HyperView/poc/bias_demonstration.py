# -*- coding: utf-8 -*-
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import geomstats.backend as gs  # type: ignore
from geomstats.geometry.poincare_ball import PoincareBall

def generate_data(n_samples, center_r, center_theta, spread, label):
    """Generates points in polar coordinates, then converts to Cartesian."""
    # Random noise in polar coordinates
    r_noise = np.random.normal(0, spread, n_samples)
    theta_noise = np.random.normal(0, spread, n_samples)
    
    r = np.clip(center_r + r_noise, 0, 0.99) # Keep within unit disk
    theta = center_theta + theta_noise
    
    # Convert to Cartesian for plotting
    x = r * np.cos(theta)
    y = r * np.sin(theta)
    
    return np.column_stack([x, y]), label

def main():
    print("Generating synthetic hierarchical data...")
    
    # 1. Define the Hierarchy
    # Majority: Center of the space
    # Minority: Periphery
    # Rare: Deep Periphery (Sub-group of Minority)
    
    # Parameters
    majority_n = 500
    minority_n = 50
    rare_n = 10
    
    # Angle for the minority group
    theta_minority = np.pi / 4  # 45 degrees
    
    # --- Euclidean Simulation ---
    # In Euclidean space, we simulate "crowding" by placing them close together
    # because the space doesn't expand.
    
    # Majority at (0,0)
    maj_euc, _ = generate_data(majority_n, 0.0, 0.0, 0.1, "Majority")
    
    # Minority at distance 0.5
    min_euc, _ = generate_data(minority_n, 0.5, theta_minority, 0.08, "Minority")

    # Rare at distance 0.52 (Buried inside the Minority cluster in Euclidean terms)
    rare_euc, _ = generate_data(rare_n, 0.52, theta_minority, 0.04, "Rare")
    
    
    # --- Hyperbolic Simulation ---
    # In Hyperbolic space, we map these same "conceptual" positions to the Poincaré disk.
    # The "Rare" group is pushed further out to the edge (r=0.95).
    # The "Minority" group is at r=0.8.
    # The "Majority" is at r=0.0.
    
    # Majority at center
    maj_hyp, _ = generate_data(majority_n, 0.0, 0.0, 0.1, "Majority")
    
    # Minority at r=0.8
    min_hyp, _ = generate_data(minority_n, 0.8, theta_minority, 0.05, "Minority")
    
    # Rare at r=0.95 (Deep in the hyperbolic tail)
    rare_hyp, _ = generate_data(rare_n, 0.95, theta_minority, 0.01, "Rare")
    
    
    # --- Visualization ---
    fig, axes = plt.subplots(1, 2, figsize=(16, 8))
    
    # Plot 1: Euclidean View
    ax = axes[0]
    ax.set_title("Euclidean Space (Standard AI)\n'Representation Collapse'", fontsize=14, fontweight='bold')
    
    # Draw Unit Circle for reference
    circle = mpatches.Circle((0, 0), 1, color='black', fill=False, linestyle='--', alpha=0.3)
    ax.add_artist(circle)
    
    ax.scatter(maj_euc[:, 0], maj_euc[:, 1], c='gray', alpha=0.3, label='Majority (Head)', s=20)
    ax.scatter(min_euc[:, 0], min_euc[:, 1], c='blue', alpha=0.6, label='Minority (Tail)', s=40)
    ax.scatter(rare_euc[:, 0], rare_euc[:, 1], c='red', alpha=0.9, label='Rare Subgroup (Long Tail)', s=40)
    
    # Annotate the "Crush"
    ax.annotate('Indistinguishable\nCluster', xy=(0.55, 0.55), xytext=(0.2, 0.7),
                arrowprops=dict(facecolor='black', shrink=0.05), fontsize=12)
    
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.set_aspect('equal')
    ax.legend(loc='lower right')
    ax.grid(True, alpha=0.2)
    
    
    # Plot 2: Hyperbolic View
    ax = axes[1]
    ax.set_title("Hyperbolic Space (HyperView)\n'Hierarchical Expansion'", fontsize=14, fontweight='bold')
    
    # Draw Poincaré Disk Boundary
    circle = mpatches.Circle((0, 0), 1, color='black', fill=False, linewidth=2)
    ax.add_artist(circle)
    
    ax.scatter(maj_hyp[:, 0], maj_hyp[:, 1], c='gray', alpha=0.3, label='Majority', s=20)
    ax.scatter(min_hyp[:, 0], min_hyp[:, 1], c='blue', alpha=0.6, label='Minority', s=40)
    ax.scatter(rare_hyp[:, 0], rare_hyp[:, 1], c='red', alpha=0.9, label='Rare Subgroup', s=40)
    
    # Calculate Geodesic Distance (Visual representation)
    # We use geomstats to calculate the actual hyperbolic distance between the centers
    manifold = PoincareBall(2)
    p_min = gs.array([0.8 * np.cos(theta_minority), 0.8 * np.sin(theta_minority)])
    p_rare = gs.array([0.95 * np.cos(theta_minority), 0.95 * np.sin(theta_minority)])
    dist = manifold.metric.dist(p_min, p_rare)
    
    # Annotate the Expansion
    ax.annotate(f'Hyperbolic Dist: {dist:.2f}\n(Distinct & Separable)', 
                xy=(0.85, 0.85), xytext=(0.2, 0.8),
                arrowprops=dict(facecolor='black', shrink=0.05), fontsize=12)
    
    ax.set_xlim(-1.1, 1.1)
    ax.set_ylim(-1.1, 1.1)
    ax.set_aspect('equal')
    ax.legend(loc='lower right')
    ax.axis('off') # Hide grid for cleaner Poincaré look
    
    plt.tight_layout()
    output_path = 'assets/bias_collapse.png'
    plt.savefig(output_path, dpi=300)
    print(f"Visualization saved to {output_path}")

if __name__ == "__main__":
    main()
