#!/usr/bin/env python
# vim: set fileencoding=utf-8
from __future__ import unicode_literals

import re
from itertools import takewhile

from six.moves import filter, filterfalse

from regulations.generator import node_types
from regulations.generator.layers.layers_applier import LayersApplier
from regulations.generator.layers.internal_citation import (
    InternalCitationLayer)
from regulations.apps import RegulationsConfig
from .link_flattener import flatten_links


class HTMLBuilder(object):
    # @todo simplify this constructor
    def __init__(self, inline_applier, p_applier, search_applier,
                 diff_applier=None):
        self.tree = None
        self.inline_applier = inline_applier
        self.p_applier = p_applier
        self.search_applier = search_applier
        self.diff_applier = diff_applier

    def generate_html(self):
        if self.diff_applier:
            self.diff_applier.tree_changes(self.tree)
        for layer in self.p_applier.layers.values():
            if hasattr(layer, 'preprocess_root'):   # @todo - remove
                layer.preprocess_root(self.tree)
        self.process_node(self.tree)

    def list_level(self, parts, node_type):
        return len(parts) - 2

    def process_node_title(self, node):
        if 'title' in node:
            node['header'] = node['title']
            if self.diff_applier:
                node['header'] = self.diff_applier.apply_diff(
                    node['header'], node['label_id'], component='title')

    @staticmethod
    def is_collapsed(node):
        """A "collapsed" paragraph is one which has no text, immediately
        starting a subparagraph. For example:
        (a)(1) Some text    <- (a) is collapsed
        (a) Some text - (1) Other text   <- (a) is not collapsed
        """
        marker = '({})'.format(node['label'][-1])
        text_without_marker = node['text'].replace(marker, '')
        return node['text'].strip() and not text_without_marker.strip()

    def process_node(self, node):
        """Every node passes through this function on the way to being
        rendered. Importantly, this adds the `marked_up` field, which contains
        the HTML version of node's text (after applying all relevant
        layers) and the `template_name` field, which defines how this node
        should be rendered."""

        node['label_id'] = '-'.join(node['label'])
        self.process_node_title(node)
        node['is_collapsed'] = self.is_collapsed(node)

        node['html_label'] = node_types.to_markup_id(node['label'])
        node['markup_id'] = "-".join(node['html_label'])
        node['tree_level'] = len(node['label']) - 1
        node['human_label'] = self.human_label(node)

        node['list_level'] = self.list_level(node['label'], node['node_type'])

        if len(node['text']):
            inline_elements = self.inline_applier.get_layer_pairs(
                node['label_id'], node['text'])
            search_elements = self.search_applier.get_layer_pairs(
                node['label_id'])

            if self.diff_applier:
                node['marked_up'] = self.diff_applier.apply_diff(
                    node['text'], node['label_id'])

            layers_applier = LayersApplier()
            layers_applier.enqueue_from_list(inline_elements)
            layers_applier.enqueue_from_list(search_elements)

            node['marked_up'] = layers_applier.apply_layers(
                node.get('marked_up', node['text']))
            node['marked_up'] = flatten_links(node['marked_up'])

        node = self.p_applier.apply_layers(node)

        node['template_name'] = RegulationsConfig.custom_tpls.get(
            node['label_id'],
            RegulationsConfig.node_type_tpls[node['node_type'].lower()])

        for c in node['children']:
            self.process_node(c)

    @staticmethod
    def human_label(node):
        """Derive a human-readable description for this node"""
        return '-'.join(node['label'])      # Default


class CFRHTMLBuilder(HTMLBuilder):
    SECTION_NUMBER_REGEX = re.compile(r'(§+)\s+')
    DOC_TITLE_REGEX = re.compile(r'\(.+\)$')

    @classmethod
    def section_space(cls, text):
        """ After a section sign, insert a non-breaking space. """
        return cls.SECTION_NUMBER_REGEX.sub(r'\1&nbsp;', text)

    def get_title(self):
        titles = {
            'part': self.tree['label'][0],
            'reg_name': ''
        }
        reg_title = self.parse_doc_title(self.tree['title'])
        if reg_title:
            titles['reg_name'] = reg_title
        return titles

    def parse_doc_title(self, reg_title):
        match = self.DOC_TITLE_REGEX.search(reg_title)
        if match:
            return match.group(0)

    def list_level(self, parts, node_type):
        """ Return the list level and the list type. Overrides"""
        if node_type == node_types.INTERP:
            prefix_length = parts.index('Interp')+1
        elif node_type == node_types.APPENDIX:
            prefix_length = 3
        else:
            prefix_length = 2

        if len(parts) > prefix_length:
            return len(parts) - prefix_length
        return 0

    def process_node_title(self, node):
        """Add space to header. Overrides"""
        super(CFRHTMLBuilder, self).process_node_title(node)
        if 'header' in node:
            node['header'] = self.section_space(node['header'])

    def process_node(self, node):
        """Overrides with custom, additional processing"""
        super(CFRHTMLBuilder, self).process_node(node)
        if 'marked_up' in node:
            node['marked_up'] = self.section_space(node['marked_up'])

        if 'TOC' in node:
            for l in node['TOC']:
                l['label'] = self.section_space(l['label'])

        if 'interp' in node and 'markup' in node['interp']:
            node['interp']['markup'] = self.section_space(
                node['interp']['markup'])

        if node['node_type'] == node_types.INTERP:
            self.modify_interp_node(node)

    def modify_interp_node(self, node):
        """Add extra fields which only exist on interp nodes"""
        #   ['105', '22', 'Interp'] => section header
        node['section_header'] = len(node['label']) == 3

        is_header = lambda child: child['label'][-1] == 'Interp'
        node['header_children'] = list(filter(is_header, node['children']))
        node['par_children'] = list(filterfalse(is_header, node['children']))
        if 'header' in node:
            node['header_markup'] = node['header']
            citation = list(takewhile(lambda p: p != 'Interp',
                                      node['label']))
            icl = self.inline_applier.layers.get(
                InternalCitationLayer.shorthand)
            if icl and len(citation) > 2:
                text = '%s(%s)' % (citation[1], ')('.join(citation[2:]))
                node['header_markup'] = node['header_markup'].replace(
                    text, icl.render_url(citation, text))

    @staticmethod
    def human_label(node):
        """Derive a human-readable description for this node. Override"""
        return node_types.label_to_text(node['label'])


class PreambleHTMLBuilder(HTMLBuilder):
    @staticmethod
    def human_label(node):
        """Derive a human-readable description for this node. Override"""
        is_markerless = node_types.MARKERLESS_REGEX.match
        prefix = list(takewhile(lambda l: not is_markerless(l),
                                node['label']))
        if len(prefix) > 1:
            return 'Section ' + '.'.join(prefix[1:])
        else:
            return 'FR #' + prefix[0]
