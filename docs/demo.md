# Interactive Poincaré Disk Demo

Experience the difference between Euclidean and Hyperbolic space firsthand!

<div style="text-align: center; margin: 2rem 0;">
  <iframe src="demo.html" width="100%" height="800px" style="border: 1px solid #ddd; border-radius: 8px;"></iframe>
</div>

## What Am I Looking At?

This interactive demo visualizes three groups of data points:

- **Gray (Majority)**: 300 points clustered at the center
- **Blue (Minority)**: 50 points at intermediate distance
- **Red (Rare)**: 10 points that get crushed or separated

## How to Use

### 1. Drag to Explore (Hyperbolic Mode)

Click and drag anywhere on the disk to pan around. Notice how:

- **Points at the edge** expand as you bring them toward the center
- The space feels "infinite" at the boundaries
- **Red rare cases** become clearly visible when centered

### 2. Toggle Between Modes

Click the **"Simulate Euclidean Collapse"** button to see what happens in flat space:

- **Red and Blue points** collapse together
- They become indistinguishable
- This is **representation collapse**!

### 3. Compare Side-by-Side

Toggle back and forth to understand:

- In **Euclidean**: Limited space crushes rare cases
- In **Hyperbolic**: Exponential space keeps them distinct

## The Medical Diagnosis Analogy

Imagine these three groups represent chest X-rays:

- **Gray = Healthy patients** (9,000 samples - 90%)
- **Blue = Common Pneumonia** (900 samples - 9%)
- **Red = Early-Stage Tuberculosis** (100 samples - 1%)

### In Euclidean Space

When you click "Simulate Euclidean Collapse":

- The TB cases (red) overlap with Pneumonia (blue)
- An AI model can't distinguish them
- **Result**: Misdiagnosis

### In Hyperbolic Space

In the default Hyperbolic mode:

- TB cases are pushed to the edge where space expands
- They remain distinct and visible
- An AI model can learn to recognize them
- **Result**: Correct diagnosis and treatment

## The Mathematics

### Volume Growth

The key difference is how space grows:

**Euclidean (Flat):**
$$V \propto r^2$$

Volume grows quadratically. Limited room at edges.

**Hyperbolic (Curved):**
$$V \propto e^r$$

Volume grows exponentially. "Infinite" room at edges!

### Poincaré Distance

Points in the hyperbolic view use this distance metric:

$$d(u, v) = \text{arccosh}\left(1 + 2 \frac{\|u - v\|^2}{(1 - \|u\|^2)(1 - \|v\|^2)}\right)$$

As points approach the boundary ($\|u\| \to 1$), distances approach infinity!

### Möbius Transformations

When you drag to pan, the demo uses Möbius transformations:

$$\text{Möbius}(z, a) = \frac{z + a}{1 + \bar{a}z}$$

This preserves hyperbolic distances and makes navigation feel natural.

## Try This Exercise

1. **Start in Hyperbolic mode** (default)
2. **Drag the red points to the center**
   - Notice how they expand and separate
   - You can clearly see all 10 red points
3. **Click "Simulate Euclidean Collapse"**
   - The red points crush together
   - They overlap with blue points
   - Can you even count 10 red points anymore?
4. **Switch back to Hyperbolic**
   - The red points separate again
   - Each one is distinct

This is exactly what happens to your real data!

## Real-World Applications

This phenomenon affects:

### 1. Medical Imaging
- Rare diseases get crushed
- Diagnostic errors increase
- Patients suffer

### 2. Fraud Detection
- Unusual fraud patterns lost
- False negatives increase
- Financial losses

### 3. Scientific Discovery
- Rare species misclassified
- New phenomena missed
- Knowledge gaps persist

### 4. Content Moderation
- Rare harmful content overlooked
- Edge cases slip through
- Platform safety compromised

## About This Demo

**Implementation:**
- Pure JavaScript with HTML5 Canvas
- ~500 lines of code
- Complex number arithmetic for Möbius transformations
- Smooth animation between modes

**Source:**
The full source code is available in the [HyperView repository](https://github.com/HackerRoomAI/HyperView/blob/main/docs/index.html).

## Next Steps

Now that you understand the concept:

1. **[Install HyperView](getting-started/installation.md)** - Try it with real data
2. **[Quick Start Guide](getting-started/quickstart.md)** - Your first dataset
3. **[Why Hyperbolic?](concepts/hyperbolic.md)** - Deep dive into the theory
4. **[Visualization Guide](guide/visualization.md)** - Learn to use both views

## Questions?

**Q: Is hyperbolic always better?**

A: No! For balanced datasets with no hierarchy, Euclidean works fine. Hyperbolic excels with:
- Hierarchical data
- Long-tail distributions
- Imbalanced classes

**Q: Can I use this for text or audio?**

A: Yes! HyperView works with any embedding model. Just compute embeddings for your data type.

**Q: How large can my dataset be?**

A: HyperView handles 100,000+ samples. The web interface stays smooth up to 10,000 visible points.

**Q: Is this production-ready?**

A: HyperView is in active development (v0.1). It's great for exploration and research. For production, consider additional testing and validation.
