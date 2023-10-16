# Copyright 2021-2023, NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

from model_analyzer.constants import CONFIG_PARSER_FAILURE, CONFIG_PARSER_SUCCESS

from .config_status import ConfigStatus
from .config_value import ConfigValue


class ConfigRangeNumeric(ConfigValue):
    """
    A range of numeric values.
    """

    def __init__(
        self,
        type_,
        preprocess=None,
        required=False,
        validator=None,
        output_mapper=None,
        name=None,
    ):
        """
        Create a new range of numeric values.

        Parameters
        ----------
        type_ : type
            The type of elements in the list
        preprocess : callable
            Function be called before setting new values.
        required : bool
            Whether a given config is required or not.
        validator : callable or None
            A validator for the final value of the field.
        output_mapper: callable or None
            This callable unifies the output value of this field.
        name : str
            Fully qualified name for this field.
        """

        # default validator
        if validator is None:

            def validator(x):
                if type(x) is list:
                    return ConfigStatus(CONFIG_PARSER_SUCCESS)

                return ConfigStatus(
                    CONFIG_PARSER_FAILURE,
                    f'The value for field "{self.name()}" should be a list'
                    " and the length must be larger than zero.",
                )

        super().__init__(preprocess, required, validator, output_mapper, name)
        self._type = type_
        self._cli_type = str
        self._value = []

    def set_value(self, value):
        """
        Set the value for this field.

        Parameters
        ----------
        value : object
            The value for this field. It can be comma delimited list, or an
            array, or a range
        """

        type_ = self._type
        new_value = []

        try:
            if self._is_string(value):
                if not ":" in value:
                    return ConfigStatus(
                        CONFIG_PARSER_FAILURE,
                        f'When a string is used for field "{self.name()}",'
                        ' it must be in the format "start:stop:step".',
                        config_object=self,
                    )

                self._value = []
                value = value.split(":")
                if len(value) == 2:
                    value = {"start": value[0], "stop": value[1], "step": 1}
                elif len(value) == 3:
                    value = {"start": value[0], "stop": value[1], "step": value[2]}
                else:
                    return ConfigStatus(
                        CONFIG_PARSER_FAILURE,
                        f'When a string is used for field "{self.name()}",'
                        ' it must be in the format "start:stop:step".',
                        config_object=self,
                    )

            if self._is_dict(value):
                two_key_condition = (
                    len(value) == 2 and "start" in value and "stop" in value
                )
                three_key_condition = (
                    len(value) == 3
                    and "start" in value
                    and "stop" in value
                    and "step" in value
                )
                if two_key_condition or three_key_condition:
                    start = int(value["start"])
                    stop = int(value["stop"])
                    step = 1 if not "step" in value else int(value["step"])

                    if start > stop:
                        return ConfigStatus(
                            CONFIG_PARSER_FAILURE,
                            f'When a dictionary is used for field "{self.name()}",'
                            ' "start" should be less than "stop".'
                            f" Current value is {value}.",
                            config_object=self,
                        )

                    new_value = [f"{start}:{stop}:{step}"]
                else:
                    return ConfigStatus(
                        CONFIG_PARSER_FAILURE,
                        f'If a dictionary is used for field "{self.name()}", it'
                        ' should only contain "start" and "stop" key with an'
                        f' optional "step" key. Currently, contains {list(value)}.',
                        config_object=self,
                    )
            elif self._is_list(value):
                new_value = value
            else:
                new_value = [type_(value)]
        except ValueError as e:
            message = f'Failed to set the value for field "{self.name()}". Error: {e}.'
            return ConfigStatus(CONFIG_PARSER_FAILURE, message, self)

        return super().set_value(new_value)
