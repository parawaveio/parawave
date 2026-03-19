"""Tests for shutdown handler."""

from parawave.shutdown import ShutdownHandler


class TestShutdownHandler:
    def test_initial_state(self):
        handler = ShutdownHandler()
        assert handler.should_stop is False
        assert handler.force_stop is False

    def test_first_interrupt(self):
        handler = ShutdownHandler()
        handler.request_shutdown()
        assert handler.should_stop is True
        assert handler.force_stop is False

    def test_second_interrupt(self):
        handler = ShutdownHandler()
        handler.request_shutdown()
        handler.request_shutdown()
        assert handler.should_stop is True
        assert handler.force_stop is True

    def test_reset(self):
        handler = ShutdownHandler()
        handler.request_shutdown()
        handler.reset()
        assert handler.should_stop is False
        assert handler.force_stop is False


class TestForceShutdown:
    def test_force_shutdown_sets_force_stop(self):
        handler = ShutdownHandler()
        assert not handler.force_stop
        handler.force_shutdown()
        assert handler.force_stop

    def test_force_shutdown_sets_should_stop(self):
        handler = ShutdownHandler()
        assert not handler.should_stop
        handler.force_shutdown()
        assert handler.should_stop
