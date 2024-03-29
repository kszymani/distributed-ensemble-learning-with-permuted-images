from model.train_configs import BATCH_SIZE
from permutation.permutations import PermutationGenerator
import albumentations as A


def get_train_valid_gens(x_train, y_train, x_val, y_val, permutations, sub_input_shape, examples_path, save_examples=False):
    train_ds = get_generator(
        x_train, y_train,
        batch_size=BATCH_SIZE,
        permutations=permutations,
        sub_input_shape=sub_input_shape,
        augmented=True,
        examples_path=examples_path,
        save_examples=False,
        shuffle=True,
    )
    valid_ds = get_generator(
        x_val, y_val,
        batch_size=BATCH_SIZE,
        permutations=permutations,
        examples_path=examples_path,
        save_examples=save_examples,
        sub_input_shape=sub_input_shape
    )
    return train_ds, valid_ds


def get_generator(
        x, y,
        permutations=None,
        examples_path=None,
        augmented=False,
        sub_input_shape=None,
        shuffle=False,
        save_examples=False,
        batch_size=None,
):
    aug = augmentation() if augmented else None
    perm_gen = PermutationGenerator(
        x, y, aug,
        subinput_shape=sub_input_shape, permutations=permutations, batch_size=batch_size, examples_path=examples_path,
        shuffle_dataset=shuffle
    )
    if save_examples:
        perm_gen.generate_and_save_examples()
    return perm_gen


def augmentation():
    return A.Compose([
        A.HorizontalFlip(),
        A.CLAHE(),
        A.ShiftScaleRotate(shift_limit=0.2, scale_limit=0.3, rotate_limit=45, p=.75),
        A.OneOf([
            A.MotionBlur(p=.20),
            A.MedianBlur(blur_limit=3, p=0.20),
            A.Blur(blur_limit=3, p=0.20),
        ], p=0.3),
        A.HueSaturationValue(p=0.35),
    ])
