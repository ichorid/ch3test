import json
import logging
import struct
from binascii import unhexlify
from dataclasses import dataclass
from functools import cached_property
from typing import Set

from ipv8.community import Community
from ipv8.lazy_community import lazy_wrapper
from ipv8.peerdiscovery.network import Network
from ipv8.requestcache import RandomNumberCache, RequestCache
from ipv8.test.REST.test_overlays_endpoint import hexlify
from ipv8.types import Peer
from tcp_over_ipv8 import TCPServer, TcpPayload, TCPConnection
from utils import hash_str_to_int

BINARY_FIELDS = ("infohash", "channel_pk")

CHANNELS_SERVER_PORT = 99


@dataclass
class PacketHeader:
    magic: bytes
    format: str

    @cached_property
    def size(self):
        return struct.calcsize(self.format)


class MessageHeader(PacketHeader):
    def try_decode_message(self, msg: bytes):
        if len(msg) > self.size:
            header = msg[:self.size]
            magic, msg_id = struct.unpack(self.format, header)
            if magic == self.magic:
                return msg_id, msg[self.size:]
        return None, None


MESSAGE_HEADER = PacketHeader(unhexlify("2dfcccbeab69fcb3"), ">8s I")

REQUEST_HEADER = MessageHeader(unhexlify("a181e2cd938fbcc0"), ">8s I")
RESPONSE_HEADER = MessageHeader(unhexlify("0ccbf839dc2e181a"), ">8s I")
PUSH_HEADER = MessageHeader(unhexlify("cbd4bf5911517bf2"), ">8s I")


def pack_message(message_data: bytes) -> bytes:
    header = struct.pack(MESSAGE_HEADER.format, MESSAGE_HEADER.magic, len(message_data))
    return header + message_data


def pack_request(request_id: int, request_data: bytes) -> bytes:
    header = struct.pack(REQUEST_HEADER.format, REQUEST_HEADER.magic, request_id)
    return header + request_data


def pack_response(response_id: int, response_data: bytes) -> bytes:
    header = struct.pack(RESPONSE_HEADER.format, RESPONSE_HEADER.magic, response_id)
    return header + response_data

def pack_push_resource(push_id: int, resource_data: bytes) -> bytes:
    header = struct.pack(PUSH_HEADER.format, PUSH_HEADER.magic, push_id)
    return header + resource_data


class SelectRequest(RandomNumberCache):
    def __init__(self, request_cache, prefix, request_data, processing_callback=None):
        super().__init__(request_cache, prefix)
        self.request_data = request_data
        # The callback to call on results of processing of the response payload
        self.processing_callback = processing_callback

    def on_timeout(self):
        pass


@dataclass
class Host:
    pass


@dataclass
class ResId:
    numeric_id: int
    providers: Set[Host]

    def __hash__(self):
        return hash(self.numeric_id)


@dataclass
class Resource:
    id_: ResId
    parent_id: ResId
    children_ids: Set[ResId]

    def __hash__(self):
        return hash(self.id_)


class Tsapa:
    def __init__(self, on_add_resource=None):
        self.on_add_resource = on_add_resource or (lambda _: None)
        self.resources = {}  # resources this host provides to the network
        # self.resources_cache = Set[ResId]  # resources this host knows about
        # self.my_resources = Dict[int]  # resources this host provides to the network
        # self.permanent_peers = Set[Host]  # Our permanent connections

    def get_resource(self, res_id: int):
        resource = self.resources.get(res_id, b"")
        return resource

    def add_resource(self, res_id: int, res_data: bytes):
        #if self.resources.get(res_id):
            #raise Exception("Trying to overwrite resource!")
        old = self.resources.get(res_id)
        if old is not None:
            if hash(json.dumps(old)) == hash(json.dumps(res_data)):
                return
        self.resources[res_id] = res_data
        self.on_add_resource(res_data)


