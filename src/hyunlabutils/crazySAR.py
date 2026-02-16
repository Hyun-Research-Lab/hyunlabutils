import json
import time
import csv
import numpy as np

from cflib.crazyflie import Crazyflie
from cflib.utils.reset_estimator import reset_estimator
from cflib.crazyflie.log import LogConfig
from cflib.crazyflie.syncLogger import SyncLogger
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.swarm import CachedCfFactory, Swarm

from hyunlabutils.mocap_thread import MocapThread

class CrazySAR(Swarm):

    def __init__(self, config_filename: str, log_vars: dict, mocap_system_type = 'vicon', host_name = '192.168.1.115'):
        # Get graph from JSON file
        with open(f"crazySAR/configs/{config_filename}.json", "r") as f:
            config = json.load(f)
        self.graph = config["graph"]
        self.rods = config["rods"]
        self.flap_params = config["flap_params"]
        self.disabled = config["disabled"]

        # Initialize the set of URIs and dict of mocap threads
        self.uris = set()
        self.mocap_threads = dict()
        for node, parent in self.graph:
            uri = CrazySAR.node2uri(node)
            self.uris.add(uri)
            self.mocap_threads[uri] = [MocapThread(mocap_system_type, host_name, f'cf{node:02d}')]

        super().__init__(self.uris, CachedCfFactory(rw_cache='./cache'))

        leader_uri = self.node2uri(self._find_leader())
        self.leader: Crazyflie = self._cfs[leader_uri].cf

        self.log_vars = log_vars
        self.file = dict()
        self.writer = dict()
        self.logconf = dict()

    def __enter__(self):
        # Open links
        super().__enter__()

        # Start sending mocap data to the Crazyflies
        self.parallel_safe(lambda scf, mocap_thread: setattr(mocap_thread, 'cf', scf.cf), args_dict=self.mocap_threads)

        # Initialize all Crazyflies
        self.parallel_safe(self.init)

        # Initialize loggers
        for uri in self.uris:
            self.file[uri] = open(f'crazySAR/data/log{CrazySAR.uri2nodestr(uri)}.csv', 'w', newline='')
            self.writer[uri] = csv.writer(self.file[uri])
            self.writer[uri].writerow(self.log_vars.keys())

            self.logconf[uri] = LogConfig(name='', period_in_ms=100)
            for var_name, var_type in self.log_vars.items():
                self.logconf[uri].add_variable(var_name, var_type)
            self._cfs[uri].cf.log.add_config(self.logconf[uri])
            self.logconf[uri].data_received_cb.add_callback(lambda timestamp, data, logconf: self.writer[logconf.cf.link_uri].writerow([data[var_name] for var_name in self.log_vars.keys()]))

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Emergency stop all (only way to kill the followers)
        self.parallel_safe(lambda scf: scf.cf.loc.send_emergency_stop())

        # Check battery voltage of each Crazyflie
        def print_vbat(scf: SyncCrazyflie):
            battery_logconf = LogConfig('', 10)
            battery_logconf.add_variable('pm.vbat', 'float')

            with SyncLogger(scf, battery_logconf) as logger:
                for log_entry in logger:
                    vbat = log_entry[1]['pm.vbat']
                    print(f'cf{CrazySAR.uri2nodestr(scf.cf.link_uri)} battery: {vbat:<.2f} V')
                    break

        time.sleep(1)
        self.parallel_safe(print_vbat)

        for uri in self.uris:
            self.logconf[uri].stop()
            time.sleep(0.1)
            self.file[uri].close()

        # Close links
        super().__exit__(exc_type, exc_val, exc_tb)

        for mocap_thread in self.mocap_threads.values():
            mocap_thread[0].close()

    def init(self, scf: SyncCrazyflie):
        cf = scf.cf

        # Set parameters
        cf.param.set_value('stabilizer.estimator', '2')
        cf.param.set_value('stabilizer.controller', '6')

        # cf.param.set_value('crazysar.kx_rob', 5.0)
        # cf.param.set_value('crazysar.kv_rob', 5.0)
        # cf.param.set_value('crazysar.ki_rob', 2.0)

        cf.param.set_value('crazysar.kR_geo', 5.0)
        cf.param.set_value('crazysar.kv_geo', 5.0)

        # cf.param.set_value('crazysar.flap_freq', 2*np.pi * 0.25) # 0.25 Hz default
        # cf.param.set_value('crazysar.flap_amp', np.pi/8)
        # cf.param.set_value('crazysar.flap_phase', -0.2)

        if int(CrazySAR.uri2nodestr(cf.link_uri)) in self.disabled:
            cf.param.set_value('crazysar.disable_props', 1)
        else:
            cf.param.set_value('crazysar.disable_props', 0)

        reset_estimator(cf)

        # Arm the Crazyflie
        cf.platform.send_arming_request(True)
        time.sleep(1)

    @staticmethod
    def _send_graph(scf: SyncCrazyflie, config_params, flap_params):
        cf = scf.cf

        cf.param.set_value('crazysar.config_params', config_params)

        cf.param.set_value('crazysar.flap_freq', flap_params[0])
        cf.param.set_value('crazysar.flap_amp', flap_params[1])
        cf.param.set_value('crazysar.flap_phase', flap_params[2])
    
    def send_graph(self):
        """
        Send the current graph to all Crazyflies in the swarm.
        """
        send_graph_dict = dict()
        
        for i, (node, parent) in enumerate(self.graph):
            config_params = np.uint32(
                (np.uint8(node) & 0x0F) |
                ((np.uint8(parent) & 0x0F) << 4) |
                ((np.int8(self.rods[i][0]) & 0xFF) << 8) |
                ((np.int8(self.rods[i][1]) & 0xFF) << 16) |
                ((np.int8(self.rods[i][2]) & 0xFF) << 24)
            )
            flap_params = self.flap_params[i]
            
            send_graph_dict[self.node2uri(node)] = [config_params, flap_params]
            
        self.parallel_safe(CrazySAR._send_graph, args_dict=send_graph_dict)

    def set_leader(self, leader_node: int):
        """
        Set a new leader and update the graph accordingly.
        """
        prev_leader_node = self._find_leader()

        if leader_node == prev_leader_node:
            return
        
        temp1 = self._get_parent(leader_node)
        self._set_parent(leader_node, leader_node) # New leader points to itself

        temp2 = self._get_parent(temp1)
        self._set_parent(temp1, leader_node)

        temp_rod1 = self._get_rod(temp1)
        self._set_and_flip_rod(temp1, self._get_rod(leader_node))

        temp_flap_params1 = self._get_flap_params(temp1)
        self._set_and_flip_flap_params(temp1, self._get_flap_params(leader_node))

        temp3 = 0
        temp_rod2 = [0, 0, 0]

        while temp1 != prev_leader_node:
            temp3 = self._get_parent(temp2)
            self._set_parent(temp2, temp1)

            temp_rod2 = self._get_rod(temp2)
            self._set_and_flip_rod(temp2, temp_rod1)
            temp_rod1 = temp_rod2

            temp_flap_params2 = self._get_flap_params(temp2)
            self._set_and_flip_flap_params(temp2, temp_flap_params1)
            temp_flap_params1 = temp_flap_params2

            temp1 = temp2
            temp2 = temp3

        leader_uri = self.node2uri(self._find_leader())
        self.leader: Crazyflie = self._cfs[leader_uri].cf

        self.send_graph()

    def set_root(self, root_node: int):
        """
        Toggle a crazyflie to be a root node and allow it to split away.
        """
        root_cf: Crazyflie = self._cfs[self.node2uri(root_node)].cf

        if int(root_cf.param.get_value('crazysar.is_root')) == 0:
            root_cf.param.set_value('crazysar.is_root', 1)
        else:
            root_cf.param.set_value('crazysar.is_root', 0)

    def _find_leader(self):
        for node, parent in self.graph:
            if node == parent:
                return node
            
    def _get_parent(self, node: int):
        for n, parent in self.graph:
            if n == node:
                return parent
    
    def _set_parent(self, node: int, new_parent: int):
        for i, (n, parent) in enumerate(self.graph):
            if n == node:
                self.graph[i][1] = new_parent
                return
    
    def _get_rod(self, node: int):
        for i, (n, parent) in enumerate(self.graph):
            if n == node:
                return self.rods[i]
    
    def _set_and_flip_rod(self, node: int, new_rod: list):
        for i, (n, parent) in enumerate(self.graph):
            if n == node:
                self.rods[i] = [-x for x in new_rod]
                return

    def _get_flap_params(self, node: int):
        for i, (n, parent) in enumerate(self.graph):
            if n == node:
                return self.flap_params[i]
    
    def _set_and_flip_flap_params(self, node: int, new_flap_params: list):
        for i, (n, parent) in enumerate(self.graph):
            if n == node:
                self.flap_params[i] = [new_flap_params[0], -new_flap_params[1], new_flap_params[2]]
                return

    @staticmethod
    def node2uri(node: int):
        return f"radio://0/80/2M/E7E7E7E7{node:02d}"

    @staticmethod
    def uri2nodestr(uri: str):
        # return uri[-17:-15]
        return uri.split('E7E7E7E7')[-1][:2]