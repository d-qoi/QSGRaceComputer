import pytest
import pytest_asyncio
import asyncio
from unittest.mock import Mock, patch
from qsgrc.messages.msgpack import MsgPack, Packet, ACK
from qsgrc.messages.core import BaseMessage


class TestMessage(BaseMessage):
    leader = "TEST"

    def __init__(self, value):
        super().__init__("test", value)


@pytest.fixture
def ack_callback():
    """Fixture to provide a mock ACK callback function"""

    async def callback(tag):
        callback.called_with = tag
        callback.call_count += 1

    callback.called_with = None
    callback.call_count = 0
    return callback


@pytest_asyncio.fixture
async def setup_queues():
    """Fixture to set up all the queues"""
    in_queue = asyncio.Queue()
    processed_queue = asyncio.Queue()
    ack_queue = asyncio.Queue()
    return in_queue, processed_queue, ack_queue


@pytest_asyncio.fixture
async def msg_pack(setup_queues, ack_callback):
    """Fixture to provide a configured MsgPack instance"""
    in_queue, processed_queue, ack_queue = setup_queues
    msg_pack = MsgPack(in_queue, processed_queue, ack_queue, ack_callback)
    # Reduce split_length for testing
    msg_pack.split_length = 40
    await msg_pack.start()
    yield msg_pack
    await msg_pack.stop()


class TestPacket:
    """Tests for the Packet class"""

    def test_packet_str_single(self):
        """Test string representation of a single packet"""
        packet = Packet(0, 0, 5, "hello")
        assert str(packet) == "|5|hello"

    def test_packet_str_fragment(self):
        """Test string representation of a fragment packet"""
        packet = Packet(1, 3, 5, "hello")
        assert str(packet) == "1/3|5|hello"

    def test_packet_unpack_single(self):
        """Test unpacking a single packet"""
        packet = Packet.unpack("|5|hello")
        assert packet.count == 0
        assert packet.total == 0
        assert packet.tag == 5
        assert packet.data == "hello"

    def test_packet_unpack_fragment(self):
        """Test unpacking a fragment packet"""
        packet = Packet.unpack("1/3|5|hello")
        assert packet.count == 1
        assert packet.total == 3
        assert packet.tag == 5
        assert packet.data == "hello"

    def test_packet_unpack_invalid(self):
        """Test unpacking an invalid packet"""
        with pytest.raises(ValueError):
            Packet.unpack("invalid")


class TestACK:
    """Tests for the ACK class"""

    def test_ack_str(self):
        """Test string representation of an ACK"""
        ack = ACK(5)
        assert str(ack) == "ACK:5"

    def test_ack_unpack(self):
        """Test unpacking an ACK"""
        ack = ACK.unpack("ACK:5")
        assert ack.tag == 5


