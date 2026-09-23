"""Division duty rotation.

Neither the number of divisions nor the length of a rotation block is fixed;
both come from configuration.  Rotation order is the administrator's division
ordering, so there is a single source of truth for it.
"""

from __future__ import annotations

from datetime import date


class DivisionRotation:
    def __init__(
        self,
        division_order: tuple[int, ...],
        block_days: int,
        anchor: date,
        enabled: bool = True,
    ) -> None:
        self._order = division_order
        self._block_days = max(1, block_days)
        self._anchor = anchor
        self._enabled = enabled and bool(division_order)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def active_division(self, day: date) -> int | None:
        """Which division holds duty on ``day``, or None when rotation is off.

        The anchor is an explicit input rather than the schedule's start date so
        that regenerating for a later window does not silently shift who is on
        duty.
        """
        if not self._enabled:
            return None
        elapsed_blocks = (day - self._anchor).days // self._block_days
        return self._order[elapsed_blocks % len(self._order)]

    def distance_from_active(self, division_id: int, day: date) -> int:
        """How many rotation steps until ``division_id`` next takes duty.

        Used to prefer borrowing from whichever division is on duty soonest,
        which is the least disruptive place to take people from.
        """
        active = self.active_division(day)
        if active is None or division_id not in self._order:
            return 0
        active_index = self._order.index(active)
        target_index = self._order.index(division_id)
        return (target_index - active_index) % len(self._order)
