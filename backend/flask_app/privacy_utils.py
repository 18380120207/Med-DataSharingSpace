"""Privacy and communication transforms for federated model updates.

The web prototype uses these transforms before accepting a local update into
the global model. CKKS encrypted aggregation remains an independent experiment
in ``FLPyfhelin.py`` because its TensorFlow/Pyfhel runtime is much heavier than
the interactive PyTorch demo.
"""

import math

import torch


def clip_and_add_adaptive_noise(update, clip_norm=1.0, noise_multiplier=0.01):
    """Clip an update and add less noise to its more important coordinates.

    This is an experimental adaptive perturbation mechanism. It follows the
    clipping/noise structure used by differential privacy, but the prototype
    does not claim a formally audited privacy budget.
    """
    if not torch.is_floating_point(update) or update.numel() == 0:
        return update.clone()

    update = update.clone()
    norm = torch.linalg.vector_norm(update)
    if norm > clip_norm:
        update.mul_(clip_norm / (norm + 1e-12))

    if noise_multiplier <= 0:
        return update

    importance = update.abs()
    max_importance = importance.max()
    if max_importance > 0:
        importance = importance / max_importance

    # Important coordinates receive less perturbation, while the global scale
    # remains bounded by the configured clipping norm and multiplier.
    allocation = 1.25 - 0.75 * importance
    base_std = noise_multiplier * clip_norm / math.sqrt(update.numel())
    return update + torch.randn_like(update) * base_std * allocation


def topk_sparsify(update, keep_ratio=0.5):
    """Keep the largest coordinates by absolute magnitude."""
    if not torch.is_floating_point(update) or update.numel() == 0:
        return update.clone()

    flat = update.flatten()
    keep = max(1, min(flat.numel(), int(math.ceil(flat.numel() * keep_ratio))))
    if keep == flat.numel():
        return update.clone()

    indices = torch.topk(flat.abs(), keep, sorted=False).indices
    sparse = torch.zeros_like(flat)
    sparse[indices] = flat[indices]
    return sparse.reshape_as(update)


def kmeans_quantize(update, bits=4, iterations=4):
    """Quantize non-zero update values with a small one-dimensional K-means."""
    if not torch.is_floating_point(update) or update.numel() == 0:
        return update.clone(), 0

    result = update.clone()
    mask = result != 0
    values = result[mask]
    if values.numel() == 0:
        return result, 0

    cluster_count = min(2 ** bits, values.numel())
    minimum = values.min()
    maximum = values.max()
    if minimum == maximum or cluster_count == 1:
        return result, 1

    centroids = torch.linspace(
        minimum.item(),
        maximum.item(),
        cluster_count,
        device=values.device,
        dtype=values.dtype,
    )

    for _ in range(iterations):
        labels = (values[:, None] - centroids[None, :]).abs().argmin(dim=1)
        for index in range(cluster_count):
            selected = values[labels == index]
            if selected.numel():
                centroids[index] = selected.mean()

    labels = (values[:, None] - centroids[None, :]).abs().argmin(dim=1)
    result[mask] = centroids[labels]
    return result, cluster_count


def protect_and_compress_update(
    update,
    keep_ratio=0.5,
    quantization_bits=4,
    clip_norm=1.0,
    noise_multiplier=0.01,
):
    """Apply privacy perturbation, Top-K sparsification and quantization."""
    if not torch.is_floating_point(update):
        return update.clone(), {
            "original_bytes": update.numel() * update.element_size(),
            "compressed_bytes": update.numel() * update.element_size(),
            "nonzero": update.numel(),
            "elements": update.numel(),
        }

    protected = clip_and_add_adaptive_noise(
        update,
        clip_norm=clip_norm,
        noise_multiplier=noise_multiplier,
    )
    sparse = topk_sparsify(protected, keep_ratio=keep_ratio)
    quantized, centroid_count = kmeans_quantize(
        sparse,
        bits=quantization_bits,
    )

    nonzero = int(torch.count_nonzero(quantized).item())
    original_bytes = update.numel() * update.element_size()
    # A bit mask records exact sparse positions; labels reference the shared
    # centroid codebook. This mirrors the payload format described in the
    # technical document instead of assuming a 32-bit index per value.
    index_bytes = int(math.ceil(update.numel() / 8))
    value_bytes = int(math.ceil(nonzero * quantization_bits / 8))
    centroid_bytes = centroid_count * update.element_size()

    return quantized, {
        "original_bytes": original_bytes,
        "compressed_bytes": index_bytes + value_bytes + centroid_bytes,
        "nonzero": nonzero,
        "elements": update.numel(),
    }


def transform_state_update(before, after, **options):
    """Transform a state-dict update and return reconstructed state + metrics."""
    transformed = {}
    totals = {
        "original_bytes": 0,
        "compressed_bytes": 0,
        "nonzero": 0,
        "elements": 0,
    }

    for name, after_value in after.items():
        before_value = before[name]
        if torch.is_floating_point(after_value):
            update = after_value - before_value
            protected, metrics = protect_and_compress_update(update, **options)
            transformed[name] = before_value + protected
        else:
            transformed[name] = after_value
            metrics = {
                "original_bytes": after_value.numel() * after_value.element_size(),
                "compressed_bytes": after_value.numel() * after_value.element_size(),
                "nonzero": after_value.numel(),
                "elements": after_value.numel(),
            }

        for key in totals:
            totals[key] += metrics[key]

    return transformed, totals


def summarize_compression(stats):
    """Convert accumulated byte counts into API-friendly metrics."""
    original = max(1, stats["original_bytes"])
    compressed = stats["compressed_bytes"]
    return {
        "original_bytes": stats["original_bytes"],
        "compressed_bytes": compressed,
        "compression_ratio": round(original / max(1, compressed), 2),
        "reduction_percent": round(max(0.0, 1 - compressed / original) * 100, 2),
        "sparsity_percent": round(
            max(0.0, 1 - stats["nonzero"] / max(1, stats["elements"])) * 100,
            2,
        ),
        "encoding": "position bitmask + quantized codebook",
    }
