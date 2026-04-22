import time
import numpy as np

from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncLogger import SyncLogger

class LLComm():

    UPDATE_PERIOD = 0.1
    
    @staticmethod
    def _get_position(cf: Crazyflie):
        position = np.zeros(3)

        logconf = LogConfig('', 10)
        logconf.add_variable('stateEstimate.x', 'float')
        logconf.add_variable('stateEstimate.y', 'float')
        logconf.add_variable('stateEstimate.z', 'float')

        with SyncLogger(cf, logconf) as logger:
            for log_entry in logger:
                position[0] = log_entry[1]['stateEstimate.x']
                position[1] = log_entry[1]['stateEstimate.y']
                position[2] = log_entry[1]['stateEstimate.z']
                break

        return position

    @staticmethod
    def go_to_first_order(cf: Crazyflie, x_desired: float, y_desired: float, z_desired: float, yaw_desired: float, duration_s: float, relative: bool = False):
        t_start = time.perf_counter()
        
        position_current = LLComm._get_position(cf)
        position_desired = np.array([x_desired, y_desired, z_desired])
        if relative:
            position_desired += position_current
        vector = position_desired - position_current

        for update_idx in range(int(duration_s / LLComm.UPDATE_PERIOD)):
            while time.perf_counter() - t_start < update_idx * LLComm.UPDATE_PERIOD:
                time.sleep(LLComm.UPDATE_PERIOD / 100)

            time_norm = update_idx * LLComm.UPDATE_PERIOD / duration_s # Fraction of total duration that has elapsed

            position = position_current + vector * time_norm
            velocity = vector / duration_s

            cf.commander.send_full_state_setpoint(
                pos=position,
                vel=velocity,
                acc=np.zeros(3),
                orientation=np.array([0, 0, 0, 1]),
                rollrate=0, pitchrate=0, yawrate=0)

        # Only return once time has reached duration_s
        while time.perf_counter() - t_start < duration_s:
            time.sleep(LLComm.UPDATE_PERIOD / 100)

    @staticmethod
    def go_to_third_order(cf: Crazyflie, x_desired: float, y_desired: float, z_desired: float, yaw_desired: float, duration_s: float):
        position_current = LLComm._get_position(cf)
        position_desired = np.array([x_desired, y_desired, z_desired])
        vector = position_desired - position_current

        for update_idx in range(int(duration_s / LLComm.UPDATE_PERIOD)):
            time_norm = update_idx * LLComm.UPDATE_PERIOD / duration_s # Fraction of total duration that has elapsed

            position = position_current - 2 * vector * time_norm ** 2 * (time_norm - 1.5)
            velocity = -6 * vector * time_norm * (time_norm - 1)
            acceleration = -6 * vector * (2 * time_norm - 1)

            # Currently there is an issue with velocity and acceleration being too high
            cf.commander.send_full_state_setpoint(
                pos=position,
                # vel=velocity,
                vel=np.zeros(3),
                # acc=acceleration,
                acc=np.zeros(3),
                orientation=np.array([0, 0, 0, 1]),
                rollrate=0, pitchrate=0, yawrate=0)

            time.sleep(LLComm.UPDATE_PERIOD)

    @staticmethod
    def hover(cf: Crazyflie, x_desired: float, y_desired: float, z_desired: float, yaw_desired: float, duration_s: float):
        t_start = time.perf_counter()
        
        while time.perf_counter() - t_start < duration_s:
            cf.commander.send_position_setpoint(x_desired, y_desired, z_desired, yaw_desired)
            time.sleep(LLComm.UPDATE_PERIOD)
    
    @staticmethod
    def takeoff(cf: Crazyflie, z_desired: float, duration_s: float):
        LLComm.go_to_first_order(cf, 0, 0, 0.5, 0, duration_s, relative=True)