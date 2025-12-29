# Why Hyperbolic Space?

Understanding the mathematical and practical reasons behind HyperView's use of hyperbolic geometry.

## The Problem: Representation Collapse

Modern AI systems rely on embedding models that map complex data (images, text, audio) into high-dimensional Euclidean space. These embeddings are then visualized in 2D for human understanding.

**But there's a fundamental problem:**

When you force hierarchical or long-tail data into flat Euclidean space, you **run out of room**.

### The Mathematics

In Euclidean space, volume grows **polynomially** with radius:

$$V_{\text{Euclidean}} \propto r^d$$

Where:
- $r$ = radius
- $d$ = dimensions

This means as you move away from the origin, space grows slowly. There's limited room at the boundaries.

### The Consequence

To fit the majority class, rare and minority classes get **crushed together**:

- **Majority Class** (9,000 samples): Dominates the center
- **Minority Class** (900 samples): Compressed toward edges  
- **Rare Subgroup** (100 samples): Crushed into minority, indistinguishable

We call this **Representation Collapse**.

## The Solution: Hyperbolic Geometry

Hyperbolic space (specifically, the Poincaré disk model) has **exponential volume growth**:

$$V_{\text{Hyperbolic}} \propto e^r$$

This gives you "infinite" room at the boundaries!

### Visual Intuition

Imagine trying to fit a hierarchical tree structure:

**In Euclidean Space:**
```
        [Root]
       /  |  \
     [A] [B] [C]
    / \  |   / \
  ... (gets cramped)
```
Branches at the bottom overlap and merge - you can't tell them apart.

**In Hyperbolic Space:**
```
        [Root]
       /  |  \
     [A] [B] [C]
    / \  |   / \
  ... (exponential space available)
```
Each branch has exponentially more room as it goes deeper. No overlap!

## Real-World Example: Medical Imaging

Consider training an AI to diagnose chest X-rays:

**Dataset:**
- **9,000 Healthy** (Majority - 90%)
- **900 Common Pneumonia** (Minority - 9%)
- **100 Early-Stage Tuberculosis** (Rare - 1%)

### In Euclidean Space

1. The model learns strong features for "Healthy" (dominates center)
2. "Common Pneumonia" gets pushed to edges
3. "Early-Stage TB" gets crushed into the Pneumonia cluster
4. **Result**: The AI cannot distinguish TB from Pneumonia
5. **Outcome**: Misdiagnosis and delayed treatment

### In Hyperbolic Space (HyperView)

1. "Healthy" still dominates center (appropriate!)
2. "Common Pneumonia" has space at intermediate radius
3. "Early-Stage TB" pushed to disk edge where space expands
4. **Result**: TB cases form a distinct, visible cluster
5. **Outcome**: Curator sees the cluster, ensures model learns it, patients are saved

## The Poincaré Disk Model

HyperView uses the **Poincaré disk model** to visualize hyperbolic space.

### Key Properties

1. **Unit Circle Boundary**: All points lie within a circle of radius 1
2. **Hyperbolic Distance**: The distance metric is non-Euclidean
3. **Geodesics**: Straight lines in hyperbolic space appear as arcs in the disk
4. **Exponential Expansion**: Space grows exponentially as you approach the boundary

### The Distance Formula

The hyperbolic distance between two points $u$ and $v$ in the Poincaré disk is:

$$d(u, v) = \text{arccosh}\left(1 + 2 \frac{\|u - v\|^2}{(1 - \|u\|^2)(1 - \|v\|^2)}\right)$$

**Key insight:** As $\|u\|$ or $\|v\|$ approaches 1 (the boundary), the denominator approaches 0, making the distance approach infinity. This is the "infinite space at the edge" property!

### Navigation with Möbius Transformations

When you drag to pan in the Poincaré disk, HyperView uses **Möbius transformations**:

$$\text{Möbius}(z, a) = \frac{z + a}{1 + \bar{a}z}$$

