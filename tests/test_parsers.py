import ast
import re
import types
import unittest
from pathlib import Path


def load_parser_functions():
    src = Path("adguard-vpn-gui.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    target_names = {"clean_ansi", "parse_status_details", "parse_locations_text"}
    body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in target_names]
    module = types.ModuleType("parsers")
    module.__dict__["re"] = re
    compiled = compile(ast.Module(body=body, type_ignores=[]), "adguard-vpn-gui.py", "exec")
    exec(compiled, module.__dict__)
    return module


parsers = load_parser_functions()


class ParserTests(unittest.TestCase):
    def test_clean_ansi(self):
        self.assertEqual(parsers.clean_ansi("\x1b[32mOK\x1b[0m"), "OK")

    def test_parse_status_connected(self):
        status, city = parsers.parse_status_details("Connected to Frankfurt in Germany")
        self.assertEqual(status, "connected")
        self.assertEqual(city, "Frankfurt")

    def test_parse_status_disconnected(self):
        status, city = parsers.parse_status_details("VPN stopped")
        self.assertEqual(status, "disconnected")
        self.assertIsNone(city)

    def test_parse_locations_sorted_and_filtered(self):
        output = "\n".join([
            "FR France Paris 83",
            "bad line",
            "DE Germany Berlin 24",
            "USA invalid 12",
            "NL Netherlands Amsterdam n/a",
        ])
        rows = parsers.parse_locations_text(output)
        self.assertEqual([code for _, _, code in rows], ["DE", "FR"])
        self.assertIn("[24 ms]", rows[0][1])


if __name__ == "__main__":
    unittest.main()
