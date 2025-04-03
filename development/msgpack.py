from asyncio import Queue
from qsgrc.messages.core import BaseMessage
from qsgrc.messages.msgpack import MsgPack

in_queue = Queue()
out_queue = Queue()

mp = MsgPack(in_queue, out_queue)

short_message = BaseMessage("test_short", "This is a short message")
long_message = BaseMessage("test_long", "a" * 600)


def send_message(data: BaseMessage):
    data_string = str(data)
    packets = []
    packet_0 = data_string[:220]
    rest = data_string[220:]

    packets.append(packet_0)
    while rest:
        next_packet = rest[:220]
        rest = rest[220:]
        packets.append(next_packet)

    return packets
