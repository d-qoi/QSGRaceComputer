import pytest
import asyncio
from qsgrc.messages import AlertMessage, AlertConditions
from qsgrc.alerts import MonitorAlerts


@pytest.fixture
def monitor():
    out_queue = asyncio.Queue()
    return MonitorAlerts("engine", out_queue), out_queue


class TestMonitorAlerts:
    def test_add_rule(self, monitor):
        """Test adding alert rule"""
        mon, _ = monitor
        mon.add_rule("rpm", AlertConditions.GT, 3000)
        assert "rpm" in mon.rules
        condition, hold, threshold = mon.rules["rpm"]
        assert condition == AlertConditions.GT
        assert threshold == 3000
        assert hold is True

    def test_remove_rule(self, monitor):
        """Test removing alert rule"""
        mon, _ = monitor
        mon.add_rule("rpm", AlertConditions.GT, 3000)
        mon.remove_rule("rpm")
        assert "rpm" not in mon.rules

    @pytest.mark.asyncio
    async def test_check_gt_condition_triggers(self, monitor):
        """Test GT condition triggering"""
        mon, queue = monitor
        mon.add_rule("rpm", AlertConditions.GT, 3000)
        await mon.check("rpm", 3500)

        # Check alert was sent
        alert = queue.get_nowait()
        assert isinstance(alert, AlertMessage)
        assert alert.listen_to == "rpm"
        assert alert.val == "3500"

    @pytest.mark.asyncio
    async def test_check_lt_condition_doesnt_trigger(self, monitor):
        """Test LT condition not triggering"""
        mon, queue = monitor
        mon.add_rule("rpm", AlertConditions.LT, 1000)
        await mon.check("rpm", 1500)

        # Queue should be empty (no alert)
        with pytest.raises(asyncio.QueueEmpty):
            queue.get_nowait()

    @pytest.mark.asyncio
    async def test_alert_clear_with_hold_false(self, monitor):
        """Test alert clearing when hold=False"""
        mon, queue = monitor
        mon.add_rule("rpm", AlertConditions.GT, 3000, hold=False)

        # Trigger alert
        await mon.check("rpm", 3500)
        alert = queue.get_nowait()
        assert alert.val == "3500"

        # Clear alert
        await mon.check("rpm", 2500)
        alert = queue.get_nowait()
        assert alert.val == "2500"

    @pytest.mark.asyncio
    async def test_alert_hold(self, monitor):
        """Test alert holding when hold=True"""
        mon, queue = monitor
        mon.add_rule("rpm", AlertConditions.GT, 3000, hold=True)

        # Trigger alert
        await mon.check("rpm", 3500)
        alert = queue.get_nowait()
        assert alert.val == "3500"

        # Check value below threshold - no new alert due to hold
        await mon.check("rpm", 2500)
        with pytest.raises(asyncio.QueueEmpty):
            queue.get_nowait()

    @pytest.mark.asyncio
    async def test_reset_alert_conditions(self, monitor):
        """Test resetting alert conditions"""
        mon, queue = monitor
        mon.add_rule("rpm", AlertConditions.GT, 3000)
        await mon.check("rpm", 3500)
        queue.get_nowait()  # Clear queue

        mon.reset_alert_conditions()

        # Alert should trigger again after reset
        await mon.check("rpm", 3500)
        alert = queue.get_nowait()
        assert alert.val == "3500"

    @pytest.mark.asyncio
    async def test_multiple_rules(self, monitor):
        """Test multiple rules triggering"""
        mon, queue = monitor
        mon.add_rule("rpm", AlertConditions.GT, 3000)
        mon.add_rule("temp", AlertConditions.GTE, 90)

        await mon.check("rpm", 3500)
        await mon.check("temp", 95)

        # Both alerts should be in queue
        alerts = [queue.get_nowait() for _ in range(2)]
        alert_data = {(a.listen_to, a.val) for a in alerts}
        assert ("rpm", "3500") in alert_data
        assert ("temp", "95") in alert_data
