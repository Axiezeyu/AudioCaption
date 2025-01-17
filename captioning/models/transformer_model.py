# -*- coding: utf-8 -*-
import random
import torch
import torch.nn as nn

from captioning.models.base_model import CaptionModel
from captioning.models.utils import repeat_tensor
import captioning.models.decoder


class TransformerModel(CaptionModel):

    def __init__(self, encoder: nn.Module, decoder: nn.Module, **kwargs):
        if not hasattr(self, "compatible_decoders"):
            self.compatible_decoders = (
                captioning.models.decoder.TransformerDecoder,
            )
        super().__init__(encoder, decoder, **kwargs)

    def seq_forward(self, input_dict):
        caps = input_dict["caps"]
        caps_padding_mask = (caps == self.pad_idx).to(caps.device)
        caps_padding_mask = caps_padding_mask[:, :-1]
        output = self.decoder(
            {
                "word": caps[:, :-1],
                "attn_embs": input_dict["attn_embs"],
                "attn_emb_lens": input_dict["attn_emb_lens"],
                "caps_padding_mask": caps_padding_mask
            }
        )
        return output

    def prepare_decoder_input(self, input_dict, output):
        decoder_input = {
            "attn_embs": input_dict["attn_embs"],
            "attn_emb_lens": input_dict["attn_emb_lens"]
        }
        t = input_dict["t"]
        
        ###############
        # determine input word
        ################
        if input_dict["mode"] == "train" and random.random() < input_dict["ss_ratio"]: # training, scheduled sampling
            word = input_dict["caps"][:, :t+1]
        else:
            start_word = torch.tensor([self.start_idx,] * input_dict["attn_embs"].size(0)).unsqueeze(1).long()
            if t == 0:
                word = start_word
            else:
                word = torch.cat((start_word, output["seqs"][:, :t]), dim=-1)
        # word: [N, T]
        decoder_input["word"] = word

        caps_padding_mask = (word == self.pad_idx).to(input_dict["attn_embs"].device)
        decoder_input["caps_padding_mask"] = caps_padding_mask
        return decoder_input

    def prepare_beamsearch_decoder_input(self, input_dict, output_i):
        decoder_input = {}
        t = input_dict["t"]
        i = input_dict["sample_idx"]
        beam_size = input_dict["beam_size"]
        ###############
        # prepare attn embeds
        ################
        if t == 0:
            attn_embs = repeat_tensor(input_dict["attn_embs"][i], beam_size)
            attn_emb_lens = repeat_tensor(input_dict["attn_emb_lens"][i], beam_size)
            output_i["attn_embs"] = attn_embs
            output_i["attn_emb_lens"] = attn_emb_lens
        decoder_input["attn_embs"] = output_i["attn_embs"]
        decoder_input["attn_emb_lens"] = output_i["attn_emb_lens"]
        ###############
        # determine input word
        ################
        start_word = torch.tensor([self.start_idx,] * beam_size).unsqueeze(1).long()
        if t == 0:
            word = start_word
        else:
            word = torch.cat((start_word, output_i["seqs"]), dim=-1)
        decoder_input["word"] = word
        caps_padding_mask = (word == self.pad_idx).to(input_dict["attn_embs"].device)
        decoder_input["caps_padding_mask"] = caps_padding_mask

        return decoder_input


class M2TransformerModel(CaptionModel):

    def __init__(self, encoder: nn.Module, decoder: nn.Module, **kwargs):
        if not hasattr(self, "compatible_decoders"):
            self.compatible_decoders = (
                captioning.models.decoder.M2TransformerDecoder
            )
        super().__init__(encoder, decoder, **kwargs)
        self.check_encoder_compatibility()

    def check_encoder_compatibility(self):
        assert isinstance(self.encoder, captioning.models.encoder.M2TransformerEncoder), \
            f"only M2TransformerModel is compatible with {self.__class__.__name__}"


    def seq_forward(self, input_dict):
        caps = input_dict["caps"]
        output = self.decoder(
            {
                "word": caps[:, :-1],
                "attn_embs": input_dict["attn_embs"],
                "attn_emb_mask": input_dict["attn_emb_mask"],
            }
        )
        return output

    def prepare_decoder_input(self, input_dict, output):
        decoder_input = {
            "attn_embs": input_dict["attn_embs"],
            "attn_emb_mask": input_dict["attn_emb_mask"]
        }
        t = input_dict["t"]
        
        ###############
        # determine input word
        ################
        if input_dict["mode"] == "train" and random.random() < input_dict["ss_ratio"]: # training, scheduled sampling
            word = input_dict["caps"][:, :t+1]
        else:
            start_word = torch.tensor([self.start_idx,] * input_dict["attn_embs"].size(0)).unsqueeze(1).long()
            if t == 0:
                word = start_word
            else:
                word = torch.cat((start_word, output["seqs"][:, :t]), dim=-1)
        # word: [N, T]
        decoder_input["word"] = word

        return decoder_input

    def prepare_beamsearch_decoder_input(self, input_dict, output_i):
        decoder_input = {}
        t = input_dict["t"]
        i = input_dict["sample_idx"]
        beam_size = input_dict["beam_size"]
        ###############
        # prepare attn embeds
        ################
        if t == 0:
            attn_embs = repeat_tensor(input_dict["attn_embs"][i], beam_size)
            attn_emb_mask = repeat_tensor(input_dict["attn_emb_mask"][i], beam_size)
            output_i["attn_embs"] = attn_embs
            output_i["attn_emb_mask"] = attn_emb_mask
        decoder_input["attn_embs"] = output_i["attn_embs"]
        decoder_input["attn_emb_mask"] = output_i["attn_emb_mask"]
        ###############
        # determine input word
        ################
        start_word = torch.tensor([self.start_idx,] * beam_size).unsqueeze(1).long()
        if t == 0:
            word = start_word
        else:
            word = torch.cat((start_word, output_i["seqs"]), dim=-1)
        decoder_input["word"] = word

        return decoder_input


