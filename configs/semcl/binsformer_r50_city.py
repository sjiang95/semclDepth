_base_ = [
    '../_base_/models/binsformer.py',
    '../_base_/default_runtime.py', 
]

pretrained='../moco4semencontrast/pretrained/bkb_r-50-1000ep.pth.tar' # cannot directly use `https://dl.fbaipublicfiles.com/moco-v3/r-50-1000ep/r-50-1000ep.pth.tar` since the base_encoder is not extracted. Do that via semcl2bkb.py
model = dict(
    backbone=dict(
        _delete_=True,
        type='ResNet',
        depth=50,
        num_stages=4,
        out_indices=(0, 1, 2, 3, 4),
        style='pytorch',
        norm_cfg=dict(type='SyncBN', requires_grad=True),#
        init_cfg=dict(type='Pretrained', checkpoint=pretrained),
    ),
    decode_head=dict(
        type='BinsFormerDecodeHead',
        class_num=25,
        in_channels=[64, 256, 512, 1024],
        conv_dim=256,
        min_depth=1e-3,
        max_depth=200,
        n_bins=64,
        index=[0, 1, 2, 3],
        trans_index=[1, 2, 3], # select index for cross-att
        loss_decode=dict(type='SigLoss', valid_mask=True, loss_weight=10),
        with_loss_chamfer=False, # do not use chamfer loss
        loss_chamfer=dict(type='BinsChamferLoss', loss_weight=1e-1),
        classify=False, # class embedding
        loss_class=dict(type='CrossEntropyLoss', loss_weight=1e-2),
        norm_cfg=dict(type='SyncBN', requires_grad=True),#
        transformer_encoder=dict( # default settings
            type='PureMSDEnTransformer',
            num_feature_levels=3,
            encoder=dict(
                type='DetrTransformerEncoder',
                num_layers=6,
                transformerlayers=dict(
                    type='BaseTransformerLayer',
                    attn_cfgs=dict(
                        type='MultiScaleDeformableAttention', 
                        embed_dims=256, 
                        num_levels=3, 
                        num_points=8),
                    ffn_cfgs=dict(
                        embed_dims=256, 
                        feedforward_channels=1024,
                        ffn_drop=0.1,),
                    operation_order=('self_attn', 'norm', 'ffn', 'norm')))),
        positional_encoding=dict(
            type='SinePositionalEncoding', num_feats=128, normalize=True),
        transformer_decoder=dict(
            type='PixelTransformerDecoder',
            return_intermediate=True,
            num_layers=9,
            num_feature_levels=3,
            hidden_dim=256,
            operation='//',
            transformerlayers=dict(
                type='PixelTransformerDecoderLayer',
                attn_cfgs=dict(
                    type='MultiheadAttention',
                    embed_dims=256,
                    num_heads=8,
                    dropout=0.0),
                ffn_cfgs=dict(
                    feedforward_channels=2048,
                    ffn_drop=0.0),
                operation_order=('cross_attn', 'norm', 'self_attn', 'norm', 'ffn', 'norm')))),
    train_cfg=dict(
        aux_loss = True,
        aux_index = [2, 5],
        aux_weight = [1/4, 1/2]
    ),
    test_cfg=dict(mode='whole')
)

# dataset settings
dataset_type = 'CSsemclDataset'
data_root = 'data/cityscapes'
img_norm_cfg = dict(
    mean=[123.675, 116.28, 103.53], std=[58.395, 57.12, 57.375], to_rgb=True)
