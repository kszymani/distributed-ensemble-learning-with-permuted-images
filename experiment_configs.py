from enums import Overlap, PermSchemas, ModelType, Aggregation


def get_configs(overlap, aggr, perm_scheme, model_arch, grid_size, model_type):
    seed = 42 if perm_scheme != PermSchemas.IDENTITY else None
    return {
        'type': model_type,
        'seed': seed,
        'permutation_scheme': perm_scheme,
        'grid_size': grid_size,
        'overlap': overlap,
        'aggregation': aggr,
        'model_architecture': model_arch,
    }


overlaps = [
    # Overlap.NONE,
    # Overlap.CENTER,
    Overlap.FULL,
]

aggregations = [
    Aggregation.STRIP_CONCAT,
    # Aggregation.CONCAT,
]

perm_schemas = [
    PermSchemas.BS_4,
    PermSchemas.NAIVE,
    PermSchemas.IDENTITY
]

model_types = [
    ModelType.CONV_MIXER,
    # ModelType.ADAPTATION_RESNET_V2,
    # ModelType.ADAPTATION_INCEPTION,
    # ModelType.ADAPTATION_VGG
]


def get_experiment():
    aggr = Aggregation.STRIP_CONCAT
    perm = PermSchemas.BS_4
    model = ModelType.CONV_MIXER
    return [
        get_configs(
            overlap=Overlap.FULL,
            aggr=aggr,
            perm_scheme=perm,
            model_arch=model,
            grid_size=(2, 2),
            model_type='composite'
        ),
        get_configs(
            overlap=Overlap.CENTER,
            aggr=aggr,
            perm_scheme=perm,
            model_arch=model,
            grid_size=(2, 2),
            model_type='composite'
        ),
        get_configs(
            overlap=Overlap.NONE,
            aggr=aggr,
            perm_scheme=perm,
            model_arch=model,
            grid_size=(2, 2),
            model_type='composite'
        ),
        get_configs(
            overlap=Overlap.NONE,
            aggr=aggr,
            perm_scheme=PermSchemas.NAIVE,
            model_arch=model,
            grid_size=(2, 2),
            model_type='composite'
        ),
        get_configs(
            overlap=Overlap.NONE,
            aggr=aggr,
            perm_scheme=PermSchemas.IDENTITY,
            model_arch=model,
            grid_size=(2, 2),
            model_type='composite'
        ),
        get_configs(
            overlap=Overlap.NONE,
            aggr=Aggregation.NONE,
            perm_scheme=PermSchemas.IDENTITY,
            model_arch=model,
            grid_size=(1, 1),
            model_type='single'
        ),
    ]


def get_experiment_config():
    return [get_configs(
        overlap=Overlap.NONE,
        aggr=Aggregation.STRIP_CONCAT,
        perm_scheme=PermSchemas.BS_4,
        model_arch=ModelType.CONV_MIXER
    )]
    # for ov in overlaps:
    #     for aggr in aggregations:
    #         for perm in perm_schemas:
    #             for model in model_types:
    #                 yield get_configs(
    #                     overlap=ov,
    #                     aggr=aggr,
    #                     perm_scheme=perm,
    #                     model_arch=model
    #                 ),
