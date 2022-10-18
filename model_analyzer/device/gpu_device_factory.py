# Copyright (c) 2020, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from model_analyzer.constants import LOGGER_NAME
from model_analyzer.device.gpu_device import GPUDevice
import model_analyzer.monitor.dcgm.dcgm_agent as dcgm_agent
import model_analyzer.monitor.dcgm.dcgm_structs as structs
from model_analyzer.model_analyzer_exceptions import TritonModelAnalyzerException

from pynvml import *

import numba.cuda
import subprocess
import logging

logger = logging.getLogger(LOGGER_NAME)


class GPUDeviceFactory:
    """
    Factory class for creating GPUDevices
    """

    def __init__(self):
        self._devices = []
        self._devices_by_bus_id = {}
        self._devices_by_uuid = {}
        self.init_all_devices()

    def init_all_devices(self, dcgmPath=None):
        """
        Create GPUDevice objects for all DCGM visible
        devices.

        Parameters
        ----------
        dcgmPath : str
            Absolute path to dcgm shared library
        """

        if numba.cuda.is_available():
            logger.info("Initializing GPUDevice handles")
            structs._dcgmInit(dcgmPath)
            dcgm_agent.dcgmInit()

            # Start DCGM in the embedded mode to use the shared library
            dcgm_handle = dcgm_agent.dcgmStartEmbedded(
                structs.DCGM_OPERATION_MODE_MANUAL)

            # Create a GPU device for every supported DCGM device
            dcgm_device_ids = dcgm_agent.dcgmGetAllSupportedDevices(dcgm_handle)

            for device_id in dcgm_device_ids:
                device_atrributes = dcgm_agent.dcgmGetDeviceAttributes(
                    dcgm_handle, device_id).identifiers
                pci_bus_id = device_atrributes.pciBusId.decode('utf-8').upper()
                device_uuid = str(device_atrributes.uuid, encoding='utf-8')
                device_name = str(device_atrributes.deviceName,
                                  encoding='utf-8')
                gpu_device = GPUDevice(device_name, device_id, pci_bus_id,
                                       device_uuid)

                self._devices.append(gpu_device)
                self._devices_by_bus_id[pci_bus_id] = gpu_device
                self._devices_by_uuid[device_uuid] = gpu_device

            dcgm_agent.dcgmShutdown()

    def get_device_by_bus_id(self, bus_id, dcgmPath=None):
        """
        Get a GPU device by using its bus ID.

        Parameters
        ----------
        bus_id : bytes
            Bus id corresponding to the GPU. The bus id should be created by
            converting the colon separated hex notation into a bytes type
            using ascii encoding. The bus id before conversion to bytes
            should look like "00:65:00".

        Returns
        -------
        Device
            The device associated with this bus id.
        """

        if bus_id in self._devices_by_bus_id:
            return self._devices_by_bus_id[bus_id]
        else:
            raise TritonModelAnalyzerException(
                f'GPU with {bus_id} bus id is either not supported by DCGM or not present.'
            )

    def get_device_by_cuda_index(self, index):
        """
        Get a GPU device using the CUDA index. This includes the index
        provided by CUDA visible devices.

        Parameters
        ----------
        index : int
            index of the device in the list of visible CUDA devices.

        Returns
        -------
        Device
            The device associated with the index provided.

        Raises
        ------
        IndexError
            If the index is out of bound.
        """

        devices = numba.cuda.list_devices()
        if index > len(devices) - 1:
            raise IndexError

        cuda_device = devices[index]
        device_identity = cuda_device.get_device_identity()
        pci_domain_id = device_identity['pci_domain_id']
        pci_device_id = device_identity['pci_device_id']
        pci_bus_id = device_identity['pci_bus_id']
        device_bus_id = \
            f'{pci_domain_id:08X}:{pci_bus_id:02X}:{pci_device_id:02X}.0'

        return self.get_device_by_bus_id(device_bus_id)

    def get_device_by_uuid(self, uuid, dcgmPath=None):
        """
        Get a GPU device using the GPU uuid.

        Parameters
        ----------
        uuid : str
            index of the device in the list of visible CUDA devices.

        Returns
        -------
        Device
            The device associated with the uuid.

        Raises
        ------
        TritonModelAnalyzerExcpetion
            If the uuid does not exist this exception will be raised.
        """

        if uuid in self._devices_by_uuid:
            return self._devices_by_uuid[uuid]
        else:
            raise TritonModelAnalyzerException(
                f'GPU UUID {uuid} was not found.')

    def verify_requested_gpus(self, requested_gpus):
        """
        Creates a list of GPU UUIDs corresponding to the GPUs visible to
        numba.cuda among the requested gpus

        Parameters
        ----------
        requested_gpus : list of str or list of ints
            Can either be GPU UUIDs or GPU device ids

        Returns
        -------
        List of GPUDevices
            list of GPUDevices corresponding to visible GPUs among requested
        
        Raises
        ------
        TritonModelAnalyzerException
        """

        cuda_visible_gpus = self.get_cuda_visible_gpus()

        if len(requested_gpus) == 1:
            if requested_gpus[0] == 'all':
                self._log_gpus_used(cuda_visible_gpus)
                return cuda_visible_gpus
            elif requested_gpus[0] == '[]':
                logger.info("No GPUs requested")
                return []

        try:
            # Check if each string in the list can be parsed as an int
            requested_cuda_indices = list(map(int, requested_gpus))
            requested_gpus = []

            for idx in requested_cuda_indices:
                try:
                    requested_gpus.append(self.get_device_by_cuda_index(idx))
                except TritonModelAnalyzerException:
                    raise TritonModelAnalyzerException(
                        f"Requested GPU with device id : {idx}. This GPU is not supported by DCGM."
                    )
        except ValueError:
            # requested_gpus are assumed to be UUIDs
            requested_gpus = [
                self.get_device_by_uuid(uuid) for uuid in requested_gpus
            ]
            pass

        # Return the intersection of CUDA visible UUIDs and requested/supported UUIDs.
        available_gpus = list(set(cuda_visible_gpus) & set(requested_gpus))
        self._log_gpus_used(available_gpus)

        return available_gpus

    def get_cuda_visible_gpus(self):
        """
        Returns
        -------
        list of GPUDevice
            UUIDs of the DCGM supported devices visible to CUDA
        """

        nvmlInit()

        gpu_devices = []
        try:
            devices = nvmlDeviceGetCount()
            for device_id in range(devices):
                gpu_handle = nvmlDeviceGetHandleByIndex(device_id)
                uuid = nvmlDeviceGetUUID(handle=gpu_handle).decode('utf-8')
                name = nvmlDeviceGetName(handle=gpu_handle).decode('utf-8')

                gpu_devices.append(
                    GPUDevice(
                        device_name=name,
                        device_id=device_id,
                        pci_bus_id=
                        '',  # FIXME: PCI bus ID isn't needed and will be removed when DCGM is removed
                        device_uuid=uuid))
        except NVMLError as error:
            raise TritonModelAnalyzerException(f"NVML error: {error}")

        return gpu_devices

    def _log_gpus_used(self, gpus):
        """
        Log the info for the GPUDevices in use
        """

        for gpu in gpus:
            logger.info(
                f"Using GPU {gpu.device_id()} {gpu.device_name()} with UUID {gpu.device_uuid()}"
            )
