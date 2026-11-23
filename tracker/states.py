"""The state machine: which status changes are allowed."""

STATES = ["created", "packed", "shipped", "delivered", "cancelled"]

# For each status, the statuses it may move to next. An empty list means
# the shipment is finished and can never move again.
ALLOWED_MOVES = {
    "created": ["packed", "cancelled"],
    "packed": ["shipped", "cancelled"],
    "shipped": ["delivered"],
    "delivered": [],
    "cancelled": [],
}

# Statuses where nothing more will happen. Used to decide what is "late".
FINISHED = ["delivered", "cancelled"]


# Answer yes/no: may a shipment go from `current` to `new`?
# Every status change asks this one function, so the rules live in one place.
def can_move(current, new):
    return new in ALLOWED_MOVES.get(current, [])
