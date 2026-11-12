from types import SimpleNamespace

from mochi.windows.activity import WindowsSystemMonitor


def test_system_monitor_exposes_the_ambisense_context_contract():
    events = []
    readings = iter([(80, False), (19, False), (20, True), None])
    connected = iter([True, False, True, True])
    monitor = WindowsSystemMonitor(
        api=SimpleNamespace(battery=lambda: next(readings)),
        network_available=lambda: next(connected),
        on_battery_low=lambda value: events.append(('low', value)),
        on_charging_started=lambda value: events.append(('charging', value)),
        on_network_lost=lambda: events.append('offline'),
        on_network_restored=lambda: events.append('online'))
    assert monitor.battery.percent is None
    assert monitor.network.connected is None
    monitor.sample()
    assert (monitor.battery.percent, monitor.battery.charging, monitor.network.connected) == (80, False, True)
    monitor.sample()
    monitor.sample()
    assert events == [('low', 19), 'offline', ('charging', 20), 'online']
    assert monitor.battery.charging is True
    monitor.sample()
    assert monitor.battery.percent is None
