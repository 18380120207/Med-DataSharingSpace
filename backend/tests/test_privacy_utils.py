import pathlib
import sys
import unittest

import torch


FLASK_APP_DIR = pathlib.Path(__file__).resolve().parents[1] / "flask_app"
sys.path.insert(0, str(FLASK_APP_DIR))

from privacy_utils import (  # noqa: E402
    kmeans_quantize,
    protect_and_compress_update,
    topk_sparsify,
    transform_state_update,
)


class PrivacyUtilsTests(unittest.TestCase):
    def test_topk_keeps_requested_share(self):
        tensor = torch.arange(1, 11, dtype=torch.float32)
        sparse = topk_sparsify(tensor, keep_ratio=0.5)
        self.assertEqual(torch.count_nonzero(sparse).item(), 5)
        self.assertEqual(sparse[-1].item(), 10)

    def test_quantization_limits_unique_values(self):
        tensor = torch.linspace(-1, 1, 100)
        quantized, centroids = kmeans_quantize(tensor, bits=2)
        self.assertLessEqual(torch.unique(quantized).numel(), 4)
        self.assertLessEqual(centroids, 4)

    def test_pipeline_reduces_estimated_payload(self):
        torch.manual_seed(7)
        tensor = torch.randn(2048)
        _, metrics = protect_and_compress_update(
            tensor,
            keep_ratio=0.25,
            quantization_bits=4,
            noise_multiplier=0,
        )
        self.assertLess(metrics["compressed_bytes"], metrics["original_bytes"])

    def test_state_transform_preserves_shapes(self):
        before = {"weight": torch.zeros(8, 4), "step": torch.tensor(1)}
        after = {"weight": torch.ones(8, 4), "step": torch.tensor(2)}
        transformed, metrics = transform_state_update(
            before,
            after,
            keep_ratio=0.5,
            noise_multiplier=0,
        )
        self.assertEqual(transformed["weight"].shape, after["weight"].shape)
        self.assertEqual(transformed["step"].item(), 2)
        self.assertGreater(metrics["original_bytes"], 0)


if __name__ == "__main__":
    unittest.main()
