# LGtagging_LSTM
## Introduction

A tagging system of local gazetteers by LSTM algorithms

## Usage

1. Download the pre-trained model from: https://dataverse.harvard.edu/file.xhtml?fileId=6373866 and decompress the model folder to the root, your directory will look like:

data/

log/

**models/**

**&ensp;\- page_model/**
 
**&ensp;\- record_model/**
 
**&ensp;\- default_x_encoder.p**

app.py

config

...

2. Run

`python main.py`
    
## Input

LGtagging_LSTM/data/input.txt

## Requirement

torch

pytorch-pretrained-bert

pytorch-crf

torchvision
