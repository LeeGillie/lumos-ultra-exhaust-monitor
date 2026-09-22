"""Networking: Wi-Fi, UDP telemetry out, command/status in, optional MQTT.

Wire format is identical to the one the PC app already speaks:

  node -> PC   UDP 47810   {"node":"laser","seq":1,"up":123,"rssi":-61,
                            "ch":{"pitot":{"pa":46.8,"t":24.0,"ok":true}},
                            "env":{"t":23.9,"rh":41.0,"p":94412},
                            "fan":{"level":7}}
  PC -> node   UDP 47811   {"cmd":"zero"} | {"cmd":"set_level","level":7} | ...
  PC -> nodes  UDP 47812   {"t":"status","cfm":142,"src":"pitot","sev":"warning",
                            "fan":{"level":7,"mode":"auto","rec":8},"msg":"..."}
"""

import json
import socket

try:
    import network
    from time import sleep_ms, ticks_ms, ticks_diff
except ImportError:                                   # host tests
    network = None
    import time as _t

    def sleep_ms(ms): _t.sleep(ms / 1000)
    def ticks_ms(): return int(_t.monotonic() * 1000)
    def ticks_diff(a, b): return a - b


def connect_wifi(ssid, password, hostname, timeout_ms=20000, log=print):
    if network is None:
        return None
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        wlan.config(hostname=hostname)
    except (OSError, ValueError):
        try:
            wlan.config(dhcp_hostname=hostname)
        except Exception:
            pass
    try:
        wlan.config(pm=0xA11140)                      # no power save: steadier UDP
    except Exception:
        pass
    if not wlan.isconnected():
        wlan.connect(ssid, password)
        t0 = ticks_ms()
        while not wlan.isconnected() and ticks_diff(ticks_ms(), t0) < timeout_ms:
            sleep_ms(250)
    log("wifi:", "connected" if wlan.isconnected() else "not connected",
        wlan.ifconfig()[0] if wlan.isconnected() else "")
    return wlan


class Link:
    """UDP telemetry publisher plus command and status listeners."""

    def __init__(self, cfg, log=print):
        self.cfg = cfg
        self.log = log
        self.out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.out.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        except OSError:
            pass
        self.cmd = self._listener(cfg.UDP_COMMAND_PORT)
        self.status = self._listener(cfg.UDP_STATUS_PORT)
        self.mqtt = None
        self.last_status = None
        self.last_status_ms = 0

    def _listener(self, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError:
            pass
        s.bind(("0.0.0.0", port))
        s.setblocking(False)
        return s

    # ---------------- outbound ----------------
    def publish(self, payload):
        data = json.dumps(payload).encode()
        try:
            self.out.sendto(data, (self.cfg.UDP_TARGET, self.cfg.UDP_PORT))
        except OSError as e:
            self.log("udp send failed:", e)
        if self.mqtt:
            try:
                topic = "%s/%s/telemetry" % (self.cfg.MQTT_TOPIC_ROOT, self.cfg.NODE_ID)
                self.mqtt.publish(topic, data)
            except Exception as e:                    # noqa: BLE001 - keep running
                self.log("mqtt publish failed:", e)
                self.mqtt = None

    # ---------------- inbound ----------------
    def poll_commands(self, handler):
        while True:
            try:
                data, _ = self.cmd.recvfrom(512)
            except OSError:
                break
            if not data:
                break
            try:
                handler(json.loads(data))
            except (ValueError, TypeError) as e:
                self.log("bad command:", e)
        if self.mqtt:
            try:
                self.mqtt.check_msg()
            except Exception:
                self.mqtt = None

    def poll_status(self):
        """Latest status broadcast from the PC app, or None when it goes quiet."""
        while True:
            try:
                data, _ = self.status.recvfrom(1024)
            except OSError:
                break
            if not data:
                break
            try:
                msg = json.loads(data)
            except ValueError:
                continue
            if msg.get("t") == "status":
                self.last_status = msg
                self.last_status_ms = ticks_ms()
        if self.last_status and ticks_diff(ticks_ms(), self.last_status_ms) > 10000:
            self.last_status = None
        return self.last_status

    # ---------------- optional MQTT ----------------
    def connect_mqtt(self, on_command):
        if not self.cfg.MQTT_ENABLED:
            return
        try:
            from umqtt.simple import MQTTClient
        except ImportError:
            self.log("umqtt not installed; staying on UDP")
            return
        try:
            root = self.cfg.MQTT_TOPIC_ROOT
            client = MQTTClient("lumosair-" + self.cfg.NODE_ID, self.cfg.MQTT_HOST,
                                port=self.cfg.MQTT_PORT,
                                user=self.cfg.MQTT_USER or None,
                                password=self.cfg.MQTT_PASSWORD or None, keepalive=30)
            client.set_last_will(("%s/%s/status" % (root, self.cfg.NODE_ID)).encode(),
                                 b"offline", retain=True)
            client.set_callback(lambda topic, msg: on_command(json.loads(msg)))
            client.connect()
            client.publish(("%s/%s/status" % (root, self.cfg.NODE_ID)).encode(),
                           b"online", retain=True)
            client.subscribe(("%s/%s/cmd" % (root, self.cfg.NODE_ID)).encode())
            self.mqtt = client
            self.log("mqtt connected")
        except Exception as e:                        # noqa: BLE001
            self.log("mqtt connect failed:", e)
            self.mqtt = None
