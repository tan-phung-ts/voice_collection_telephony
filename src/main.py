import socket
import time
from contextlib import contextmanager

import pyaudio
import PyWave as pywave

from src import pyrtp

UDP_LOWEST_PORT = 16384
UDP_MAX_PORT = 32766
UDP_SERVER_IP = "0.0.0.0"
UDP_SERVER_PORT = 5005
UDP_CLIENT_IP = "103.170.122.78"
UDP_CLIENT_PORT = 1

RTP_PACKET_SSRC = 12345678
RTP_PACKET_PAYLOAD_TYPE = 8  # 8 for 16-bit audio, 10 for 8-bit audio
RTP_PACKET_PACKETIZATION = 160
RTP_PACKET_BYTE_ENCODING = "latin-1"

AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHANNELS = 1
AUDIO_RATE = 16000


class TelephonyRTPServer:
    _client_ip: str
    _client_port: int
    _buffer_size: int
    _socket: socket.socket

    def __init__(
        self,
        server_ip=UDP_SERVER_IP,
        server_port=UDP_SERVER_PORT,
        client_ip=UDP_CLIENT_IP,
        client_port=UDP_CLIENT_PORT,
        buffer_size: int = RTP_PACKET_PACKETIZATION,
    ):
        self._client_ip = client_ip
        self._client_port = client_port
        self._buffer_size = buffer_size

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind((server_ip, server_port))

    def close(self):
        self._socket.close()

    def send(self, data: str):
        self._socket.sendto(data, (self._client_ip, self._client_port))

    def recv(self):
        data, addr = self._socket.recvfrom(1024)
        return data, addr

    @contextmanager
    def open_audio_data(
        self,
        audio_file_path: str,
    ):
        with pywave.open(audio_file_path) as audio_file:
            audio_data: pywave.Wave = audio_file
            yield audio_data
            audio_data.close()

    def send_audio_data(
        self,
        audio_data: bytes,
    ):
        for rtp_packet in self.rtp_packet_generator(
            audio_data,
        ):
            print("packet", rtp_packet)
            self.send(rtp_packet)

    def open_and_send_audio_data(
        self,
        audio_file_path: str,
    ):
        with self.open_audio_data(audio_file_path) as audio_data:
            self.send_audio_data(audio_data)

    def extract_audio_data_from_packet(self, packet: bytes):
        packet_vars = pyrtp.DecodeRTPpacket(packet)
        print("packet_var", packet_vars)

        audio_chunk = bytes(packet_vars["payload"], RTP_PACKET_BYTE_ENCODING)
        return audio_chunk

    def receive_audio_data_generator(self):
        while True:
            packet, addr = self.recv()
            if packet == b"":
                break

            yield self.extract_audio_data_from_packet(packet)

    def receive_audio_data_and_playback(self):
        with self.playback_stream() as stream:
            for audio_chunk in self.receive_audio_data_generator():
                stream.write(audio_chunk)

    @contextmanager
    @staticmethod
    def playback_stream(
        fmt=AUDIO_FORMAT,
        channels=AUDIO_CHANNELS,
        rate=AUDIO_RATE,
        output=True,
    ):
        p = pyaudio.PyAudio()
        stream = p.open(
            rate=rate,
            channels=channels,
            format=fmt,
            output=output,
        )

        yield stream

        stream.stop_stream()
        stream.close()

        p.terminate()

    @staticmethod
    def rtp_packet_generator(
        audio_data: pywave.Wave,
        ssrc: int = RTP_PACKET_SSRC,
        payload_type: int = RTP_PACKET_PAYLOAD_TYPE,
        packetization: int = RTP_PACKET_PACKETIZATION,
        rtp_header: dict = {},
    ):
        sequence_number = 0  # Initialize sequence number
        timestamp = int(time.time())  # Use current time as the timestamp

        while True:
            # Change here to split chunk from audio_data directly
            audio_chunk = audio_data.read(packetization)
            if audio_chunk == b"":
                break

            packet_vars = {
                "version": rtp_header.get("version", 2),
                "padding": rtp_header.get("padding", 0),
                "extension": rtp_header.get("extension", 0),
                "csi_count": rtp_header.get("csi_count", 0),
                "marker": rtp_header.get("marker", 0),
                "payload_type": payload_type,
                "sequence_number": sequence_number,
                "timestamp": timestamp,
                "ssrc": ssrc,
                "payload": str(audio_chunk, RTP_PACKET_BYTE_ENCODING),
            }

            header_hex = pyrtp.GenerateRTPpacket(packet_vars)
            yield header_hex

            sequence_number += 1
            # time.sleep(packetization / 1000)  # Wait for the packetization interval, will cause lag


def test_playback(audio_file_path: str):
    telephony_server = TelephonyRTPServer()
    with TelephonyRTPServer.playback_stream() as stream:
        with telephony_server.open_audio_data(audio_file_path) as audio_data:
            # # raw test
            # while True:
            #     audio_chunk = audio_data.read(RTP_PACKET_PACKETIZATION)
            #     if audio_chunk == b"":
            #         break

            #     stream.write(audio_chunk)

            # pack and unpack test
            for packet in telephony_server.rtp_packet_generator(audio_data):
                print("packet", packet)

                resp_audio_chunk = telephony_server.extract_audio_data_from_packet(
                    packet
                )
                print("resp_audio_chunk", resp_audio_chunk)

                stream.write(resp_audio_chunk)


def main() -> None:
    test_playback("src/output_audio_8k.wav")


if __name__ == "__main__":
    main()