crop_size= (352, 704)
train_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='DisparityLoadAnnotations'),
    dict(type='Resize', img_scale=(1216, 352), keep_ratio=False),
    dict(type='KBCrop', depth=True),
    dict(type='RandomRotate', prob=0.5, degree=2.5),
    dict(type='RandomFlip', prob=0.5),
    dict(type='RandomCrop', crop_size=(352, 704)),
    dict(type='ColorAug', prob=1, gamma_range=[0.9, 1.1], brightness_range=[0.9, 1.1], color_range=[0.9, 1.1]),
    dict(type='Normalize', **img_norm_cfg),
    dict(type='DefaultFormatBundle'),
    dict(type='Collect', keys=['img', 'depth_gt']),
]
test_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='Resize', img_scale=(1216, 352), keep_ratio=False),
    dict(type='KBCrop', depth=False),
    dict(
        type='MultiScaleFlipAug',
        img_scale=(1024, 2048),
        flip=True,
        flip_direction='horizontal',
        transforms=[
            dict(type='RandomFlip', direction='horizontal'),
            dict(type='Normalize', **img_norm_cfg),
            dict(type='DefaultFormatBundle'),
            dict(type='Collect', keys=['img']),
        ])
]
eval_pipeline = [
    dict(type='LoadImageFromFile'),
    dict(type='RandomFlip', direction='horizontal', prob=0),
    dict(type='Normalize', **img_norm_cfg),
    dict(type='DefaultFormatBundle'),
    dict(type='Collect', keys=['img']),
]

data = dict(
    samples_per_gpu=4, # batchsize=16 on two dual-gpu node
    workers_per_gpu=4,
    train=dict(
        type='RepeatDataset',
        times=8,
        dataset=dict(
            type=dataset_type,
            data_root=data_root,
            img_dir='leftImg8bit',
            cam_dir='camera',
            ann_dir='disparity',
            depth_scale=256,
            split='cityscapes_train.txt',
            pipeline=train_pipeline,
            garg_crop=True,
            eigen_crop=False,
            min_depth=1e-3,
            max_depth=200        
        )
    ),
    val=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='leftImg8bit',
        cam_dir='camera',
        ann_dir='disparity',
        depth_scale=256,
        split='cityscapes_test.txt',
        pipeline=test_pipeline,
        garg_crop=True,
        eigen_crop=False,
        min_depth=1e-3,
        max_depth=200),
    test=dict(
        type=dataset_type,
        data_root=data_root,
        img_dir='leftImg8bit',
        cam_dir='camera',
        ann_dir='disparity',
        depth_scale=256,
        split='cityscapes_test.txt',
        pipeline=test_pipeline,
        garg_crop=True,
        eigen_crop=False,
        min_depth=1e-3,
        max_depth=200)
)


# AdamW optimizer, no weight decay for position embedding & layer norm
# in backbone
max_lr = 5e-5
optimizer = dict(
    type='AdamW',
    lr=max_lr,
    betas=(0.9, 0.999),
    weight_decay=0.01,
    paramwise_cfg=dict(
        custom_keys={
            'absolute_pos_embed': dict(decay_mult=0.),
            'relative_position_bias_table': dict(decay_mult=0.),
            'norm': dict(decay_mult=0.),
        }))
# learning policy
lr_config = dict(
    policy='OneCycle',
    max_lr=max_lr,
    warmup_iters=1600 * 8,
    div_factor=25,
    final_div_factor=100,
    by_epoch=False)
optimizer_config = dict(grad_clip=dict(max_norm=35, norm_type=2))
# runtime settings
runner = dict(type='IterBasedRunner', max_iters=1600 * 24)
checkpoint_config = dict(by_epoch=False, max_keep_ckpts=1, interval=1600)
evaluation = dict(by_epoch=False, 
                  start=0,
                  interval=1600, 
                  pre_eval=True, 
                  rule='less', 
                  save_best='abs_rel',
                  greater_keys=("a1", "a2", "a3"), 
                  less_keys=("abs_rel", "rmse"))

# iter runtime
log_config = dict(
    _delete_=True,
    interval=50,
    hooks=[
        dict(type='TextLoggerHook', by_epoch=False),
        dict(type='TensorboardLoggerHook') # TensorboardImageLoggerHook
    ])

find_unused_parameters=True

# use dynamicscale, and initialize with 512. 
# [已有模型 AMP 使用方法](https://zhuanlan.zhihu.com/p/375224982)
fp16 = dict(loss_scale=dict(init_scale=512.,mode='dynamic'))  