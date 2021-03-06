# -*- coding: utf-8 -*-

"""Slack topic implementation for Slack-Pack Topic Summarizer

.. module:: nlp.text.topic
   :platform: Unix, Windows
   :synopsis: Topic object

.. |message| replace:: :class:`nlp.text.message.Message`
.. |topic| replace:: :class:`nlp.text.topic.Topic`

"""


class Topic:
    """Slack conversation topic: subset of highly-related messages

    Attributes
    ----------
    start_message : :class:`nlp.text.message.Message`
        First message of the topic
    messages : list[|message|]
        List of Message was added to the topic
    reasons : list[str]
        List of the rationales why the messages were added to the topic

    """

    def __init__(self, start_message, reason):
        self.start_message = start_message
        self.messages = [self.start_message, ]
        self.reasons = [reason, ]
        self.last_timestamp = start_message.timestamp
        # TODO: possible summary

    def append_message(self, message, reason):
        """Add a message into the topic

        Parameters
        ----------
        message : |message|
            Message to be appended
        reason : str
            Reason as to why this message is being appended

        """
        self.messages.append(message)
        self.reasons.append(reason)
        self.last_timestamp = message.timestamp

    @property
    def size(self):
        """Topic message-length

        Returns
        -------
        int
            Amount of messages in the topic
        """
        return len(self.messages)

    def absorb(self, other_topic):
        """Absorb another topic

        Parameters
        ----------
        other_topic : |topic|
            Topic to be absorbed

        """
        self.messages = self.messages + other.messages
        self.messages.sort(key=lambda msg: msg.id)
        self.reasons.extend( other.reasons )  # append reasons from other topic

    def get_starter_url(self):
        """Returns the topic's starter message URL for go-to link creation

        Returns
        -------
        str
            URL for the topic's starter message
        """
        return self.start_message.url

    def __getitem__(self, item):
        return self.messages[item]

    def __len__(self):
        """Length of the topic (number of messages)

        Returns
        -------
        int
            Number of messages in the topic
        """
        return len(self.messages)

    def __iter__(self):
        """Iterates over the messages

        Yields
        -------
        |message|
            Next message to be iterated over
        """
        for message in self.messages:
            yield message

    def report_messages(self):
        """Prints out the messages along with the reason as to why they were appended
        """
        for i,(m,r) in enumerate(zip(self.messages, self.reasons)):
            print '{} -- {}\n\t\033[33m{}\033[0m\n\n'.format(i,r,m.text)
