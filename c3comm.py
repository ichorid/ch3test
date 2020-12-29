from binascii import unhexlify

from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.logger import QuicLogger

from ipv8.community import Community
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.lazy_payload import VariablePayload, vp_compile

BINARY_FIELDS = ("infohash", "channel_pk")


@vp_compile
class RawBinPayload(VariablePayload):
    msg_id = 202
    format_list = ['raw']
    names = ['raw_blob']


class C3Community(Community):
    community_id = unhexlify('eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee')

    def setup_quic_server(self):
        server_configuration = QuicConfiguration(
            is_client=False, quic_logger=QuicLogger(), **server_options
        )
        server_configuration.load_cert_chain(server_certfile, server_keyfile)

        server = QuicConnection(
            configuration=server_configuration,
            original_destination_connection_id=client.original_destination_connection_id,
            **server_kwargs
        )
        server._ack_delay = 0
        disable_packet_pacing(server)
        server_patch(server)

    def __init__(self, my_peer, endpoint, network):
        super().__init__(my_peer, endpoint, network=network)
        self.add_message_handler(RawBinPayload, self.on_raw_data)

    def send_raw_data(self, peer, raw_data):
        self.ez_send(peer, RawBinPayload(raw_data))

    @lazy_wrapper(RawBinPayload)
    async def on_raw_data(self, peer, request_payload):
        print(peer, request_payload)
