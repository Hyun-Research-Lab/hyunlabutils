import os
import time
from .mocap_thread import MocapThread
from .mocap_thread2 import MocapThread2

import cflib.crtp
from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.utils.reset_estimator import reset_estimator
from cflib.crazyflie.log import LogConfig

# setup logging
# https://docs.python.org/3/howto/logging-cookbook.html#logging-to-multiple-destinations
# https://docs.python.org/3/library/logging.html#logging.LogRecord
import logging

def setup_logging(prefix):

    class EpochFormatter(logging.Formatter):
        def format(self, record):
            # Add epoch time to the record
            record.epoch_time = time.time()
            return super().format(record)
    formatter = EpochFormatter('%(epoch_time).6f, %(levelname)s, %(message)s')

    # Setup file handler (this is what is written to a file)
    file_handler = logging.FileHandler(f'{prefix}/terminal.log', mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Setup console handler (this is what is printed to the console)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)

    # Configure root logger (this will also capture all crazyflie logging)
    logging.basicConfig(level=logging.DEBUG, handlers=[file_handler])
    logger = logging.getLogger('myapp')
    logger.addHandler(console_handler)
    
    return logger

"""
LogConfigWrapper is a simple class which contains a LogConfig object
and a data buffer to store the received data.

Only the LogConfigHelper class should interact with this class directly.
"""
class LogConfigWrapper:
    
    def __init__(self, name, period_in_ms):
        self.name = name
        self.period_in_ms = period_in_ms
        self.log_config = LogConfig(name, period_in_ms)
        self.data_buffer = []
        self.variable_names = []
        
    def add_variable(self, var_name, var_type):
        self.log_config.add_variable(var_name, var_type)
        self.variable_names.append(var_name)
        
    def log_data(self, epoch_time, timestamp, data):
        self.data_buffer.append([epoch_time, timestamp] + [data[var_name] for var_name in self.variable_names])
        
    def write_to_csv(self, prefix):
        with open(f'{prefix}/{self.name}.csv', 'w') as f:
            header = 'epoch, timestamp, ' + ', '.join(self.variable_names) + '\n'
            f.write(header)
            for dataline in self.data_buffer:
                f.write(",".join([str(item) for item in dataline]) + '\n')

"""
LogConfigHelper is a class which manages multiple LogConfigWrapper objects.
This is the only class that should be interacted with directly.
"""
class LogConfigHelper:
    
    def __init__(self, cf, logger):
        self.cf = cf
        self.logger = logger # logging to the terminal
        self.lcws = {} # for storing LogConfigWrapper objects. 'name' -> LogConfigWrapper
        
    def add_log_config(self, name, period_in_ms, variables):
        """
        variables = {'ctrlLQR.px': 'float', ...}
        """
        lcw = LogConfigWrapper(name, period_in_ms)
        for var_name, var_type in variables.items():
            lcw.add_variable(var_name, var_type)
        self.lcws[name] = lcw
        
    # callback for all log config wrappers
    def log_error(self, logconf, msg):
        msg = f"{logconf.name}: {msg}"
        self.logger.error(msg)
    
    # callback for all log config wrappers
    def log_data(self, timestamp, data, logconf):
        epoch_time = time.time()
        self.lcws[logconf.name].log_data(epoch_time, timestamp, data)
        
    def start(self):
        for name, lcw in self.lcws.items():
            self.cf.log.add_config(lcw.log_config)
            lcw.log_config.data_received_cb.add_callback(self.log_data)
            lcw.log_config.error_cb.add_callback(self.log_error)
            lcw.log_config.start()
            
    def write_to_csv(self, prefix):
        for name, lcw in self.lcws.items():
            lcw.write_to_csv(prefix)
        
"""
Useful flight functions which can be called from the user-defined function.
"""
def arm(cf, logger):
    logger.info('Arming...')
    cf.platform.send_arming_request(True)
    logger.info('Arming complete.')
    
def disarm(cf, logger):
    logger.info('Disarming...')
    cf.platform.send_arming_request(False)
    logger.info('Disarming complete.')

def takeoff(cf, logger, target_height=1.5, duration=2):
    logger.info(f'Taking off...')
    cf.high_level_commander.takeoff(target_height, duration)
    time.sleep(duration)
    logger.info('Taking off complete.')
    
def go_to(cf, logger, x, y, z, yaw, duration):
    logger.info(f'Go to ({x}, {y}, {z})...')
    cf.high_level_commander.go_to(x, y, z, yaw, duration)
    time.sleep(duration)
    logger.info(f'Go to ({x}, {y}, {z}) complete.')
    
def land(cf, logger, target_height, duration, ):
    logger.info('Landing...')
    cf.high_level_commander.land(target_height, duration)
    time.sleep(duration)
    logger.info('Landing complete.')
    
def stop(cf, logger):
    logger.info('Stopping Motors...')
    cf.high_level_commander.stop()
    logger.info('Stopping Motors complete.')
    
def e_stop(cf, logger):
    logger.info('Emergency stop...')
    cf.loc.send_emergency_stop()
    logger.info('Emergency stop complete. Reboot required.')
    
    