Where:
- $z$ = point in the disk
- $a$ = translation offset
- $\bar{a}$ = complex conjugate of $a$

This preserves hyperbolic distances and makes navigation feel natural!

## When to Use Hyperbolic vs Euclidean

### Use Hyperbolic When:

✅ **Hierarchical data**: Taxonomies, ontologies, organizational structures

✅ **Long-tail distributions**: Many majority samples, few rare samples

✅ **Imbalanced datasets**: Medical diagnoses, rare events, edge cases

✅ **Semantic hierarchies**: WordNet, knowledge graphs, category trees

✅ **Finding rare subgroups**: Fraud detection, anomaly detection

### Use Euclidean When:

✅ **Balanced datasets**: Equal representation across classes

✅ **Non-hierarchical data**: Random distributions, no clear structure

✅ **Standard clustering**: When you just need basic grouping

✅ **Familiar analysis**: When stakeholders are used to standard plots

### Use BOTH (HyperView's Approach!):

The best practice is to **compare both views**:

1. Start with **Euclidean** for initial exploration
2. Switch to **Hyperbolic** to find rare cases
3. Toggle between views to understand collapse
4. Make informed decisions about dataset balance

## Practical Benefits

### 1. Fairness in AI

By preventing representation collapse, you ensure:
- Minority groups are learned properly
- Rare cases are not ignored
- Models generalize better
- Less bias in predictions

### 2. Dataset Curation

Hyperbolic visualization helps you:
- Identify underrepresented classes
- Find duplicate or near-duplicate samples
- Spot labeling errors in rare classes
- Build balanced training sets

### 3. Quality Control

Easily spot:
- Outliers in rare classes (may be errors)
- Subgroups within minority classes
- Hierarchical structure in data
- Edge cases that need attention

### 4. Interpretability

Help stakeholders understand:
- Why the model struggles with rare cases
- What the data distribution really looks like
- Where to collect more data
- How to balance the dataset

## Scientific Foundation

HyperView is built on solid mathematical and scientific foundations:

### Key Papers

1. **[Poincaré Embeddings for Learning Hierarchical Representations](https://arxiv.org/abs/1705.08039)**  
   Nickel & Kiela, NeurIPS 2017
   - Original paper on hyperbolic embeddings
   - Showed benefits for hierarchical data

2. **[Hyperbolic Neural Networks](https://arxiv.org/abs/1805.09112)**  
   Ganea et al., NeurIPS 2018
   - Demonstrated how to train neural networks in hyperbolic space
   - Theoretical foundations for hyperbolic deep learning

3. **[Hyperbolic Image Embeddings](https://arxiv.org/abs/1904.02239)**  
   Khrulkov et al., CVPR 2020
   - Applied hyperbolic embeddings to computer vision
   - Showed improvements on hierarchical image datasets

### Mathematical Foundations

- **Riemannian Geometry**: Hyperbolic space is a Riemannian manifold with constant negative curvature
- **Geoopt**: Library for optimization on manifolds (used in HyperView)
- **UMAP**: Supports hyperbolic output spaces for dimensionality reduction

## Interactive Demo

Want to experience the difference yourself?

Try our [Interactive Poincaré Disk Demo](../demo.md) to:
- See representation collapse in action
- Toggle between Euclidean and Hyperbolic views
- Drag to explore "infinite" space
- Understand why it matters for your data

## Summary

**The Core Insight:**

> Hierarchical and long-tail data needs hyperbolic space because exponential volume growth prevents representation collapse and keeps rare classes distinct.

**The HyperView Advantage:**

> By providing both Euclidean and Hyperbolic views side-by-side, HyperView lets you see exactly where and how your data collapses - and do something about it.

## Next Steps

- [Architecture Overview](architecture.md) - How HyperView implements hyperbolic visualization
- [Interactive Demo](../demo.md) - Try it yourself
- [Visualization Guide](../guide/visualization.md) - Learn to use both view types effectively
