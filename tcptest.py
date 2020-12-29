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
        raw_data = b"ffff00"

        self.nodes[0].overlay.send_raw_data(self.nodes[1].my_peer, raw_data)
        await self.deliver_messages(timeout=0.5)


class TestTcpConn:

    def test_tcp(self):
        syn_seq = 0
        my_ip = 123
        my_port = 333
        other_ip = 345
        other_port = 444
        connection_over_callback = Mock()
        has_data_to_send_callback = Mock()
        conn = TCPConnection(syn_seq, my_ip, my_port, other_ip, other_port,
                             connection_over_callback, has_data_to_send_callback)

        raw_data = b"aaaaaaaa"
        conn.add_data_to_send(raw_data)
        data_to_send = conn.get_packets_to_send()
        print (data_to_send)

        server = TCPServer(TCPServer.ANY_PORT)
        server.handle_tcp(data_to_send[0])
