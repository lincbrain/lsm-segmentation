import os
import sys
import time
import numpy as np
from tqdm import tqdm

import torch
from torch.utils.data.dataloader import DataLoader

from lsm.dataio import get_data
from lsm.models import get_model
from lsm.utils.logger import Logger
from lsm.utils.console_log import log
from lsm.utils.train_utils import count_trainable_parameters
from lsm.utils.load_config import create_args_parser, load_config, backup
from lsm.utils.distributed_util import (
    init_env,
    get_rank,
    is_master,
    get_local_rank,
    get_world_size,
)

color_map = np.random.randint(0, 256, (500, 3), dtype=np.uint8)
color_map[0] = [0, 0, 0]


def main_function(args):
    init_env(args)
    rank = get_rank()
    local_rank = get_local_rank()
    world_size = get_world_size()
    i_backup = (
        int(args.training.i_backup // world_size) if args.training.i_backup > 0 else -1
    )
    i_val = int(args.training.i_val // world_size) if args.training.i_val > 0 else -1
    exp_dir = args.training.exp_dir

    device = torch.device("cuda", local_rank)

    logger = Logger(
        log_dir=exp_dir,
        save_dir=os.path.join(exp_dir, "predictions"),
        monitoring=args.training.get("monitoring", "tensorboard"),
        monitoring_dir=os.path.join(exp_dir, "events"),
        rank=rank,
        is_master=is_master(),
        multi_process_logging=(world_size > 1),
    )

    log.info(f"Experiments directory: {exp_dir}")

    if is_master():
        pass

    # get data from dataloader
    dataset, val_dataset = get_data(args=args, return_val=True)

    batch_size = args.data.get("batch_size", None)

    if args.ddp:
        train_sampler = DistributedSampler(dataset)
        dataloader = torch.utils.data.DataLoader(
            dataset, sampler=train_sampler, batch_size=batch_size
        )
        val_sampler = DistributedSampler(val_dataset)
        valloader = torch.utils.data.DataLoader(
            val_dataset, sampler=val_sampler, batch_size=batch_size
        )
    else:
        dataloader = DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=True,
            pin_memory=args.data.get("pin_memory", False),
        )
        valloader = DataLoader(val_dataset, batch_size=1, shuffle=True)

    # create model
    model = get_model(args)
    model.to(device)
    log.info(model)
    model_name = args.model.framework

    if world_size > 1:
        dist.barrier()

    tick = time.time()
    log.info(f"Start evaluating in {exp_dir}")

    it, epoch_idx = 0, 0
    end = it >= len(dataset)

    with tqdm(range(len(dataset)), disable=not is_master()) as pbar:
        if is_master():
            pbar.update()

        while it <= len(dataset) and not end:
            try:
                for (indices, model_input, ground_truth) in dataloader:
                    int_it = int(it // world_size)

                    norm_rgb = model_input["norm_rgb"]
                    orig_rgb = ground_truth["orig_rgb"]

                    pred_mask = model(norm_rgb)

                    # check if we have worked with 3d data
                    # save a single slice in that case
                    if args.data_dim == "3D":
                        logger.add_imgs_3d(
                            imgs=orig_rgb,
                            class_name="gt_rgb",
                            it=it,
                            save_seg=False,
                        )
                        logger.add_imgs_3d(
                            imgs=pred_mask, class_name="pred_mask", it=it, save_seg=True
                        )

                    elif args.data_dim == "2D":
                        # save images
                        logger.add_imgs_eval(
                            imgs=orig_rgb,
                            class_name="gt_rgb",
                            it=it,
                            save_seg=False,
                        )
                        logger.add_imgs_eval(
                            imgs=pred_mask,
                            class_name="pred_mask",
                            it=it,
                            save_seg=True,
                        )
                    else:
                        raise NotImplementedError(
                            f"Data dimension: {args.data_dim} not supported. Try one of 2D/3D"
                        )

                    if it >= len(dataset):
                        end = True
                        break

                    it += world_size
                    if is_master():
                        pbar.update(world_size)

                epoch_idx += 1

            except KeyboardInterrupt:
                if is_master():
                    print(f"TODO: idk")
                sys.exit()


if __name__ == "__main__":
    parser = create_args_parser()
    parser.add_argument("--ddp", action="store_true", help="Distributed processing")
    args, unknown = parser.parse_known_args()
    config = load_config(args, unknown)
    main_function(config)
