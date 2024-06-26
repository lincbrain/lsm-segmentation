import numpy as np
import os
from glob import glob
from stardist import Rays_GoldenSpiral
from stardist.models import Config3D, StarDist3D

from lsm.synthetic.stardist_utils import FileData, augmenter
from lsm.synthetic.training_args import training_args

from csbdeep.utils.tf import limit_gpu_memory

limit_gpu_memory(None, allow_growth=True)


if __name__ == "__main__":
    args = training_args()

    nepochs = args.epochs
    nsteps = args.steps
    nbatchsize = args.batch_size
    dataset_imdir = args.dataset_ims
    dataset_labdir = args.dataset_labs
    model_name = args.name
    lr = args.lr
    losswt_1 = args.losswt_1
    losswt_2 = args.losswt_2
    nrays = args.nrays
    nval_samples = args.val_samples
    rng_seed = args.rng_seed
    basedir = args.parent_dir

    np.random.seed(rng_seed)  # Set numpy seed

    # Gather data generated by AnyStar's generative model:
    fnamesall = os.listdir(basedir + "/" + dataset_imdir)
    fnamesall = np.random.RandomState(rng_seed).permutation(fnamesall)

    imgs = []
    labs = []

    for i in range(len(fnamesall)):
        imgs = imgs + sorted(
            glob(
                basedir + "/" + dataset_imdir + "/{}/*.nii.gz".format(fnamesall[i]),
            )
        )
        labs = labs + sorted(
            glob(basedir + "/" + dataset_labdir + "/{}/*.nii.gz".format(fnamesall[i]))
        )

    # Shuffle images and labels:
    imgs = np.random.RandomState(seed=rng_seed).permutation(imgs)
    labs = np.random.RandomState(seed=rng_seed).permutation(labs)

    # Set aside `nval_samples` images to use as a synthetic 'validation set'
    # Required as we do not use any real data to decide when to stop training.
    # Only used to decide when to stop training:
    assert nval_samples < len(imgs), "More val imgs specified than imgs exist"
    vimgs = imgs[-nval_samples:].copy()
    vlabs = labs[-nval_samples:].copy()

    # Use the rest for training:
    imgs = imgs[:-nval_samples]
    labs = labs[:-nval_samples]

    # Set up tf data sequences:
    X_trn = FileData(imgs)
    Y_trn = FileData(labs, label_mode=True)
    X_val = FileData(vimgs)
    Y_val = FileData(vlabs, label_mode=True)

    # Training modeling decisions:
    n_rays = nrays
    rays = Rays_GoldenSpiral(n_rays, anisotropy=(1, 1, 1))

    # StarDist training configuration:
    conf = Config3D(
        rays=rays,
        grid=(1, 1, 1),  #
        anisotropy=(1, 1, 1),  # AnyStar generates isotropic data
        use_gpu=False,  # This refers to whether to use `gputools`
        n_channel_in=1,
        train_patch_size=(64, 64, 64),  # crop size
        train_batch_size=nbatchsize,
        train_epochs=nepochs,
        train_steps_per_epoch=nsteps,
        unet_batch_norm=True,
        train_learning_rate=lr,
        train_reduce_lr=None,  # paper used linear lr decay
        train_dist_loss="mae",
        train_loss_weights=(losswt_1, losswt_2),
        unet_n_depth=5,
        unet_n_filter_base=32,
        train_sample_cache=False,
    )
    print(conf)
    vars(conf)

    # Create model and save ckpts to 'models' folder:
    model = StarDist3D(conf, name=model_name, basedir="models")
    model.train(
        X_trn,
        Y_trn,
        validation_data=(X_val, Y_val),
        augmenter=augmenter,
    )
