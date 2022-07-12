# LGtagging_LSTM
## Introduction

A tagging system of local gazetteers by LSTM algorithms

## Usage

1. Download the pre-trained model from: https://dataverse.harvard.edu/file.xhtml?fileId=6373866&version=DRAFT and decompress the model folder to the root, the directory looks like:

data/

&ensp;\- page_model/
 
&ensp;\- record_model/
 
&ensp;\- default_x_encoder.p

log/

models/

app.py

config

...

2. Run

python main.py
    
## Input

LGtagging_LSTM/data/input.txt

## Requirement

torch

pytorch-pretrained-bert

pytorch-crf

torchvision


## Download the Latest Version

The model is too big, so we compressed and uploaded the whole folder to LGTaggingApp.7z https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/BWIBNL
