from threading import Thread
import time
from enum import Enum

from cflib.crazyflie import Crazyflie
from cfclient.utils.config import Config
from cfclient.utils.input.inputreaders.linuxjsdev import Joystick

class Xbox360Controller(Thread):

    A = 0
    B = 1
    X = 2
    Y = 3
    LB = 4
    RB = 5
    BACK = 6
    START = 7
    XBOX = 8
    LJ_PRESS = 9
    RJ_PRESS = 10

    LJ_H = 0
    LJ_V = 1
    LT = 2
    RJ_H = 3
    RJ_V = 4
    RT = 5
    DPAD_H = 6
    DPAD_V = 7

    DPAD_LEFT_DIRECTION = -1
    DPAD_RIGHT_DIRECTION = 1
    DPAD_UP_DIRECTION = -1
    DPAD_DOWN_DIRECTION = 1

    def __init__(self, cf: Crazyflie = None):
        Thread.__init__(self)

        self.cf = cf

        self.joystick = Joystick()

        devices = self.joystick.devices()
        self.device_id = None
        if len(devices) > 0:
            self.device_id = devices[0]["id"]
        else:
            raise Exception("No joystick devices found. Please connect a joystick and try again.")

        self.button_press_callbacks = {}
        self.button_prevs = {}

        self.axis_press_positive_callbacks = {}
        self.axis_press_negative_callbacks = {}
        self.axis_signs = {}
        self.axis_prevs = {}

        self.axis_callbacks = {}

        self.flight_axes = []
        self.flight_callback = None

    def run(self):
        while self.is_open:
            self.read()
            time.sleep(0.01)
    
    def open(self):
        """
        Open the joystick device and start the thread to read input data.
        """
        self.joystick.open(self.device_id)
        self.is_open = True
        self.start()

    def close(self):
        """
        Close the joystick device and stop the thread.
        """
        self.is_open = False
        self.joystick.close(self.device_id)

    def read(self):
        [axis_values, button_values] = self.joystick.read(self.device_id)
        
        if self.flight_callback is not None and len(self.flight_axes) == 4:
            self.flight_callback(axis_values[self.flight_axes[0]],
                                axis_values[self.flight_axes[1]],
                                axis_values[self.flight_axes[2]], 
                                axis_values[self.flight_axes[3]])

        for button, callback in self.button_press_callbacks.items():
            if self.button_prevs[button] == 0 and button_values[button] == 1:
                callback()
        
        for axis, callback in self.axis_callbacks.items():
            callback(axis_values[axis])

        for axis, callback in self.axis_press_positive_callbacks.items():
            if self.axis_prevs[axis] <= 0.5 and axis_values[axis] > 0.5:
                callback()

        for axis, callback in self.axis_press_negative_callbacks.items():
            if self.axis_prevs[axis] >= -0.5 and axis_values[axis] < -0.5:
                callback()

        # Update previous states
        for button in self.button_prevs.keys():
            self.button_prevs[button] = button_values[button]

        for axis in self.axis_prevs.keys():
            self.axis_prevs[axis] = axis_values[axis]

    def add_flight_controls(self, axes, callback):
        """
        Add custom flight controls for the given Crazyflie.

        :param axes: List of 4 axis identifiers for the desired flight controls
        :param callback: Function to call when the axes are moved. The function should take four arguments which correspond to the axes in the order they are given in the axes list.
        """
        if len(axes) != 4:
            raise Exception("Axes list must contain exactly 4 axis identifiers.")
        
        self.flight_axes = axes
        self.flight_callback = callback

    def add_manual_flight_controls(self):
        """
        Add manual flight controls for the given Crazyflie.
        """
        if self.cf is None:
            raise Exception("Crazyflie instance is None. Please use add_flight_controls instead.")

        def flight_controls(roll, pitch, yawrate, thrust):
            roll = roll * Config().get("max_rp")
            pitch = -pitch * Config().get("max_rp")
            yawrate = 0 # yawrate * Config().get("max_yaw")
            thrust = int(-thrust * 0xFFFF if -thrust > 0 else 0)
            self.cf.commander.send_setpoint(roll, pitch, yawrate, thrust)

        self.add_flight_controls([Xbox360Controller.LJ_H, Xbox360Controller.LJ_V, Xbox360Controller.RJ_H, Xbox360Controller.RJ_V], flight_controls)

    def add_velocity_flight_controls(self):
        """
        Add velocity flight controls for the given Crazyflie.
        """
        if self.cf is None:
            raise Exception("Crazyflie instance is None. Please use add_flight_controls instead.")

        def flight_controls(backward, right, down, yawrate):
            vx = right
            vy = -backward
            vz = -down
            yawrate = 0
            self.cf.commander.send_velocity_world_setpoint(vx, vy, vz, yawrate)

        self.add_flight_controls([Xbox360Controller.LJ_V, Xbox360Controller.LJ_H, Xbox360Controller.RJ_V, Xbox360Controller.RJ_H], flight_controls)

    def add_button_press_callback(self, button: int, callback):
        """
        Add a callback for button press events. The callback is called when the button is pressed.

        :param button: Button identifier
        :param callback: Function to call when the button is pressed. The function should take no arguments.
        """
        self.button_press_callbacks[button] = callback
        self.button_prevs[button] = 0
    
    def add_axis_callback(self, axis: int, callback):
        """
        Add a callback for axis movements. The callback is called continuously while the thread is running.

        :param axis: Axis identifier
        :param callback: Function to call when the axis is moved. The function should take one argument: the axis value between -1 and 1.
        """
        self.axis_callbacks[axis] = callback

    def add_axis_press_callback(self, axis: int, axis_sign: int, callback):
        """
        Add a callback for axis press events. The callback is called when the axis is pressed.

        :param axis: Axis identifier
        :param axis_sign: The sign of the axis to trigger on: should be either 1 or -1
        :param callback: Function to call when the axis is pressed. The function should take no arguments.
        """
        self.axis_prevs[axis] = 0

        if axis_sign == 1:
            self.axis_press_positive_callbacks[axis] = callback
        elif axis_sign == -1:
            self.axis_press_negative_callbacks[axis] = callback
        else:
            raise Exception("axis_sign should be either 1 or -1")