class EventEncoder(nn.Module):
    """
    Encode the Label information in AudioCaps and AudioSet
    """
    def __init__(self, emb_dim, vocab_size=527):
        super(EventEncoder, self).__init__()
        self.label_embedding = nn.Parameter(
            torch.randn((vocab_size, emb_dim)), requires_grad=True)
        
    def forward(self, word_idxs):
        indices = word_idxs / word_idxs.sum(dim=1, keepdim=True)
        embeddings = indices @ self.label_embedding
        return embeddings


class EventCondTransformerModel(TransformerModel):

    def __init__(self, encoder: nn.Module, decoder: nn.Module, **kwargs):
        if not hasattr(self, "compatible_decoders"):
            self.compatible_decoders = (
                captioning.models.decoder.EventTransformerDecoder
            )
        super().__init__(encoder, decoder, **kwargs)
        self.label_encoder = EventEncoder(decoder.emb_dim, 527)
        self.train_forward_keys += ["events"]
        self.inference_forward_keys += ["events"]

    # def seq_forward(self, input_dict):
        # caps = input_dict["caps"]
        # caps_padding_mask = (caps == self.pad_idx).to(caps.device)
        # caps_padding_mask = caps_padding_mask[:, :-1]
        # output = self.decoder(
            # {
                # "word": caps[:, :-1],
                # "attn_embs": input_dict["attn_embs"],
                # "attn_emb_lens": input_dict["attn_emb_lens"],
                # "caps_padding_mask": caps_padding_mask
            # }
        # )
        # return output

    def prepare_decoder_input(self, input_dict, output):
        decoder_input = super().prepare_decoder_input(input_dict, output)
        decoder_input["events"] = self.label_encoder(input_dict["events"])
        return decoder_input

    def prepare_beamsearch_decoder_input(self, input_dict, output_i):
        decoder_input = super().prepare_beamsearch_decoder_input(input_dict, output_i)
        t = input_dict["t"]
        i = input_dict["sample_idx"]
        beam_size = input_dict["beam_size"]
        if t == 0:
            output_i["events"] = repeat_tensor(self.label_encoder(input_dict["events"])[i], beam_size)
        decoder_input["events"] = output_i["events"]
        return decoder_input


class KeywordCondTransformerModel(TransformerModel):

    def __init__(self, encoder: nn.Module, decoder: nn.Module, **kwargs):
        if not hasattr(self, "compatible_decoders"):
            self.compatible_decoders = (
                captioning.models.decoder.KeywordProbTransformerDecoder,
            )
        super().__init__(encoder, decoder, **kwargs)
        self.train_forward_keys += ["keywords"]
        self.inference_forward_keys += ["keywords"]

    def seq_forward(self, input_dict):
        caps = input_dict["caps"]
        caps_padding_mask = (caps == self.pad_idx).to(caps.device)
        caps_padding_mask = caps_padding_mask[:, :-1]
        keywords = input_dict["keywords"]
        output = self.decoder(
            {
                "word": caps[:, :-1],
                "attn_embs": input_dict["attn_embs"],
                "attn_emb_lens": input_dict["attn_emb_lens"],
                "keywords": keywords,
                "caps_padding_mask": caps_padding_mask
            }
        )
        return output

    def prepare_decoder_input(self, input_dict, output):
        decoder_input = super().prepare_decoder_input(input_dict, output)
        decoder_input["keywords"] = input_dict["keywords"]
        return decoder_input

    def prepare_beamsearch_decoder_input(self, input_dict, output_i):
        decoder_input = super().prepare_beamsearch_decoder_input(input_dict, output_i)
        t = input_dict["t"]
        i = input_dict["sample_idx"]
        beam_size = input_dict["beam_size"]
        if t == 0:
            output_i["keywords"] = repeat_tensor(input_dict["keywords"][i],
                                                 beam_size)
        decoder_input["keywords"] = output_i["keywords"]
        return decoder_input

