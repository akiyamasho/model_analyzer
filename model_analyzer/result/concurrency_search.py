# Copyright (c) 2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from typing import List, Optional, Generator

from model_analyzer.model_analyzer_exceptions import TritonModelAnalyzerException
from model_analyzer.config.input.config_command_profile import ConfigCommandProfile
from model_analyzer.result.run_config_measurement import RunConfigMeasurement

from math import log2

import logging
from model_analyzer.constants import LOGGER_NAME, THROUGHPUT_MINIMUM_GAIN, THROUGHPUT_MINIMUM_CONSECUTIVE_CONCURRENCY_TRIES

logger = logging.getLogger(LOGGER_NAME)


class ConcurrencySearch():
    """
    Generates the next concurrency value to use when searching through
    RunConfigMeasurements for the best value (according to the users objective)
      - Will sweep from by powers of two from min to max concurrency
      - If the user specifies a constraint, the algorithm will perform a binary search 
        around the boundary if the constraint is violated
        
    Invariant: It is necessary for the user to add new measurements as they are taken
    """

    def __init__(self, config: ConfigCommandProfile) -> None:
        """
        Parameters
        ----------
        config: ConfigCommandProfile
            Profile configuration information
        """
        self._min_concurrency_index = int(
            log2(config.run_config_search_min_concurrency))
        self._max_concurrency_index = int(
            log2(config.run_config_search_max_concurrency))
        self._max_binary_search_steps = config.run_config_search_max_binary_search_steps

        self._run_config_measurements: List[Optional[RunConfigMeasurement]] = []
        self._concurrencies: List[int] = []
        self._last_failing_concurrency = 0
        self._last_passing_concurrency = 0

    def add_run_config_measurement(
            self,
            run_config_measurement: Optional[RunConfigMeasurement]) -> None:
        """
        Adds a new RunConfigMeasurement
        Invariant: Assumed that RCMs are added in the same order they are measured
        """
        self._run_config_measurements.append(run_config_measurement)

    def search_concurrencies(self) -> Generator[int, None, None]:
        """
        First performs a concurrency sweep, and then, if necessary, perform
        a binary concurrency search around the point where the constraint
        violated
        """
        yield from self._perform_concurrency_sweep()

        if self._was_constraint_violated():
            yield from self._perform_binary_concurrency_search()

    def _perform_concurrency_sweep(self) -> Generator[int, None, None]:
        for concurrency in (2**i for i in range(
                self._min_concurrency_index, self._max_concurrency_index + 1)):
            if self._should_continue_concurrency_sweep():
                self._concurrencies.append(concurrency)
                yield concurrency
            else:
                logger.info(
                    "Terminating concurrency sweep - throughput is decreasing")
                return

    def _should_continue_concurrency_sweep(self) -> bool:
        self._check_measurement_count()

        if not self._are_minimum_tries_reached():
            return True
        else:
            return not self._has_objective_gain_saturated()

    def _check_measurement_count(self) -> None:
        if len(self._run_config_measurements) != len(self._concurrencies):
            raise TritonModelAnalyzerException(f"Internal Measurement count: {self._concurrencies}, doesn't match number " \
                f"of measurements added: {len(self._run_config_measurements)}.")

    def _are_minimum_tries_reached(self) -> bool:
        if len(self._run_config_measurements
              ) < THROUGHPUT_MINIMUM_CONSECUTIVE_CONCURRENCY_TRIES:
            return False
        else:
            return True

    def _has_objective_gain_saturated(self) -> bool:
        gain = self._calculate_gain()
        return gain < THROUGHPUT_MINIMUM_GAIN

    def _calculate_gain(self) -> float:
        first_rcm = self._run_config_measurements[
            -THROUGHPUT_MINIMUM_CONSECUTIVE_CONCURRENCY_TRIES]

        best_rcm = self._get_best_rcm()

        # These cover the cases where we don't get a result from PA
        if not first_rcm and not best_rcm:
            return 0
        if not first_rcm:
            return 1
        elif not best_rcm:
            return -1
        else:
            gain = first_rcm.compare_measurements(best_rcm)

        return gain

    def _get_best_rcm(self) -> Optional[RunConfigMeasurement]:
        # Need to remove entries (None) with no result from PA before sorting
        pruned_rcms = [
            rcm for rcm in self._run_config_measurements[
                -THROUGHPUT_MINIMUM_CONSECUTIVE_CONCURRENCY_TRIES:] if rcm
        ]
        best_rcm = max(pruned_rcms) if pruned_rcms else None

        return best_rcm

    def _was_constraint_violated(self) -> bool:
        for i in range(len(self._run_config_measurements) - 1, 1, -1):
            if self._at_constraint_failure_boundary(i):
                self._last_failing_concurrency = self._concurrencies[i]
                self._last_passing_concurrency = self._concurrencies[i - 1]
                return True

        if self._run_config_measurements[
                0] and not self._run_config_measurements[
                    0].is_passing_constraints():
            self._last_failing_concurrency = self._concurrencies[i]
            self._last_passing_concurrency = 0
            return True
        else:
            return False

    def _at_constraint_failure_boundary(self, index: int) -> bool:
        if not self._run_config_measurements[
                index] or not self._run_config_measurements[index - 1]:
            return False

        at_failure_boundary = not self._run_config_measurements[  # type: ignore
            index].is_passing_constraints() and self._run_config_measurements[
                index -  # type: ignore
                1].is_passing_constraints()

        return at_failure_boundary

    def _perform_binary_concurrency_search(self) -> Generator[int, None, None]:
        # This is needed because we are going to restart the search from the
        # concurrency that failed - so we expect this to be at the end of the list
        self._concurrencies.append(self._last_failing_concurrency)

        for i in range(0, self._max_binary_search_steps):
            concurrency = self._determine_next_binary_concurrency()

            if concurrency != self._concurrencies[-1]:
                self._concurrencies.append(concurrency)
                yield concurrency

    def _determine_next_binary_concurrency(self) -> int:
        if not self._run_config_measurements[-1]:
            return 0

        if self._run_config_measurements[-1].is_passing_constraints():
            self._last_passing_concurrency = self._concurrencies[-1]
            concurrency = int(
                (self._last_failing_concurrency + self._concurrencies[-1]) / 2)
        else:
            self._last_failing_concurrency = self._concurrencies[-1]
            concurrency = int(
                (self._last_passing_concurrency + self._concurrencies[-1]) / 2)

        return concurrency