class C3Community(Community):
    community_id = unhexlify('eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee')

    def __init__(self, my_peer, endpoint, network):
        super().__init__(my_peer, endpoint, network=network)
        self.request_cache = RequestCache()
        self.tsapa = Tsapa(on_add_resource=self.push_resource_to_peers)
        self.received_messages = []

        self.tcp_server = TCPServer(has_data_to_send_callback=self.send_segments_for_connection)

        self.add_message_handler(TcpPayload, self.on_tcp8_packet)
        self.tcp_message_reactions = (
            (RESPONSE_HEADER, self.on_response_received),
            (REQUEST_HEADER, self.on_request_received),
            (PUSH_HEADER, self.on_push_received))
        
        
    def push_resource_to_peers(self, res):
        print ("PUSHING", res["title"])
        for p in self.get_peers():
            self.push_resource(p, res)

    def push_resource(self, dst_peer, res):
        push_msg = pack_push_resource(123, json.dumps(res).encode('utf8'))
        self.send_message(dst_peer, push_msg)

    def on_push_received(self, src_peer, push_id, push_data):
        push_dict = json.loads(push_data.decode('utf8'))
        print ("RECEIVED PUSH", push_dict["title"])
        res_id = hash_str_to_int(push_dict["title"])
        self.tsapa.add_resource(res_id, push_dict)

    def on_request_received(self, src_peer, req_id, req_data):
        res_id = json.loads(req_data.decode('utf8'))["data_id"]
        resource = self.tsapa.get_resource(res_id)
        self.send_message(src_peer, pack_response(req_id, resource))

    def on_response_received(self, src_peer, req_id, req_data):
        request = self.request_cache.get(hexlify(src_peer.mid), req_id)
        if request is None:
            return
        self.request_cache.pop(hexlify(src_peer.mid), req_id)

        if req_data != b"":
            res_id = request.request_data["data_id"]
            self.tsapa.add_resource(res_id, req_data)

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
        magic, message_size = struct.unpack(MESSAGE_HEADER.format, segment_data[:MESSAGE_HEADER.size])
        frame_size = MESSAGE_HEADER.size + message_size
        if magic != MESSAGE_HEADER.magic:
            raise Exception("Wrong magic bytes in message %s", hexlify(magic))

        if len(segment_data) < frame_size:
            # Not enough bytes in the segment to decode the whole message - skipping
            return None

        message_body = conn.release_segment_memory(frame_size)[MESSAGE_HEADER.size:]
        self.received_messages.append(message_body)
        return message_body

    def send_segments_for_connection(self, connection: TCPConnection):
        for segment_payload in connection.get_packets_to_send():
            self.ez_send(connection.other_ip, segment_payload)

    @lazy_wrapper(TcpPayload)
    async def on_tcp8_packet(self, src_peer, tcp8_payload):

        # Data contains a segment
        conn = self.tcp_server.handle_tcp(tcp8_payload, src_peer, self.my_peer)
        if not conn.has_ready_data():
            return

        # Segment contains a message
        message_data = self.check_message_ready(conn)
        if message_data is None:
            return

        # Message contains a request/response
        for header_type, reaction_callback in self.tcp_message_reactions:
            msg_id, msg_content = header_type.try_decode_message(message_data)

            if msg_id is not None:
                reaction_callback(src_peer, msg_id, msg_content)
                return

    def started(self):
        async def print_peers():
            print("I am:", self.my_peer, "\nI know:", [str(p) for p in self.get_peers()])

        # We register a asyncio task with this overlay.
        # This makes sure that the task ends when this overlay is unloaded.
        # We call the 'print_peers' function every 5.0 seconds, starting now.
        self.register_task("print_peers", print_peers, interval=5.0, delay=0)

    async def unload(self):
        await self.request_cache.shutdown()
        for conn in self.tcp_server.connections.values():
            await conn.shutdown_task_manager()

        await super().unload()

