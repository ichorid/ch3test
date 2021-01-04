import inspect
import logging

import logging
import random
import sys
from asyncio import sleep

import asynctest

random.seed(123)
root = logging.getLogger()
root.setLevel(logging.DEBUG)

class PrintHandler(logging.Handler):
  def emit(self, record):
    print(self.format(record))

handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
logging.getLogger('faker').setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
#root.addHandler(handler)
root.addHandler(PrintHandler())

from unittest.mock import Mock

from c3comm import C3Community
from ipv8.test.base import TestBase
from tcp_over_ipv8 import TCPConnection, TCPServer

class TestC3Transfer(TestBase):
    """
    Unit tests for the base RemoteQueryCommunity which do not need a real Session.
    """

    def setUp(self):
        super().setUp()
        self.count = 0
        self.initialize(C3Community, 2)

    def create_node(self, *args, **kwargs):
        node = super().create_node(*args, **kwargs)
        self.count += 1
        return node


    async def test_data_transfer(self):
        raw_data = b"a"*1000*10

        peer0 = self.nodes[0].my_peer
        peer1 = self.nodes[1].my_peer

        request_title = "test_stuff_foo"
        self.nodes[1].overlay.data_dict[request_title] = raw_data

        request_title2 = "test_stuff_bar"
        self.nodes[0].overlay.data_dict[request_title2] = raw_data

        request_title3 = "test_stuff_foobar"
        self.nodes[0].overlay.data_dict[request_title3] = b"c"*3000

        self.nodes[0].overlay.send_message(peer1, request_title.encode('utf8'))
        await self.deliver_messages(timeout=0.5)

        self.nodes[1].overlay.send_message(peer0, request_title2.encode('utf8'))
        await self.deliver_messages(timeout=0.5)


        self.nodes[1].overlay.send_message(peer0, request_title3.encode('utf8'))
        await self.deliver_messages(timeout=0.5)

        print(self.nodes[0].overlay.received_messages)
        print(self.nodes[1].overlay.received_messages)

        request_dict = {"data_id": 123}
        self.nodes[1].overlay.send_request(peer0, request_dict)
        await self.deliver_messages(timeout=0.5)



class TestTcpConn:
    def test_tcp(self):
        print()
        syn_seq = 0
        my_ip = 123
        my_port = 333
        server_ip = 345
        other_port = 444
        connection_over_callback = Mock()
        has_data_to_send_callback = Mock()
        conn = TCPConnection(
            syn_seq,
            my_ip,
            my_port,
            server_ip,
            other_port,
            connection_over_callback,
            has_data_to_send_callback,
        )
        #import logging_tree
        #logging_tree.printout()

        raw_data = b"a"*1000*10
        conn.add_data_to_send(raw_data)
        data_to_send = conn.get_packets_to_send()
        print(data_to_send)

        server = TCPServer(TCPServer.ANY_PORT)
        for packet in data_to_send:
            ret_conn = server.handle_tcp(packet, my_ip, server_ip)
            if ret_conn:
                ret_packets = ret_conn.get_packets_to_send()
                print (ret_packets)
