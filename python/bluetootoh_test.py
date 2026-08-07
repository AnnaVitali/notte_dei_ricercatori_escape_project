""" import asyncio
from bleak import BleakClient

ADDRESS = "C2:38:E3:86:54:78"

UART_RX = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"


async def main():

    async with BleakClient(ADDRESS) as client:

        print("Connected")

        while True:
            await client.write_gatt_char(
                UART_RX,
                b"HELLO#"
            )

            print("sent")

            await asyncio.sleep(2)


asyncio.run(main()) """

import asyncio
from bleak import BleakClient

ADDRESS = "C2:38:E3:86:54:78"

UART_WRITE = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"


async def main():

    async with BleakClient(ADDRESS) as client:

        print("Connected")

        while True:
            await client.write_gatt_char(
                UART_WRITE,
                b"HELLO#",
                response=False
            )

            print("sent HELLO")
            await asyncio.sleep(2)


asyncio.run(main())