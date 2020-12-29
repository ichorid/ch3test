import contextlib
import logging
import os
import time
from unittest import TestCase

from aioquic.h0.connection import H0_ALPN, H0Connection
from aioquic.h3.events import DataReceived, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.connection import QuicConnection
from aioquic.quic.logger import QuicLogger
from aioquic.quic.recovery import QuicPacketPacer

SERVER_CACERTFILE = os.path.join(os.path.dirname(__file__), "pycacert.pem")
SERVER_CERTFILE = os.path.join(os.path.dirname(__file__), "ssl_cert.pem")
SERVER_KEYFILE = os.path.join(os.path.dirname(__file__), "ssl_key.pem")

logging.basicConfig(level=logging.DEBUG)

CLIENT_ADDR = ("1.2.3.4", 1234)

SERVER_ADDR = ("2.3.4.5", 4433)


def disable_packet_pacing(connection):
    class DummyPacketPacer(QuicPacketPacer):
        def next_send_time(self, now):
            return None

    connection._loss._pacer = DummyPacketPacer()


def roundtrip(sender, receiver):
    """
    Send datagrams from `sender` to `receiver` and back.
    """
    return (transfer(sender, receiver), transfer(receiver, sender))


@contextlib.contextmanager
def client_and_server(
        client_kwargs={},
        client_options={},
        client_patch=lambda x: None,
        handshake=True,
        server_kwargs={},
        server_certfile=SERVER_CERTFILE,
        server_keyfile=SERVER_KEYFILE,
        server_options={},
        server_patch=lambda x: None,
):
    client_configuration = QuicConfiguration(
        is_client=True, quic_logger=QuicLogger(), **client_options
    )
    client_configuration.load_verify_locations(cafile=SERVER_CACERTFILE)

    client = QuicConnection(configuration=client_configuration, **client_kwargs)
    client._ack_delay = 0
    disable_packet_pacing(client)
    client_patch(client)

    server_configuration = QuicConfiguration(
        is_client=False, quic_logger=QuicLogger(), **server_options
    )
    server_configuration.load_cert_chain(server_certfile, server_keyfile)

    print(client.original_destination_connection_id, type(client.original_destination_connection_id))

    server = QuicConnection(
        configuration=server_configuration,
        original_destination_connection_id=client.original_destination_connection_id,
        **server_kwargs
    )
    server._ack_delay = 0
    disable_packet_pacing(server)
    server_patch(server)

    # perform handshake
    if handshake:
        client.connect(SERVER_ADDR, now=time.time())
        for i in range(3):
            roundtrip(client, server)

    yield client, server

    # close
    client.close()
    server.close()


def transfer(sender, receiver):
    """
    Send datagrams from `sender` to `receiver`.
    """
    datagrams = 0
    from_addr = CLIENT_ADDR if sender._is_client else SERVER_ADDR
    for data, addr in sender.datagrams_to_send(now=time.time()):
        datagrams += 1
        receiver.receive_datagram(data, from_addr, now=time.time())
    return datagrams


def h0_client_and_server():
    return client_and_server(
        client_options={"alpn_protocols": H0_ALPN},
        server_options={"alpn_protocols": H0_ALPN},
    )


def h0_transfer(quic_sender, h0_receiver):
    quic_receiver = h0_receiver._quic
    transfer(quic_sender, quic_receiver)

    # process QUIC events
    http_events = []
    event = quic_receiver.next_event()
    while event is not None:
        http_events.extend(h0_receiver.handle_event(event))
        event = quic_receiver.next_event()
    return http_events


class H0ConnectionTest(TestCase):
    def test_connect(self):
        with h0_client_and_server() as (quic_client, quic_server):
            h0_client = H0Connection(quic_client)
            h0_server = H0Connection(quic_server)

            # send request
            stream_id = quic_client.get_next_available_stream_id()
            h0_client.send_headers(
                stream_id=stream_id,
                headers=[
                    (b":method", b"GET"),
                    (b":scheme", b"https"),
                    (b":authority", b"localhost"),
                    (b":path", b"/"),
                ],
            )
            h0_client.send_data(stream_id=stream_id, data=b"", end_stream=True)

            # receive request
            events = h0_transfer(quic_client, h0_server)
            self.assertEqual(len(events), 2)

            self.assertTrue(isinstance(events[0], HeadersReceived))
            self.assertEqual(
                events[0].headers, [(b":method", b"GET"), (b":path", b"/")]
            )
            self.assertEqual(events[0].stream_id, stream_id)
            self.assertEqual(events[0].stream_ended, False)

            self.assertTrue(isinstance(events[1], DataReceived))
            self.assertEqual(events[1].data, b"")
            self.assertEqual(events[1].stream_id, stream_id)
            self.assertEqual(events[1].stream_ended, True)

            # send response
            h0_server.send_headers(
                stream_id=stream_id,
                headers=[
                    (b":status", b"200"),
                    (b"content-type", b"text/html; charset=utf-8"),
                ],
            )
            h0_server.send_data(
                stream_id=stream_id,
                data=b"<html><body>hello</body></html>",
                end_stream=True,
            )

            # receive response
            events = h0_transfer(quic_server, h0_client)
            self.assertEqual(len(events), 2)

            self.assertTrue(isinstance(events[0], HeadersReceived))
            self.assertEqual(events[0].headers, [])
            self.assertEqual(events[0].stream_id, stream_id)
            self.assertEqual(events[0].stream_ended, False)

            self.assertTrue(isinstance(events[1], DataReceived))
            self.assertEqual(events[1].data, b"<html><body>hello</body></html>")
            self.assertEqual(events[1].stream_id, stream_id)
            self.assertEqual(events[1].stream_ended, True)
