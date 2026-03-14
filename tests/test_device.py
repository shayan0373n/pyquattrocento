import unittest
from unittest.mock import Mock, patch

from quattrocento.config import QuattrocentoConfig
from quattrocento.device import SocketQuattrocentoStream
from quattrocento.settings import SocketStreamSettings


class TestSocketQuattrocentoStream(unittest.TestCase):
    def setUp(self):
        self.config = QuattrocentoConfig(sample_rate_hz=512)
        self.settings = SocketStreamSettings(
            fsamp=512,
            nch=3,
            socket_read_size=65536,
            force_channel_indices=tuple(range(10)),
            aux_in_channel_index=10,
        )
        self.stream = SocketQuattrocentoStream(self.config, self.settings)

    @patch("socket.socket")
    def test_drain_socket_buffer_capping_preserves_packet_alignment(self, mock_socket_cls):
        mock_sock = Mock()
        mock_socket_cls.return_value = mock_sock

        self.stream._ensure_connected()

        bytes_per_packet = self.stream._bytes_per_packet
        samples_per_packet = self.stream._samples_per_packet
        max_buffer_size = 50 * 1024 * 1024
        partial_packet_size = 17

        prefill_packets = (45 * 1024 * 1024) // bytes_per_packet
        initial_buffer_size = prefill_packets * bytes_per_packet + partial_packet_size
        self.stream._byte_buffer.extend(b"p" * initial_buffer_size)

        payload_packets = (10 * 1024 * 1024) // bytes_per_packet
        payload = b"x" * (payload_packets * bytes_per_packet)
        payload_offset = 0

        def mock_recv(size):
            nonlocal payload_offset
            if payload_offset >= len(payload):
                raise BlockingIOError

            chunk = payload[payload_offset : payload_offset + size]
            payload_offset += len(chunk)
            return chunk

        mock_sock.recv.side_effect = mock_recv

        total_size_before_cap = initial_buffer_size + len(payload)
        excess_bytes = total_size_before_cap - max_buffer_size
        expected_dropped_packets = (excess_bytes + bytes_per_packet - 1) // bytes_per_packet

        self.stream._drain_socket()

        self.assertLessEqual(len(self.stream._byte_buffer), max_buffer_size)
        self.assertEqual(len(self.stream._byte_buffer) % bytes_per_packet, partial_packet_size)
        self.assertEqual(self.stream._sample_index, expected_dropped_packets * samples_per_packet)


if __name__ == "__main__":
    unittest.main()
