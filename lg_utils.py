# -*- coding: utf-8 -*-
"""
Created on Mon Oct 21 00:11:24 2019

@author: Zhou
"""

import os
import re
import pickle
import numpy as np
import pandas as pd
import itertools

import config

def convert_to_orig(s):
    """
    Convert string from database to corresponding original text
    """
    return s.replace(' ', config.PADDING_CHAR)


def concat_lists(ls):
    return list(itertools.chain.from_iterable(ls))


def random_separate(xs, percs):
    """
    given a list of objects xs, split it randomly into n+1 parts where n=len(percs)
    """
    ns = list(map(int, [p * len(xs) for p in percs]))
    index_permuted = np.random.permutation(len(xs))
    bs = np.clip(np.array(ns).cumsum(), 0, len(xs))
    bs = [0] + list(bs) + [len(xs)]
    return [[xs[i] for i in index_permuted[beg:end]] for beg, end in zip(bs[:-1], bs[1:])]


def modify_tag_seq(text, tag_seq, keyword, tagname):
    """
    Modify tag_seq in the same location of keyword in text by tagname
    """
    if is_empty_cell(keyword):
        return
    keyword = convert_to_orig(keyword)
    if keyword not in text or len(text) != len(tag_seq):
        return
    begin_locs = [loc.start() for loc in re.finditer(keyword, text)]
    for begin_loc in begin_locs:
        for loc in range(begin_loc, begin_loc + len(keyword)):
            if tag_seq[loc] != config.NULL_TAG:
                raise ValueError("Same char cannot bear more than one tag!")
            tag_seq[loc] = tagname
    

def is_empty_cell(x):
    return (not isinstance(x, str)) or len(x) == 0
    
    
def nan_weighted_average(arr, w):
    a = np.array(arr)
    weights = np.array(w)
    indices = ~np.isnan(a)
    return np.average(a[indices], weights=weights[indices])


def get_sent_len_for_pages(tag_seq_list, eos_tag):
    """
    tag_seq_list: list of list of tags
    """
    parsed_sent_len_for_pages = []
    for tag_seq in tag_seq_list:
        # make list of int (i.e. sentence lengths) out of list of tags
        parsed_sent_len = []
        current_len = 0
        for tag in tag_seq[1:-1]: # ignore <S> and </S>
            current_len += 1
            if tag == eos_tag:
                parsed_sent_len.append(current_len)
                current_len = 0
        # in case last char is not tagged as 'S'
        if current_len > 0:
            parsed_sent_len.append(current_len)
        parsed_sent_len_for_pages.append(parsed_sent_len)
    return parsed_sent_len_for_pages


def get_keywords_from_tagged_record(char_samples, tag_name):
    res = []
    is_inside_keyword = False
    current_keyword = ""
    for cs in char_samples:
        if cs.get_tag() == tag_name:
            is_inside_keyword = True
            current_keyword += cs.get_char()
        else:
            if is_inside_keyword:       # First char sample after keyword
                res.append(current_keyword)
                current_keyword = ""
            is_inside_keyword = False
    # In case last keyword is by end of sentence
    if len(current_keyword) > 0:
        res.append(current_keyword)
    return res


def get_data_from_samples(samples, x_encoder, y_encoder):
    retv = []
    for i, p in enumerate(samples):
        if i % 1000 == 0:
            print(i)
        retv.append((p.get_x(x_encoder), p.get_y(y_encoder)))
    return retv
        
        
def prepare_confusion_matrix(tag_true, tag_pred, tag_list):
    tag_to_idx = {t: i for i, t in enumerate(tag_list)}
    confusion_matrix = np.zeros([len(tag_list), len(tag_list)])
    
    for ps, ts in zip(tag_pred, tag_true):
        assert len(ps) == len(ts)
        for p, t in zip(ps, ts):
            if p not in tag_list or t not in tag_list:
                continue
            confusion_matrix[tag_to_idx[t], tag_to_idx[p]] += 1
            
    return tag_to_idx, confusion_matrix


