import logging
import random
import struct
from binascii import unhexlify, hexlify

from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.logger import QuicLogger

from ipv8.community import Community
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.lazy_payload import VariablePayload, vp_compile
from ipv8.types import Peer
from tcp_over_ipv8 import TCPServer, TcpPayload, TCPConnection, TCPSegment

BINARY_FIELDS = ("infohash", "channel_pk")

CHANNELS_SERVER_PORT = 99

MESSAGE_HEADER_MAGIC_BYTES = b"8d3276bf3156d8ba"
MESSAGE_HEADER_FORMAT = ">16s I"
MESSAGE_HEADER_SIZE = 20


def pack_response(response_data:bytes) -> bytes:
    header = struct.pack(MESSAGE_HEADER_FORMAT, MESSAGE_HEADER_MAGIC_BYTES, len(response_data))
    return header + response_data

class C3Community(Community):
    community_id = unhexlify('eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee')

    def __init__(self, my_peer, endpoint, network):
        super().__init__(my_peer, endpoint, network=network)
        self.data_dict = {}
        self.received_messages = []

        self.tcp_server = TCPServer(TCPServer.ANY_PORT, has_data_to_send_callback=self.send_segments_for_connection)

        self.add_message_handler(TcpPayload, self.on_tcp8_packet)

    def push_message(self, peer:Peer, message_data:bytes):
        header = struct.pack(MESSAGE_HEADER_FORMAT, MESSAGE_HEADER_MAGIC_BYTES, len(message_data))
        self.push_data(peer, header+message_data)

    def push_data(self, peer, raw_data):
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

    def check_message_ready(self, conn):
        # Parse the message header
        segment_data = conn.get_data()
        # TODO: stop unpacking every time
        magic, message_size = struct.unpack(MESSAGE_HEADER_FORMAT, segment_data[:MESSAGE_HEADER_SIZE])
        frame_size = MESSAGE_HEADER_SIZE + message_size
        if magic != MESSAGE_HEADER_MAGIC_BYTES:
            raise Exception("Wrong magic bytes in message %s", hexlify(magic))

        if len(segment_data) < frame_size:
            # Not enough bytes in the segment to decode the whole message - skipping
            return None
        message_body = conn.release_segment_memory(frame_size)[MESSAGE_HEADER_SIZE:]
        self.received_messages.append(message_body)
        return message_body

    def send_segments_for_connection(self, connection: TCPConnection):
        for segment_payload in connection.get_packets_to_send():
            self.ez_send(connection.other_ip, segment_payload)

    @lazy_wrapper(TcpPayload)
    async def on_tcp8_packet(self, src_peer, tcp8_payload):
        conn = self.tcp_server.handle_tcp(tcp8_payload, src_peer, self.my_peer)
        if conn.has_ready_data():
            message_data = self.check_message_ready(conn)
            if conn.my_port == CHANNELS_SERVER_PORT:
                response_data = self.on_client_message_received(message_data)
                conn.add_data_to_send(pack_response(response_data))
            else:
                print(message_data)

    def on_client_message_received(self, message_data):
        return self.data_dict.get(message_data.decode('utf8'))

    async def unload(self):
        for conn in self.tcp_server.connections.values():
            await conn.shutdown_task_manager()

        await super().unload()

