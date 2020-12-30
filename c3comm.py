import logging
import random
from binascii import unhexlify

from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.logger import QuicLogger

from ipv8.community import Community
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.lazy_payload import VariablePayload, vp_compile
from tcp_over_ipv8 import TCPServer, TcpPayload, TCPConnection

BINARY_FIELDS = ("infohash", "channel_pk")

CHANNELS_SERVER_PORT = 99


class C3Community(Community):
    community_id = unhexlify('eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee')

    def __init__(self, my_peer, endpoint, network):
        super().__init__(my_peer, endpoint, network=network)
        self.tcp_server = TCPServer(TCPServer.ANY_PORT, has_data_to_send_callback=self.send_segments_for_connection)

        self.add_message_handler(TcpPayload, self.on_tcp8_packet)

    def send_data(self, peer, raw_data):
        ip_src = self.my_peer
        tcp_src_port = random.randint(1024, 6500)
        ip_dst = peer
        tcp_dst_port = CHANNELS_SERVER_PORT
        def over_callback(s:TCPConnection):
            print ("OVER")
        connection_over_callback = over_callback
        has_data_to_send_callback = self.send_segments_for_connection

        socket_client = (ip_src, tcp_src_port)
        socket_server = (ip_dst, tcp_dst_port)
        socket_pair = (socket_server, socket_client)
        conn = self.tcp_server.connections.get(socket_pair)
        if not conn:
            syn_seq = 0
            logging.debug(
                "Creating a TCP8 connection: %s" % str(socket_pair)
            )
            conn = TCPConnection(
                syn_seq,
                ip_src,
                tcp_src_port,
                ip_dst,
                tcp_dst_port,
                connection_over_callback,
                has_data_to_send_callback,
            )
            self.tcp_server.connections[socket_pair] = conn
        conn.add_data_to_send(raw_data)

    def send_segments_for_connection(self, connection: TCPConnection):
        for segment_payload in connection.get_packets_to_send():
            self.ez_send(connection.other_ip, segment_payload)

    @lazy_wrapper(TcpPayload)
    async def on_tcp8_packet(self, src_peer, tcp8_payload):
        conn = self.tcp_server.handle_tcp(tcp8_payload, src_peer, self.my_peer)
        if conn.my_port == CHANNELS_SERVER_PORT:
            print(len(conn.get_data()))

    async def unload(self):
        for conn in self.tcp_server.connections.values():
            await conn.shutdown_task_manager()

        await super().unload()