def process_confusion_matrix(confusion_matrix, tag_idx):
    tp = confusion_matrix[tag_idx, tag_idx]
    fp = confusion_matrix[:, tag_idx].sum() - tp
    fn = confusion_matrix[tag_idx, :].sum() - tp
    tn = confusion_matrix.sum() - tp - fp - fn
    precision = tp / float(tp + fp)
    recall = tp / float(tp + fn)
    accuracy = (tp + tn) / float(confusion_matrix.sum())
    f_score = 2 / (1 / precision + 1 / recall)
    return precision, recall, accuracy, f_score


def process_confusion_matrix_macro(confusion_matrix, tag_to_idx,
                                   ignore_tags=[], weighted=True):
    #TODO: unit tests
    precisions, recalls, accuracys, f_scores, weights = [], [], [], [], []
    for tag_name, tag_idx in tag_to_idx.items():
        if tag_name in ignore_tags:
            continue
        weights.append(confusion_matrix[tag_idx, :].sum() if weighted else 1.0)
        precision, recall, accuracy, f_score = process_confusion_matrix(confusion_matrix, tag_idx)
        precisions.append(precision)
        recalls.append(recall)
        accuracys.append(accuracy)
        f_scores.append(f_score)
    
    precision_macro = nan_weighted_average(precisions, weights)
    recall_macro = nan_weighted_average(recalls, weights)
    accuracy_macro = nan_weighted_average(accuracys, weights)
    f_score_macro = nan_weighted_average(f_scores, weights)
    return precision_macro, recall_macro, accuracy_macro, f_score_macro


def process_confusion_matrix_micro(confusion_matrix, tag_to_idx, ignore_tags=[]):
    tps, fps, fns, tns = [], [], [], []
    for tag_name, tag_idx in tag_to_idx.items():
        if tag_name in ignore_tags:
            continue
        tp = confusion_matrix[tag_idx, tag_idx]
        fp = confusion_matrix[:, tag_idx].sum() - tp
        fn = confusion_matrix[tag_idx, :].sum() - tp
        tn = confusion_matrix.sum() - tp - fp - fn
        tps.append(tp)
        fps.append(fp)
        fns.append(fn)
        tns.append(tn)
    precision = sum(tps) / float(sum(tps) + sum(fps))
    recall = sum(tps) / float(sum(tps) + sum(fns))
    accuracy = (sum(tps) + sum(tns)) / float(sum(tps) + sum(fps) + sum(fns) + sum(tns))
    f_score = 2 / (1 / precision + 1 / recall)
    return precision, recall, accuracy, f_score


def tag_correct_ratio(samples, model, subset_name, args, logger):
    '''
    Return entity-level correct ratio only for record model
    '''
    inputs = [(s.get_x(), s.get_y()) for s in samples]
    tags = model.evaluate_model(inputs, args)  
    tag_pred = [tag[0] for tag in tags]
    tag_true = [tag[1] for tag in tags]
#    sent_str = [tag[2] for tag in tags]
    assert len(tag_pred) == len(tag_true)
    for x, y in zip(tag_pred, tag_true):
        assert len(x) == len(y)
    correct_and_total_counts = [word_count(ps, ts) for ps, ts in zip(tag_pred, tag_true)]
#    output_entity_details(tag_pred, tag_true, sent_str, mismatch_only=False)
    entity_correct_ratio = sum([x[0] for x in correct_and_total_counts]) \
                            / float(sum([x[1] for x in correct_and_total_counts]))
    
    # Log info of correct ratio
    info_log = "Entity level correct ratio of {} set is {}".format(subset_name,
                                                              entity_correct_ratio)
    print(info_log)
    logger.info(info_log)
    
    return entity_correct_ratio
    

