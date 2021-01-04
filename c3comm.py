import json
import logging
import random
import struct
from binascii import unhexlify

from ipv8.community import Community
from ipv8.lazy_community import lazy_wrapper
from ipv8.requestcache import RandomNumberCache, RequestCache
from ipv8.test.REST.test_overlays_endpoint import hexlify
from ipv8.types import Peer
from tcp_over_ipv8 import TCPServer, TcpPayload, TCPConnection

BINARY_FIELDS = ("infohash", "channel_pk")

CHANNELS_SERVER_PORT = 99

MESSAGE_HEADER_MAGIC = unhexlify("2dfcccbeab69fcb3")
MESSAGE_HEADER_FORMAT = ">8s I"
MESSAGE_HEADER_SIZE = 12

REQUEST_MAGIC = unhexlify("a181e2cd938fbcc0")
REQUEST_HEADER_FORMAT = ">8s I"
REQUEST_HEADER_SIZE = 12

RESPONSE_MAGIC = unhexlify("0ccbf839dc2e181a")
RESPONSE_HEADER_FORMAT = ">8s I"
RESPONSE_HEADER_SIZE = 12


def pack_message(message_data: bytes) -> bytes:
    header = struct.pack(MESSAGE_HEADER_FORMAT, MESSAGE_HEADER_MAGIC, len(message_data))
    return header + message_data


def pack_request(request_id: int, request_data: bytes) -> bytes:
    header = struct.pack(REQUEST_HEADER_FORMAT, REQUEST_MAGIC, request_id)
    return header + request_data


def pack_response(response_id: int, response_data: bytes) -> bytes:
    header = struct.pack(RESPONSE_HEADER_FORMAT, RESPONSE_MAGIC, response_id)
    return header + response_data


class SelectRequest(RandomNumberCache):
    def __init__(self, request_cache, prefix, request_data, processing_callback=None):
        super().__init__(request_cache, prefix)
        self.request_data = request_data
        # The callback to call on results of processing of the response payload
        self.processing_callback = processing_callback

    def on_timeout(self):
        pass


class C3Community(Community):
    community_id = unhexlify('eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee')

    def __init__(self, my_peer, endpoint, network):
        super().__init__(my_peer, endpoint, network=network)
        self.request_cache = RequestCache()
        self.data_dict = {}
        self.received_messages = []

        self.tcp_server = TCPServer(has_data_to_send_callback=self.send_segments_for_connection)

        self.add_message_handler(TcpPayload, self.on_tcp8_packet)

    def send_request(self, peer: Peer, request_dict: dict):
        def on_response(data):
            print("RESPONSE", data)

        request = SelectRequest(self.request_cache, hexlify(peer.mid), request_dict, processing_callback=on_response)
        self.request_cache.add(request)
        request_serialized = pack_request(request.number, json.dumps(request_dict).encode('utf8'))
        self.send_message(peer, request_serialized)

    def send_message(self, peer: Peer, message_data: bytes):
        self.push_data(peer, pack_message(message_data))

    def push_data(self, peer, raw_data):
        ip_src = self.my_peer
        ip_dst = peer

        def connection_over_callback(s: TCPConnection):
            print("OVER")

        has_data_to_send_callback = self.send_segments_for_connection

        socket_client = ip_src
        socket_server = ip_dst
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
                ip_dst,
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
        if magic != MESSAGE_HEADER_MAGIC:
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

    @staticmethod
    def try_decode_message(msg):
        if len(msg) > REQUEST_HEADER_SIZE:
            header = msg[:REQUEST_HEADER_SIZE]
            magic, msg_id = struct.unpack(REQUEST_HEADER_FORMAT, header)
            if magic == REQUEST_MAGIC:
                return msg_id, msg[REQUEST_HEADER_SIZE:]
        return None, None

    @lazy_wrapper(TcpPayload)
    async def on_tcp8_packet(self, src_peer, tcp8_payload):
        conn = self.tcp_server.handle_tcp(tcp8_payload, src_peer, self.my_peer)
        if not conn.has_ready_data():
            return

        message_data = self.check_message_ready(conn)
        if message_data is None:
            return

        msg_id, msg_content = self.try_decode_message(message_data)
        if msg_id is None:
            return

        response = self.on_client_message_received(msg_content)
        print ("RESP ", response)
        conn.add_data_to_send(pack_message(pack_response(msg_id, response)))


    def on_client_message_received(self, message_data):
        return self.data_dict.get(json.loads(message_data.decode('utf8'))["data_id"], b"")

    async def unload(self):
        await self.request_cache.shutdown()
        for conn in self.tcp_server.connections.values():
            await conn.shutdown_task_manager()

        await super().unload()
