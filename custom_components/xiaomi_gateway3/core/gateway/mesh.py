from .base import GatewayBase, SIGNAL_PREPARE_GW
from .. import shell
from ..converters import MESH, MESH_GROUP_MODEL
from ..device import XDevice


# noinspection PyMethodMayBeStatic,PyUnusedLocal
class MeshGateway(GatewayBase):
    def mesh_init(self):
        if not self.ble_mode:
            return
        self.dispatcher_connect(SIGNAL_PREPARE_GW, self.mesh_prepare_gateway)

    async def mesh_read_devices(self, sh: shell.ShellGw3):
        try:
            # prevent read database two times
            db = await sh.read_db_bluetooth()

            childs = {}

            # load Mesh bulbs
            rows = sh.db.read_table(sh.mesh_device_table)
            for row in rows:
                did = row[0]
                mac = row[1].replace(':', '').lower()
                device = self.devices.get(did)
                if not device:
                    self.devices[did] = device = XDevice(
                        MESH, row[2], did=did, mac=mac,
                    )
                self.add_device(device)

                # add bulb to group address
                childs.setdefault(row[5], []).append(did)

            # load Mesh groups
            rows = sh.db.read_table(sh.mesh_group_table)
            for row in rows:
                did = 'group.' + row[0]
                device = self.devices.get(did)
                if not device:
                    # don't know if 8 bytes enougth
                    mac = int(row[0]).to_bytes(8, 'big').hex()
                    self.devices[did] = device = XDevice(
                        MESH, MESH_GROUP_MODEL, did, mac
                    )
                # update childs of device
                device.extra["childs"] = childs.get(row[1])
                self.add_device(device)

        except Exception as e:
            self.debug("Can't read mesh DB", exc_info=e)

    async def mesh_prepare_gateway(self, sh: shell.ShellGw3):
        if self.available is None:
            await self.mesh_read_devices(sh)
