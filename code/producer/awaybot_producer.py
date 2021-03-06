# -*- coding: utf-8 -*-



"""
  Implements a class called AwaybotProducer. Fetches
  messages from the Slack Real Time Messaging API
  and publishes them to a kafka topic using
  python-kafka. For each message, the latest
  timestamp of the last produced message is recorded
  in Simple DB.



.. module:: awaybot_producer

  :platform: Unix, Windows

  :synopsis: Slack RTM API, python-kafka, KafkaProducer, SimpleDB

"""


from slackclient import SlackClient
from kafka import KafkaClient, KafkaConsumer, KafkaProducer
import logging
import logging.handlers
import time
import os
import boto3
import sys
import uuid
import datetime
import json

logger = logging.getLogger('awaybot_producer_logger')
logger.setLevel(logging.DEBUG)
LOGFILE = 'log/awaybot_producer'

# create formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# create console handler, set level of logging and add formatter
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(formatter)

# create file handler, set level of logging and add formatter
fh = logging.handlers.TimedRotatingFileHandler(LOGFILE, when='M', interval=1)
fh.setLevel(logging.DEBUG)
fh.setFormatter(formatter)
fh.suffix = '%Y-%m-%d_%H-%M-%S.log'

# add handlers to logger
logger.addHandler(ch)
logger.addHandler(fh)


