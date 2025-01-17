import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from .base import Converter
from .const import GATEWAY, ZIGBEE, BLE

if TYPE_CHECKING:
    from ..device import XDevice

RE_SERIAL = re.compile(r'(tx|rx|oe|fe|brk):(\d+)')

ZIGBEE_CLUSTERS = {
    0x0000: 'Basic',
    0x0001: 'PowerCfg',
    0x0003: 'Identify',
    0x0006: 'OnOff',
    0x0008: 'LevelCtrl',
    0x000A: 'Time',
    0x000C: 'AnalogInput',  # cube, gas sensor
    0x0012: 'Multistate',
    0x0019: 'OTA',  # illuminance sensor
    0x0101: 'DoorLock',
    0x0400: 'Illuminance',  # motion sensor
    0x0402: 'Temperature',
    0x0403: 'Pressure',
    0x0405: 'Humidity',
    0x0406: 'Occupancy',  # motion sensor
    0x0500: 'IasZone',  # gas sensor
    0x0B04: 'ElectrMeasur',
    0xFCC0: 'Xiaomi'
}


def now():
    return datetime.now()


class GatewayStatsConverter(Converter):
    childs = {
        "network_pan_id", "radio_tx_power", "radio_channel",
        "free_mem", "load_avg", "rssi", "uptime",
        "bluetooth_tx", "bluetooth_rx", "bluetooth_oe",
        "zigbee_tx", "zigbee_rx", "zigbee_oe"
    }

    def decode(self, device: 'XDevice', payload: dict, value: dict):
        if self.attr in value:
            payload[self.attr] = value[self.attr]

        if 'networkUp' in value:
            payload.update({
                'network_pan_id': value.get('networkPanId'),
                'radio_tx_power': value.get('radioTxPower'),
                'radio_channel': value.get('radioChannel'),
            })

        if 'free_mem' in value:
            s = value['run_time']
            d = s // (3600 * 24)
            h = s % (3600 * 24) // 3600
            m = s % 3600 // 60
            s = s % 60
            payload.update({
                'free_mem': value['free_mem'],
                'load_avg': value['load_avg'],
                'rssi': value['rssi'] - 100,
                'uptime': f"{d} days, {h:02}:{m:02}:{s:02}",
            })

        if 'serial' in value:
            lines = value['serial'].split('\n')
            for k, v in RE_SERIAL.findall(lines[2]):
                payload[f"bluetooth_{k}"] = int(v)
            for k, v in RE_SERIAL.findall(lines[3]):
                payload[f"zigbee_{k}"] = int(v)


class ZigbeeStatsConverter(Converter):
    childs = {
        "ieee", "nwk", "msg_received", "msg_missed", "linkquality", "rssi",
        "last_msg", "type", "parent", "new_resets"
    }

    def decode(self, device: 'XDevice', payload: dict, value: dict):
        if 'sourceAddress' in value:
            cid = int(value['clusterId'], 0)

            if 'msg_received' in device.extra:
                device.extra['msg_received'] += 1
            else:
                device.extra.update({'msg_received': 1, 'msg_missed': 0})

            # For some devices better works APSCounter, for other - sequence
            # number in payload. Sometimes broken messages arrived.
            try:
                raw = value['APSPlayload']
                manufact_spec = int(raw[2:4], 16) & 4
                new_seq1 = int(value['APSCounter'], 0)
                new_seq2 = int(raw[8:10] if manufact_spec else raw[4:6], 16)
                # new_seq2 == 0 -> probably device reset
                if 'last_seq1' in device.extra and new_seq2 != 0:
                    miss = min(
                        (new_seq1 - device.extra['last_seq1'] - 1) & 0xFF,
                        (new_seq2 - device.extra['last_seq2'] - 1) & 0xFF
                    )
                    device.extra['msg_missed'] += miss

                device.extra['last_seq1'] = new_seq1
                device.extra['last_seq2'] = new_seq2
            except:
                pass

            payload.update({
                ZIGBEE: now().isoformat(timespec='seconds'),
                'ieee': value['eui64'],
                'nwk': value['sourceAddress'],
                'msg_received': device.extra['msg_received'],
                'msg_missed': device.extra['msg_missed'],
                'linkquality': value['linkQuality'],
                'rssi': value['rssi'],
                'last_msg': ZIGBEE_CLUSTERS.get(cid, cid),
            })

        if 'ago' in value:
            ago = timedelta(seconds=value['ago'])
            payload.update({
                ZIGBEE: (now() - ago).isoformat(timespec='seconds'),
                'type': value['type'],
                'parent': '0xABCD',
            })

        elif 'parent' in value:
            payload['parent'] = value['parent']

        if 'resets' in value:
            if 'resets0' not in device.extra:
                device.extra['resets0'] = value['resets']
            payload['new_resets'] = value['resets'] - device.extra['resets0']


class BLEStatsConv(Converter):
    childs = {"mac", "msg_received"}

    def decode(self, device: 'XDevice', payload: dict, value: dict):
        if 'msg_received' in device.extra:
            device.extra['msg_received'] += 1
        else:
            device.extra['msg_received'] = 1

        payload.update({
            BLE: now().isoformat(timespec='seconds'),
            'mac': device.mac,
            'msg_received': device.extra['msg_received'],
        })

GatewayStats = GatewayStatsConverter(GATEWAY, "binary_sensor")

STAT_GLOBALS = {
    BLE: BLEStatsConv(BLE, "sensor"),
    ZIGBEE: ZigbeeStatsConverter(ZIGBEE, "sensor"),
}
