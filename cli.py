import argparse
import sys
from asyncio import DatagramTransport

import asyncio
from google.protobuf.message import Message

from protobuf.steammessages_remoteclient_discovery_pb2 import k_ERemoteClientBroadcastMsgDiscovery, \
    CMsgRemoteClientBroadcastDiscovery, \
    k_ERemoteClientBroadcastMsgStatus, ERemoteClientBroadcastMsg
from service.commands.base import CliCommand
from service.commands.pair import PairCommand
from service.commands.stream import StreamCommand
from service.common import ServiceProtocol


class ArgumentParser(argparse.ArgumentParser):

    def exit(self, status: int, message: str):
        raise Exception(message)


def exception_handler(loop: asyncio.AbstractEventLoop, context: dict[str]):
    loop.default_exception_handler(context)
    # ex = context.get('exception')
    loop.stop()


async def ainput(string: str) -> str:
    await asyncio.get_event_loop().run_in_executor(
        None, lambda s=string: sys.stdout.write(s + ' '))
    return await asyncio.get_event_loop().run_in_executor(
        None, sys.stdin.readline)


class ServiceProtocolImpl(ServiceProtocol):
    discovered: [str, tuple[Message, Message]] = {}
    commands: [str, type[CliCommand]] = {
        'stream': StreamCommand,
        's': StreamCommand,
        'pair': PairCommand,
        'p': PairCommand,
    }
    command: CliCommand = None

    def __init__(self):
        super().__init__()
        asyncio.get_event_loop().create_task(self.read_command())
        self.seq_num = 0

    def connection_made(self, transport: DatagramTransport) -> None:
        super().connection_made(transport)
        asyncio.get_event_loop().create_task(self.scan())

    def message_received(self, header: Message, msg: Message, addr: tuple[str, int]):
        msg_type = header.msg_type
        if self.command and self.command.message_received(header, msg, addr):
            return
        elif msg_type == k_ERemoteClientBroadcastMsgStatus:
            ip, _ = addr
            self.discovered[ip] = (header, msg)
        else:
            print(f'{ERemoteClientBroadcastMsg.Name(msg_type)}: {msg}')

    async def scan(self, *_):
        body = CMsgRemoteClientBroadcastDiscovery(seq_num=self.seq_num)
        self.send_message(k_ERemoteClientBroadcastMsgDiscovery, body, ('255.255.255.255', 27036))
        self.seq_num += 1

    async def list(self, *_):
        for k in self.discovered:
            print(k)

    async def show(self, args):
        host = self.discovered.get(args.ip, None)
        if not host:
            print('Host info not available')
            return
        print(host)

    async def pair(self, args):
        _, host = self.discovered.get(args.ip, (None, None))
        if not host:
            print('Host info not available')
            return
        self.command = PairCommand(self, args.ip, host)
        await self.command.run()

    async def read_command(self):
        while True:
            args = (await ainput('>')).strip().split(' ')
            command_type = self.commands.get(args[0], None)
            if not command_type:
                print(f'Unrecognized command {args[0]}.')
                continue
            command: CliCommand = command_type(self)
            if not command.parse_args(args[1:]):
                continue
            self.command = command
            await command.run()

    def setup_argparser(self) -> argparse.ArgumentParser:
        parser = ArgumentParser(prog='', description='CLI shell', add_help=False, exit_on_error=False)
        subparsers = parser.add_subparsers()
        subparsers.add_parser('scan').set_defaults(action=self.scan)
        subparsers.add_parser('list').set_defaults(action=self.list)
        show = subparsers.add_parser('show')
        show.add_argument('ip', type=str)
        show.set_defaults(action=self.show)
        pair = subparsers.add_parser('pair')
        pair.set_defaults(action=self.pair)
        pair.add_argument('ip', type=str)
        return parser


if __name__ == '__main__':
    main_loop = asyncio.get_event_loop()
    # main_loop.set_exception_handler(exception_handler)
    t = main_loop.create_datagram_endpoint(ServiceProtocolImpl, local_addr=('0.0.0.0', 0), allow_broadcast=True)
    main_loop.run_until_complete(t)
    main_loop.run_forever()