class AwaybotProducer:

    """A class for producing messages from the Slack RTM api to
    a remote kafka cluster.

    This class needs to do the following:
    1. Connect to the slack api
    2. Connect to simpleDB client.
    3. Fetch timestamp of last message produced.
    4. Fetch history if possible from the slack api.
    5. Produce messages from the fetched history to kafka.
    6. Connect to the RTM api
    7. Produce messages from the RTM api to kafka.
    """

    def __init__(self, token=None, kafka_ip=None):
        """
        Constructor for AwaybotProducer class

        Paramaters:
        -----------
        token: str
            String representing a token used to connect to the slack api
        kafka_ip: str, list
            String representing host:port of the kafka server(s). 
            If a list is supplied, format is ['h:p', 'h:p', ...]
        """

        self.token = token
        self.kafka_ip = kafka_ip
        self.sc = None
        self.slack_status = False
        self.kafka_status = False
        self.sdb_status = False

    
    def getTokenFromFile(self, auth_file):
        """
        Function that returns the slack token contained
        in the supplied file.

        Parameters: 
        -----------
        auth_file: str
            A single line text file containing a valid slack 
            authorization token.

        Returns: 
        ----------
        None
        """
        token_file = open(auth_file, 'r')
        token = [line.strip() for line in token_file.readlines()][0]
        token_file.close()
        self.token = token
        return

    
    def slackConnect(self):
        """
        Function that uses the supplied token to connect to the Slack API.
        Tests if the connection is valid and raises a value error if it is
        not.

        Parameters:
        -----------
        None

        Returns: 
        ----------
        None
        """

        self.sc = SlackClient(self.token)
        connection_test = self.sc.api_call("api.test")
        if not connection_test['ok']:
            if self.token:
                raise ValueError(
                    "Could not connect to Slack API. "
                    "Check that the token is valid")
                sys.exit()
            else:
                raise ValueError(
                    "Could not connect to Slack API. "
                    "No token was supplied")
                sys.exit()
        else:
            self.slack_status = True
            return

    
    def getChannelList(self):
        """
        Function that calls the slack API channels.list function
        and returns the channel names, as aliased by the Slack API.

        Parameters:
        -----------
        None

        Returns: 
        ----------
        channel_list: list
            List with each channel represnted as a string.
        """
        if not self.slack_status:
            self.slackConnect(self.token)
        channel_list = [
            {channel_dict['id']:channel_dict['name']}  for channel_dict in 
            self.sc.api_call("channels.list")['channels']]
        return channel_list

    
    def getTeamName(self):
        """
        Function that calls the slack API channels.list function
        and returns the channel names, as aliased by the Slack API.

        Parameters:
        -----------
        None

        Returns: 
        ----------
        team_id: str
            The name of the slack team as aliased by the Slack API
        """
        if not self.slack_status:
            self.slackConnect()
        team_id = self.sc.api_call('team.info')['team']['name']
    
        return team_id


    def getTeamDomain(self):
        """
        Function that calls the slack API channels.list function
        and returns the channel names, as aliased by the Slack API.

        Parameters:
        -----------
        None

        Returns: 
        ----------
        team_domain: str
            The portion of the url before '.slack.com'
            example:
                awaybot-slack-team(.slack.com)
        """
        if not self.slack_status:
            self.slackConnect()
        team_id = self.sc.api_call('team.info')['team']['domain']
    
        return team_id

    
    def simpledbConnect(self):
        """
        Function that uses the supplied token to connect to the AWS simpleDB
        client. Quits if failure to connect.

        Parameters:
        -----------
        None

        Returns: 
        ----------
        None
        """
        try:
            self.sdb = boto3.client('sdb')
        except:
            logger.error(
                "Failed to connect to AWS. Have you configured "
                "AWS CLI?", exc_info=True)
            sys.exit()
        else:
            self.sdb_status = True
        return


    def getLatestTimestamp(self, domain, team_name):
        """
        Function that gets the latest timestamp value for the supplied domain,
        if one exist.

        Parameters:
        -----------
        domain: str
            The name of the domain stored in simpleDB
        team_name: str
            The name of the slack team for which you are fetching messages

        Returns:
        ---------
        timestamp: str
            Unix timestamp as string
        """
        if not self.sdb_status:
            self.simpledbConnect()

        try:
            ts_request = self.sdb.get_attributes(
                DomainName=domain,
                ItemName=team_name,
                AttributeNames=[
                    'ts'
                    ],
                ConsistentRead=True)
        except:
            logger.error(
                "Failed to fetch timestamp from SimpleDB. "
                "Check that the domain exists.", exc_info=True)
            sys.exit()
        else:
            if 'Attributes' in ts_request:
                return ts_request['Attributes'][0]['Value']
            else:
                return '0'


    def updateLatestTimestamp(self, domain, team_name, ts):
        """
        Function that comparse the time stamp of the current
        message and compares it to the current timestamp value in
        SimpleDB. If it is greater, updates the value.

        Parameters:
        -----------
        domain: str
            The name of the domain stored in simpleDB
        team_name: str
            The name of the slack team for which you are fetching messages
        ts:
            The timestamp value of the current message

        Returns:
            None
        """
        if not self.sdb_status:
            self.simpledbConnect()
        latest_ts = self.getLatestTimestamp(domain, team_name)
        logger.info(
            'Updating timestamp: latest: {}\nnew:{}'.format(latest_ts, ts))
        if float(ts) > float(latest_ts):
            item_attrs = [
                {'Name': 'Team', 'Value': team_name, 'Replace': True},
                {'Name': 'ts', 'Value': ts, 'Replace': True}
                ]
            response = self.sdb.put_attributes(
                DomainName=domain,
                ItemName=team_name,
                Attributes=item_attrs)
            logger.info(response)
            return

    
    def fetchSlackHistory(self, team_name, archive_url,
        channel_list, timestamp = '0'):
        """
        Generator function that fetches messages from the
        slack api using the channel.history method for each channel
        and yields each message.
        NOTES: 
        1. This method only fetches the text of messages and
        not reactions.
        2. Only users and bot users have access to channel.history.
        If you try and apply this code with a Slack app, the app
        will not have access to channel history.

        Parameters:
        team_name: str
            The name of the slack team for which you are fetching messages
        archive_url: str
            The URL to the archive of the teams messages
        channel_list: dict
            A dictionary of channel ids and the names of channels
            we will fetch history from.
        timestamp: str
            The unix timestamp (as string) after which we will retrieve
            messages. 
            Default: '0'

        Yields:
        message_dict: dict
             key-value descriptions:
                user: The user who sent the message
                text: The text of the message
                type: The type of message that was sent
                ts: The unix timestamp when the message was sent
                channel: The channel the message was senf from
                team: The slack team the user belongs to.
                message_url: URL to the archived version of the message
        """
        if not self.slack_status:
            self.slackConnect(self.token)
        for channel in channel_list:
            channel_history = self.sc.api_call(
                "channels.history", channel=channel.keys()[0],
                oldest = timestamp, count="1000")
            for message_dict in channel_history['messages']:
                if (
                    sorted(['user', 'text', 'type', 'ts'])
                        == sorted(message_dict.keys())):
                    message_dict['channel'] = channel.values()[0]
                    message_dict['team'] = team_name
                    message_dict['message_url'] = '{}{}/p{}'.format(
                        archive_url, message_dict['channel'],
                        message_dict['ts'].replace('.', ''))
                    message_dict['uuid'] = str(uuid.uuid1())
                    yield message_dict

    
    def connectKafkaProducer(self):
        """
        Function that connects to the remote server as a
        new kafka producer.

        Parameters:
            None
        Returns:
            None
        """
        try:
            self.kp = KafkaProducer(bootstrap_servers=self.kafka_ip)
        except:
            logger.error(
                'Could not connect to Kafka cluster. '
                'Check the ip address and cluster status.', exc_info=True)
            sys.exit()
        else:
            self.kafka_status = True
        return


    def produceMessage(self, message_topic, message_value):
        """
        Function that sends a message to the remote kafka server.
        Messages are serialized as json before sending.

        Parameters:
            message_topic: str
                The name of the topic the message belongs to
            message_value: dict
                Dictionary that defines the message of it's metadata.

        Returns:
            None
        """ 
        if not self.kafka_status:
            self.connectKafkaProducer()

        if ('team' in message_value and 'ts' in message_value):
            try:
                self.updateLatestTimestamp(
                    'awaybot', message_value['team'], 
                    message_value['ts'])
            except:
                logger.error('Failed to update timestamp for {}'.format(
                    message_value), exc_info=True)
        try:
            self.kp.send(message_topic, json.dumps(message_value))
        except:
            logger.error(
                'Failed to send message of topic:\n\t{}'
                ' and value:\n\t{}'.format(message_topic, message_value),
                exc_info=True)
        return


    def openRtmConnection(self, team_name):
        """
        Generator function that fetches messages from the
        slack RTM API. 

        TODO:
        -------
        If there is an error, returns None.
        This is done to give the RTM a chance to reconnect.
        I'm not sure this is the right way to do this, as it
        doesn't always seem to resolve websocket closing.

        Parameters:
        ----------
        None

        Yields:
        ---------
        message_dict: dict
             key-value descriptions:
                user: The user who sent the message
                text: The text of the message
                type: The type of message that was sent
                ts: The unix timestamp when the message was sent
                channel: The channel the message was senf from
        """
        if not self.slack_status:
            self.slackConnect(self.token)
        if self.sc.rtm_connect():
            logger.info('Connected to Slack RTM API!')
            while True:
                time.sleep(5)
                try:
                    message_dict = self.sc.rtm_read()
                except Exception as e:
                    logger.info(
                        'Failed to fetch latest message.', exc_info=True)
                    time.sleep(500)
                    return
                else:
                    if message_dict:
                        for message in message_dict:
                            if message:
                                message['uuid'] = str(uuid.uuid1())
                                message['team'] = team_name
                                yield message
        else:
            raise ValueError(
                "Could not connect to Slack RTM API. "
                "Check that token is valid and you have "
                "permission to access RTM API.")


