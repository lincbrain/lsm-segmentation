import torch
import numpy as np


def count_trainable_parameters(model):
    # count the number of trainable parameters in a model
    model_parameters = filter(lambda p: p.requires_grad, model.parameters())
    return sum([np.prod(p.size()) for p in model_parameters])
