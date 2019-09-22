from gc import collect, mem_free
from sys import platform

from asyn import Event
from homie import __version__, utils
from homie.constants import (
    DEVICE_STATE,
    MAIN_DELAY,
    QOS,
    RESTORE_DELAY,
    SLASH,
    STATE_INIT,
    STATE_READY,
    STATE_RECOVER,
    UNDERSCORE,
    WDT_DELAY,
)
from homie.utils import get_unique_id
from machine import WDT, reset
from mqtt_as import MQTTClient, eliza
from uasyncio import get_event_loop, sleep_ms
from ubinascii import hexlify
from utime import time

_EVENT = Event()


def await_ready_state(func):
    def new_gen(*args, **kwargs):
        # fmt: off
        await _EVENT
        await func(*args, **kwargs)
        # fmt: on

    return new_gen


class HomieDevice:

    """MicroPython implementation of the Homie MQTT convention for IoT."""

    def __init__(self, settings):
        self._state = STATE_INIT
        self._extensions = getattr(settings, "EXTENSIONS", [])
        self._first_start = True

        self.async_tasks = []
        self.stats_interval = getattr(settings, "DEVICE_STATS_INTERVAL", 60)

        self.nodes = []
        self.callback_topics = {}

        self.device_name = getattr(settings, "DEVICE_NAME", b"mydevice")

        device_id = getattr(settings, "DEVICE_ID", get_unique_id())
        self.btopic = getattr(settings, "MQTT_BASE_TOPIC", b"homie")
        self.dtopic = SLASH.join((self.btopic, device_id))

        self.mqtt = MQTTClient(
            client_id=device_id,
            server=settings.MQTT_BROKER,
            port=getattr(settings, "MQTT_PORT", 1883),
            user=getattr(settings, "MQTT_USERNAME", None),
            password=getattr(settings, "MQTT_PASSWORD", None),
            keepalive=getattr(settings, "MQTT_KEEPALIVE", 30),
            ping_interval=0,
            ssl=getattr(settings, "MQTT_SSL", False),
            ssl_params=getattr(settings, "MQTT_SSL_PARAMS", {}),
            response_time=10,
            clean_init=True,
            clean=True,
            max_repubs=4,
            will=(SLASH.join((self.dtopic, DEVICE_STATE)), b"lost", True, QOS),
            subs_cb=self.sub_cb,
            wifi_coro=eliza,
            connect_coro=self.connection_handler,
            ssid=settings.WIFI_SSID,
            wifi_pw=settings.WIFI_PASSWORD,
        )

    def add_node(self, node):
        """add a node class of Homie Node to this device"""
        node.device = self
        self.nodes.append(node)
        loop = get_event_loop()
        loop.create_task(node.publish_data())
        collect()

    def format_topic(self, topic):
        return SLASH.join((self.dtopic, topic))

    async def subscribe(self, topic):
        topic = self.format_topic(topic)
        # print("MQTT SUBSCRIBE: {}".format(topic))
        await self.mqtt.subscribe(topic, QOS)

    async def unsubscribe(self, topic):
        topic = self.format_topic(topic)
        # print("MQTT UNSUBSCRIBE: {}".format(topic))
        await self.mqtt.unsubscribe(topic)

    async def connection_handler(self, client):
        """subscribe to all registered device and node topics"""
        if self._first_start is False:
            await self.publish(DEVICE_STATE, STATE_RECOVER)

        subscribe = self.subscribe
        unsubscribe = self.unsubscribe

        # device topics
        await self.mqtt.subscribe(
            SLASH.join((self.btopic, b"$broadcast/#")), QOS
        )

        # node topics
        nodes = self.nodes
        for n in nodes:
            props = n._properties
            for p in props:
                if p.settable:
                    nid_enc = n.id.encode()
                    if nid_enc not in self.callback_topics:
                        self.callback_topics[nid_enc] = n.callback
                    # retained topics to restore messages
                    if p.restore:
                        t = b"{}/{}".format(n.id, p.id)
                        await subscribe(t)
                        await sleep_ms(RESTORE_DELAY)
                        await unsubscribe(t)

                    # final subscribe to /set topics
                    t = b"{}/{}/set".format(n.id, p.id)
                    await subscribe(t)

        # on first connection:
        # * publish device and node properties
        # * enable WDT
        # * run all coros
        if self._first_start is True:
            await self.publish_properties()
            self._first_start = False

            # activate WDT
            loop = get_event_loop()
            loop.create_task(self.wdt())

            # start coros waiting for ready state
            _EVENT.set()
            await sleep_ms(MAIN_DELAY)
            _EVENT.clear()

        await self.publish(DEVICE_STATE, STATE_READY)

    def sub_cb(self, topic, msg, retained):
        # print("MQTT MESSAGE: {} --> {}, {}".format(topic, msg, retained))

        # broadcast callback passed to nodes
        if b"/$broadcast" in topic:
            nodes = self.nodes
            for n in nodes:
                n.broadcast_callback(topic, msg, retained)
        else:
            # node property callbacks
            nt = topic.split(SLASH)
            node = nt[len(self.dtopic.split(SLASH))]
            if node in self.callback_topics:
                self.callback_topics[node](topic, msg, retained)

    async def publish(self, topic, payload, retain=True):
        if not isinstance(payload, bytes):
            payload = bytes(str(payload), "utf-8")

        t = SLASH.join((self.dtopic, topic))
        # print('MQTT PUBLISH: {} --> {}'.format(t, payload))
        await self.mqtt.publish(t, payload, retain, QOS)

    async def broadcast(self, payload, level=None):
        if not isinstance(payload, bytes):
            payload = bytes(str(payload), "utf-8")

        topic = SLASH.join((self.btopic, b"$broadcast"))
        if level is not None:
            if isinstance(level, str):
                level = level.encode()
            topic = SLASH.join((topic, level))
        # print("MQTT BROADCAST: {} --> {}".format(topic, payload))
        await self.mqtt.publish(topic, payload, retain=False, qos=QOS)

    async def publish_properties(self):
        """publish device and node properties"""
        publish = self.publish

        # device properties
        await publish(b"$homie", b"4.0.0")
        await publish(b"$name", self.device_name)
        await publish(DEVICE_STATE, STATE_INIT)
        await publish(b"$implementation", bytes(platform, "utf-8"))
        await publish(
            b"$nodes", b",".join([n.id.encode() for n in self.nodes])
        )

        # node properties
        nodes = self.nodes
        for n in nodes:
            await n.publish_properties()

        if self._extensions:
            await publish(b"$extensions", b",".join(self._extensions))
            if b"org.homie.legacy-firmware:0.1.1:[4.x]" in self._extensions:
                await publish(b"$localip", utils.get_local_ip())
                await publish(b"$mac", utils.get_local_mac())
                await publish(b"$fw/name", b"Microhomie")
                await publish(b"$fw/version", __version__)
            if b"org.homie.legacy-stats:0.1.1:[4.x]" in self._extensions:
                await self.publish(b"$stats/interval", self.stats_interval)
                # Start stats coro
                loop = get_event_loop()
                loop.create_task(self.publish_stats())

    @await_ready_state
    async def publish_stats(self):
        from utime import time

        start_time = time()
        delay = self.stats_interval * MAIN_DELAY
        publish = self.publish
        while True:
            uptime = time() - start_time
            await publish(b"$stats/uptime", uptime)
            await publish(b"$stats/freeheap", mem_free())
            await sleep_ms(delay)

    async def run(self):
        try:
            await self.mqtt.connect()
        except OSError:
            print("ERROR: can not connect to MQTT")
            await sleep_ms(5000)
            reset()

        while True:
            await sleep_ms(MAIN_DELAY)

    def run_forever(self):
        loop = get_event_loop()
        loop.run_until_complete(self.run())

    async def wdt(self):
        wdt = WDT()
        while True:
            wdt.feed()
            await sleep_ms(WDT_DELAY)

    def start(self):
        # DeprecationWarning
        self.run_forever()