if __name__ == "__main__":
    logger.info("Starting __main__ for awaybot_producer.py")

    ap = AwaybotProducer(
        token=os.environ.get('SLACK_TOKEN'),
        kafka_ip=os.environ.get('KAFKA_IP'))
    team_id = ap.getTeamName()
    team_domain = ap.getTeamDomain()
    team_archive_url = r'https://{}.slack.com/archives/'.format(team_domain)
    logger.info('Team name: {}'.format(team_id))
    latest_timestamp = ap.getLatestTimestamp(
        domain='awaybot', team_name=team_id)
    logger.info(
        'Latest timestamp for team {} is {}'.format(
            team_id, datetime.datetime.fromtimestamp(
                float(latest_timestamp)).strftime('%Y-%m-%d %H:%M:%S')))
    channels = ap.getChannelList()
    channel_dict = {}
    for i in channels:
        channel_dict.update(i)
    logger.info('Channnels available to producer: {}'.format
        (' '.join([i.values()[0] for i in channels])))
    history = ap.fetchSlackHistory(
        team_name=team_id, archive_url=team_archive_url,
        channel_list=channels, timestamp=latest_timestamp)
    for msg in history:
        logger.info(msg)
        ap.produceMessage("test_topic", msg)


    message_keys = sorted(
                [
                    u'text', u'ts', u'user',
                    u'team', u'type',
                    u'channel', u'uuid'
                ])
    c = 0
    while True:
        if c:
            logger.info('Reconnected to RTM API {} time(s)'.format(c))
        real_time_messages = ap.openRtmConnection(team_name=team_id)
        for msg in real_time_messages:
            if 'channel' in msg:
                if not msg['channel'] in channel_dict:
                    continue
                msg['channel'] = channel_dict[msg['channel']]

            if sorted(msg.keys()) == message_keys:
                msg['message_url'] = '{}{}/p{}'.format(
                    team_archive_url, msg['channel'],
                    msg['ts'].replace('.', ''))

            logger.info(msg)
            ap.produceMessage("test_topic", msg)
        c += 1


