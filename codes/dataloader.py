#!/usr/bin/python3

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import torch

from torch.utils.data import Dataset

class TrainDataset(Dataset):
    def __init__(self, triples, nentity, nrelation, negative_sample_size, pair_sample_size, mode, multi_path):
        self.len = len(triples)
        self.triples = triples
        self.triple_set = set(triples)
        self.nentity = nentity
        self.nrelation = nrelation
        self.negative_sample_size = negative_sample_size
        self.pair_sample_size = pair_sample_size
        self.mode = mode
        self.count = self.count_frequency(triples)
        self.true_head, self.true_tail = self.get_true_head_and_tail(self.triples)
        self.rel_head, self.rel_tail = self.get_relation2headtail(self.triples)
        
        if multi_path is not None:
            self.path_probs, self.path_confidence, self.max_n_cand, self.max_steps = multi_path
            self.multi_path = True
        else:
            self.multi_path = False
        
    def __len__(self):
        return self.len
    
    def __getitem__(self, idx):
        positive_sample = self.triples[idx]
        head, relation, tail = positive_sample

        subsampling_weight = self.count[(head, relation)] + self.count[(tail, -relation-1)]
        subsampling_weight = torch.sqrt(1 / torch.Tensor([subsampling_weight]))
        
        negative_sample_list = []
        negative_sample_size = 0

        while negative_sample_size < self.negative_sample_size:
            negative_sample = np.random.randint(self.nentity, size=self.negative_sample_size*2)
            if self.mode == 'head-batch':
                mask = np.in1d(
                    negative_sample, 
                    self.true_head[(relation, tail)], 
                    assume_unique=True, 
                    invert=True
                )
            elif self.mode == 'tail-batch':
                mask = np.in1d(
                    negative_sample, 
                    self.true_tail[(head, relation)], 
                    assume_unique=True, 
                    invert=True
                )
            else:
                raise ValueError('Training batch mode %s not supported' % self.mode)
            negative_sample = negative_sample[mask]
            negative_sample_list.append(negative_sample)
            negative_sample_size += negative_sample.size
        
        if self.multi_path:
            weak_positive = []
            rel_paths = []
            for i in range(len(self.path_probs[idx])):
                rel_path, prob = self.path_probs[idx][i]
                path_str = ' '.join(map(str, rel_path))
                weak_positive += rel_path
                
                confidence = 0.0
                if (path_str, relation) in self.path_confidence:
                    confidence = self.path_confidence[(path_str, relation)]
                confidence = 0.99*confidence + 0.01
                reliability = prob*confidence
                rel_paths.append(rel_path + [reliability])
            rel_paths.sort(key=lambda x: x[-1], reverse=True)
            
            rel_paths_for_batch = []
            probs_for_batch = []
            if len(rel_paths)==0:
                rel_paths_for_batch = torch.zeros(self.max_n_cand, self.max_steps) - 1
                probs_for_batch = torch.zeros(self.max_n_cand)
            else:
                for i in range(min(len(rel_paths), self.max_n_cand)):
                    probs_for_batch.append(rel_paths[i][-1])
                    rel_path = rel_paths[i][:-1]
                    if len(rel_path) < self.max_steps:
                        rel_path += [-1]*(self.max_steps - len(rel_path))
                    elif len(rel_path) > self.max_steps:
                        rel_path = rel_path[:self.max_steps]
                    rel_paths_for_batch.append(rel_path)
                
                if len(rel_paths_for_batch) != self.max_n_cand:
                    rel_paths_for_batch += [[-1]*self.max_steps]*(self.max_n_cand-len(rel_paths_for_batch))
                    probs_for_batch += [0.0]*(self.max_n_cand-len(probs_for_batch))
                    
                rel_paths_for_batch = torch.LongTensor(np.array(rel_paths_for_batch))
                probs_for_batch = torch.from_numpy(np.array(probs_for_batch))
                
            # Negative relation sampling
            while True:
                negative_relation = np.random.randint(self.nrelation, size=4)
                mask = np.in1d(
                    negative_relation,
                    np.array(list(set([relation] + weak_positive))),
                    assume_unique=True,
                    invert=True,
                )
                negative_relation = negative_relation[mask]
                if np.sum(mask) >= 1:
                    break
            negative_relation = torch.from_numpy(negative_relation[:1])
                    
        negative_sample = np.concatenate(negative_sample_list)[:self.negative_sample_size]
        negative_sample = torch.from_numpy(negative_sample)
        positive_sample = torch.LongTensor(positive_sample)

        negative_pair_list = []
        pair_sample_size = 0

        while pair_sample_size < self.pair_sample_size:
            negative_pair_sample = np.random.randint(self.nentity, size=self.pair_sample_size*2)
            if self.mode == 'head-batch':
                mask = np.in1d(
                    negative_pair_sample, 
                    self.rel_head[relation], 
                    assume_unique=False, 
                    invert=True
                )
            elif self.mode == 'tail-batch':
                mask = np.in1d(
                    negative_pair_sample, 
                    self.rel_tail[relation], 
                    assume_unique=False, 
                    invert=True
                )
            else:
                raise ValueError('Training batch mode %s not supported' % self.mode)
            negative_pair_sample = negative_pair_sample[mask]
            negative_pair_list.append(negative_pair_sample)
            pair_sample_size += negative_pair_sample.size
        
        negative_pair_sample = np.concatenate(negative_pair_list)[:self.pair_sample_size]

        negative_pair_sample = torch.from_numpy(negative_pair_sample)

        #print("negative_pair_sample: {}".format(negative_pair_sample))

        positive_pair_list = []
        pair_sample_size = 0

        if self.mode == 'head-batch':
            if (len(self.rel_head[relation]) < self.pair_sample_size):
                rel_head_repeat = np.tile(self.rel_head[relation], self.pair_sample_size)
                positive_pair_sample = np.random.choice(rel_head_repeat, size=self.pair_sample_size)
            else:
                positive_pair_sample = np.random.choice(self.rel_head[relation], size=self.pair_sample_size)

        elif self.mode == 'tail-batch':
            if (len(self.rel_tail[relation]) < self.pair_sample_size):
                rel_tail_repeat = np.tile(self.rel_tail[relation], self.pair_sample_size)
                positive_pair_sample = np.random.choice(rel_tail_repeat, size=self.pair_sample_size)
            else:
                positive_pair_sample = np.random.choice(self.rel_tail[relation], size=self.pair_sample_size)

        '''
        if (self.mode == 'head-batch'):
            if (len(self.rel_head[relation]) < self.pair_sample_size):
                print(len(self.rel_head[relation]))
                positive_pair_list = np.array(self.rel_head[relation] * self.pair_sample_size)
                positive_pair_sample = positive_pair_list[:self.pair_sample_size]
                positive_pair_sample = torch.from_numpy(positive_pair_sample)
                return positive_sample, negative_sample, subsampling_weight, self.mode, positive_pair_sample, negative_pair_sample

        if (self.mode == 'tail-batch'):
            if (len(self.rel_tail[relation]) < self.pair_sample_size):
                print(len(self.rel_tail[relation]))
                positive_pair_list = np.array(self.rel_tail[relation] * self.pair_sample_size)
                positive_pair_sample = positive_pair_list[:self.pair_sample_size]
                positive_pair_sample = torch.from_numpy(positive_pair_sample)
                return positive_sample, negative_sample, subsampling_weight, self.mode, positive_pair_sample, negative_pair_sample
        '''
        '''
        while pair_sample_size < self.pair_sample_size:
            if self.mode == 'head-batch':
#                print("\nhead-batch:")
                if (len(self.rel_head[relation]) < self.pair_sample_size * 2):
                    rel_head_repeat = self.rel_head[relation] * self.pair_sample_size * 2
#                    print("rel_head_repeat")
                    positive_pair_sample = np.random.choice(rel_head_repeat, size=self.pair_sample_size*2)
#                    print("positive_pair_sample choose from repeat")
                else:
                    positive_pair_sample = np.random.choice(self.rel_head[relation], size=self.pair_sample_size*2)
#                    print("positive_pair_sample choose from rel_head")

            elif self.mode == 'tail-batch':
                if (len(self.rel_tail[relation]) < self.pair_sample_size * 2):
                    rel_tail_repeat = self.rel_tail[relation] * self.pair_sample_size * 2
#                    print("rel_tail_repeat")
                    positive_pair_sample = np.random.choice(rel_tail_repeat, size=self.pair_sample_size*2)
#                    print("positive_pair_sample choose from repeat")
                else:
                    positive_pair_sample = np.random.choice(self.rel_tail[relation], size=self.pair_sample_size*2)
#                    print("positive_pair_sample choose from rel_tail")

            print("positive_pair_sample: {}".format(positive_pair_sample))

            if self.mode == 'head-batch':
                mask = np.in1d(
                    positive_pair_sample, 
                    self.rel_head[relation], 
                    assume_unique=False, 
                    invert=False
                )
            elif self.mode == 'tail-batch':
                mask = np.in1d(
                    positive_pair_sample, 
                    self.rel_tail[relation], 
                    assume_unique=False, 
                    invert=False
                )
            else:
                raise ValueError('Training batch mode %s not supported' % self.mode)
            positive_pair_sample = positive_pair_sample[mask]
            positive_pair_list.append(positive_pair_sample)
            pair_sample_size += positive_pair_sample.size
        
        positive_pair_sample = np.concatenate(positive_pair_list)[:self.pair_sample_size]
        '''
        positive_pair_sample = torch.from_numpy(positive_pair_sample)
        #print("positive_pair_sample: {}".format(positive_pair_sample))
        
        if self.multi_path:
            return positive_sample, negative_sample, subsampling_weight, self.mode, positive_pair_sample, negative_pair_sample, negative_relation, rel_paths_for_batch, probs_for_batch

        return positive_sample, negative_sample, subsampling_weight, self.mode, positive_pair_sample, negative_pair_sample
    
    @staticmethod
    def collate_fn(data):
        positive_sample = torch.stack([_[0] for _ in data], dim=0)
        negative_sample = torch.stack([_[1] for _ in data], dim=0)
        subsample_weight = torch.cat([_[2] for _ in data], dim=0)
        mode = data[0][3]
        positive_pair_sample = torch.stack([_[4] for _ in data], dim=0)
        negative_pair_sample = torch.stack([_[5] for _ in data], dim=0)
        
        return positive_sample, negative_sample, subsample_weight, mode, positive_pair_sample, negative_pair_sample
    
    @staticmethod
    def collate_fn_multi_path(data):
        positive_sample = torch.stack([_[0] for _ in data], dim=0)
        negative_sample = torch.stack([_[1] for _ in data], dim=0)
        subsample_weight = torch.cat([_[2] for _ in data], dim=0)
        mode = data[0][3]
        positive_pair_sample = torch.stack([_[4] for _ in data], dim=0)
        negative_pair_sample = torch.stack([_[5] for _ in data], dim=0)
        
        negative_relation = torch.stack([_[6] for _ in data], dim=0)
        rel_paths = torch.stack([_[7] for _ in data], dim=0)
        probs = torch.stack([_[8] for _ in data], dim=0)
        
        return positive_sample, negative_sample, subsample_weight, mode, positive_pair_sample, negative_pair_sample, negative_relation, rel_paths, probs
    
    @staticmethod
    def count_frequency(triples, start=4):
        '''
        Get frequency of a partial triple like (head, relation) or (relation, tail)
        The frequency will be used for subsampling like word2vec
        '''
        count = {}
        for head, relation, tail in triples:
            if (head, relation) not in count:
                count[(head, relation)] = start
            else:
                count[(head, relation)] += 1

            if (tail, -relation-1) not in count:
                count[(tail, -relation-1)] = start
            else:
                count[(tail, -relation-1)] += 1
        return count
    
    @staticmethod
    def get_true_head_and_tail(triples):
        '''
        Build a dictionary of true triples that will
        be used to filter these true triples for negative sampling
        '''
        
        true_head = {}
        true_tail = {}

        for head, relation, tail in triples:
            if (head, relation) not in true_tail:
                true_tail[(head, relation)] = []
            true_tail[(head, relation)].append(tail)
            if (relation, tail) not in true_head:
                true_head[(relation, tail)] = []
            true_head[(relation, tail)].append(head)

        for relation, tail in true_head:
            true_head[(relation, tail)] = np.array(list(set(true_head[(relation, tail)])))
        for head, relation in true_tail:
            true_tail[(head, relation)] = np.array(list(set(true_tail[(head, relation)])))                 

        return true_head, true_tail

    @staticmethod
    def get_relation2headtail(triples):
        rel_head = {}
        rel_tail = {}
        
        for head, relation, tail in triples:
            if (relation not in rel_head):
                rel_head[relation] = []
            if (relation not in rel_tail):
                rel_tail[relation] = []
            if (head not in rel_head[relation]):
                rel_head[relation].append(head)
            if (tail not in rel_tail[relation]):
                rel_tail[relation].append(tail)

        for relation in rel_head:
            rel_head[relation] = np.array(list(set(rel_head[relation])))
            rel_tail[relation] = np.array(list(set(rel_tail[relation])))

        return rel_head, rel_tail
    
