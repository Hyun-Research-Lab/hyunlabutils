import time
import numpy as np

from cflib.crazyflie import Crazyflie
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncLogger import SyncLogger

class LLComm():

    UPDATES_PER_SECOND = 100
    
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
    def go_to_first_order(cf: Crazyflie, x_desired: float, y_desired: float, z_desired: float, yaw_desired: float, duration_s: float):
        position_current = LLComm._get_position(cf)
        position_desired = np.array([x_desired, y_desired, z_desired])

        for update_idx in range(duration_s * LLComm.UPDATES_PER_SECOND):
            velocity = (position_desired - position_current) / duration_s
            position = position_current + velocity * update_idx / LLComm.UPDATES_PER_SECOND

            cf.commander.send_full_state_setpoint(
                pos=position,
                vel=velocity,
                acc=np.zeros(3),
                orientation=np.array([0, 0, 0, 1]),
                rollrate=0, pitchrate=0, yawrate=0)
            
            time.sleep(1 / LLComm.UPDATES_PER_SECOND)

    @staticmethod
    def hover(cf: Crazyflie, x_desired: float, y_desired: float, z_desired: float, yaw_desired: float, duration_s: float):
        for _ in range(duration_s * LLComm.UPDATES_PER_SECOND):
            cf.commander.send_position_setpoint(x_desired, y_desired, z_desired, yaw_desired)
            time.sleep(1 / LLComm.UPDATES_PER_SECOND)