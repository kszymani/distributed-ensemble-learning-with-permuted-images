import pathlib
from os.path import join

import cv2
import imageio
import matplotlib.pyplot as plt
import numpy as np
import tensorflow as tf
from PIL import Image
from tensorflow.keras.preprocessing.image import ImageDataGenerator
from sklearn.utils import shuffle

from enums import Overlap, PermSchemas
from permutation.BlockShuffle import BlockScramble

MAX_SEED = 10000000


def cross(r, c, size=None, cntr=None):
    return (r == cntr[0] - 0.5 and abs(c - cntr[1] - 0.5 <= size)) or (
            c == cntr[1] - 0.5 and abs(r - cntr[0] - 0.5 <= size))


def center(r, c, radius=None, cntr=None):
    return np.sqrt((r - cntr[0] + 0.5) ** 2 + (c - cntr[1] + 0.5) ** 2) <= radius


def init_keys(seed, grid_shape, overlap_scheme, n_repeats):
    apply_base_grid = overlap_scheme.value[1]
    if seed is not None:
        np.random.seed(seed)
    keys = {}
    if apply_base_grid:
        for r in range(grid_shape[0]):
            for c in range(grid_shape[1]):
                if (r, c) not in keys:
                    keys[(r, c)] = [np.random.randint(1, MAX_SEED) for _ in range(n_repeats)]

    def add_overlap(condition, **kwargs):
        for r in np.arange(0, grid_shape[0] - 0.5, 0.5):
            for c in np.arange(0, grid_shape[1] - 0.5, 0.5):
                if (r, c) not in keys and condition(r, c, **kwargs):
                    keys[(r, c)] = [np.random.randint(1, MAX_SEED) for _ in range(n_repeats)]

    if overlap_scheme == Overlap.CENTER:
        add_overlap(condition=center, radius=0.1, cntr=(grid_shape[0] / 2, grid_shape[1] / 2))

    elif overlap_scheme == Overlap.CROSS:
        add_overlap(condition=cross, size=grid_shape[0] // 2, cntr=(grid_shape[0] / 2, grid_shape[1] / 2))

    elif overlap_scheme == Overlap.EDGES:
        add_overlap(condition=lambda r, c: (int(r) != r and int(c) == c) or (int(r) == r and int(c) != c))

    elif overlap_scheme == Overlap.CORNERS:
        add_overlap(condition=lambda r, c: int(r) != r and int(c) != c)

    elif overlap_scheme == Overlap.FULL:
        add_overlap(condition=lambda r, c: int(r) != r and int(c) != c)
        add_overlap(condition=lambda r, c: (int(r) != r and int(c) == c) or (int(r) == r and int(c) != c))

    else:  # no overlap
        pass
    np.random.seed()  # restore randomness
    if seed is None:  # identity mode does not use seeds
        for key in keys:
            keys[key] = None
    return keys


def generate_perm(shape, seed=None, blockSize=None):
    if blockSize is not None:
        size = (blockSize[0], blockSize[1], shape[-1])
        return BlockScramble(size, seed)

    indexes = np.arange(shape[0] * shape[1])
    if seed is None:  # identity
        return indexes
    return shuffle(indexes, random_state=seed)


def generate_permutations(seed, grid_shape, subinput_shape, overlap, scheme):
    n_repeats = subinput_shape[-1] \
        if scheme in [PermSchemas.NAIVE, PermSchemas.IDENTITY] \
        else 1
    random_states = init_keys(seed, grid_shape, Overlap.FULL, n_repeats)
    if overlap == Overlap.CENTER:
        random_states = {(row, col): keys for (row, col), keys in list(random_states.items())[:5]}
    if overlap == Overlap.NONE:
        random_states = {(row, col): keys for (row, col), keys in list(random_states.items())[:4]}
    permutations = {}
    for (row, col), keys in random_states.items():
        if seed is None:
            permutations[(row, col)] = [generate_perm(subinput_shape, seed=None) for _ in range(n_repeats)]
        else:
            blockSize = scheme.value \
                if scheme not in [PermSchemas.NAIVE, PermSchemas.IDENTITY] \
                else None
            permutations[(row, col)] = [generate_perm(subinput_shape, blockSize=blockSize, seed=s) for s in keys]
    return permutations


def plot_hist(x, x_patch, x_enc, path, patch_id, enc_type):
    images = [x, x_patch, x_enc]
    fig, axs = plt.subplots(len(images), 4, figsize=[12, 12])
    rgb = ['r', 'g', 'b']
    patch_name = \
        ('top left',
         'top right',
         'bottom left',
         'bottom right'
         )[patch_id] + ' patch' if patch_id < 4 else ''

    ymax = 0
    for i, x in enumerate(images):
        axs[i, 0].imshow(x)
        if i == 0:
            title = 'whole image'
        if i == 1:
            title = patch_name
        if i == 2:
            enc = 'block-wise' if type(enc_type) == BlockScramble else 'full channel-wise'
            title = patch_name + f' \n{enc}\nencryption'
        axs[i, 0].set_title(title, fontsize=15)
        for c in range(x.shape[-1]):
            ax = axs[i, c + 1]
            y, _, _ = ax.hist(x[:, :, c].flatten(), 255, color=rgb[c])
            top_limit = y.max()
            if top_limit > ymax:
                ymax = top_limit
    for i, x in enumerate(images):
        for c in range(x.shape[-1]):
            ax = axs[i, c + 1]
            ax.set_ylim([None, ymax])
            ax.set_xlim([None, 255])
    plt.tight_layout()
    fig.savefig(path)
    plt.close('all')


class PermutationGenerator(tf.keras.utils.Sequence):
    def __init__(self, X, Y, augmenter, subinput_shape, shuffle_dataset=True, batch_size=None, permutations=None,
                 examples_path=None):
        self.n = len(X)
        self.batch_gen = ImageDataGenerator().flow(X, Y, batch_size=batch_size, shuffle=shuffle_dataset)
        self.augmenter = augmenter
        self.n_models = len(permutations)
        self.shuffle = shuffle_dataset
        self.batch_size = batch_size
        self.sub_input_shape = subinput_shape
        self.permutations = permutations
        self.examples_path = examples_path

    def run_histograms(self, xb):
        max_imgs = len(xb)
        sr, sc, channels = self.sub_input_shape
        hist_path = join(self.examples_path, 'histograms')
        for index, x in enumerate(xb[:max_imgs]):
            x = cv2.normalize(x, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)
            x = x.astype(np.uint8)
            subimages = self.generate_patches(np.array([x]))
            ind_path = join(hist_path, f'{index + 1}')
            pathlib.Path(ind_path).mkdir(exist_ok=True, parents=True)
            for i, ((row, col), subimg) in enumerate(zip(self.permutations, subimages)):
                r_s = slice(int(row * sr), int((row + 1) * sr))
                c_s = slice(int(col * sc), int((col + 1) * sc))
                subimg = subimg[0, ...]
                subimg = cv2.normalize(subimg, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)
                subimg = subimg.astype(np.uint8)
                plot_hist(x, x[r_s, c_s, :], subimg, join(ind_path, f'{i}.svg'), patch_id=i,
                          enc_type=self.permutations[(row, col)][0])

    def generate_and_save_examples(self, borders=True):
        print("Generating examples...")
        scale = 15
        xb, yb = self.batch_gen.next()
        self.run_histograms(xb)
        xb = self.augment(xb)
        max_imgs = len(xb)
        sr, sc, channels = self.sub_input_shape
        for index, x in enumerate(xb[:max_imgs]):
            subimages = self.generate_patches(np.array([x]))
            x = cv2.normalize(x, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)
            x = x.astype(np.uint8)
            if channels == 1:
                x = cv2.cvtColor(x, cv2.COLOR_GRAY2RGB)
            imgs = []
            x = resize_img(x, scale=scale)
            for i, ((row, col), subimg) in enumerate(zip(self.permutations, subimages)):
                if int(row) == row and int(col) == col:
                    color = (0, 255, 0)
                    width = int(0.02 * x.shape[0])
                elif int(row) == row or int(col) == col:
                    color = (0, 0, 255)
                    width = int(0.02 * x.shape[0])
                else:
                    color = (255, 0, 0)
                    width = int(0.02 * x.shape[0])
                if borders:
                    x = cv2.rectangle(
                        x, (int(col * sc) * scale, int(row * sr) * scale),
                        (int((col + 1) * sc) * scale, int((row + 1) * sr * scale)),
                        color, width
                    )
                subimg = subimg[0, ...]
                subimg = cv2.normalize(subimg, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_32F)
                subimg = subimg.astype(np.uint8)
                if channels == 1:
                    subimg = cv2.cvtColor(subimg, cv2.COLOR_GRAY2RGB)
                subimg = resize_img(subimg, scale=scale)
                padded = pad_around(subimg, x.shape)
                res = np.hstack((x, padded))
                imgs.append(res)
            if len(imgs) > 1:
                gif_path = join(self.examples_path, f'frames-{index + 1}.gif')
                imageio.mimsave(gif_path, imgs, fps=55, duration=0.5)
            else:
                img_path = join(self.examples_path, f'frames-{index + 1}.svg')
                plt.imsave(img_path, imgs[0], format='svg')

    def augment(self, x):
        return np.array(
            [self.augmenter(image=img.astype(np.uint8))['image'] / 255.0 for img in x]
        ) if self.augmenter else x / 255.0

    def next(self):
        x, y = self.batch_gen.next()
        x = self.augment(x)
        xp = self.generate_patches(x)
        return xp, y

    def on_epoch_end(self):
        pass

    def __getitem__(self, index):
        return self.next()

    def __len__(self):
        return self.n // self.batch_size

    def generate_patches(self, x_batch):
        sr, sc, _ = self.sub_input_shape
        x_frames = []
        for (row, col), perm in self.permutations.items():
            # (row, col) is the position of top left corner of subinput window
            xb = np.zeros((x_batch.shape[0], *self.sub_input_shape))
            r_s = slice(int(row * sr), int((row + 1) * sr))
            c_s = slice(int(col * sc), int((col + 1) * sc))
            if type(perm[0]) == BlockScramble:
                xb = permute(x_batch[:, r_s, c_s, :], perm[0])
            else:
                for i, x in enumerate(x_batch):
                    sub_img = x[r_s, c_s, :]
                    xb[i, ...] = permute(sub_img, perm)
            x_frames.append(xb)
        return x_frames  # shape = [batch, n_models, subwidth, subheight, channels]


def permute(arr, perm):
    if type(perm) == BlockScramble:
        return perm.Scramble(arr)

    res = np.zeros(arr.shape)
    for c in range(arr.shape[-1]):
        channel = arr[:, :, c]
        res[:, :, c] = channel.ravel()[perm[c]].reshape(channel.shape)
    return res


def pad_around(img, dims=None):
    old_image_height, old_image_width, channels = img.shape
    new_image_width, new_image_height, _ = dims
    color = (0, 0, 0)
    result = np.full(dims, color, dtype=np.uint8)

    x_center = (new_image_width - old_image_width) // 2
    y_center = (new_image_height - old_image_height) // 2
    result[y_center:y_center + old_image_height, x_center:x_center + old_image_width] = img
    return result


def resize_img(img, scale):
    width = int(img.shape[1] * scale)
    height = int(img.shape[0] * scale)
    dim = (width, height)
    return np.array(Image.fromarray(img).resize(dim, resample=Image.NEAREST))
