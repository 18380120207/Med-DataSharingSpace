import math
import random

import torch


class TorchHook:
    """Small compatibility shim for the legacy PySyft API used by this demo."""

    def __init__(self, torch_module):
        self.torch = torch_module

        if not hasattr(torch.Tensor, "get"):
            torch.Tensor.get = lambda tensor: tensor

        if not hasattr(torch.nn.Module, "send"):
            torch.nn.Module.send = lambda module, location: module

        if not hasattr(torch.nn.Module, "get"):
            torch.nn.Module.get = lambda module: module


class VirtualWorker:
    def __init__(self, hook, id):
        self.hook = hook
        self.id = id

    def clear_objects(self):
        return None


class BaseDataset:
    def __init__(self, data, targets):
        self.data = data
        self.targets = targets

    def __len__(self):
        return len(self.data)

    def __getitem__(self, index):
        return self.data[index], torch.tensor(self.targets[index])

    def federate(self, workers):
        return _FederatedDataset(self.data, self.targets, workers)


class _FederatedDataset:
    def __init__(self, data, targets, workers):
        self.data = data
        self.targets = targets
        self.workers = workers

    def __len__(self):
        return len(self.data)


class FederatedDataLoader:
    def __init__(self, dataset, batch_size=1, shuffle=False):
        self.dataset = dataset
        self.batch_size = batch_size
        self.shuffle = shuffle

    def __len__(self):
        return math.ceil(len(self.dataset) / self.batch_size)

    def __iter__(self):
        indexes = list(range(len(self.dataset)))
        if self.shuffle:
            random.shuffle(indexes)

        workers = self.dataset.workers
        for batch_number, start in enumerate(range(0, len(indexes), self.batch_size)):
            selected = indexes[start:start + self.batch_size]
            data = torch.stack([
                self.dataset.data[index].detach().clone()
                for index in selected
            ])
            target = torch.tensor([
                self.dataset.targets[index]
                for index in selected
            ])
            data.location = workers[batch_number % len(workers)]
            yield data, target
