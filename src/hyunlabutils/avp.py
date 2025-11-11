from threading import Thread
import time
import os
from flask import Flask, request

from cflib.crazyflie import Crazyflie

class AVP(Thread):

    def __init__(self, cf: Crazyflie):
        Thread.__init__(self)
        
        self.cf = cf
        self.is_open = False
        self.gesture: str = ""
        self.last_updated = 0
        self.leader_position = (0.0, 0.0, 0.0)

        app = Flask(__name__)
        app.add_url_rule("/", view_func=self.index, methods=["POST"])

        port = int(os.getenv("PORT", "5050"))

        app_thread = Thread(target=lambda: app.run(host="0.0.0.0", port=port, debug=False))
        app_thread.start()

    def run(self):
        while self.is_open:
            vx, vy, vz = 0, 0, 0

            if self.leader_position[2] >= 3.0:
                self.gesture = "Down"

            if self.gesture == "Forward":
                vy = 1.0
            elif self.gesture == "Backward":
                vy = -1.0
            elif self.gesture == "RollRight":
                vx = 1.0
            elif self.gesture == "RollLeft":
                vx = -1.0
            elif self.gesture == "Up":
                vz = 1.0
            elif self.gesture == "Down":
                vz = -1.0

            multiplier = 0.5
            vx = vx * multiplier
            vy = vy * multiplier
            vz = vz * multiplier

            yawrate = 0
            self.cf.commander.send_velocity_world_setpoint(vx, vy, vz, yawrate)

            # If it has been more than 0.5 seconds since the last update, clear the gesture
            if time.time() - self.last_updated > 0.5:
                self.gesture = ""

            time.sleep(0.01)
            print(self.gesture)

    def open(self):
        self.is_open = True
        self.start()

    def close(self):
        self.is_open = False

    def index(self):
        try:
            self.gesture = request.get_json(force=False, silent=True)["gesture"]
            self.last_updated = time.time()

        except Exception:
            pass

        return "ok", 200

    def update_leader_position(self, position):
        self.leader_position = position

if __name__ == "__main__":
    avp = AVP(None)
    avp.open()
    time.sleep(100)
    avp.close()