def output_entity_details(tag_pred, tag_true, inputs, mismatch_only=True):
    df = pd.DataFrame(columns=["word", "expected", "pred", "correct"])
    assert len(inputs) == len(tag_pred)
    assert len(inputs) == len(tag_true)
    i_entity = 0
    for sent, ps, ts in zip(inputs, tag_pred, tag_true):
        i_entity += 1
        if i_entity > config.MAX_ENTITY_RECORD:
            break
        assert len(sent) == len(ps)
        assert len(sent) == len(ts)
        true_cuts = get_cut(ts)
        pred_cuts = get_cut(ps)
        for tc in true_cuts:
            if (not mismatch_only) or (tc not in pred_cuts):
                start, end, tag_type = tc
                if tag_type in config.special_tag_list:
                    continue
                df = df.append({"word": sent[start:end],
                                "expected": ts[start:end],
                                "pred": ps[start:end],
                                "correct": tc in pred_cuts},
                                ignore_index=True)
    df.to_csv(os.path.join(config.OUTPUT_PATH, "entity_detail.csv"),
              encoding='utf-8-sig',
              index=False)
    
    
def is_collocated(c1, c2):
    return c1[0] == c2[0] and c1[1] == c2[1]

    
def calc_entity_metrics(tag_pred, tag_true, tag_list):
    tag_to_idx = {t: i for i, t in enumerate(tag_list)}
    n_dim = len(tag_list) + 1
    confusion_matrix = np.zeros([n_dim, n_dim])
    
    for ps, ts in zip(tag_pred, tag_true):
        assert len(ps) == len(ts)
        pcs = [c for c in get_cut(ps) if c[2] in tag_list]
        tcs = [c for c in get_cut(ts) if c[2] in tag_list]
        # Round 1: handle all pred cuts
        for pc in pcs:
            has_collocated = False
            for tc in tcs:
                if is_collocated(pc, tc):
                    confusion_matrix[tag_to_idx[tc[2]], tag_to_idx[pc[2]]] += 1
                    has_collocated = True
                    break
            # If no match after checking all tc, then increment last row of matrix
            if not has_collocated:
                confusion_matrix[n_dim - 1, tag_to_idx[pc[2]]] += 1
        # Round 2: handle all true cuts without collocation
        for tc in tcs:
            for pc in pcs:
                if is_collocated(pc, tc):
                    # Don't increment here, to avoid double counting
                    has_collocated = True
                    break
            # If no match after checking all pc, then increment last col of matrix
            if not has_collocated:
                confusion_matrix[tag_to_idx[tc[2]], n_dim - 1] += 1
            
    # calculate metrics, this is a generalization of micro metrics
    tp = confusion_matrix.diagonal().sum()
    tp_plus_fp = confusion_matrix[:, :-1].sum()
    tp_plus_fn = confusion_matrix[:-1, :].sum()
    
    precision = tp / float(tp_plus_fp)
    recall = tp / float(tp_plus_fn)
    accuracy = (tp + 0) / float(confusion_matrix.sum())
    f_score = 2 / (1 / precision + 1 / recall)
    collocation_ratio = confusion_matrix[:-1, :-1].sum() / float(confusion_matrix.sum())
    return precision, recall, accuracy, f_score, collocation_ratio

    
def word_count(ps, ts):
    """
    given two lists of tags, count matched words and total words of the first list
    both counts exclude special tags, i.e. BEG, END, etc
    """
    pred_cuts = [c for c in get_cut(ps) if c[2] not in config.special_tag_list]
    true_cuts = get_cut(ts)
    matches = [c for c in pred_cuts if c in true_cuts]
    return len(matches), len(pred_cuts)
    
    
def get_cut(seq):
    """
    triplets are (start_index, end_index, tag_type)
    """
    # TODO: see if other papers handle BEG, END, null tag
    if len(seq) == 0:
        return []
    triplets = []
    start, last = 0, seq[0]
    for i, x in enumerate(seq):
        if x != last:
            triplets.append((start, i, last))
            start, last = i, x
    triplets.append((start, len(seq), last))
    return triplets   
    
    
def correct_ratio_calculation(samples, model, args, subset_name, logger):
    '''
    Take in samples (pages / records), input_encoder, model, output_encoder 
    Get the predict tags and return the correct ratio
    '''
    inputs = [(s.get_x(), s.get_y()) for s in samples]    
    tags = model.evaluate_model(inputs, args)   # list of (list of tags, list of tags)
    tag_pred = [tag[0] for tag in tags]
    tag_true = [tag[1] for tag in tags]
    assert len(tag_pred) == len(tag_true)
    
