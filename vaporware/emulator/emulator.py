#!/usr/bin/env python3

"""
Quick/dirty Vaporlight emulator.

:Author: Felix Kaiser <felix.kaiser@fxkr.net>
:Version: 0.1.0
:License: revised BSD

Provides a network server implementing the bus protocol
and displays LED states in a GTK window. Useful when you
are working on the/a Vaporlight daemon.

Here's how you can try it out: start it, then
send it a commands via netcat::

    python emulator.py &
    netcat -c localhost 23429 < sample/rgb.bin

This should make the first three virtual LEDs
become red, green and blue.

Notes:
- only one client can be connected at a time.
- this emulator uses the bus protocol (which
  is the protocol used to speak to the actual
  hardware), not the "low level" protocol
  (which is used to speak to the router).
  Support for the latter could/should be added
  in the future.
"""

import argparse
import copy
import signal
import socket
import sys
import threading
import traceback

import cairo
from gi.repository import Gtk, GObject


class Model(object):

    def __init__(self, modules, leds_per_module):
        self.observers = []
        self.modules = modules
        self.leds_per_module = leds_per_module
        self.back_buffer = [[[0, 0, 0] # [r, g, b]
            for x in range(self.leds_per_module)]
            for y in range(self.modules)]
        self.front_buffer = copy.deepcopy(self.back_buffer)

    def set_value(self, module, channel, value):
        """set a channel brightness; takes effect when `strobe()` is called"""
        try:
            self.back_buffer[module][channel // 3][channel % 3] = value
        except IndexError as e:
            pass

    def add_observer(self, func):
        """add a function thats called once per strobe command"""
        self.observers.append(func)

    def strobe(self):
        """apply led state changes"""
        self.front_buffer = copy.deepcopy(self.back_buffer)
        for observer in self.observers:
            observer()


class GtkView(object):

    def __init__(self, model):
        self.model = model
        model.add_observer(self.please_redraw)
        self.init()

    def run(self):
        signal.signal(signal.SIGINT, signal.SIG_DFL) # fix ctrl-c
        GObject.threads_init()
        Gtk.main() # blocks until window is closed

    def init(self):
        self.window = Gtk.Window(
            title="Vaporlight emulator",
            default_width=800,
            default_height=600,
            can_focus=False,
            window_position="center-always")
        self.window.connect("destroy", self.on_destroy)

        self.drawing = Gtk.DrawingArea(visible=True, can_focus=False)
        self.drawing.connect("draw", self.on_draw)
        self.drawing.connect("configure-event", self.on_configure)
        self.window.add(self.drawing)

        self.double_buffer = None
        self.window.show()

    def please_redraw(self):
        def idle_func():
            self.redraw()
            self.drawing.queue_draw()
            return False # don't reschedule automatically
        GObject.idle_add(idle_func)

    def redraw(self):
        db = self.double_buffer
        cc = cairo.Context(db)
        cc.scale(db.get_width(), db.get_height())
        cc.set_source_rgb(1, 1, 1)

        rows = self.model.modules
        cols = self.model.leds_per_module
        cell_size_w = 1.0 / cols
        cell_size_h = 1.0 / rows
        line_width = 1.0
        line_width, _ = cc.device_to_user(line_width, 0.0)

        for y in range(self.model.modules):
            for x in range(self.model.leds_per_module):
                cc.rectangle(
                    x * cell_size_w, y * cell_size_h,
                    cell_size_w, cell_size_h)
                cc.set_line_width(line_width)
                cc.set_source_rgb(*self.model.front_buffer[y][x])
                cc.fill()

        db.flush()

    def on_destroy(self, widget):
        Gtk.main_quit()

    def on_draw(self, widget, cr):
        cr.set_source_surface(self.double_buffer, 0.0, 0.0)
        cr.paint()
        return False

    def on_configure(self, widget, event, data=None): # window resized
        if self.double_buffer != None:
            self.double_buffer.finish()
            self.double_buffer = None
        self.double_buffer = cairo.ImageSurface(
            cairo.FORMAT_ARGB32,
            widget.get_allocated_width(),
            widget.get_allocated_height())
        self.redraw()
        return False


class NetworkByteSource(object):

    def __init__(self, addr):
        self.addr = addr

    def get_bytes(self):
        server_sck = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sck.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sck.bind(self.addr)
        server_sck.listen(5)
        while True:
            try:
                client_address = server_sck.accept()
                yield from self._read_bytes(client_address[0])
            except ProtocolViolation:
                traceback.print_exc(file=sys.stderr)
            finally:
                try:
                    client_address[0].close()
                except Exception:
                    traceback.print_exc(file=sys.stderr)

    def _read_bytes(self, sck):
        while True:
            data = sck.recv(1024)
            if not data:
                break # Connection closed
            yield from data


class StdinByteSource(object):

    def get_bytes(self):
        source = sys.stdin.buffer # .buffer is in binary mode
        while True:
            byte = source.read(1)
            if byte:
                yield ord(byte)
            else:
                return # EOF


class Controller(threading.Thread):

    def __init__(self, model, byte_source):
        self.byte_source = byte_source
        self.model = model
        threading.Thread.__init__(self)
        self.daemon = True

    def run(self): # runs in its own thread
        for frame in self.read_frames(self.byte_source.get_bytes()):
            print(frame)
            if frame == [0xfe]:
                self.model.strobe()
            elif len(frame) >= 1:
                for channel, value in enumerate(frame[1:]):
                    self.model.set_value(frame[0], channel, value)
            else:
                raise ProtocolViolation()

    def read_frames(self, byte_stream):
        STATE_IGNORE = 0
        STATE_NORMAL = 1
        STATE_ESCAPE = 2

        ESCAPE_MARK = 0x54
        START_MARK = 0x55
        ESCAPE_ESCAPED = 0x00
        START_ESCAPED = 0x01

        payload_buf = []
        state = STATE_IGNORE

        for num in byte_stream:

            # start state; synchronize to start of a frame
            if state == STATE_IGNORE:
                if num == START_MARK:
                    state = STATE_NORMAL

            # somewhere within a frame
            elif state == STATE_NORMAL:
                if num == ESCAPE_MARK:
                    state = STATE_ESCAPE
                elif num == START_MARK: # start of new frame
                    yield payload_buf
                    payload_buf = []
                else:
                    payload_buf.append(num)

            # within a frame, after an escape mark
            elif state == STATE_ESCAPE:
                if num == ESCAPE_ESCAPED:
                    payload_buf.append(ESCAPE_MARK)
                    state = STATE_NORMAL
                elif num == START_ESCAPED:
                    payload_buf.append(START_MARK)
                    state = STATE_NORMAL
                else:
                    raise ProtocolViolation()


class ProtocolViolation(Exception):
    pass


def main():

    par = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description='Vaporlight bus master emulator')
    par.add_argument('-a', '--addr', metavar="X",
        dest='addr', action='store', default="localhost",
        help='TCP address to listen on')
    par.add_argument('-p', '--port', metavar="X",
        dest='port', action='store', type=int, default=23429,
        help='TCP port to listen on')
    par.add_argument('-m', '--modules', metavar="X",
        dest='modules', action='store', type=int, default=4,
        help='number of modules')
    par.add_argument('-l', '--leds', metavar="X",
        dest='leds', action='store', type=int, default=5,
        help='number of leds per module')
    par.add_argument('-i', '--stdin',
        dest='use_stdin', action='store_true', default=False,
        help='read from stdin instead of a socket')
    args = par.parse_args()

    if args.use_stdin:
        bytesrc = StdinByteSource()
    else:
        bytesrc = NetworkByteSource((args.addr, args.port))

    model = Model(args.modules, args.leds)
    view = GtkView(model)
    ctrl = Controller(model, bytesrc)
    ctrl.start()
    view.run()


if __name__ == "__main__":
    main()

