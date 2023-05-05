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

from model_analyzer.config.generate.search_config import SearchConfig
from model_analyzer.config.generate.quick_run_config_generator import QuickRunConfigGenerator
from model_analyzer.config.generate.model_variant_name_manager import ModelVariantNameManager
from model_analyzer.config.generate.perf_analyzer_config_generator import PerfAnalyzerConfigGenerator
from model_analyzer.config.run.run_config import RunConfig
from model_analyzer.triton.client.client import TritonClient
from model_analyzer.device.gpu_device import GPUDevice
from model_analyzer.config.input.config_command_profile import ConfigCommandProfile
from model_analyzer.config.generate.model_profile_spec import ModelProfileSpec
from model_analyzer.result.result_manager import ResultManager
from model_analyzer.result.run_config_measurement import RunConfigMeasurement
from model_analyzer.result.parameter_search import ParameterSearch

from model_analyzer.constants import LOGGER_NAME

from copy import deepcopy
from math import log2

import logging

logger = logging.getLogger(LOGGER_NAME)


class QuickPlusConcurrencySweepRunConfigGenerator(ConfigGeneratorInterface):
    """
    First run QuickRunConfigGenerator for a hill climbing search, then use 
    ParameterSearch for a concurrency sweep + binary search of the default 
    and Top N results
    """

    def __init__(self, search_config: SearchConfig,
                 config: ConfigCommandProfile, gpus: List[GPUDevice],
                 models: List[ModelProfileSpec],
                 composing_models: List[ModelProfileSpec], client: TritonClient,
                 result_manager: ResultManager,
                 model_variant_name_manager: ModelVariantNameManager):
        """
        Parameters
        ----------
        search_config: SearchConfig
            Defines parameters and dimensions for the search
        config: ConfigCommandProfile
            Profile configuration information
        gpus: List of GPUDevices
        models: List of ModelProfileSpec
            List of models to profile
        composing_models: List of ModelProfileSpec
            List of composing models that exist inside of the supplied models
        client: TritonClient
        result_manager: ResultManager
            The object that handles storing and sorting the results from the perf analyzer
        model_variant_name_manager: ModelVariantNameManager
            Maps model variants to config names
        """
        self._search_config = search_config
        self._config = config
        self._gpus = gpus
        self._models = models
        self._composing_models = composing_models
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
        logger.info("Starting quick mode search to find optimal configs")
        logger.info("")
        yield from self._execute_quick_search()
        logger.info("")
        logger.info(
            "Done with quick mode search. Gathering concurrency sweep measurements for reports"
        )
        logger.info("")
        yield from self._sweep_concurrency_over_top_results()
        logger.info("")
        logger.info("Done gathering concurrency sweep measurements for reports")
        logger.info("")

    def _execute_quick_search(self) -> Generator[RunConfig, None, None]:
        self._rcg: ConfigGeneratorInterface = self._create_quick_run_config_generator(
        )

        yield from self._rcg.get_configs()

    def _create_quick_run_config_generator(self) -> QuickRunConfigGenerator:
        return QuickRunConfigGenerator(
            search_config=self._search_config,
            config=self._config,
            gpus=self._gpus,
            models=self._models,
            composing_models=self._composing_models,
            client=self._client,
            model_variant_name_manager=self._model_variant_name_manager)

    def _sweep_concurrency_over_top_results(
            self) -> Generator[RunConfig, None, None]:
        for model_name in self._result_manager.get_model_names():
            top_results = self._result_manager.top_n_results(
                model_name=model_name,
                n=self._config.num_configs_per_model,
                include_default=True)

            for result in top_results:
                run_config = deepcopy(result.run_config())
                parameter_search = ParameterSearch(self._config)
                for concurrency in parameter_search.search_parameters():
                    run_config = self._set_concurrency(run_config, concurrency)
                    yield run_config
                    parameter_search.add_run_config_measurement(
                        self._last_measurement)

    def _set_concurrency(self, run_config: RunConfig,
                         concurrency: int) -> RunConfig:
        for model_run_config in run_config.model_run_configs():
            perf_config = model_run_config.perf_config()
            perf_config.update_config({'concurrency-range': concurrency})

        return run_config
