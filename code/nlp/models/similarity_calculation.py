# -*- coding: utf-8 -*-

"""Analyze the similarity between a message and a topic

.. module:: nlp.model.similarity_calculator
   :platform: Unix, Windows
   :synopsis: Measure message-topic similarity

.. |message| replace:: :class:`nlp.text.message.Message`
.. |topic| replace:: :class:`nlp.text.topic.Topic`
.. |window| replace:: :class:`nlp.text.window.Window`
.. |tokenizer| replace:: :class:`nlp.text.grammar.tokenizer`
.. |nparray| replace:: `Numpy Array <https://docs.scipy.org/doc/numpy/reference/generated/numpy.array.html>`_
"""

import sys
import math
import numpy as np
import gensim

# For our internal toolbox imports
import os, sys
path_to_here = os.path.abspath('.')
sys.path.append(path_to_here[:path_to_here.index('code')+4])

from nlp.geometry import dist as gd
from nlp.geometry.repr import GloVe
from nlp.geometry.repr import list_corpora as list_representations
from nlp.grammar.tokenizer import SimpleCleaner


def list_distances():
    """Lists the distances available

    Returns
    -------
    list[str]
        List of distances available
    """
    return filter( lambda x: (not x.startswith('__')) and (x not in  ['np', 'entropy']) , dir(gd) )


class MessageSimilarity(object):
    """Callable object that calculates message-to-message similarity

    Attributes
    ----------
    cleaner : callable
        Text cleaner (for removing symbols, stopwrods, etc...)
    dist : callable
        Callable object that calculates a multi-dimensional distance (for the geometric embeddings of each message)
    repr : callable
        Callable object that returns geometric representation of the passed text
    """
    def __init__(self, cleaner=None, representation=None, distance=None):

        self.cleaner = cleaner if cleaner is not None else SimpleCleaner()

        # Set representation
        if representation is None:
            self.repr = self.get_repr()  # default
        else:
            if hasattr(representation, '__call__'):
                self.repr = cleaner
            else:
                self.repr = self.get_repr(representation)

        # Set distance
        if distance is None:
            self.dist = self.get_dist()  # default
        else:
            if hasattr(distance, '__call__'):
                self.dist = cleaner
            else:
                self.dist = self.get_dist(distance)

    @staticmethod
    def get_dist(dist_id='cosine'):
        """Load the distance callable and return it

        Parameters
        ----------
        dist_id : str ,  optional
            Identifier of the distance object (to obtain a list of the available id's run `list_distances()`)
            Defaults to 'cosine'

        Returns
        -------
        callable
            Distance calculator

        Raises
        ------
        ValueError
            If the specified distance is not found
        """
        if dist_id not in list_distances():
            raise ValueError('The distance {} was not found, use `list_distances()` to check which are available on your machine'.format(dist_id))

        return eval( 'gd.{}'.format(dist_id) )

    @staticmethod
    def get_repr(repr_id='glove.6B.100d.txt'):
        """Load the representation callable and return it

        Parameters
        ----------
        repr_id : str, optional
            Identifier of the geometric representation object (to obtain a list of the available id's run `list_representations()`)
            Defaults to 'glove.6B.100d.txt'

        Returns
        -------
        callable
            Representation callable object

        Raises
        ------
        ValueError
            If the specified geometric representation is not found
        """
        print ' -- Loading GloVe, this might take a few (10~30) seconds... -- \n'
        try:
            glove = GloVe(repr_id)
        except:
            raise ValueError('Fail on loading the representation... Check if the representation is available with `list_representations()`')

        return glove

    def __call__(self, m1, m2):
        """Similarity between two texts

        Parameters
        ----------
        m1 : str
            Text #1
        m2 : str
            Text #2

        Returns
        -------
        float
            Similarity between texts
        """
        # tokenize
        text1 = self.cleaner(m1)
        text2 = self.cleaner(m2)

        # get geometric representation
        rep1 = self.repr(text1)
        rep2 = self.repr(text2)

        return self.dist(rep1, rep2)


class SimilarTopicCalculator:
    """Processes messages a calculates similarity to a |window| of |topic|s

    Attributes
    ----------
    representation : callable
        Callable that returns a messages representation
    similarity : callable
        Callable that returns a float when called over two representations
    tokenizer : callable, optional
        Message tokenizer

    Raises
    ------
    AttributeError
        If representation or similarity are not callable objects. Will also raise if tokenizer is not None nor callable.
    """

    def __init__(self, representation, similarity, tokenizer=None):
        if not hasattr(representation, '__call__'):
            raise AttributeError('representation needs to be a callable object')
        self.representation = representation

        if not hasattr(similarity, '__call__'):
            raise AttributeError('similarity needs to be a callable object')
        self.similarity = similarity

        if (tokenizer is not None) and not hasattr(tokenizer, '__call__'):
            raise AttributeError('tokenizer needs to be a callable object or None')
        self.tokenizer = tokenizer

    @property
    def has_tokenizer(self):
        """Does the similarity calculator have a tokenizer

        Returns
        -------
        bool
            True if messages will be tokenized
        """
        return self.tokenizer is not None

    def get_similarities(self, window, message):
        """Calculates the similarity of the |message| with the |topic|s in the |window|

        Parameters
        ----------
        window : |window|
            Window of |topic|s to which the mesage will be added to
        message : |message|
            Message to calculate the similarity

        Returns
        -------
        list[float]
            List of the similarities of the |message| with each of the |topic|s in the |window|
        """
        similarities = []

        for topic in window.topics:

            # get centroid of the topic
            centroid = self.calculate_centroid(topic)

            # get similarity with centroid
            similarities.append( self.similarity(centroid, message.text_repr) )

        return similarities

    def calculate_centroid(self, topic):  # NOTE: might want to implement top 5% later...
        """Calculate the centroid of the topic based on the message representations

        Parameters
        ----------
        topic : |topic|
            Topic to calculate the centroid

        Returns
        -------
        |nparray|
            Geometric centroid of the geometric representations
        """
        proc = self.get_processor()  # obtain processor in case necessary
        pre_centroid = np.zeros_like( topic.start_message.text_repr )

        for topic_message in topic.messages:
            # check if message was processed, process if necessary
            if not topic_message.is_processed:
                topic_message.process( proc )

            # update centroid based on the text_repr
            pre_centroid += topic_message.text_repr

        pre_centroid /= len(topic)

        return pre_centroid

    def get_processor(self):
        """Produces a message processor according to the specified similarity_calculator

        Returns
        -------
        callable
            Message processing function. The processor will have an internal additional attribute `__id` with the processor specifications
        """
        def processor(message_text):
            """Proccesses the message according to

            Parameters
            ----------
            message : str
                Message text

            Returns
            -------
            numpy.array(float)
                representation of the message
            """
            if self.has_tokenizer:
                message = self.tokenizer(message_text)  # the tokenizer is a callable object
            return self.representation(message_text)  # the representation is a callable object
            processor.__id = 't:{tok!s}#r:{rep!s}'.format(tok=self.tokenizer, rep=self.representation)
        return processor


class TopicSimilarity:
    def __init__(self, topic, score, centroidDistance):
        self.topic = topic
        self.score = score
        self.centroidDistance = centroidDistance
