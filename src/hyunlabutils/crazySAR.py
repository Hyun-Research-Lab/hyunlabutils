import numpy as np

from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.swarm import CachedCfFactory, Swarm

class CrazySAR(Swarm):

    LED_LEADER =   0b10110101 # red and blue
    LED_ROOT =     0b10101011 # green and blue
    LED_FOLLOWER = 0b10000000 # all off

    def __init__(self, uris, graph: list, rods: list, flap_params: list):
        super().__init__(uris, CachedCfFactory(rw_cache='./cache'))
        
        self.graph = graph
        self.rods = rods
        self.flap_params = flap_params

        leader_uri = f"radio://0/80/2M/E7E7E7E7{self._find_leader():02d}"
        self.leader: Crazyflie = self._cfs[leader_uri].cf

    def send_graph(self):
        """
        Send the current graph to all Crazyflies in the swarm.
        """
        for i, (node, parent) in enumerate(self.graph):
            cf: Crazyflie = self._cfs[f"radio://0/80/2M/E7E7E7E7{node:02d}"].cf

            config_params = np.uint32(
                (np.uint8(node) & 0x0F) |
                ((np.uint8(parent) & 0x0F) << 4) |
                ((np.int8(self.rods[i][0]) & 0xFF) << 8) |
                ((np.int8(self.rods[i][1]) & 0xFF) << 16) |
                ((np.int8(self.rods[i][2]) & 0xFF) << 24)
            )

            cf.param.set_value('crazysar.config_params', config_params)

            cf.param.set_value('crazysar.flap_freq', self.flap_params[i][0])
            cf.param.set_value('crazysar.flap_amp', self.flap_params[i][1])
            cf.param.set_value('crazysar.flap_phase', self.flap_params[i][2])

            if node == parent:
                cf.param.set_value('led.bitmask', self.LED_LEADER)
            else:
                cf.param.set_value('led.bitmask', self.LED_FOLLOWER)

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

        leader_uri = f"radio://0/80/2M/E7E7E7E7{self._find_leader():02d}"
        self.leader: Crazyflie = self._cfs[leader_uri].cf

        self.send_graph()

    def set_root(self, root_node: int):
        """
        Toggle a crazyflie to be a root node and allow it to split away.
        """
        root_uri = f"radio://0/80/2M/E7E7E7E7{root_node:02d}"
        root_cf: Crazyflie = self._cfs[root_uri].cf

        if int(root_cf.param.get_value('crazysar.is_root')) == 0:
            root_cf.param.set_value('crazysar.is_root', 1)
            root_cf.param.set_value('led.bitmask', self.LED_ROOT)
        else:
            root_cf.param.set_value('crazysar.is_root', 0)
            root_cf.param.set_value('led.bitmask', self.LED_FOLLOWER)

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