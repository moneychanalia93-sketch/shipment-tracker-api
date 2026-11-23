import unittest

from tracker.states import ALLOWED_MOVES, FINISHED, STATES, can_move


# Tests for the state machine alone (no server, no database).
class StateMachineTests(unittest.TestCase):
    def test_created_can_go_to_packed_or_cancelled(self):
        self.assertTrue(can_move("created", "packed"))
        self.assertTrue(can_move("created", "cancelled"))

    def test_packed_can_go_to_shipped_or_cancelled(self):
        self.assertTrue(can_move("packed", "shipped"))
        self.assertTrue(can_move("packed", "cancelled"))

    def test_shipped_can_only_be_delivered(self):
        self.assertTrue(can_move("shipped", "delivered"))
        self.assertFalse(can_move("shipped", "cancelled"))

    def test_finished_shipments_cannot_move_anywhere(self):
        for finished in FINISHED:
            for target in STATES:
                self.assertFalse(can_move(finished, target), f"{finished} -> {target}")

    def test_cannot_skip_a_step(self):
        self.assertFalse(can_move("created", "shipped"))
        self.assertFalse(can_move("created", "delivered"))
        self.assertFalse(can_move("packed", "delivered"))

    def test_cannot_go_backwards_or_stay_put(self):
        self.assertFalse(can_move("packed", "created"))
        self.assertFalse(can_move("packed", "packed"))

    def test_unknown_status_is_never_allowed(self):
        self.assertFalse(can_move("created", "lost"))
        self.assertFalse(can_move("lost", "packed"))

    def test_every_status_has_a_rule_and_targets_are_real_statuses(self):
        self.assertEqual(set(ALLOWED_MOVES), set(STATES))
        for targets in ALLOWED_MOVES.values():
            for target in targets:
                self.assertIn(target, STATES)
