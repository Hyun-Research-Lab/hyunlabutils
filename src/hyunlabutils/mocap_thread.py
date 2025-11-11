from threading import Thread
import motioncapture
import time

class MocapThread(Thread):
    def __init__(self, mocap_system_type, host_name, body_name, log_file_name=None, only_position=False):
        Thread.__init__(self)

        self.mocap_system_type = mocap_system_type
        self.host_name = host_name
        self.body_name = body_name

        self.cf = None
        self._stay_open = True
        
        self.log_file_name = log_file_name
        self.log_array = []

        self.only_position = only_position

        self.start()

    def close(self):
        self._stay_open = False
        if self.log_file_name is not None:
            with open(self.log_file_name + '.csv', 'w') as f:
                f.write('epoch,x,y,z,qx,qy,qz,qw\n')
                for dataline in self.log_array:
                    f.write(",".join([str(item) for item in dataline]) + '\n')

    def run(self):
        mc = motioncapture.connect(self.mocap_system_type, {'hostname': self.host_name})
        while self._stay_open:
            mc.waitForNextFrame()
            if self.cf:
                for name, obj in mc.rigidBodies.items():
                    if name == self.body_name:
                        if self.only_position:
                            self.cf.extpos.send_extpos(obj.position[0], obj.position[1], obj.position[2])
                        else:
                            self.cf.extpos.send_extpose(obj.position[0], obj.position[1], obj.position[2], obj.rotation.x, obj.rotation.y, obj.rotation.z, obj.rotation.w)

                        if self.log_file_name is not None:
                            self.log_array.append((time.time(), obj.position[0], obj.position[1], obj.position[2], obj.rotation.x, obj.rotation.y, obj.rotation.z, obj.rotation.w))
                        