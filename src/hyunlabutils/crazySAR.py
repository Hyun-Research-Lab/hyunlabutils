from cflib.crazyflie import Crazyflie
from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
from cflib.crazyflie.swarm import CachedCfFactory, Swarm

class CrazySAR(Swarm):

    def __init__(self, uris, graph: dict):
        super().__init__(uris, CachedCfFactory(rw_cache='./cache'))
        
        self._graph = graph

        leader_uri = self._find_key(self._graph, [0, 0])
        self.leader: Crazyflie = self._cfs[leader_uri].cf

    def set_graph(self, graph: dict):
        """
        Set a new graph for the swarm and update the leader.
        """
        self._graph = graph

        leader_uri = self._find_key(self._graph, [0, 0])
        self.leader = self._cfs[leader_uri].cf

    def send_graph(self, graph: dict = None):
        """
        Send the current graph to all Crazyflies in the swarm.
        If a new graph is provided, update the swarm's graph before sending.
        """
        if graph is not None:
            self.set_graph(graph)

        self.parallel_safe(self._set_node_parent, args_dict=self._graph)
        # self.parallel_safe(lambda scf: scf.cf.commander.send_notify_setpoint_stop())

    @staticmethod
    def _find_key(my_dict: dict, value_to_find):
        for key, value in my_dict.items():
            if value == value_to_find:
                return key

    @staticmethod
    def _set_node_parent(scf: SyncCrazyflie, node: int, parent: int):
        cf = scf.cf
        cf.param.set_value('ctrlLee2.node', node)
        cf.param.set_value('ctrlLee2.parent', parent)