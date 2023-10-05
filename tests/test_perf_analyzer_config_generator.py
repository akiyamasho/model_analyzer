#!/usr/bin/env python3

# Copyright 2022-2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

import unittest
from unittest.mock import MagicMock, mock_open, patch

from model_analyzer.config.generate.generator_utils import GeneratorUtils as utils
from model_analyzer.config.generate.perf_analyzer_config_generator import (
    PerfAnalyzerConfigGenerator,
)
from model_analyzer.config.input.config_defaults import (
    DEFAULT_RUN_CONFIG_MAX_CONCURRENCY,
    DEFAULT_RUN_CONFIG_MAX_REQUEST_RATE,
    DEFAULT_RUN_CONFIG_MIN_REQUEST_RATE,
)
from tests.common.test_utils import (
    construct_perf_analyzer_config,
    construct_run_config_measurement,
    evaluate_mock_config,
)

from .common import test_result_collector as trc
from .mocks.mock_os import MockOSMethods


class TestPerfAnalyzerConfigGenerator(trc.TestResultCollector):
    def __init__(self, methodname):
        super().__init__(methodname)
        self._perf_throughput = 1

    @patch(
        "model_analyzer.config.input.config_command_profile.ConfigCommandProfile.is_llm_model",
        return_value=False,
    )
    def test_set_last_results(self, *args):
        """
        Test set_last_results() with multi model

        Confirm that set_last_results will properly choose the measurement with
        the highest total throughput
        """
        measurement1 = self.make_multi_model_measurement(
            ["modelA", "modelB"], [{"perf_throughput": 1}, {"perf_throughput": 2}]
        )

        measurement2 = self.make_multi_model_measurement(
            ["modelA", "modelB"], [{"perf_throughput": 7}, {"perf_throughput": 7}]
        )

        measurement3 = self.make_multi_model_measurement(
            ["modelA", "modelB"], [{"perf_throughput": 10}, {"perf_throughput": 2}]
        )

        args = [
            "model-analyzer",
            "profile",
            "--model-repository",
            "cli_repository",
            "-f",
            "path-to-config-file",
        ]

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        config = evaluate_mock_config(args, yaml_str, subcommand="profile")

        pacg = PerfAnalyzerConfigGenerator(
            config, MagicMock(), MagicMock(), MagicMock(), early_exit_enable=False
        )

        pacg.set_last_results([measurement1, measurement2, measurement3])
        self.assertEqual(pacg._last_results[0], measurement2)

    def test_default(self):
        """
        Test Default:
            - No CLI options specified

        Default (1) value will be used for batch size
        and log2(DEFAULT_RUN_CONFIG_MAX_CONCURRENCY)+1 configs
        will be generated by the auto-search
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        concurrencies = utils.generate_doubled_list(
            1, DEFAULT_RUN_CONFIG_MAX_CONCURRENCY
        )
        expected_configs = [
            construct_perf_analyzer_config(concurrency=c) for c in concurrencies
        ]

        self._run_and_test_perf_analyzer_config_generator(yaml_str, expected_configs)

    def test_search_disabled(self):
        """
        Test Search Disabled:
            - Run Config Search disabled

        Default (1) value will be used for batch size
        and concurrency will be set to 1
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        expected_configs = [construct_perf_analyzer_config()]

        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, "--run-config-search-disable"
        )

    def test_c_api(self):
        """
        Test C_API:
            - Launch mode is C_API

        Default (1) values will be used for batch size/concurrency
        and only one config will be generated
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        concurrencies = utils.generate_doubled_list(
            1, DEFAULT_RUN_CONFIG_MAX_CONCURRENCY
        )
        expected_configs = [
            construct_perf_analyzer_config(concurrency=c, launch_mode="c_api")
            for c in concurrencies
        ]

        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, "--triton-launch-mode=c_api"
        )

    def test_http(self):
        """
        Test HTTP:
            - Client protocol is HTTP

        Default (1) values will be used for batch size/concurrency
        and only one config will be generated
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        concurrencies = utils.generate_doubled_list(
            1, DEFAULT_RUN_CONFIG_MAX_CONCURRENCY
        )
        expected_configs = [
            construct_perf_analyzer_config(concurrency=c, client_protocol="http")
            for c in concurrencies
        ]

        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, "--client-protocol=http"
        )

    def test_batch_size_search_disabled(self):
        """
        Test Batch Size Search Disabled:
            - Schmoo batch sizes
            - Run Config Search disabled

        Batch sizes: 1,2,4
        Default (1) value will be used concurrency
        and 3 configs will be generated
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        batch_sizes = [1, 2, 4]
        expected_configs = [
            construct_perf_analyzer_config(batch_size=b) for b in batch_sizes
        ]

        pa_cli_args = ["-b 1,2,4", "--run-config-search-disable"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_batch_size_search_enabled(self):
        """
        Test Batch Size Search Enabled:
            - Schmoo batch sizes
            - Run Config Search enabled

        Batch sizes: 1,2,4
        Concurrency: log2(DEFAULT_RUN_CONFIG_MAX_CONCURRENCY)+1
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        batch_sizes = [1, 2, 4]
        concurrencies = utils.generate_doubled_list(
            1, DEFAULT_RUN_CONFIG_MAX_CONCURRENCY
        )
        expected_configs = [
            construct_perf_analyzer_config(batch_size=b, concurrency=c)
            for b in batch_sizes
            for c in concurrencies
        ]

        pa_cli_args = ["-b 1,2,4"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_concurrency(self):
        """
        Test Concurrency:
            - Schmoo concurrency
            - Test with auto-search enabled & disabled

        Concurrency: 1-4
        Default (1) value will be used for batch size
        and 4 configs will be generated
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        concurrencies = [1, 2, 3, 4]
        expected_configs = [
            construct_perf_analyzer_config(concurrency=c) for c in concurrencies
        ]

        pa_cli_args = ["-c 1,2,3,4"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

        pa_cli_args = ["-c 1,2,3,4", "--run-config-search-disable"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_batch_size_and_concurrency(self):
        """
        Test Batch Size and Concurrency:
            - Schmoo batch sizes and concurrency
            - Run Config Search enabled & disabled

        Batch sizes: 1,2,4
        Concurrency: 1-4


        12 configs will be generated
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        batch_sizes = [1, 2, 4]
        concurrencies = [1, 2, 3, 4]

        expected_configs = [
            construct_perf_analyzer_config(batch_size=b, concurrency=c)
            for b in batch_sizes
            for c in concurrencies
        ]

        pa_cli_args = ["-b 1,2,4", "-c 1,2,3,4"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

        pa_cli_args = ["-b 1,2,4", "-c 1,2,3,4", "--run-config-search-disable"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_max_concurrency(self):
        """
        Test Max Concurrency:
            - Change max concurrency to non-default value

        Max Concurrency: 16
        Default (1) value will be used for batch size
        and 5 configs (log2(16)+1) will be generated
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        concurrencies = utils.generate_doubled_list(1, 16)
        expected_configs = [
            construct_perf_analyzer_config(concurrency=c) for c in concurrencies
        ]

        pa_cli_args = ["--run-config-search-max-concurrency", "16"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_min_concurrency(self):
        """
        Test Min Concurrency:
            - Change min concurrency to non-default value

        Min Concurrency: 5
        2 configs [5, 10] will be generated
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        concurrencies = [5, 10]
        expected_configs = [
            construct_perf_analyzer_config(concurrency=c) for c in concurrencies
        ]

        pa_cli_args = [
            "--run-config-search-min-concurrency",
            "5",
            "--run-config-search-max-concurrency",
            "16",
        ]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_request_rate_list(self):
        """
        Test Request Rate:
            - Shmoo request-rate
            - Test with auto-search enabled & disabled

        Request Rate: 1,2,3,4
        Default (1) value will be used for batch size
        and 4 configs will be generated
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        request_rates = [1, 2, 3, 4]
        expected_configs = [
            construct_perf_analyzer_config(request_rate=request_rate)
            for request_rate in request_rates
        ]

        pa_cli_args = ["--request-rate", "1,2,3,4"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

        pa_cli_args = ["--request-rate", "1,2,3,4", "--run-config-search-disable"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

        # yapf: disable
        yaml_str = ("""
            profile_models:
              my-model:
                parameters:
                  request_rate: 1,2,3,4
            """)
        # yapf: enable

        pa_cli_args = []
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_request_rate_enable(self):
        """
        Test Request Rate:
            - Shmoo request rate
            - Test with auto-search enabled & disabled

        Request Rate: MIN-MAX
        Default (1) value will be used for batch size
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        request_rates = utils.generate_doubled_list(
            DEFAULT_RUN_CONFIG_MIN_REQUEST_RATE, DEFAULT_RUN_CONFIG_MAX_REQUEST_RATE
        )
        expected_configs = [
            construct_perf_analyzer_config(request_rate=request_rate)
            for request_rate in request_rates
        ]

        pa_cli_args = ["--request-rate-search-enable"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_max_request_rate(self):
        """
        Test Max Request Rate:
            - Change max request rate to non-default value

        Max Request Rate: DEFAULT_RUN_CONFIG_MAX_REQUEST_RATE / 2
        Default (1) value will be used for batch size
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        request_rates = utils.generate_doubled_list(
            DEFAULT_RUN_CONFIG_MIN_REQUEST_RATE,
            int(DEFAULT_RUN_CONFIG_MAX_REQUEST_RATE / 2),
        )
        expected_configs = [
            construct_perf_analyzer_config(request_rate=request_rate)
            for request_rate in request_rates
        ]

        pa_cli_args = [
            "--run-config-search-max-request-rate",
            f"{int(DEFAULT_RUN_CONFIG_MAX_REQUEST_RATE / 2)}",
        ]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_min_request_rate(self):
        """
        Test Min Request Rate:
            - Change max request rate to non-default value

        Min Request Rate: DEFAULT_RUN_CONFIG_MAX_REQUEST_RATE * 2
        Default (1) value will be used for batch size
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        request_rates = utils.generate_doubled_list(
            DEFAULT_RUN_CONFIG_MIN_REQUEST_RATE * 2,
            int(DEFAULT_RUN_CONFIG_MAX_REQUEST_RATE),
        )
        expected_configs = [
            construct_perf_analyzer_config(request_rate=request_rate)
            for request_rate in request_rates
        ]

        pa_cli_args = [
            "--run-config-search-min-request-rate",
            f"{int(DEFAULT_RUN_CONFIG_MIN_REQUEST_RATE * 2)}",
        ]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_perf_analyzer_flags(self):
        """
        Test Perf Analyzer Flags:
            - No CLI options specified
            - Percentile (PA flag) set in model's YAML

        Default (1) value will be used for batch size
        and log2(DEFAULT_RUN_CONFIG_MAX_CONCURRENCY)+1 configs
        will be generated by the auto-search
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model:
                    perf_analyzer_flags:
                        percentile: 96
            """)
        # yapf: enable

        concurrencies = utils.generate_doubled_list(
            1, DEFAULT_RUN_CONFIG_MAX_CONCURRENCY
        )
        expected_configs = [
            construct_perf_analyzer_config(
                concurrency=c, perf_analyzer_flags={"percentile": "96"}
            )
            for c in concurrencies
        ]

        self._run_and_test_perf_analyzer_config_generator(yaml_str, expected_configs)

    def test_llm_search_max_token_count(self):
        """
        Test LLM Search:
            - max token count 1->256

        Concurrency and prompt length max set to 1
        """

        # yapf: disable
        yaml_str = ("""
            perf_analyzer_flags:
                input-data: input_data.json
            profile_models:
                - my-model
            """)
        # yapf: enable

        max_token_counts = utils.generate_doubled_list(1, 256)
        expected_configs = [
            construct_perf_analyzer_config(max_token_count=mtc, llm_search_mode=True)
            for mtc in max_token_counts
        ]

        pa_cli_args = [
            "--llm-search-enable",
            "--run-config-search-max-concurrency",
            "1",
            "--run-config-search-max-prompt-length",
            "1",
        ]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_llm_search_prompt_length(self):
        """
        Test LLM Search:
            - Prompt length 1->1024

        Concurrency and max token count set to 1
        """

        # yapf: disable
        yaml_str = ("""
            perf_analyzer_flags:
                input-data: input_data.json
            profile_models:
                - my-model
            """)
        # yapf: enable

        prompt_lengths = utils.generate_doubled_list(1, 1024)
        expected_configs = [
            construct_perf_analyzer_config(llm_search_mode=True)
            for pl in prompt_lengths
        ]

        pa_cli_args = [
            "--llm-search-enable",
            "--run-config-search-max-concurrency",
            "1",
            "--run-config-search-max-token-count",
            "1",
        ]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args
        )

    def test_perf_analyzer_config_ssl_options(self):
        """
        Test Perf Analyzer SSL options:
            - No CLI options specified
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model:
                    perf_analyzer_flags:
                        ssl-grpc-root-certifications-file: a
                        ssl-grpc-private-key-file: b
                        ssl-grpc-certificate-chain-file: c
                        ssl-https-verify-peer: 1
                        ssl-https-verify-host: 2
                        ssl-https-ca-certificates-file: d
                        ssl-https-client-certificate-type: e
                        ssl-https-client-certificate-file: f
                        ssl-https-private-key-type: g
                        ssl-https-private-key-file: h
            """)
        # yapf: enable

        concurrencies = utils.generate_doubled_list(
            1, DEFAULT_RUN_CONFIG_MAX_CONCURRENCY
        )
        expected_configs = [
            construct_perf_analyzer_config(
                concurrency=c,
                perf_analyzer_flags={
                    "ssl-grpc-root-certifications-file": "a",
                    "ssl-grpc-private-key-file": "b",
                    "ssl-grpc-certificate-chain-file": "c",
                    "ssl-https-verify-peer": "1",
                    "ssl-https-verify-host": "2",
                    "ssl-https-ca-certificates-file": "d",
                    "ssl-https-client-certificate-type": "e",
                    "ssl-https-client-certificate-file": "f",
                    "ssl-https-private-key-type": "g",
                    "ssl-https-private-key-file": "h",
                },
            )
            for c in concurrencies
        ]

        self._run_and_test_perf_analyzer_config_generator(yaml_str, expected_configs)

    def test_early_exit_on_no_plateau(self):
        """
        Test if early_exit is true but the throughput is still increasing, we
        do not early exit
        """
        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        concurrencies = utils.generate_doubled_list(1, 64)
        expected_configs = [
            construct_perf_analyzer_config(concurrency=c) for c in concurrencies
        ]

        pa_cli_args = ["--run-config-search-max-concurrency", "64"]
        self._run_and_test_perf_analyzer_config_generator(
            yaml_str, expected_configs, pa_cli_args, early_exit=True
        )

    def test_early_exit_on_yes_plateau(self):
        """
        Test if early_exit is true and the throughput plateaus, we do early exit
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        concurrencies = utils.generate_doubled_list(1, 32)
        expected_configs = [
            construct_perf_analyzer_config(concurrency=c) for c in concurrencies
        ]

        pa_cli_args = ["--run-config-search-max-concurrency", "64"]
        with patch.object(
            TestPerfAnalyzerConfigGenerator, "_get_next_perf_throughput_value"
        ) as mock_method:
            mock_method.side_effect = [1, 2, 4, 4, 4, 4, 4]
            self._run_and_test_perf_analyzer_config_generator(
                yaml_str, expected_configs, pa_cli_args, early_exit=True
            )

    def test_early_exit_off_yes_plateau(self):
        """
        Test if early_exit is off and the throughput plateaus, we do not early exit
        """

        # yapf: disable
        yaml_str = ("""
            profile_models:
                - my-model
            """)
        # yapf: enable

        concurrencies = utils.generate_doubled_list(1, 64)
        expected_configs = [
            construct_perf_analyzer_config(concurrency=c) for c in concurrencies
        ]

        pa_cli_args = ["--run-config-search-max-concurrency", "64"]
        with patch.object(
            TestPerfAnalyzerConfigGenerator, "_get_next_perf_throughput_value"
        ) as mock_method:
            mock_method.side_effect = [1, 2, 4, 4, 4, 4, 4]
            self._run_and_test_perf_analyzer_config_generator(
                yaml_str, expected_configs, pa_cli_args, early_exit=False
            )

    def test_throughput_gain_based_on_max(self):
        # Expect false because no increases
        throughput_values = [50, 40, 30, 20]
        expected_result = False
        self._test_throughput_gain_valid_helper(throughput_values, expected_result)

        # Expect false because no increases in the last 4
        throughput_values = [10, 20, 30, 40, 50, 40, 30, 20]
        expected_result = False
        self._test_throughput_gain_valid_helper(throughput_values, expected_result)

        # Expect false because gain is only 5%
        throughput_values = [50, 50, 50, 52.5]
        expected_result = False
        self._test_throughput_gain_valid_helper(throughput_values, expected_result)

        # Expect false because gain is only 5%
        throughput_values = [50, 35, 45, 51.5]
        expected_result = False
        self._test_throughput_gain_valid_helper(throughput_values, expected_result)

        # Expect true because gain is more than 5%
        throughput_values = [50, 50, 50, 52.51]
        expected_result = True
        self._test_throughput_gain_valid_helper(throughput_values, expected_result)

        # Expect true because not enough data
        throughput_values = [50, 10]
        expected_result = True
        self._test_throughput_gain_valid_helper(throughput_values, expected_result)

        # Expect true because of increases
        throughput_values = [50, 100, 200, 400]
        expected_result = True
        self._test_throughput_gain_valid_helper(throughput_values, expected_result)

        # Expect false because no new max
        throughput_values = [50, 10, 50, 10]
        expected_result = False
        self._test_throughput_gain_valid_helper(throughput_values, expected_result)

    def _test_throughput_gain_valid_helper(self, throughput_values, expected_result):
        throughputs = [
            construct_run_config_measurement(
                model_name=MagicMock(),
                model_config_names=["test_model_config_name"],
                model_specific_pa_params=MagicMock(),
                gpu_metric_values=MagicMock(),
                non_gpu_metric_values=[{"perf_throughput": throughput_value}],
            )
            for throughput_value in throughput_values
        ]

        result = PerfAnalyzerConfigGenerator.throughput_gain_valid_helper(
            throughputs=throughputs, min_tries=4, min_gain=0.05
        )

        self.assertEqual(result, expected_result)

    def _get_next_measurement(self):
        throughput_value = self._get_next_perf_throughput_value()
        if throughput_value is None:
            return None
        else:
            return construct_run_config_measurement(
                model_name=MagicMock(),
                model_config_names=["test_model_config_name"],
                model_specific_pa_params=MagicMock(),
                gpu_metric_values=MagicMock(),
                non_gpu_metric_values=[{"perf_throughput": throughput_value}],
            )

    def _get_next_perf_throughput_value(self):
        self._perf_throughput *= 2
        return self._perf_throughput

    def _run_and_test_perf_analyzer_config_generator(
        self, yaml_str, expected_configs, pa_cli_args=None, early_exit=False
    ):
        args = [
            "model-analyzer",
            "profile",
            "--model-repository",
            "cli_repository",
            "-f",
            "path-to-config-file",
        ]

        if type(pa_cli_args) == list:
            args = args + pa_cli_args
        elif type(pa_cli_args) == str:
            args.append(pa_cli_args)

        config = evaluate_mock_config(args, yaml_str, subcommand="profile")

        with patch(
            "model_analyzer.config.generate.perf_analyzer_config_generator.open",
            mock_open(read_data=self._input_data),
        ):
            pacg = PerfAnalyzerConfigGenerator(
                config,
                config.profile_models[0].model_name(),
                config.profile_models[0].perf_analyzer_flags(),
                config.profile_models[0].parameters(),
                early_exit,
            )

        perf_analyzer_configs = []
        for perf_config in pacg.get_configs():
            perf_analyzer_configs.append(perf_config)
            pacg.set_last_results([self._get_next_measurement()])

        self.assertEqual(len(expected_configs), len(perf_analyzer_configs))
        for i in range(len(expected_configs)):
            self.assertEqual(
                expected_configs[i]._options["-m"],
                perf_analyzer_configs[i]._options["-m"],
            )
            self.assertEqual(
                expected_configs[i]._options["-b"],
                perf_analyzer_configs[i]._options["-b"],
            )
            self.assertEqual(
                expected_configs[i]._options["-i"],
                perf_analyzer_configs[i]._options["-i"],
            )
            self.assertEqual(
                expected_configs[i]._options["-u"],
                perf_analyzer_configs[i]._options["-u"],
            )

            self.assertEqual(
                expected_configs[i]._args["concurrency-range"],
                perf_analyzer_configs[i]._args["concurrency-range"],
            )
            self.assertEqual(
                expected_configs[i]._args["measurement-mode"],
                perf_analyzer_configs[i]._args["measurement-mode"],
            )
            self.assertEqual(
                expected_configs[i]._args["service-kind"],
                perf_analyzer_configs[i]._args["service-kind"],
            )
            self.assertEqual(
                expected_configs[i]._args["triton-server-directory"],
                perf_analyzer_configs[i]._args["triton-server-directory"],
            )
            self.assertEqual(
                expected_configs[i]._args["model-repository"],
                perf_analyzer_configs[i]._args["model-repository"],
            )

            # Future-proofing (in case a new field gets added)
            self.assertEqual(
                expected_configs[i]._options, perf_analyzer_configs[i]._options
            )
            self.assertEqual(expected_configs[i]._args, perf_analyzer_configs[i]._args)
            self.assertEqual(
                expected_configs[i]._additive_args,
                perf_analyzer_configs[i]._additive_args,
            )

    def setUp(self):
        # Mock path validation
        self.mock_os = MockOSMethods(
            mock_paths=["model_analyzer.config.input.config_utils"]
        )
        self.mock_os.start()

        self._input_data = """{
            "data": [{"PROMPT": ["Hello, my name is"], "STREAM": [true]}]
        }"""

    def tearDown(self):
        self.mock_os.stop()
        patch.stopall()

    def make_multi_model_measurement(self, model_names, non_gpu_metric_values):
        return construct_run_config_measurement(
            model_name=MagicMock(),
            model_config_names=model_names,
            model_specific_pa_params=MagicMock(),
            gpu_metric_values=MagicMock(),
            non_gpu_metric_values=non_gpu_metric_values,
        )


if __name__ == "__main__":
    unittest.main()
