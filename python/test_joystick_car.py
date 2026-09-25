import unittest
from joystick_car import hat_command, button_command, ReleaseGate, pump


class DpadTests(unittest.TestCase):
    def test_directions_and_diagonals(self):
        for hat, expected in [((0, 1), "FORWARD"), ((0, -1), "BACKWARD"),
                              ((-1, 0), "LEFT"), ((1, 0), "RIGHT"),
                              ((0, 0), "STOP"), ((1, 1), "STOP"),
                              ((-1, -1), "STOP"), ((1, -1), "STOP"), ((-1, 1), "STOP")]:
            self.assertEqual(hat_command(hat), expected)
        self.assertEqual(button_command([False, False, True, False]), "LEFT")
        self.assertEqual(button_command([True, True, False, False]), "STOP")

    def test_release_required_at_start_and_after_focus_loss(self):
        gate = ReleaseGate()
        self.assertEqual(gate.command("FORWARD", True, False), "STOP")
        gate.command("STOP", True, True)
        self.assertEqual(gate.command("FORWARD", True, False), "FORWARD")
        self.assertEqual(gate.command("FORWARD", False, False), "STOP")
        self.assertEqual(gate.command("FORWARD", True, False), "STOP")
        gate.command("STOP", True, True)
        self.assertEqual(gate.command("LEFT", True, False), "LEFT")


class PumpTests(unittest.IsolatedAsyncioTestCase):
    async def test_input_failure_sends_final_stop(self):
        sent = []
        class Window:
            closed = False
            def read(self):
                raise RuntimeError("Controller unplugged")
        async def write(command):
            sent.append(command)
        with self.assertRaisesRegex(RuntimeError, "unplugged"):
            await pump(Window(), write, True)
        self.assertEqual(sent, ["STOP", "STOP"])


if __name__ == "__main__":
    unittest.main()
