==========
Microhomie
==========

|build-status|

Microhomie is a MicroPython framework for `Homie <https://github.com/homieiot/convention>`_, a lightweight MQTT convention for the IoT. Main target for Microhomie is the ESP8266 device and has been well tested and used on ESP32.

Microhomie v2 implements `Homie v4.0.0 <https://github.com/homieiot/convention/releases/tag/v4.0.0>`_.

Read the `Microhomie documentation <https://microhomie.readthedocs.io>`_ to get started.

If you want to make your own node, learn from our examples until we have a "howto build nodes" section in the documentation or join the #microhomie channel on the `MicroPython Slack community <https://slack-micropython.herokuapp.com/>`_ and chat with us.

Binaries can be verified with `minisign <https://jedisct1.github.io/minisign/>`_ and the following public key:

.. code-block::

    RWTwPeRvouNzP+mcL1t7QDTnKz96i3Kuf95fjpE28szMq8OTycMmiTzX


MicroPython changes
-------------------

To save some space we disabled **webrepl** and **btree** support. The AccessPoint SSID is `Microhomie-MAC` with the secret `microhomiE`. You can see all the details in the `micropython.patch` file.


Install
-------

Download the `latest image <https://github.com/microhomie/microhomie/releases>`_ and flash it like any MircoPython image to your ESP8266 device. I.E:

.. code-block:: shell

    esptool --port PORT --baud 460800 write_flash --flash_size=detect --verify -fm dio 0x0 microhomie-esp8266-VERSION.bin

Make your changes in `settings.example.py` and copy this file as `settings.py` to your device. You can now test our example nodes from `examples/`, just copy the `main.py` to your device. Start with the `examples/led` node to turn on and off the on-board LED.


Build image
-----------

To build your own Microhomie image run:

.. code-block:: shell

    make bootstrap
    make
    make delpoy PORT=/dev/ttyUSBX


Known issues
------------

* No SSL support for now


.. |build-status| image:: https://readthedocs.org/projects/microhomie/badge/?version=master
    :target: http://microhomie.readthedocs.io/en/master/?badge=master
    :alt: Documentation Status


Included libraries
------------------

* `mqtt_as.py <https://github.com/peterhinch/micropython-mqtt>`_ by Peter Hinch but we use the `patched version <https://github.com/kevinkk525/micropython-mqtt>`_ from Kevin Köck. Kevins version has support for a keyword based configuration and unsubscribe.
* asyn.py ('micro' synchronisation primitives for uasyncio) and aswitch.py (Switch and pushbutton classes for asyncio) from Peter Hinch `micropython-async <https://github.com/peterhinch/micropython-async>`_ repository.
* uasyncio and uasyncio.core from the MicroPython library `repository <https://github.com/micropython/micropython-lib>`_