#    do_stats_for_tags(tag_true, subset_name, "real")
#    correct_tag_pred = [[p for p,t in zip(ps,ts) \
#                      if p == t and t not in config.special_tag_list] \
#                        for ps,ts in zip(tag_pred, tag_true)]
#    do_stats_for_tags(correct_tag_pred, subset_name, "correctly predicted")
    
    for x, y in zip(tag_pred, tag_true):
        assert len(x) == len(y)
    if args.task_type == "page":    # only calculate the EOS tag for page model
        upstairs = [sum([p==t for p,t in zip(ps, ts) if t == config.EOS_TAG]) \
                              for ps, ts in zip(tag_pred, tag_true)]
        downstairs = [len([r for r in rs if r == config.EOS_TAG]) for rs in tag_true]
    else:       # ignore BEG, END etc for record model, although they are learned
        upstairs = [sum([p==t for p,t in zip(ps, ts) if t not in config.special_tag_list]) \
                    for ps, ts in zip(tag_pred, tag_true)]
        downstairs = [len([r for r in rs if r not in config.special_tag_list]) for rs in tag_true]
    # There should be no empty page/record so no check for divide-by-zero needed here
    correct_ratio = sum(upstairs) / float(sum(downstairs))
    
    # Log info of correct ratio
    info_log = "Correct ratio of {} set is {}".format(subset_name, correct_ratio)
    print(info_log)
    logger.info(info_log)
    
    return correct_ratio


def do_stats_for_tags(tag_seq, subset_name, stat_type):
    flatted_tag_true = [item for sub_list in tag_seq for item in sub_list] #list of tags
    true_tag_set = set(flatted_tag_true)
    for tag in true_tag_set:
        count = 0
        for item in flatted_tag_true:
            if item == tag:
                count += 1
        print("For {} data, the number of {} tag {} : {}".format(subset_name, stat_type, tag, count))
    
    


def tag_count(samples, model, subset_name, args):
    '''
    Take in samples (pages / records), input_encoder, model, output_encoder 
    Get the counts of each tags
    '''
    inputs = [(s.get_x(), s.get_y()) for s in samples]    
    tags = model.evaluate_model(inputs, args)   # list of (list of tags, list of tags)
    tag_pred = [tag[0] for tag in tags]    # list of list of tags
    tag_true = [tag[1] for tag in tags]
    assert len(tag_pred) == len(tag_true)
    
    true_tag_statistics = []
    flatted_tag_true = [item for sub_list in tag_true for item in sub_list] #list of tags
    true_tag_set = set(flatted_tag_true)
    for tag in true_tag_set:
        count = 0
        for item in flatted_tag_true:
            if item == tag:
                count += 1
        true_tag_statistics.append((tag, count))
    for t,c in true_tag_statistics:
        print("For {} data, the number of real tag {} : {}".format(subset_name, t, c))
        
    for x, y in zip(tag_pred, tag_true):
        assert len(x) == len(y)
    correct_pairs = []
    for ps,ts in zip(tag_pred, tag_true):
        for p,t in zip(ps,ts):
            if p == t and t not in config.special_tag_list:
                correct_pairs.append((p,t))
    tag_set = set([item[0] for item in correct_pairs])           
    tag_statistics = []              
    for tag in tag_set:
        count = 0
        for item in correct_pairs:
            if item[1] == tag:
                count += 1
        tag_statistics.append((tag, count))
    for t,c in tag_statistics:
        print("For {} data, the number of correctly predicted tag {} : {}".format(subset_name, t, c))
    return tag_statistics

def load_data_from_pickle(filename, size):
    path = os.path.join(config.DATA_PATH, size)
    return pickle.load(open(os.path.join(path, filename), "rb"))


def get_filename_from_embed_type(embed_type):
    return os.path.join(config.EMBEDDING_PATH,
                        config.EMBEDDING_FILENAME_DICT[embed_type])
