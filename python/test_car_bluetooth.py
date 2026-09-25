import unittest
from car_bluetooth import BluetoothConnection, MovementMailbox


class MailboxTests(unittest.TestCase):
    def test_latest_command_stop_and_expiry(self):
        now = [0.0]
        mailbox = MovementMailbox(clock=lambda: now[0])
        self.assertIsNone(mailbox.current())
        mailbox.put("FORWARD")
        mailbox.put("LEFT")
        self.assertEqual(mailbox.current(), "LEFT")
        mailbox.put("STOP")
        self.assertEqual(mailbox.current(), "STOP")
        mailbox.put("RIGHT")
        now[0] = 0.25
        self.assertEqual(mailbox.current(), "STOP")


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_movement_before_led_and_shared_uart(self):
        sent = []
        connection = BluetoothConnection("fake")
        class Client:
            is_connected = True
            async def write_gatt_char(self, uuid, value, response):
                sent.append(value)
                if len(sent) == 2:
                    connection.close()
        connection.client = Client()
        connection.running = True
        connection.queue_command("GREEN")
        connection.set_movement("FORWARD")
        connection.set_movement("STOP")
        await connection._process_queue()
        self.assertEqual(sent, [b"STOP#", b"GREEN#"])
        self.assertTrue(connection.closing.is_set())

    async def test_close_sends_stop_and_disconnects(self):
        sent = []
        connection = BluetoothConnection("fake")
        class Client:
            is_connected = True
            async def write_gatt_char(self, uuid, value, response):
                sent.append(value)
            async def disconnect(self):
                self.is_connected = False
        client = Client()
        async def connect():
            connection.client = client
        connection.connect = connect
        connection.running = True
        connection.close()
        await connection._connect_and_process()
        self.assertEqual(sent, [b"STOP#"])
        self.assertFalse(client.is_connected)

    def test_offline_movement_is_not_queued(self):
        connection = BluetoothConnection("fake")
        connection.set_movement("FORWARD")
        self.assertIsNone(connection.movement.current())


if __name__ == "__main__":
    unittest.main()