class TestMsgPack:
    """Tests for the MsgPack class"""

    @pytest.mark.asyncio
    async def test_single_packet_processing(self, msg_pack, setup_queues):
        """Test processing a single packet"""
        in_queue, processed_queue, _ = setup_queues

        # Put a single packet in the input queue
        await in_queue.put("|10|hello world")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check that it was processed
        assert processed_queue.qsize() == 1
        result = await processed_queue.get()
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_ack_processing(self, msg_pack, setup_queues, ack_callback):
        """Test processing an ACK message"""
        in_queue, _, _ = setup_queues

        # Put an ACK in the input queue
        await in_queue.put("ACK:75")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check that the callback was called
        assert ack_callback.call_count == 1
        assert ack_callback.called_with == 75

    @pytest.mark.asyncio
    async def test_multi_packet_message(self, msg_pack, setup_queues):
        """Test processing a multi-packet message"""
        in_queue, processed_queue, _ = setup_queues

        # Put fragments in the input queue
        await in_queue.put("1/3|10|part one")
        await in_queue.put("2/3|10|part two")
        await in_queue.put("3/3|10|part three")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check that the message was reassembled
        assert processed_queue.qsize() == 1
        result = await processed_queue.get()
        assert result == "part onepart twopart three"

    @pytest.mark.asyncio
    async def test_out_of_order_fragments(self, msg_pack, setup_queues):
        """Test processing fragments that arrive out of order"""
        in_queue, processed_queue, _ = setup_queues

        # Put fragments in the input queue out of order
        await in_queue.put("2/3|10|part two")
        await in_queue.put("3/3|10|part three")
        await in_queue.put("1/3|10|part one")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check that the message was reassembled
        assert processed_queue.qsize() == 1
        result = await processed_queue.get()
        assert result == "part onepart twopart three"

    @pytest.mark.asyncio
    async def test_send_small_message(self, msg_pack, setup_queues):
        """Test sending a small message (fits in single packet)"""
        _, _, _ = setup_queues

        # Create a queue to capture outgoing packets
        out_queue = asyncio.Queue()

        # Send a small message
        test_msg = TestMessage("small message")

        await msg_pack.split_messages_to_queue(test_msg, out_queue, ack_needed=False)

        # Check the output
        assert out_queue.qsize() == 1
        packet_str = await out_queue.get()
        packet = Packet.unpack(packet_str)

        assert packet.count == 0  # Single packet
        assert packet.total == 0
        assert packet.tag < 50  # Non-ACK tag
        assert packet.data == "TEST:test=small message"

    @pytest.mark.asyncio
    async def test_send_large_message(self, msg_pack, setup_queues):
        """Test sending a large message (requires multiple packets)"""
        _, _, _ = setup_queues

        # Create a queue to capture outgoing packets
        out_queue = asyncio.Queue()

        # Send a large message (longer than the split_length of 40)
        test_msg = TestMessage(
            "this is a longer message that will be split into multiple packets"
        )
        await msg_pack.split_messages_to_queue(test_msg, out_queue, ack_needed=True)

        # Check the output - should be multiple packets
        packet_count = out_queue.qsize()
        assert packet_count > 1

        # Collect all packets
        packets = []
        for _ in range(packet_count):
            packet_str = await out_queue.get()
            packet = Packet.unpack(packet_str)
            packets.append(packet)

        # Verify packet properties
        assert packets[0].count == 1  # First fragment
        assert packets[0].total == packet_count
        assert packets[0].tag >= 50  # ACK tag

        # Make sure we can reconstruct the original message
        data_parts = [""] * packet_count
        for packet in packets:
            data_parts[packet.count - 1] = packet.data

        full_data = "".join(data_parts)
        assert (
            full_data
            == "TEST:test=this is a longer message that will be split into multiple packets"
        )

    @pytest.mark.asyncio
    async def test_tag_rotation(self, msg_pack):
        """Test that tags rotate properly"""
        # Force tags to be near rotation points
        msg_pack.nack_tag = 49  # One below ack_threshold
        msg_pack.ack_tag = 99  # One below max_tag

        # Get non-ACK tag (should be 49)
        tag1 = msg_pack._MsgPack__get_tag(False)
        assert tag1 == 49

        # Get non-ACK tag again (should rotate to 1)
        tag2 = msg_pack._MsgPack__get_tag(False)
        assert tag2 == 1

        # Get ACK tag (should be 99)
        tag3 = msg_pack._MsgPack__get_tag(True)
        assert tag3 == 99

        # Get ACK tag again (should rotate to 50)
        tag4 = msg_pack._MsgPack__get_tag(True)
        assert tag4 == 50

    @pytest.mark.asyncio
    async def test_ack_generation(self, msg_pack, setup_queues):
        """Test ACK generation for incoming packets with tag ≥ threshold"""
        in_queue, _, ack_queue = setup_queues

        # Put a packet with tag above threshold in the input queue
        await in_queue.put("|75|hello world")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check that an ACK was generated
        assert ack_queue.qsize() == 1
        ack_tag = await ack_queue.get()
        assert ack_tag == 75

    @pytest.mark.asyncio
    async def test_no_ack_for_low_tag(self, msg_pack, setup_queues):
        """Test that no ACK is generated for packets with tag < threshold"""
        in_queue, _, ack_queue = setup_queues

        # Put a packet with tag below threshold in the input queue
        await in_queue.put("|25|hello world")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check that no ACK was generated
        assert ack_queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_error_handling(self, msg_pack, setup_queues):
        """Test handling of invalid packets"""
        in_queue, processed_queue, _ = setup_queues

        # Put an invalid packet in the input queue
        await in_queue.put("this is not a valid packet")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check that nothing was processed
        assert processed_queue.qsize() == 0

    @pytest.mark.asyncio
    async def test_buffer_cleanup(self, msg_pack, setup_queues):
        """Test that buffers are cleaned up after message completion"""
        in_queue, _, _ = setup_queues

        # Send a multi-packet message
        await in_queue.put("1/2|10|part one")
        await in_queue.put("2/2|10|part two")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check the buffers are empty
        assert len(msg_pack.buffers) == 0

    @pytest.mark.asyncio
    async def test_conflicting_tag_handling(self, msg_pack, setup_queues):
        """Test handling of single packet with tag that already has a buffer"""
        in_queue, processed_queue, _ = setup_queues

        # First create a buffer with a fragmented message
        await in_queue.put("1/3|10|part one")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check that a buffer was created
        assert 10 in msg_pack.buffers

        # Now send a single packet with the same tag
        await in_queue.put("|10|single message")

        # Wait for processing
        await asyncio.sleep(0.1)

        # Check that the buffer was cleared and the single message was processed
        assert 10 not in msg_pack.buffers
        assert processed_queue.qsize() == 1
        assert await processed_queue.get() == "single message"
