"""Exercise actual GUI callbacks without a desktop, camera or Bluetooth."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from car_challenge import Challenge


class Widget:
    instances = []
    callbacks = {}
    scenario = None
    focused = True

    def __init__(self, *args, **kwargs):
        self.options = kwargs
        self.selected = -1
        self.value = kwargs.get("value", "")
        self.bindings = {}
        Widget.instances.append(self)

    def __getattr__(self, name):
        return lambda *args, **kwargs: None

    def config(self, **kwargs):
        self.options.update(kwargs)

    configure = config

    def bind(self, event, callback):
        self.bindings[event] = callback

    def protocol(self, event, callback):
        Widget.callbacks[event] = callback

    def after(self, delay, callback):
        Widget.callbacks[callback.__name__] = callback

    def current(self, value=None):
        if value is not None:
            self.selected = value
        return self.selected

    def get(self):
        if "values" in self.options and self.selected >= 0:
            return self.options["values"][self.selected]
        return self.value

    def set(self, value):
        self.value = value

    def get_children(self):
        return []

    def focus_displayof(self):
        return self if Widget.focused else None

    def mainloop(self):
        Widget.scenario()


class FakeJoystick:
    command = "STOP"
    def devices(self): return ["0: Test controller"]
    def select(self, index): self.selected = index
    def release(self): pass
    def close(self): pass
    def read(self, allowed): return self.command


class GuiTests(unittest.TestCase):
    def test_physical_drive_starts_timer_before_node_entry(self):
        now = [0.0]
        run = Challenge(clock=lambda: now[0])
        run.start("Driver")
        now[0] = 5.0
        run.start("Changed name")
        run.move(2, "Changed name")
        self.assertEqual(run.elapsed, 5.0)
        self.assertEqual(run.player, "Driver")
        self.assertEqual(run.path, [1, 2])

    def test_drive_reset_focus_finish_and_close_share_connection(self):
        Widget.instances, Widget.callbacks = [], {}
        Widget.focused = True
        sent = []
        bt = SimpleNamespace(is_connected=True, client=SimpleNamespace(is_connected=True),
                             set_movement=sent.append, close=lambda: sent.append("CLOSE"))
        namespace = {"tk": SimpleNamespace(**{name: Widget for name in
                     ("Tk", "Frame", "Label", "Canvas", "Entry", "StringVar")}, ROUND="round"),
                     "ttk": SimpleNamespace(Treeview=Widget, Scrollbar=Widget, Combobox=Widget, Button=Widget),
                     "Button": Widget, "Challenge": Challenge, "GuiJoystick": FakeJoystick,
                     "load_results": lambda: [], "save_result": lambda result: None,
                     "RESULTS_FILE": Path("fake.csv"), "messagebox": SimpleNamespace(showerror=lambda *args: None)}
        tree = ast.parse(Path(__file__).with_name("car_gui.py").read_text(encoding="utf-8"))
        guards = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "NODE_GUARDS" for t in node.targets))
        namespace["NODE_GUARDS"] = ast.literal_eval(guards.value)
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ArUcoDetector")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "process_digital_twin_gui")
        exec(compile(ast.Module(body=[method], type_ignores=[]), "car_gui.py", "exec"), namespace)
        detector = SimpleNamespace(bt_connection=bt, guard_sum=0, consecutive_guard_node=0,
                                   guards_collected=set(), send_bt_command=lambda command: sent.append(command))

        def button(label):
            return next(w.options["command"] for w in Widget.instances if w.options.get("text") == label)

        def scenario():
            self.assertIn("CYAN", sent)
            self.assertTrue(any(w.options.get("text") == "CYAN\nStart / finish" for w in Widget.instances))
            poll = Widget.callbacks["poll_joystick"]
            button("Enable joystick")()
            FakeJoystick.command = "FORWARD"
            poll()
            self.assertEqual(sent[-1], "FORWARD")
            button("STOP")()
            poll()
            self.assertEqual(sent[-1], "STOP")
            button("Enable joystick")()
            Widget.focused = False
            poll()
            self.assertEqual(sent[-1], "STOP")
            Widget.focused = True
            poll()
            self.assertEqual(sent[-1], "STOP")
            button("Reset")()
            self.assertEqual(sent[-1], "CYAN")
            button("Enable joystick")()
            poll()
            self.assertEqual(sent[-1], "FORWARD")
            node_entry = next(w for w in Widget.instances if "<Return>" in w.bindings)
            def visit(node):
                node_entry.options["textvariable"].set(str(node))
                node_entry.bindings["<Return>"](None)
            for node, command, label in [(2, "ORANGE", "YELLOW\n1 consecutive guard node"),
                                         (3, "PURPLE", "PURPLE\n2 consecutive guard nodes"),
                                         (4, "RED", "RED\n3 consecutive guards: GAME OVER")]:
                previous_count = len(sent)
                visit(node)
                self.assertIn(command, sent[previous_count:])
                self.assertTrue(any(w.options.get("text") == label for w in Widget.instances))
            self.assertEqual(sent[-1], "STOP")
            button("Reset")()
            visit(2)
            self.assertEqual(sent[-1], "ORANGE")
            visit(3)
            self.assertEqual(sent[-1], "PURPLE")
            visit(11)
            self.assertEqual(sent[-1], "GREEN")
            visit(14)
            self.assertEqual(sent[-1], "ORANGE")
            button("Reset")()
            for node in (10, 6, 11, 14, 15, 9):
                node_entry.options["textvariable"].set(str(node))
                node_entry.bindings["<Return>"](None)
            self.assertIn("CYAN", sent[-3:])
            self.assertTrue(any(w.options.get("text") == "CYAN\nStart / finish" for w in Widget.instances))
            self.assertEqual(sent[-1], "STOP")
            button("Enable joystick")()
            poll()
            self.assertEqual(sent[-1], "STOP")
            Widget.callbacks["WM_DELETE_WINDOW"]()
            self.assertEqual(sent[-2:], ["STOP", "CLOSE"])

        Widget.scenario = scenario
        namespace["process_digital_twin_gui"](detector)


if __name__ == "__main__":
    unittest.main()
