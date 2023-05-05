# Copyright (c) 2022, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from typing import List, Optional, Generator, Dict

from .config_generator_interface import ConfigGeneratorInterface

from model_analyzer.config.generate.brute_run_config_generator import BruteRunConfigGenerator
from model_analyzer.config.generate.model_variant_name_manager import ModelVariantNameManager
from model_analyzer.config.generate.perf_analyzer_config_generator import PerfAnalyzerConfigGenerator
from model_analyzer.config.run.run_config import RunConfig
from model_analyzer.triton.client.client import TritonClient
from model_analyzer.device.gpu_device import GPUDevice
from model_analyzer.config.input.config_command_profile import ConfigCommandProfile
from model_analyzer.config.generate.model_profile_spec import ModelProfileSpec
from model_analyzer.result.result_manager import ResultManager
from model_analyzer.result.run_config_measurement import RunConfigMeasurement
from model_analyzer.result.concurrency_search import ConcurrencySearch

from model_analyzer.constants import LOGGER_NAME

from copy import deepcopy
from math import log2

import logging

logger = logging.getLogger(LOGGER_NAME)


class BrutePlusBinaryParameterSearchRunConfigGenerator(ConfigGeneratorInterface
                                                      ):
    """
    First run BruteRunConfigGenerator for a brute search, then for 
    automatic searches use ParameterSearch to perform a binary search
    """

    def __init__(self, config: ConfigCommandProfile, gpus: List[GPUDevice],
                 models: List[ModelProfileSpec], client: TritonClient,
                 result_manager: ResultManager,
                 model_variant_name_manager: ModelVariantNameManager):
        """
        Parameters
        ----------
        config: ConfigCommandProfile
            Profile configuration information
        gpus: List of GPUDevices
        models: List of ModelProfileSpec
            List of models to profile
        client: TritonClient
        result_manager: ResultManager
            The object that handles storing and sorting the results from the perf analyzer
        model_variant_name_manager: ModelVariantNameManager
            Maps model variants to config names
        """
        self._config = config
        self._gpus = gpus
        self._models = models
        self._client = client
        self._result_manager = result_manager
        self._model_variant_name_manager = model_variant_name_manager

    def set_last_results(
            self, measurements: List[Optional[RunConfigMeasurement]]) -> None:
        self._last_measurement = measurements[-1]
        self._rcg.set_last_results(measurements)

    def get_configs(self) -> Generator[RunConfig, None, None]:
        """
        Returns
        -------
        RunConfig
            The next RunConfig generated by this class
        """

        logger.info("")
        logger.info("Starting brute mode search")
        logger.info("")
        yield from self._execute_brute_search()
        logger.info("")
        logger.info("Done with brute mode search.")
        logger.info("")

        if self._is_automatic_search_mode():
            yield from self._binary_search_over_top_results()
        logger.info("")
        logger.info("Done gathering concurrency sweep measurements for reports")
        logger.info("")

    def _execute_brute_search(self) -> Generator[RunConfig, None, None]:
        self._rcg: ConfigGeneratorInterface = self._create_brute_run_config_generator(
        )

        yield from self._rcg.get_configs()

    def _create_brute_run_config_generator(self) -> BruteRunConfigGenerator:
        return BruteRunConfigGenerator(
            config=self._config,
            gpus=self._gpus,
            models=self._models,
            client=self._client,
            model_variant_name_manager=self._model_variant_name_manager)

    def _is_automatic_search_mode(self) -> bool:
        for model in self._models:
            if model.model_config_parameters():
                return False

        return True

    def _binary_search_over_top_results(
            self) -> Generator[RunConfig, None, None]:
        for model_name in self._result_manager.get_model_names():
            top_results = self._result_manager.top_n_results(
                model_name=model_name,
                n=self._config.num_configs_per_model,
                include_default=True)

            for result in top_results:
                run_config = deepcopy(result.run_config())
                concurrency_search = ConcurrencySearch(
                    self._config, skip_parameter_sweep=True)
                for concurrency in concurrency_search.search_concurrencies():
                    run_config = self._set_concurrency(run_config, concurrency)
                    yield run_config
                    concurrency_search.add_run_config_measurement(
                        self._last_measurement)

    def _set_concurrency(self, run_config: RunConfig,
                         concurrency: int) -> RunConfig:
        for model_run_config in run_config.model_run_configs():
            perf_config = model_run_config.perf_config()
            perf_config.update_config({'concurrency-range': concurrency})

        return run_config
