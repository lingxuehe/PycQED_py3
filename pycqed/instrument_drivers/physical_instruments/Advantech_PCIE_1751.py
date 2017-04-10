import cffi
from functools import partial
import collections
import os
import logging

from qcodes.instrument.base import Instrument
from qcodes.utils import validators as vals


class DAQNaviException(Exception):
    """
    Exception raised if one of the Advantech's DAQNavi library's functions
    encounters an error.
    """


class DAQNaviWarning(Warning):
    """
    Warning raised if one of the Advantech's DAQNavi library's functions
    encounters a warning condition.
    """


class Advantech_PCIE_1751(Instrument):
    """
    QCodes driver for DIO card from Advantech. The card has six 8255 PPI mode
    C DI/O ports, each containing 8 pins, that can be configured for either
    input or output in groups of four.
    
    The Advantech drivers have to be installed so that biodaq.dll can be
    accessed. This QCodes driver uses python's C foreign function interface
    cffi to call the necessary functions from the dynamically linked library.
    Automatically loads the declaration of the library from the
    _bdaqctrl.h file, that can be generated by running only the C preprocessor
    on the header included with Advantech drivers:
        gcc -D_BDAQ_C_INTERFACE -E bdaqctrl.h > _bdaqctrl.h
    Before running the above command, WIN32 and _WIN32 should be undefined at
    the start of the bdaqctrl.h and #include <stdlib.h> should be commented
    out.
    
    Current version of this driver implements only instant digital input and
    output. Buffered input and output, interrupts and counters are not
    implemented.

    Tested with driver version 3.1.10.0 and ddl version 3.1.12.1.
    """
    
    def __init__(self, name, device_description="PCIE-1751,BID#0", **kw):
        logging.info(__name__ + ' : Initializing instrument')
        super().__init__(name, **kw)
        
        self.device_description = device_description
        
        # parse the header
        self.ffi = cffi.FFI()
        package_directory = os.path.dirname(os.path.abspath(__file__))
        header_file = os.path.join(package_directory, '_Advantech',
                                   '_bdaqctrl.h')
        with open(header_file) as h:
            self.ffi.cdef(h.read())
        self.dll = self.ffi.dlopen("biodaq.dll")
        
        # create the digital input and output devices
        self.info = self.ffi.new("DeviceInformation *")
        self.info.Description = self.device_description
        self.info.DeviceNumber = -1
        self.info.DeviceMode = self.dll.ModeWriteWithReset
        self.info.ModuleIndex = 0
        
        self.di = self.dll.AdxInstantDiCtrlCreate()
        self.check(self.dll.InstantDiCtrl_setSelectedDevice(self.di, self.info))
        self.do = self.dll.AdxInstantDoCtrlCreate()
        self.check(self.dll.InstantDoCtrl_setSelectedDevice(self.do, self.info))

        # Create QCodes parameters
        for i in range(self.port_count()):
            self.add_parameter(
                'port{}_dir'.format(i),
                label='Port {} direction'.format(i),
                vals=vals.Enum(0x00, 0x0f, 0xf0, 0xff),
                get_cmd=partial(self._get_port_direction, i),
                set_cmd=partial(self._set_port_direction, i),
                docstring="The direction (input or output) of the digital i/o"
                    " port nr {}. Possible values are\n"
                    "    0x00 indicating that all pins of the port are "
                    "configured as inputs\n"
                    "    0x0f indicating that pins 0 to 3 are configured as "
                    "outputs and pins 4 to 7 as inputs\n"
                    "    0xf0 indicating that pins 0 to 3 are configured as "
                    "inputs and pins 4 to 7 as outputs\n"
                    "    0xff indicating that all pins are configured as "
                    "outputs".format(i))
        
        self.connect_message()

    def read_port(self, i, n=1):
        """
        Reads and returns the values of ports i, ..., i+n-1.
        For n=1 returns a single integer which encodes the 8 bit values,
        for n>1 returns a list of integers.
        """
        values = self.ffi.new('uint8[]', n)
        self.check(self.dll.InstantDiCtrl_ReadAny(self.di, i, n, values))
        if n == 1:
            return values[0]
        else:
            return list(values)
        
    def write_port(self, i, value):
        """
        Writes values to output ports. If value is an integer, writes its
        binary representation to the pins of port i. If value is a list of
        integers, writes the binary representations of their values to the pins
        of ports i, ..., i+len(value)-1 respectively.
        """
        if isinstance(value, collections.Iterable):
            vallist = list(value)
        else:
            vallist = [value]
        data = self.ffi.new('uint8[]', vallist)
        logging.debug('PCIE-1751: Write({}, {}, {})'.format(i, len(vallist),
                                                            vallist))
        self.check(self.dll.InstantDoCtrl_WriteAny(self.do, i, len(vallist),
                                                   data))
    
    def read_pin(self, port, pin):
        """
        Reads and returns the value pin pin of port port.
        """
        data = self.ffi.new('uint8 *')
        self.check(self.dll.InstantDiCtrl_ReadBit(self.di, port, pin, data))
        return data[0]
        
    
    def write_pin(self, port, pin, value):
        """
        Sets pin pin of port port to 1 if value != 0, and to 0 otherwise.
        """
        self.check(self.dll.InstantDoCtrl_WriteBit(self.do, port, pin, value))

    def port_count(self):
        """
        Returns the number of ports on the device. Each port contains 8 input
        or output pins.
        """
        return self.dll.InstantDoCtrl_getPortCount(self.do)

    def check(self, errorcode):
        """
        Checks the errorcode and raises an Exception if error occurred.
        """
        if errorcode == self.dll.Success:
            return
        elif errorcode < 0xE0000000:
            message = self.ERRORMSG.get(errorcode, "Undefined error code.")
            raise DAQNaviWarning("DAQNavi warning {:#010X}: {}".format(
                errorcode, message))
        else:
            message = self.ERRORMSG.get(errorcode, "Undefined error code.")
            raise DAQNaviException("DAQNavi error {:#010X}: {}".format(
                errorcode, message))

    def close(self):
        self.dll.InstantDoCtrl_Dispose(self.do)
        self.dll.InstantDiCtrl_Dispose(self.di)
        super().close()
        
    def _get_port_direction(self, i):
        """
        Returns the direction of port i as a 8-bit number where for each bit,
        the value 0 means that the corresponding pin is set up as an input and
        the value 1 means that it is set up as an output.
        """
        pcoll = self.dll.InstantDoCtrl_getPortDirection(self.do)
        port_objs = self._ICollection_to_list(pcoll, 'PortDirection *')
        return self.dll.PortDirection_getDirection(port_objs[i])
    
    def _set_port_direction(self, i, direction):
        """
        i is the number of the port to configure
        direction has to be one of the following:
            0x00 for all pins configured as inputs
            0x0f for the 4 lower pins configured as outputs and 4 higher pins
                 as inputs
            0xf0 for the 4 lower pins configured as inputs and 4 higher pins as
                 outputs
            0xff for all pins configured as outputs
        """
        pcoll = self.dll.InstantDoCtrl_getPortDirection(self.do)
        port_objs = self._ICollection_to_list(pcoll, 'PortDirection *')
        self.check(self.dll.PortDirection_setDirection(port_objs[i], direction))
       
    def _ICollection_to_list(self, collection, ctype='void *'):
        """
        collection is a cffi object of type 'ICollection *'
        ctype is the data type of the collection members
        """
        n = self.dll.ICollection_getCount(collection)
        result = [None] * n
        for i in range(n):
            voidptr_i = self.dll.ICollection_getItem(collection, i)
            result[i] = self.ffi.cast(ctype, voidptr_i)
        return result

    def get_idn(self):
        return {'vendor': 'Advantech',
                'model': self.device_description.split(',')[0],
                'serial': '',
                'firmware': ''}

    ERRORMSG = {
        0x00000000: "The operation is completed successfully.",
        0xA0000000: "The interrupt resource is not available.",
        0xA0000001: "The parameter is out of the range.",
        0xA0000002: "The property value is out of range.",
        0xA0000003: "The property value is not supported.",
        0xA0000004: "The property value conflicts with the current state.",
        0xA0000005: "The value range of all channels in a group should be "
                    "same, such as 4~20mA of PCI-1724.",
        0xE0000000: "The handle is NULL or its type doesn't match the required "
                    "operation.",
        0xE0000001: "The parameter value is out of range.",
        0xE0000002: "The parameter value is not supported.",
        0xE0000003: "The parameter value format is not the expected.",
        0xE0000004: "Not enough memory is available to complete the operation.",
        0xE0000005: "The data buffer is null.",
        0xE0000006: "The data buffer is too small for the operation.",
        0xE0000007: "The data length exceeded the limitation.",
        0xE0000008: "The required function is not supported.",
        0xE0000009: "The required event is not supported.",
        0xE000000A: "The required property is not supported.",
        0xE000000B: "The required property is read-only.",
        0xE000000C: "The specified property value conflicts with the current "
                    "state.",
        0xE000000D: "The specified property value is out of range.",
        0xE000000E: "The specified property value is not supported.",
        0xE000000F: "The handle hasn't own the privilege of the operation the "
                    "user wanted.",
        0xE0000010: "The required privilege is not available because someone "
                    "else had own it.",
        0xE0000011: "The driver of specified device was not found.",
        0xE0000012: "The driver version of the specified device mismatched.",
        0xE0000013: "The loaded driver count exceeded the limitation.",
        0xE0000014: "The device is not opened.",
        0xE0000015: "The required device does not exist.",
        0xE0000016: "The required device is unrecognized by driver.",
        0xE0000017: "The configuration data of the specified device is lost or "
                    "unavailable.",
        0xE0000018: "The function is not initialized and can't be started.",
        0xE0000019: "The function is busy.",
        0xE000001A: "The interrupt resource is not available.",
        0xE000001B: "The DMA channel is not available.",
        0xE000001C: "Time out when reading/writing the device.",
        0xE000001D: "The given signature does not match with the device "
                    "current one.",
        0xE000001E: "The function cannot be executed while the buffered AI is "
                    "running.",
        0xE000001F: "The value range is not available in single-ended mode.",
        0xE000FFFF: "Undefined error.",
    }