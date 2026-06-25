import unittest

from approve_and_build_tool.proposed_work_parser import (
    parse_latest_proposed_work,
    SENTINEL_OPEN,
    SENTINEL_CLOSE,
)


def _block(body):
    return SENTINEL_OPEN + "\n" + body + "\n" + SENTINEL_CLOSE


class ProposedWorkParserTests(unittest.TestCase):
    def test_no_block_returns_none(self):
        self.assertIsNone(parse_latest_proposed_work("just chatting, no proposal here"))

    def test_empty_input_returns_none(self):
        self.assertIsNone(parse_latest_proposed_work(""))

    def test_single_block_parsed(self):
        text = "Here is my plan.\n" + _block('{"summary": "add parser", "details": "x"}')
        proposal = parse_latest_proposed_work(text)
        self.assertEqual(proposal["summary"], "add parser")

    def test_latest_block_wins(self):
        text = (
            _block('{"summary": "first"}')
            + "\nthen reconsidered\n"
            + _block('{"summary": "second"}')
        )
        self.assertEqual(parse_latest_proposed_work(text)["summary"], "second")

    def test_bad_json_in_only_block_returns_none(self):
        text = _block("{not valid json}")
        self.assertIsNone(parse_latest_proposed_work(text))

    def test_falls_back_to_earlier_valid_block_when_latest_is_bad(self):
        text = _block('{"summary": "good"}') + _block("{broken")
        self.assertEqual(parse_latest_proposed_work(text)["summary"], "good")

    def test_non_object_json_rejected(self):
        text = _block('["a", "list", "not", "an", "object"]')
        self.assertIsNone(parse_latest_proposed_work(text))


if __name__ == "__main__":
    unittest.main()