"""
run_flight_test()

Handles all of the boiler-plate code for setting up 
the mocap system, loggers, and connecting to the crazyflie.
Pass in a user-specified function which will make the crazyflie
takeoff, do something, and then land.

Make sure you are connected to the same WiFi network as the host computer.
e.g., Connect to HyunLab-B022C

params = {'ctrlLQR.flap_hz': '5.0', 'stabilizer.estimator'': '2', ...}
uri='radio://0/80/2M/E7E7E7E7B1' | 'radio://0/80/2M/E7E7E7E701'
rigid_body_name='Meloncopter' | 'cf01'

log_variables = [
        {
            'name': 'translation',
            'period_in_ms': 20,
            'variables': {
                'ctrlLQR.px': 'float',
                'ctrlLQR.py': 'float',
                'ctrlLQR.pz': 'float',
                'ctrlLQR.vx': 'float',
                'ctrlLQR.vy': 'float',
                'ctrlLQR.vz': 'float',
            },
        },
        ...
    ]
"""
def run_flight_test(user_function,
                    params={},
                    log_variables=[],
                    uri='radio://0/80/2M/E7E7E7E7B1',
                    rigid_body_name='Meloncopter',
                    host_name='192.168.1.115',
                    mocap_system_type='vicon',
                    ):
    
    # first, check the user function signature
    import inspect

    # Check what your user_function expects
    sig = inspect.signature(user_function)
    param_count = len(sig.parameters)
    param_names = list(sig.parameters.keys())
    
    assert param_names[0] == 'cf', "First parameter must be 'cf' (Crazyflie object)"
    assert param_names[1] == 'logger', "Second parameter must be 'logger' (logging.Logger object)"
    
    cwd = os.getcwd()

    # create a new folder to store the log files
    i = 0
    while True:
        prefix = f'run{i:02d}'
        if not os.path.exists(prefix):
            break
        i += 1
    os.makedirs(prefix, exist_ok=False)
    
    cflib.crtp.init_drivers()

    # for the bicopter, we can fly with just the one rigid body, or we can also have the left and right frames, too
    if type(rigid_body_name) == str:
        mocap_thread = MocapThread(mocap_system_type, host_name, rigid_body_name, log_file_name=prefix+'/mocap')
    elif type(rigid_body_name) == list:
        mocap_thread = MocapThread2(mocap_system_type, host_name, rigid_body_name, log_file_name=prefix+'/mocap')


    with SyncCrazyflie(uri, cf=Crazyflie(rw_cache='./cache')) as scf:
        cf = scf.cf

        # Start sending mocap data to the Crazyflie
        mocap_thread.cf = cf
        
        logger = setup_logging(prefix)
        try:
            for param_name, param_value in params.items():
                cf.param.set_value(param_name, param_value)
                logger.info(f'{param_name} = {param_value}')
        except Exception as e:
            logger.error(f'Error setting parameters: ' + str(e))
            return # exit the program

        reset_estimator(cf)
        
        # create our LogConfigHelper to set up the cf.logging
        try:
            log_config_helper = LogConfigHelper(cf, logger)
            for log in log_variables:
                name, period_in_ms, variables = log['name'], log['period_in_ms'], log['variables']
                log_config_helper.add_log_config(name, period_in_ms, variables)
            log_config_helper.start() # start logging
        except Exception as e:
            logger.error(f'Error setting up cf logging: ' + str(e))
            return
        
        # the battery voltage is not going to be logged, so let's just set it up manually
        batt_log_config = LogConfig(name="vbat", period_in_ms=2000)
        batt_log_config.add_variable('pm.vbat', 'float')
        
        def log_battery_data(timestamp, data, logconf):
            vbat = data['pm.vbat']
            if vbat > 14.8:
                logger.info(f'VBat = {vbat:.2f} V')
            elif vbat > 14.4:
                logger.warning(f'VBat = {vbat:.2f} V. Charge soon.')
            else:
                logger.critical(f'VBat = {vbat:.2f} V. Land immediately!')
                
        cf.log.add_config(batt_log_config)
        batt_log_config.data_received_cb.add_callback(log_battery_data)
        batt_log_config.start()
        
        # debug print logging (not often used)
        def console_received(text):
            logger.info(f"[CONSOLE] {text}")
        cf.console.receivedChar.add_callback(console_received)
        
        try:
            logger.info('Starting user function...')
            logger.info('Press Ctrl+C to send emergency stop signal.')
            # depending on how many argument the user function expects,
            # call it appropriately
            if param_count == 2:
                user_function(cf, logger)
            elif param_count == 3:
                user_function(cf, logger, mocap_thread.log_array)
                
        except KeyboardInterrupt:
            logger.info(f'KeyboardInterrupt was detected!')
            e_stop(cf, logger)
                
        except Exception as e:
            # press Ctrl+C to immediately send an emergency stop signal
            # or if there's any other sort of issue this will trigger
            import traceback
            logger.exception('Unhandled exception in user function')
            logger.error('Exception type: %s', type(e))
            logger.error('Exception repr: %r', e)
            traceback.print_exc()
            e_stop(cf, logger)
            
        else:
            logger.info('User function completed without exception.')
            stop(cf, logger)
            disarm(cf, logger)
            
        # stop writing to the micro SD card
        logger.info('Setting usd.logging to 0.')
        cf.param.set_value('usd.logging', '0')
        time.sleep(1.0)
        logger.info('Done setting usd.logging to 0.')
        
        # write the log data to csv files
        log_config_helper.write_to_csv(prefix)
        logger.info('Done writing to csv.')
        
    mocap_thread.close()
    logger.info('Mocap thread closed.')