class TestDataset(Dataset):
    def __init__(self, triples, all_true_triples, nentity, nrelation, mode):
        self.len = len(triples)
        self.triple_set = set(all_true_triples)
        self.triples = triples
        self.nentity = nentity
        self.nrelation = nrelation
        self.mode = mode

    def __len__(self):
        return self.len
    
    def __getitem__(self, idx):
        head, relation, tail = self.triples[idx]

        if self.mode == 'head-batch':
            tmp = [(0, rand_head) if (rand_head, relation, tail) not in self.triple_set
                   else (-1, head) for rand_head in range(self.nentity)]
            tmp[head] = (0, head)
        elif self.mode == 'tail-batch':
            tmp = [(0, rand_tail) if (head, relation, rand_tail) not in self.triple_set
                   else (-1, tail) for rand_tail in range(self.nentity)]
            tmp[tail] = (0, tail)
        else:
            raise ValueError('negative batch mode %s not supported' % self.mode)
            
        tmp = torch.LongTensor(tmp)            
        filter_bias = tmp[:, 0].float()
        negative_sample = tmp[:, 1]

        positive_sample = torch.LongTensor((head, relation, tail))
            
        return positive_sample, negative_sample, filter_bias, self.mode
    
    @staticmethod
    def collate_fn(data):
        positive_sample = torch.stack([_[0] for _ in data], dim=0)
        negative_sample = torch.stack([_[1] for _ in data], dim=0)
        filter_bias = torch.stack([_[2] for _ in data], dim=0)
        mode = data[0][3]
        return positive_sample, negative_sample, filter_bias, mode
    
class BidirectionalOneShotIterator(object):
    def __init__(self, dataloader_head, dataloader_tail):
        self.iterator_head = self.one_shot_iterator(dataloader_head)
        self.iterator_tail = self.one_shot_iterator(dataloader_tail)
        self.step = 0
        
    def __next__(self):
        self.step += 1
        if self.step % 2 == 0:
            data = next(self.iterator_head)
        else:
            data = next(self.iterator_tail)
        return data
    
    @staticmethod
    def one_shot_iterator(dataloader):
        '''
        Transform a PyTorch Dataloader into python iterator
        '''
        while True:
            for data in dataloader:
                yield data
