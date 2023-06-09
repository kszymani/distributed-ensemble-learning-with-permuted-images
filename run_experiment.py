import os

# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # suppress logging
import pathlib
import pickle
from contextlib import redirect_stdout
from copy import copy
from pprint import pprint

import numpy as np
from scipy.stats import ttest_rel
from sklearn.model_selection import RepeatedStratifiedKFold
from tensorflow.python.client import device_lib
from tabulate import tabulate

from datasets import load_data, get_classes_names_for_dataset
from experiment_configs import get_experiment
from model.training import train_model, predict, skip_training
from permutation.permutations import generate_permutations

print(device_lib.list_local_devices())

N_REPEATS = 5
N_SPLITS = 2
kfold = RepeatedStratifiedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS)

ds = [
    'cifar10',
    'cifar100',
    # 'fashion_mnist',
    # 'emnist-letters',
    # 'cats_vs_dogs',
    # 'mnist',
    # 'eurosat',
]


def parse_config(model_params, ds_name, f_id, n_classes, input_shape, experiment_name):
    mode = model_params['type']
    grid_size = model_params['grid_size']
    seed = model_params['seed']
    overlap = model_params['overlap']
    aggr_scheme = model_params['aggregation']
    scheme = model_params.get('permutation_scheme')
    arch = model_params.get('model_architecture')
    print(f'{input_shape=} {grid_size=}')
    sub_input_shape = (input_shape[0] // grid_size[0], input_shape[1] // grid_size[1], input_shape[2])

    permutations = generate_permutations(seed, grid_size, sub_input_shape, overlap, scheme)

    model_path = f"experiments/{experiment_name}/{ds_name}/{mode}/" \
                 f"{arch.value}/" \
                 f"{'perm-' if seed is not None else 'identity'}" \
                 f"{scheme.name.lower() if scheme and seed else ''}/" \
                 f"ov_{overlap.name.lower()}-agg_{aggr_scheme.name.lower()}-{grid_size[0]}x{grid_size[1]}/fold_{f_id}"

    classes = get_classes_names_for_dataset(ds_name)
    print(
        f"Running with ({mode}, {arch.name.lower()}, {scheme.name.lower()}, {aggr_scheme.name.lower()},"
        f" {overlap.name.lower()})")
    return (model_path, permutations, sub_input_shape, n_classes, ds_name, arch, mode, aggr_scheme), classes


def train_models(data, models, experiment_name):
    for d_id, ds_name in enumerate(data):
        (x, y), _, n_classes = load_data(ds_name)
        y_s = np.argmax(y, axis=1) if n_classes != 2 else y
        for m_id, m_config in enumerate(models):
            for f_id, (train, valid) in enumerate(kfold.split(x, y_s)):
                params, _ = parse_config(m_config, ds_name, f_id, n_classes, x.shape[1:],
                                         experiment_name=experiment_name)
                print(f'{m_id=} , {f_id=}')
                model_path = params[0]
                if not skip_training(model_path):
                    train_model(x[train], y[train], x[valid], y[valid], *params)


def evaluate_models(data, models, scores_path, experiment_name, run_faulty_test=True):
    configs = [[[None for _ in range(kfold.get_n_splits())] for _ in range(len(models))] for _ in range(len(data))]
    scores = np.zeros((len(data), len(models), kfold.get_n_splits()))
    for d_id, ds_name in enumerate(data):
        _, (x_test, y_test), n_classes = load_data(ds_name)
        for f_id in range(kfold.get_n_splits()):
            for m_id, m_config in enumerate(models):
                params, classes_names = parse_config(m_config, ds_name, f_id, n_classes, x_test.shape[1:],
                                                     experiment_name)
                model_path = params[0]
                if run_faulty_test:
                    print("Running test with invalid key")
                    invalid_test_config = copy(m_config)
                    invalid_test_config['seed'] = 1111
                    predict(
                        model_path, x_test, y_test, params[2], classes_names,
                        invalid_test=invalid_test_config,
                        test_dir_name='test_invalid_perm'
                    )
                acc = predict(model_path, x_test, y_test, params[2], classes_names)
                print("Accuracy: ", acc)
                scores[d_id, m_id, f_id] = acc
                configs[d_id][m_id][f_id] = m_config
    result = {
        'configs': configs,
        'scores': scores
    }
    with open(scores_path, 'wb') as file:
        pickle.dump(result, file)
    return result


def run_tests(data, experiment_name=None):
    exp_dir = f'experiments/{experiment_name}'
    scores_path = f'{exp_dir}/scores'
    pathlib.Path(exp_dir).mkdir(exist_ok=True, parents=True)
    models_params = get_experiment(experiment_name)
    with open(f'{exp_dir}/experiment_config', 'w') as conf:
        pprint(models_params, conf)

    train_models(data, models_params, experiment_name)

    if not os.path.exists(scores_path):
        results = evaluate_models(data, models_params, scores_path, experiment_name)
    else:
        with open(scores_path, 'rb') as file:
            results = pickle.load(file)
    run_stats(results['scores'], exp_dir, models_params)


def run_stats(scores, exp_dir, models, alfa=0.05):
    headers = []
    for model_params in models:
        overlap = model_params['overlap'].name.lower()
        scheme = model_params.get('permutation_scheme').name.lower()
        headers.append(f'ConvMixer-{overlap}-{scheme}')
    pathlib.Path(exp_dir).mkdir(exist_ok=True)
    n_models = scores.shape[1]
    for d_id, ds_scores in enumerate(scores):
        t_statistic = np.zeros((n_models, n_models))
        p_value = np.zeros((n_models, n_models))
        for i in range(n_models):
            for j in range(n_models):
                if i != j:
                    t_statistic[i, j], p_value[i, j] = ttest_rel(ds_scores[i], ds_scores[j])
        advantage = np.zeros((n_models, n_models))
        advantage[t_statistic > 0] = 1
        significance = np.zeros((n_models, n_models))
        significance[p_value <= alfa] = 1
        adv_table = significance * advantage
        print_pretty_table(t_statistic, p_value, adv_table, save_path=f'{exp_dir}/{ds[d_id]}', headers=headers)


def print_pretty_table(t_statistic, p_value, advantage_table, save_path, headers):
    names_column = np.array([[n] for n in headers])
    t_statistic_table = np.concatenate((names_column, t_statistic), axis=1)
    t_statistic_table = tabulate(t_statistic_table, headers, floatfmt=".2f")

    p_value_table = np.concatenate((names_column, p_value), axis=1)
    p_value_table = tabulate(p_value_table, headers, floatfmt=".6f")

    adv_table = np.concatenate((names_column, advantage_table), axis=1)
    adv_table = tabulate(adv_table, headers)

    results = f"t-statistic:\n {t_statistic_table}" \
              f"\n\np-value:\n{p_value_table}" \
              f"\n\nadvantage-table:\n{adv_table}"
    print(results)
    with open(f'{save_path}/summary.txt', 'w') as f:
        with redirect_stdout(f):
            print(results)


if __name__ == '__main__':
    run_tests(ds, experiment_name='overlap_5')
    run_tests(ds, experiment_name='permutation_5')
