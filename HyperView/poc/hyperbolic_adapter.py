import torch
import torch.nn as nn
import geoopt

class HyperbolicAdapter(nn.Module):
    """
    A lightweight adapter that maps Euclidean embeddings (e.g., from CLIP/ResNet)
    into the Poincaré ball.
    
    This solves the "Representation Collapse" by projecting crowded Euclidean
    vectors into a space with exponentially growing volume.
    """
    def __init__(self, input_dim=512, output_dim=128, c=1.0):
        super().__init__()
        self.c = c  # Curvature of the manifold
        self.manifold = geoopt.PoincareBall(c=self.c)
        
        # 1. Linear Layer (Euclidean transformation)
        # We first compress/transform the features in Euclidean space
        self.encoder = nn.Linear(input_dim, output_dim)
        
        # 2. Mobius Linear (Hyperbolic transformation - Optional but powerful)
        # For a simple adapter, we can just project the output of the linear layer.
        # But a true hyperbolic layer operates on the manifold.
        # self.hyp_layer = geoopt.MobiusLinear(output_dim, output_dim, c=self.c)

    def forward(self, x):
        """
        Args:
            x: Euclidean input tensor (Batch, Input_Dim)
        Returns:
            x_hyp: Hyperbolic output tensor (Batch, Output_Dim) on the Poincaré ball
        """
        # Step 1: Standard Euclidean processing
        x_euc = self.encoder(x)
        
        # Step 2: Exponential Map (The "Bridge")
        # This projects the Euclidean vector onto the Hyperbolic manifold.
        # Ideally, we map to the tangent space at the origin (which is Euclidean-like)
        # and then use expmap0 to project to the manifold.
        
        # expmap0(v) maps a vector v in the tangent space at 0 to the manifold.
        x_hyp = self.manifold.expmap0(x_euc)
        
        return x_hyp

def demo():
    print("--- Hyperbolic Adapter Demo ---")
    
    # Simulate CLIP embeddings (Batch=32, Dim=512)
    # These represent our "crowded" Euclidean data
    batch_size = 32
    input_dim = 512
    clip_embeddings = torch.randn(batch_size, input_dim)
    print(f"Input (Euclidean): {clip_embeddings.shape}")
    
    # Initialize Adapter
    # We project to a lower dimension (128) which is common for hyperbolic spaces
    # as they are more efficient (can capture hierarchy in fewer dimensions).
    adapter = HyperbolicAdapter(input_dim=input_dim, output_dim=128)
    
    # Forward Pass
    hyp_embeddings = adapter(clip_embeddings)
    
    print(f"Output (Hyperbolic): {hyp_embeddings.shape}")
    
    # Verify they are on the manifold
    # In Poincaré ball, norm must be < 1/sqrt(c) (usually < 1)
    norms = hyp_embeddings.norm(dim=-1)
    max_norm = norms.max().item()
    print(f"Max Norm of embeddings: {max_norm:.4f} (Should be < 1.0)")
    
    if max_norm < 1.0:
        print("SUCCESS: All points are validly projected onto the Poincaré disk.")
    else:
        print("FAILURE: Points escaped the manifold!")

if __name__ == "__main__":
    demo()
