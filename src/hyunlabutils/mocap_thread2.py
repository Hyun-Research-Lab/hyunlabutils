from threading import Thread
import motioncapture # make sure this is the libmotioncapture from Hyun-Research-Lab
import time

class MocapThread2(Thread):
    def __init__(self, mocap_system_type: str, host_name: str, body_names: list, log_file_name: str|None = None):
        Thread.__init__(self)

        self.mocap_system_type = mocap_system_type
        self.host_name = host_name
        self.body_names = body_names
        # the 0th element of body_names corresponds to the crazyflie's name

        self.cf = None
        self._stay_open = True
        
        self.log_file_name = log_file_name
        self.log_array = {body_name: [] for body_name in body_names}
        
        assert len(body_names) > 0, "At least one body must have a name"

        self.start()

    def close(self):
        self._stay_open = False
        if self.log_file_name is not None:
            
            # create one CSV file per body name
            for body_name in self.body_names:
                with open(f'{self.log_file_name}_{body_name}.csv', 'w') as f:
                    f.write('epoch,x,y,z,qx,qy,qz,qw' + '\n')
                    for dataline in self.log_array[body_name]:
                        f.write(",".join([str(item) for item in dataline]) + '\n')

    def run(self):
        mc = motioncapture.connect(self.mocap_system_type, {'hostname': self.host_name})
        while self._stay_open:
            mc.waitForNextFrame()
            frameTime = time.time()
            for name, obj in mc.rigidBodies.items():
                if name not in self.body_names:
                    # print(f'Name {name} not in self.body_names = {self.body_names}')
                    continue
                
                # log the data
                self.log_array[name].append((frameTime, obj.position[0], obj.position[1], obj.position[2], obj.rotation.x, obj.rotation.y, obj.rotation.z, obj.rotation.w))
                
                # send the crazyflie the data, too
                if self.cf and name == self.body_names[0]:
                    self.cf.extpos.send_extpose(obj.position[0], obj.position[1], obj.position[2], obj.rotation.x, obj.rotation.y, obj.rotation.z, obj.rotation.w)
                
                    